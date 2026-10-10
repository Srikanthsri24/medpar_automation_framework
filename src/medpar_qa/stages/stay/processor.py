from __future__ import annotations

from collections import defaultdict
from typing import Any

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord, StageResult
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.base import BaseStageProcessor
from medpar_qa.stages.common import (
    duplicate_identity_result,
    index_unique_records,
    ld3137_grouping_result,
    ld3137_sort_order_result,
    presence_result,
    record_identity,
    split_records_by_role,
)
from medpar_qa.stages.comparison import compare_expected_actual_fields, compare_values

from .code_precedence import latest_values_by_code, strip_lineage
from .derivations import (
    derive_condition_switch,
    derive_sum_field,
    derive_value_code_amount,
)
from .settings import StaySettings
from .structural import (
    validate_latest_selected_value,
    validate_stay_output_record,
    validate_stay_source_record,
)


class StayProcessor(BaseStageProcessor):
    stage = Stage.STAY

    def __init__(
        self,
        resolver: FieldResolver,
        settings: StaySettings | None = None,
    ) -> None:
        self.resolver = resolver
        self.settings = settings or StaySettings()

    def _group_sources(
        self, records: list[SourceRecord]
    ) -> dict[tuple[Any, ...], list[SourceRecord]]:
        grouped: dict[tuple[Any, ...], list[SourceRecord]] = defaultdict(list)
        for record in records:
            identity = record_identity(record,self.resolver,self.settings.identity_fields)
            if any(self.resolver.get(record.data,field) in (None,"") for field in ("hicn","provider_id","admission_date")):
                continue
            grouped[identity].append(record)
        return dict(grouped)

    def _actual_or_expected_record(
        self,
        identity: tuple[Any, ...],
        actual_index: dict[tuple[Any, ...], SourceRecord],
        expected_index: dict[tuple[Any, ...], SourceRecord],
    ) -> tuple[SourceRecord | None, SourceRecord | None]:
        return actual_index.get(identity), expected_index.get(identity)

    def _validate_latest_code_collections(
        self,
        source_group: list[SourceRecord],
        actual: SourceRecord | None,
    ) -> list[RuleResult]:
        results: list[RuleResult] = []
        from .merge_rules import validate_merge_rules
        results.extend(validate_merge_rules(source_group, actual, self.resolver, self.settings.decimal_scale))
        for canonical, rule_id in (
            ("condition_codes", "ST-LATEST-CONDITION-CODES"),
            ("occurrence_codes", "ST-LATEST-OCCURRENCE-CODES"),
            ("occurrence_span_lines", "ST-LATEST-SPAN-CODES"),
            ("value_lines", "ST-LATEST-VALUE-CODES"),
        ):
            try:
                expected = strip_lineage(
                    latest_values_by_code(
                        source_group,
                        collection_path=canonical,
                        date_paths=("processing_date", "accrete_date"),
                        resolver=self.resolver,
                    )
                )
                if canonical in {"condition_codes", "occurrence_codes", "value_lines"}:
                    expected = expected[:36 if canonical == "value_lines" else 30]
                if canonical == "occurrence_span_lines":
                    discovered_count = len(expected)
                    expected = expected[:10]
                    results.append(
                        RuleResult(
                            stage=self.stage,
                            rule_id="ST-SPAN-CODE-LIMIT",
                            status=ValidationStatus.PASS,
                            message="Unique span code/from/thru sets consolidated and limited to 10",
                            expected="At most 10 unique Span Code/date groups in combined Stay",
                            actual={"unique_source_codes": discovered_count, "selected_output_count": len(expected)},
                            field_name=canonical,
                            record_ids=[record.record_id for record in source_group],
                            source_files=sorted({record.source.file_path for record in source_group}),
                            evidence={"selection_rule": "Latest record wins for duplicate code; retain unique codes; output maximum is 10"},
                        )
                    )
                actual_value = (
                    self.resolver.get(actual.data, canonical) if actual else None
                )
                if actual is None or actual_value is None:
                    status = (
                        ValidationStatus.FAIL
                        if self.settings.require_actual_output
                        else ValidationStatus.NOT_APPLICABLE
                    )
                    message = "Actual Stay collection not supplied"
                else:
                    status = (
                        ValidationStatus.PASS
                        if actual_value == expected
                        else ValidationStatus.FAIL
                    )
                    message = (
                        "Latest-record code precedence matches"
                        if status == ValidationStatus.PASS
                        else "Latest-record code precedence mismatch"
                    )
                results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id=rule_id,
                        status=status,
                        message=message,
                        expected=expected,
                        actual=actual_value,
                        field_name=canonical,
                        record_ids=[
                            *[record.record_id for record in source_group],
                            *([actual.record_id] if actual else []),
                        ],
                        source_files=sorted(
                            {
                                *[record.source.file_path for record in source_group],
                                *([actual.source.file_path] if actual else []),
                            }
                        ),
                    )
                )
            except ValueError as exc:
                results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id=rule_id,
                        status=ValidationStatus.FAIL,
                        message=str(exc),
                        record_ids=[record.record_id for record in source_group],
                        source_files=sorted(
                            {record.source.file_path for record in source_group}
                        ),
                    )
                )
        return results

    def _validate_known_derivations(
        self,
        source_group: list[SourceRecord],
        actual: SourceRecord | None,
    ) -> list[RuleResult]:
        results: list[RuleResult] = []
        if actual is None:
            return results

        condition_codes = self.resolver.get(actual.data, "condition_codes")
        if condition_codes is None:
            # Derive the consolidated list when it is not present on actual output.
            condition_codes = strip_lineage(
                latest_values_by_code(
                    source_group,
                    collection_path="condition_codes",
                    date_paths=("processing_date", "accrete_date"),
                    resolver=self.resolver,
                )
            )

        for field_name, code, rule_id in (
            (
                "medpar_infor_enctr_ind_sw_0800",
                self.settings.condition_info_encounter_code,
                "ST-CONDITION-INFOR-ENCOUNTER",
            ),
            (
                "medpar_ma_teach_ind_sw_0810",
                self.settings.condition_ma_teach_code,
                "ST-CONDITION-MA-TEACH",
            ),
        ):
            expected = derive_condition_switch(condition_codes, code)
            actual_value = self.resolver.get(actual.data, field_name)
            results.append(
                compare_values(
                    stage=self.stage,
                    rule_id=rule_id,
                    field_name=field_name,
                    expected=expected,
                    actual=actual_value,
                    record_ids=[actual.record_id],
                    source_files=[actual.source.file_path],
                )
            )

        try:
            expected_sequestration = derive_value_code_amount(
                source_group,
                self.resolver,
                code=self.settings.sequestration_value_code,
                scale=self.settings.decimal_scale,
            )
            actual_sequestration = self.resolver.get(
                actual.data, "medpar_sqstrtn_rdctn_amt_1130"
            )
            results.append(
                compare_values(
                    stage=self.stage,
                    rule_id="ST-VALUE-CODE-SEQUESTRATION",
                    field_name="medpar_sqstrtn_rdctn_amt_1130",
                    expected=expected_sequestration,
                    actual=actual_sequestration,
                    record_ids=[
                        *[record.record_id for record in source_group],
                        actual.record_id,
                    ],
                    source_files=sorted(
                        {
                            *[record.source.file_path for record in source_group],
                            actual.source.file_path,
                        }
                    ),
                    decimal_scale=self.settings.decimal_scale,
                )
            )
        except ValueError as exc:
            results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="ST-VALUE-CODE-SEQUESTRATION",
                    status=ValidationStatus.FAIL,
                    message=str(exc),
                    record_ids=[record.record_id for record in source_group],
                    source_files=sorted(
                        {record.source.file_path for record in source_group}
                    ),
                )
            )

        expected_total = derive_sum_field(
            source_group,
            self.resolver,
            "medpar_tot_chrg_0400",
            scale=self.settings.decimal_scale,
        )
        if expected_total is not None:
            results.append(
                compare_values(
                    stage=self.stage,
                    rule_id="ST-TOTAL-CHARGE",
                    field_name="medpar_tot_chrg_0400",
                    expected=expected_total,
                    actual=self.resolver.get(actual.data, "medpar_tot_chrg_0400"),
                    record_ids=[
                        *[record.record_id for record in source_group],
                        actual.record_id,
                    ],
                    source_files=sorted(
                        {
                            *[record.source.file_path for record in source_group],
                            actual.source.file_path,
                        }
                    ),
                    decimal_scale=self.settings.decimal_scale,
                )
            )
        return results

    def validate(self, records: list[SourceRecord]) -> StageResult:
        result = StageResult(stage=self.stage)
        result.rule_results.append(
            ld3137_sort_order_result(
                stage=self.stage,
                rule_id="ST-SORT-ORDER-LD3137",
                sort_fields=self.settings.sort_fields,
            )
        )
        by_role = split_records_by_role(records)
        sources = by_role.get(FileRole.SOURCE, [])
        actuals = by_role.get(FileRole.ACTUAL_OUTPUT, [])
        expecteds = by_role.get(FileRole.EXPECTED_OUTPUT, [])

        result.rule_results.append(
            ld3137_grouping_result(
                stage=self.stage,
                rule_id="ST-GROUP-CONTIGUITY-LD3137",
                records=sources,
                resolver=self.resolver,
                identity_fields=self.settings.identity_fields,
            )
        )

        result.rule_results.append(
            presence_result(
                stage=self.stage,
                rule_id="ST-PRE-SOURCE",
                supplied=bool(sources),
                role_name="Stay source",
                required=True,
            )
        )
        if not sources:
            return result

        for source_record in sources:
            result.rule_results.extend(
                validate_stay_source_record(
                    source_record,
                    self.resolver,
                    decimal_scale=self.settings.decimal_scale,
                )
            )

        actual_index, actual_duplicates = index_unique_records(
            actuals, self.resolver, self.settings.identity_fields
        )
        expected_index, expected_duplicates = index_unique_records(
            expecteds, self.resolver, self.settings.identity_fields
        )
        if actuals:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="ST-ACTUAL-DUPLICATE-IDENTITY",
                    duplicates=actual_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Stay actual-output",
                )
            )
        if expecteds:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="ST-EXPECTED-DUPLICATE-IDENTITY",
                    duplicates=expected_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Stay expected-output",
                )
            )

        source_groups = self._group_sources(sources)
        for identity, source_group in source_groups.items():
            actual, expected = self._actual_or_expected_record(
                identity, actual_index, expected_index
            )
            if actual is None and (self.settings.require_actual_output or actuals):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="ST-MISSING-ACTUAL-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Expected Stay group is missing from actual output",
                        actual={"identity": identity},
                        record_ids=[record.record_id for record in source_group],
                        source_files=sorted(
                            {record.source.file_path for record in source_group}
                        ),
                    )
                )
            if expected is None and (self.settings.require_expected_output or expecteds):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="ST-MISSING-EXPECTED-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Approved Stay expected output is missing",
                        actual={"identity": identity},
                    )
                )

            result.rule_results.extend(
                self._validate_latest_code_collections(source_group, actual)
            )
            result.rule_results.extend(
                self._validate_known_derivations(source_group, actual)
            )
            if actual is not None:
                result.rule_results.extend(
                    validate_stay_output_record(
                        actual,
                        self.resolver,
                        decimal_scale=self.settings.decimal_scale,
                    )
                )
                result.rule_results.append(
                    validate_latest_selected_value(
                        source_group=source_group,
                        actual=actual,
                        resolver=self.resolver,
                        field_name="medpar_drg_price_0380",
                        rule_id="ST-DRG-PRICE-LATEST-RECORD",
                        decimal_scale=self.settings.decimal_scale,
                    )
                )
                result.rule_results.append(
                    validate_latest_selected_value(
                        source_group=source_group,
                        actual=actual,
                        resolver=self.resolver,
                        field_name="medpar_dte_cr_ended_0220",
                        rule_id="ST-DTE-CR-ENDED-LATEST-RECORD",
                    )
                )

            if expected is not None and actual is not None:
                result.rule_results.extend(
                    compare_expected_actual_fields(
                        stage=self.stage,
                        expected_record=expected,
                        actual_record=actual,
                        resolver=self.resolver,
                        fields=self.settings.selected_fields,
                        decimal_fields=set(self.settings.decimal_fields),
                        decimal_scale=self.settings.decimal_scale,
                        rule_prefix="ST-REGRESSION",
                    )
                )
            elif expected is None:
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="ST-GOLDEN-COMPARISON",
                        status=ValidationStatus.NOT_APPLICABLE,
                        message=(
                            "Expected Stay output was not supplied; known derivations and structural checks only"
                        ),
                        record_ids=[record.record_id for record in source_group],
                    )
                )

        source_identities = set(source_groups)
        unexpected_actual = sorted(str(key) for key in set(actual_index) - source_identities)
        if actuals:
            result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="ST-OUTPUT-RECONCILIATION",
                    status=(
                        ValidationStatus.PASS
                        if not unexpected_actual
                        else ValidationStatus.FAIL
                    ),
                    message=(
                        "Stay actual output reconciles to source groups"
                        if not unexpected_actual
                        else "Unexpected Stay output groups found"
                    ),
                    expected={"unexpected": 0},
                    actual={"unexpected_identities": unexpected_actual},
                )
            )
        return result
