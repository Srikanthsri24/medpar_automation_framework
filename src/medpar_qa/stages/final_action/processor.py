from __future__ import annotations

from typing import Any

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
