from __future__ import annotations

from typing import Any
from collections import Counter

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord, StageResult
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.base import BaseStageProcessor
from medpar_qa.stages.common import ld3137_grouping_result, ld3137_sort_order_result

from .context import FinalActionGroupContext
from .grouping import build_group_key, group_key_to_dict, group_records
from .ordering import order_newest_first
from .reconciler import reconcile_actual_output, validate_group_decisions
from .router import FinalActionRuleRouter
from .schema import validate_source_record
from .settings import FinalActionSettings


class FinalActionProcessor(BaseStageProcessor):
    stage = Stage.FINAL_ACTION

    def __init__(
        self,
        resolver: FieldResolver,
        settings: FinalActionSettings | None = None,
    ) -> None:
        self.resolver = resolver
        self.settings = settings or FinalActionSettings()
        self.router = FinalActionRuleRouter(self.settings)

    @staticmethod
    def derive_record_type(transaction_code: Any) -> str:
        from .grouping import derive_record_type

        return derive_record_type(transaction_code)

    def group_key(self, record: SourceRecord) -> tuple[Any, ...]:
        return build_group_key(record, self.resolver)

    def order_group(self, group: list[SourceRecord]) -> list[SourceRecord]:
        return list(order_newest_first(group, self.resolver).ordered_records)

    def _qc(self, record: SourceRecord) -> int:
        return int(self.resolver.get(record.data, "query_code"))

    def _icn(self, record: SourceRecord) -> str:
        return str(self.resolver.get(record.data, "icn")).strip()

    def _action_code(self, record: SourceRecord) -> str | None:
        value = self.resolver.get(record.data, "action_code")
        return None if value is None else str(value).strip()

    def _transaction_code(self, record: SourceRecord) -> str | None:
        value = self.resolver.get(record.data, "transaction_code")
        return None if value is None else str(value).strip()

    def _context(
        self,
        ordered: tuple[SourceRecord, ...],
        group_key: dict[str, Any],
    ) -> FinalActionGroupContext:
        return FinalActionGroupContext(
            records=ordered,
            group_key=group_key,
            query_codes=tuple(self._qc(record) for record in ordered),
            icns=tuple(self._icn(record) for record in ordered),
            action_codes=tuple(self._action_code(record) for record in ordered),
            transaction_codes=tuple(self._transaction_code(record) for record in ordered),
        )

    def validate_group(self, group: list[SourceRecord]) -> StageResult:
        result = StageResult(stage=self.stage)
        if not group:
            result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FA-PRE-EMPTY-GROUP",
                    status=ValidationStatus.FAIL,
                    message="Final Action group is empty",
                )
            )
            return result

        # Direct unit calls to validate_group still receive full schema validation.
        record_errors = [
            error
            for record in group
            for error in validate_source_record(record, self.resolver, self.settings)
        ]
        if record_errors:
            for error in record_errors:
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="FA-PRE-SCHEMA",
                        status=ValidationStatus.FAIL,
                        message=error.message,
                        actual=error.actual,
                        field_name=error.field_name,
                        record_ids=[error.record.record_id],
                        source_files=[error.record.source.file_path],
                    )
                )
            return result

        # Legacy table limits are enforced explicitly; oversized groups are
        # quarantined rather than truncated and silently processed.
        continuation_count = sum(
            str(self.resolver.get(r.data, "record_table_type", "")).strip().lower()
            in {"continuation", "cont", "c"} for r in group
        )
        hold_count = sum(
            str(self.resolver.get(r.data, "record_table_type", "")).strip().lower()
            in {"hold", "h"} for r in group
        )
        for name, actual, limit in (
            ("continuation", continuation_count, self.settings.max_continuation_records),
            ("hold", hold_count, self.settings.max_hold_records),
        ):
            if actual > limit:
                result.rule_results.append(RuleResult(
                    stage=self.stage, rule_id="FA-PRE-TABLE-LIMIT",
                    status=ValidationStatus.FAIL,
                    message=f"{name} table limit exceeded: {actual} > {limit}",
                    expected={"maximum": limit}, actual={"count": actual},
                    record_ids=[r.record_id for r in group],
                    source_files=sorted({r.source.file_path for r in group}),
                ))
        if any(x.rule_id == "FA-PRE-TABLE-LIMIT" for x in result.rule_results):
            return result

        if self.settings.bypass_direction not in (None, "covered_gt_los", "los_gt_covered"):
            raise ValueError("bypass_direction must be None, covered_gt_los, or los_gt_covered")
        if self.settings.bypass_direction is not None:
            from medpar_qa.normalization.dates import parse_date
            for record in group:
                raw_days = self.resolver.get(record.data, "covered_days")
                if raw_days is None:
                    # Legacy and sparse QA fixtures may omit this optional field.
                    # No bypass can be inferred without covered days.
                    continue
                try:
                    covered = int(raw_days)
                    los = (parse_date(self.resolver.get(record.data, "stay_thru_date")) -
                           parse_date(self.resolver.get(record.data, "stay_from_date"))).days + 1
                except (TypeError, ValueError):
                    result.rule_results.append(RuleResult(
                        stage=self.stage, rule_id="FA-BYPASS-INVALID-DAYS",
                        status=ValidationStatus.BLOCKED,
                        message="Cannot calculate bypass eligibility",
                        record_ids=[record.record_id], source_files=[record.source.file_path],
                    ))
                    continue
                should_bypass = (covered > los if self.settings.bypass_direction == "covered_gt_los"
                                 else los > covered)
                if should_bypass:
                    result.rule_results.append(RuleResult(
                        stage=self.stage, rule_id="FA-BYPASS-EXCEPTION",
                        status=ValidationStatus.BLOCKED,
                        message="Claim quarantined for covered-days / LOS mismatch (warning 04 = 2)",
                        actual={"covered_days": covered, "los": los,
                                "direction": self.settings.bypass_direction, "warning_04": "2"},
                        record_ids=[record.record_id], source_files=[record.source.file_path],
                    ))
            if any(x.status == ValidationStatus.BLOCKED for x in result.rule_results):
                return result

        key = build_group_key(group[0], self.resolver)
        group_key = group_key_to_dict(key)
        ordering = order_newest_first(group, self.resolver)
        if self.settings.block_ambiguous_ordering and ordering.is_ambiguous:
            result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FA-PRE-ORDERING",
                    status=ValidationStatus.BLOCKED,
                    message=(
                        "Newest record cannot be determined because multiple records "
                        "have identical processing date, accrete date, and source sequence"
                    ),
                    expected="Unique business ordering key inside each claim group",
                    actual={"ambiguous_record_ids": list(ordering.ambiguous_record_ids)},
                    record_ids=[record.record_id for record in group],
                    source_files=sorted({record.source.file_path for record in group}),
                    group_key=group_key,
                )
            )
            return result

        context = self._context(ordering.ordered_records, group_key)
        # A Rule 2 sequence must not fall through to Rule 10B when the
        # accretion-date requirement is absent or contradicted.  The V3
        # requires QC5 to have the greatest processing AND accretion date.
        if context.count == 3 and context.query_codes in ((5, 0, 3), (5, 0, 1)):
            from medpar_qa.normalization.dates import parse_date
            dates = [parse_date(self.resolver.get(record.data, "accrete_date"), allow_none=True)
                     for record in context.records]
            if any(value is None for value in dates) or dates[0] != max(dates):
                result.rule_results.append(RuleResult(
                    stage=self.stage,
                    rule_id="FA-RULE-02-PRECONDITION",
                    status=ValidationStatus.BLOCKED,
                    message="Rule 2 candidate cannot be approved: QC5 does not have a verified latest accretion date",
                    expected="QC5 latest processing and accretion dates",
                    actual={"accretion_dates": [x.isoformat() if x else None for x in dates]},
                    record_ids=[record.record_id for record in context.records],
                    source_files=sorted({record.source.file_path for record in context.records}),
                    group_key=group_key,
                ))
                return result
        selected_rule = self.router.select(context)
        evaluation = selected_rule.evaluate(context)
        result.rule_results.append(evaluation.rule_result)
        result.decisions.extend(evaluation.decisions)

        if evaluation.rule_result.status == ValidationStatus.PASS:
            result.rule_results.append(
                validate_group_decisions(
                    context.records,
                    evaluation.decisions,
                    group_key,
                )
            )
        return result

    def validate(self, records: list[SourceRecord]) -> StageResult:
        overall = StageResult(stage=self.stage)
        overall.rule_results.append(
            ld3137_sort_order_result(
                stage=self.stage,
                rule_id="FA-SORT-ORDER-LD3137",
                sort_fields=self.settings.sort_fields,
            )
        )
        source_records = [
            record for record in records if record.source.role == FileRole.SOURCE
        ]
        actual_records = [
            record for record in records if record.source.role == FileRole.ACTUAL_OUTPUT
        ]

        overall.rule_results.append(
            ld3137_grouping_result(
                stage=self.stage,
                rule_id="FA-GROUP-CONTIGUITY-LD3137",
                records=source_records,
                resolver=self.resolver,
                identity_fields=("hicn", "provider_id", "stay_from_date", "stay_thru_date"),
            )
        )

        if not source_records:
            overall.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FA-PRE-SOURCE-FILES",
                    status=ValidationStatus.FAIL,
                    message="No Final Action source records were supplied",
                )
            )
            return overall

        # A single input file must not mix service years (V3 p20).
        # Service year is derived from the stay-through date, not process date.
        if self.settings.enforce_single_service_year:
            per_file_years: dict[str, set[int]] = {}
            from medpar_qa.normalization.dates import parse_date
            for record in source_records:
                try:
                    year = parse_date(self.resolver.get(record.data, "stay_thru_date")).year
                except (TypeError, ValueError):
                    continue  # Schema reports malformed dates below.
                per_file_years.setdefault(record.source.file_path, set()).add(year)
            for path, years in per_file_years.items():
                if len(years) > 1:
                    overall.rule_results.append(RuleResult(
                        stage=self.stage, rule_id="FA-PRE-SERVICE-YEARS",
                        status=ValidationStatus.FAIL,
                        message="Multiple service years in a Final Action source file",
                        expected="One service year per source file",
                        actual={"years": sorted(years)}, source_files=[path],
                        record_ids=[r.record_id for r in source_records if r.source.file_path == path],
                    ))
            if any(x.rule_id == "FA-PRE-SERVICE-YEARS" for x in overall.rule_results):
                return overall

        valid_source_records: list[SourceRecord] = []
        for record in source_records:
            errors = validate_source_record(record, self.resolver, self.settings)
            if errors:
                for error in errors:
                    overall.rule_results.append(
                        RuleResult(
                            stage=self.stage,
                            rule_id="FA-PRE-SCHEMA",
                            status=ValidationStatus.FAIL,
                            message=error.message,
                            actual=error.actual,
                            field_name=error.field_name,
                            record_ids=[record.record_id],
                            source_files=[record.source.file_path],
                        )
                    )
            else:
                valid_source_records.append(record)

        grouped: dict[tuple[Any, ...], list[SourceRecord]] = {}
        for record in valid_source_records:
            try:
                key = build_group_key(record, self.resolver)
                grouped.setdefault(key, []).append(record)
            except (TypeError, ValueError) as exc:
                overall.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="FA-PRE-GROUPING",
                        status=ValidationStatus.FAIL,
                        message=str(exc),
                        record_ids=[record.record_id],
                        source_files=[record.source.file_path],
                    )
                )

        for group in grouped.values():
            group_result = self.validate_group(group)
            overall.rule_results.extend(group_result.rule_results)
            overall.decisions.extend(group_result.decisions)

        # Auditable netting statistics by claim type and decision.
        by_id = {r.record_id: r for r in valid_source_records}
        stats = Counter()
        for r in valid_source_records:
            stats[f"input_{self.derive_record_type(self.resolver.get(r.data, 'transaction_code'))}"] += 1
        for decision in overall.decisions:
            record = by_id.get(decision.record_id)
            if record is not None:
                kind = self.derive_record_type(self.resolver.get(record.data, 'transaction_code'))
                stats[f"{decision.decision.value.lower()}_{kind}"] += 1
        overall.rule_results.append(RuleResult(
            stage=self.stage, rule_id="FA-NETTING-STATISTICS",
            status=ValidationStatus.PASS,
            message="Separate inpatient and SNF netting totals",
            actual=dict(stats),
        ))

        decided_ids = {decision.record_id for decision in overall.decisions}
        expected_decidable_ids = {record.record_id for record in valid_source_records}
        blocked_or_failed_group_ids = {
            record_id
            for rule_result in overall.rule_results
            if rule_result.status in {ValidationStatus.FAIL, ValidationStatus.BLOCKED}
            for record_id in rule_result.record_ids
        }
        undecided = sorted(
            expected_decidable_ids - decided_ids - blocked_or_failed_group_ids
        )
        stage_reconciliation_passed = not undecided
        overall.rule_results.append(
            RuleResult(
                stage=self.stage,
                rule_id="FA-STAGE-RECONCILIATION",
                status=(
                    ValidationStatus.PASS
                    if stage_reconciliation_passed
                    else ValidationStatus.FAIL
                ),
                message=(
                    "All valid source records were decided or explicitly blocked/failed"
                    if stage_reconciliation_passed
                    else "Some valid source records have no Final Action outcome"
                ),
                expected={"undecided_records": 0},
                actual={"undecided_record_ids": undecided},
                record_ids=[record.record_id for record in valid_source_records],
                source_files=sorted({record.source.file_path for record in source_records}),
            )
        )

        if actual_records:
            overall.rule_results.append(
                reconcile_actual_output(
                    valid_source_records,
                    actual_records,
                    overall.decisions,
                    self.resolver,
                    self.settings,
                )
            )
        else:
            overall.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FA-ACTUAL-OUTPUT-RECONCILIATION",
                    status=ValidationStatus.NOT_APPLICABLE,
                    message="Actual Final Action output was not supplied; expected decisions only",
                )
            )

        return overall
