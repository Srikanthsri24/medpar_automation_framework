from __future__ import annotations

from datetime import date
from collections import defaultdict
from typing import Any

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord, StageResult
from medpar_qa.normalization.dates import january_aligned_window, parse_date
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.base import BaseStageProcessor
from medpar_qa.stages.field_checks import required_fields_results, date_order_result
from medpar_qa.stages.common import (
    duplicate_identity_result,
    index_unique_records,
    ld3137_grouping_result,
    ld3137_sort_order_result,
    presence_result,
    record_identity,
    split_records_by_role,
)

from .settings import SplitSettings


class SplitProcessor(BaseStageProcessor):
    stage = Stage.SPLIT

    def __init__(
        self,
        resolver: FieldResolver,
        run_date: date,
        window_years: int | None = None,
        settings: SplitSettings | None = None,
    ) -> None:
        self.resolver = resolver
        self.run_date = run_date
        self.settings = settings or SplitSettings(
            window_years=window_years if window_years is not None else 4
        )

    def _transaction_code(self, record: SourceRecord) -> int | None:
        value = self.resolver.get(record.data, "transaction_code")
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid transactionCode: {value!r}") from exc

    def calculate_indicator(self, record: SourceRecord) -> str:
        admission = parse_date(
            self.resolver.get(record.data, "admission_date"), allow_none=True
        )
        stay_from = parse_date(
            self.resolver.get(record.data, "stay_from_date"), allow_none=False
        )
        stay_thru = parse_date(
            self.resolver.get(record.data, "stay_thru_date"), allow_none=False
        )
        assert stay_from is not None and stay_thru is not None
        if stay_from > stay_thru:
            raise ValueError("stayFromDate must be on or before stayThruDate")

        start, end = january_aligned_window(
            self.run_date, self.settings.window_years
        )
        if stay_from < start or stay_thru > end:
            return self.settings.outside_window_indicator

        reference = admission or stay_from
        suffix = "0109" if reference.month <= 9 else "1012"
        return f"Y{reference.year % 10}{suffix}"

    def validate(self, records: list[SourceRecord]) -> StageResult:
        stage_result = StageResult(stage=self.stage)
        stage_result.rule_results.append(
            ld3137_sort_order_result(
                stage=self.stage,
                rule_id="SP-SORT-ORDER-LD3137",
                sort_fields=self.settings.sort_fields,
            )
        )
        by_role = split_records_by_role(records)
        source_records = by_role.get(FileRole.SOURCE, [])
        actual_records = by_role.get(FileRole.ACTUAL_OUTPUT, [])

        stage_result.rule_results.append(
            ld3137_grouping_result(
                stage=self.stage,
                rule_id="SP-GROUP-CONTIGUITY-LD3137",
                records=source_records,
                resolver=self.resolver,
                identity_fields=self.settings.identity_fields,
            )
        )

        stage_result.rule_results.append(
            presence_result(
                stage=self.stage,
                rule_id="SP-PRE-SOURCE",
                supplied=bool(source_records),
                role_name="Split source",
                required=True,
            )
        )
        if not source_records:
            return stage_result

        for source_record in source_records:
            stage_result.rule_results.extend(
                required_fields_results(
                    stage=self.stage,
                    rule_prefix="SP-PRE",
                    record=source_record,
                    resolver=self.resolver,
                    fields=(
                        "claim_can", "hicn", "provider_id",
                        "stay_from_date", "stay_thru_date", "transaction_code",
                    ),
                )
            )
            stage_result.rule_results.append(
                date_order_result(
                    stage=self.stage,
                    rule_id="SP-PRE-DATE-ORDER",
                    record=source_record,
                    resolver=self.resolver,
                    start_field="stay_from_date",
                    end_field="stay_thru_date",
                    allow_missing=False,
                )
            )

        # V3 Split stay-group table capacity (SPL-04/SPL-05).
        # Admission date is part of the legacy stay key; missing admission
        # dates are represented consistently and do not get guessed.
        stay_groups: dict[tuple[Any, ...], list[SourceRecord]] = defaultdict(list)
        for record in source_records:
            key = tuple(self.resolver.get(record.data, name) for name in
                        ("hicn", "provider_id", "admission_date"))
            stay_groups[key].append(record)
        for key, group in stay_groups.items():
            if len(group) > self.settings.maximum_bills_per_stay:
                stage_result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="SP-STAY-BILL-LIMIT",
                        status=ValidationStatus.FAIL,
                        message=f"Stay has {len(group)} bills; legacy maximum is {self.settings.maximum_bills_per_stay}",
                        expected=f"<= {self.settings.maximum_bills_per_stay}",
                        actual=len(group),
                        record_ids=[r.record_id for r in group],
                        source_files=sorted({r.source.file_path for r in group}),
                        evidence={"stay_key": [str(x) for x in key]},
                    )
                )

        actual_index, actual_duplicates = index_unique_records(
            actual_records, self.resolver, self.settings.identity_fields
        )
        if actual_records:
            stage_result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="SP-ACTUAL-DUPLICATE-IDENTITY",
                    duplicates=actual_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Split actual-output",
                )
            )

        expected_eligible: set[tuple[Any, ...]] = set()
        for record in source_records:
            try:
                transaction_code = self._transaction_code(record)
                if transaction_code not in self.settings.allowed_transaction_codes:
                    stage_result.rule_results.append(
                        RuleResult(
                            stage=self.stage,
                            rule_id="SP-INVALID-TRANSACTION-CODE",
                            status=ValidationStatus.FAIL,
                            message=f"Split transaction code {transaction_code!r} is not in {self.settings.allowed_transaction_codes}; exception required",
                            expected=list(self.settings.allowed_transaction_codes),
                            actual=transaction_code,
                            record_ids=[record.record_id],
                            source_files=[record.source.file_path],
                        )
                    )
                    continue
                if transaction_code in self.settings.skip_transaction_codes:
                    stage_result.rule_results.append(
                        RuleResult(
                            stage=self.stage,
                            rule_id="SP-REC-TYPE-BYPASS",
                            status=ValidationStatus.NOT_APPLICABLE,
                            message=(
                                f"Transaction code {transaction_code} is configured to bypass slicing"
                            ),
                            record_ids=[record.record_id],
                            source_files=[record.source.file_path],
                        )
                    )
                    continue

                expected = self.calculate_indicator(record)
                identity = record_identity(
                    record, self.resolver, self.settings.identity_fields
                )
                expected_eligible.add(identity)
                actual_record = actual_index.get(identity)
                inline_actual = self.resolver.get(
                    record.data, "split_year_indicator"
                )
                actual = (
                    self.resolver.get(actual_record.data, "split_year_indicator")
                    if actual_record is not None
                    else inline_actual
                )

                if actual is None:
                    status = (
                        ValidationStatus.FAIL
                        if self.settings.require_actual_output
                        else ValidationStatus.NOT_APPLICABLE
                    )
                    message = (
                        "Required actual Split output is missing"
                        if self.settings.require_actual_output
                        else "Expected Split indicator calculated; actual output not supplied"
                    )
                else:
                    status = (
                        ValidationStatus.PASS
                        if str(actual).strip() == expected
                        else ValidationStatus.FAIL
                    )
                    message = (
                        "Split indicator matches expected"
                        if status == ValidationStatus.PASS
                        else "Split indicator mismatch"
                    )

                stage_result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="SP-RULE-INDICATOR",
                        status=status,
                        message=message,
                        expected=expected,
                        actual=actual,
                        field_name="splitYearIndicator",
                        record_ids=[
                            record.record_id,
                            *([actual_record.record_id] if actual_record else []),
                        ],
                        source_files=[
                            record.source.file_path,
                            *(
                                [actual_record.source.file_path]
                                if actual_record
                                else []
                            ),
                        ],
                        evidence={
                            "window": [
                                str(
                                    january_aligned_window(
                                        self.run_date,
                                        self.settings.window_years,
                                    )[0]
                                ),
                                str(self.run_date),
                            ]
                        },
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                stage_result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="SP-PRE-DATES",
                        status=ValidationStatus.FAIL,
                        message=str(exc),
                        record_ids=[record.record_id],
                        source_files=[record.source.file_path],
                    )
                )

        if actual_records:
            actual_keys = set(actual_index)
            unexpected = sorted(str(key) for key in actual_keys - expected_eligible)
            stage_result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="SP-OUTPUT-RECONCILIATION",
                    status=(
                        ValidationStatus.PASS
                        if not unexpected
                        else ValidationStatus.FAIL
                    ),
                    message=(
                        "Split actual output contains only expected eligible identities"
                        if not unexpected
                        else "Unexpected Split actual-output records found"
                    ),
                    expected={"unexpected": 0},
                    actual={"unexpected_identities": unexpected},
                )
            )
        return stage_result
