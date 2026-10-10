# from __future__ import annotations

# from medpar_qa.enums import FileRole, Stage, ValidationStatus
# from medpar_qa.models import RuleResult, SourceRecord, StageResult
# from medpar_qa.normalization.dates import january_aligned_window
# from medpar_qa.normalization.fields import FieldResolver
# from medpar_qa.stages.base import BaseStageProcessor
# from medpar_qa.stages.common import (
#     duplicate_identity_result,
#     index_unique_records,
#     presence_result,
#     split_records_by_role,
# )
# from medpar_qa.stages.comparison import compare_expected_actual_fields
# from medpar_qa.stages.field_checks import required_fields_results

# from .settings import IntermediateSettings
# from .direct_fields import (
#     validate_intermediate_direct_fields,
#     validate_repeated_alignment,
# )
# from .legacy_discrepancies import (
#     validate_admission_day,
#     validate_bill_total_perdiem,
#     validate_condition_switches,
#     validate_revenue_indicator,
#     validate_revenue_line_items,
#     validate_source_to_actual_direct_moves,
# )
# from .structural import (
#     validate_accommodation_totals,
#     validate_age_and_ndc,
#     validate_death_after_admission,
#     validate_decimal_values,
#     validate_diagnosis_structure,
#     validate_procedure_structure,
# )


# class IntermediateProcessor(BaseStageProcessor):
#     stage = Stage.INTERMEDIATE

#     def __init__(
#         self,
#         resolver: FieldResolver,
#         run_date,
#         settings: IntermediateSettings | None = None,
#     ) -> None:
#         self.resolver = resolver
#         self.run_date = run_date
#         self.settings = settings or IntermediateSettings()

#     def _validate_actual_structure(self, record: SourceRecord) -> list[RuleResult]:
#         start, end = january_aligned_window(
#             self.run_date, self.settings.window_years
#         )
#         results = validate_decimal_values(
#             record,
#             self.resolver,
#             self.settings.decimal_fields,
#             self.settings.repeated_decimal_fields,
#             self.settings.decimal_scale,
#         )
#         results.extend(
#             validate_procedure_structure(record, self.resolver, start, end)
#         )
#         results.extend(validate_diagnosis_structure(record, self.resolver))
#         results.extend(
#             validate_intermediate_direct_fields(
#                 record, self.resolver, window_start=start, window_end=end
#             )
#         )
#         results.extend(validate_repeated_alignment(record, self.resolver))
#         results.append(validate_death_after_admission(record, self.resolver))
#         results.extend(
#             validate_age_and_ndc(record, self.resolver, self.settings.ndc_length)
#         )
#         results.append(
#             validate_accommodation_totals(
#                 record, self.resolver, self.settings.decimal_scale
#             )
#         )
#         results.append(
#             validate_bill_total_perdiem(
#                 record, self.resolver, scale=self.settings.decimal_scale
#             )
#         )
#         results.append(
#             validate_revenue_indicator(
#                 record,
#                 self.resolver,
#                 field_name="medpar_intensive_care_ind_0481",
#                 rule_id="INT-INTENSIVE-CARE-IND-0481",
#                 search_codes=self.settings.intensive_care_revenue_codes,
#             )
#         )
#         results.append(
#             validate_revenue_indicator(
#                 record,
#                 self.resolver,
#                 field_name="medpar_organ_ind_0487",
#                 rule_id="INT-ORGAN-IND-0487",
#                 search_codes=self.settings.organ_revenue_codes,
#             )
#         )
#         results.append(validate_admission_day(record, self.resolver))
#         results.extend(
#             validate_condition_switches(
#                 record, self.resolver, self.settings.condition_switch_map
#             )
#         )
#         results.extend(
#             validate_revenue_line_items(
#                 record, self.resolver, scale=self.settings.decimal_scale
#             )
#         )
#         if self.settings.required_selected_fields:
#             results.extend(
#                 required_fields_results(
#                     stage=self.stage,
#                     rule_prefix="INT-SELECTED",
#                     record=record,
#                     resolver=self.resolver,
#                     fields=self.settings.required_selected_fields,
#                 )
#             )
#         return results

#     def validate(self, records: list[SourceRecord]) -> StageResult:
#         result = StageResult(stage=self.stage)
#         by_role = split_records_by_role(records)
#         sources = by_role.get(FileRole.SOURCE, [])
#         actuals = by_role.get(FileRole.ACTUAL_OUTPUT, [])
#         expecteds = by_role.get(FileRole.EXPECTED_OUTPUT, [])

#         result.rule_results.append(
#             presence_result(
#                 stage=self.stage,
#                 rule_id="INT-PRE-SOURCE",
#                 supplied=bool(sources),
#                 role_name="Intermediate source",
#                 required=True,
#             )
#         )
#         if not sources:
#             return result

#         actual_index, actual_duplicates = index_unique_records(
#             actuals, self.resolver, self.settings.identity_fields
#         )
#         expected_index, expected_duplicates = index_unique_records(
#             expecteds, self.resolver, self.settings.identity_fields
#         )
#         source_index, source_duplicates = index_unique_records(
#             sources, self.resolver, self.settings.identity_fields
#         )
#         result.rule_results.append(
#             duplicate_identity_result(
#                 stage=self.stage,
#                 rule_id="INT-SOURCE-DUPLICATE-IDENTITY",
#                 duplicates=source_duplicates,
#                 identity_fields=self.settings.identity_fields,
#                 role_name="Intermediate source",
#             )
#         )
#         if actuals:
#             result.rule_results.append(
#                 duplicate_identity_result(
#                     stage=self.stage,
#                     rule_id="INT-ACTUAL-DUPLICATE-IDENTITY",
#                     duplicates=actual_duplicates,
#                     identity_fields=self.settings.identity_fields,
#                     role_name="Intermediate actual-output",
#                 )
#             )
#         if expecteds:
#             result.rule_results.append(
#                 duplicate_identity_result(
#                     stage=self.stage,
#                     rule_id="INT-EXPECTED-DUPLICATE-IDENTITY",
#                     duplicates=expected_duplicates,
#                     identity_fields=self.settings.identity_fields,
#                     role_name="Intermediate expected-output",
#                 )
#             )

#         for identity, source in source_index.items():
#             actual = actual_index.get(identity)
#             expected = expected_index.get(identity)
#             target = actual or source
#             if actual is None and self.settings.require_actual_output:
#                 result.rule_results.append(
#                     RuleResult(
#                         stage=self.stage,
#                         rule_id="INT-MISSING-ACTUAL-OUTPUT",
#                         status=ValidationStatus.FAIL,
#                         message="Intermediate actual output is missing",
#                         actual={"identity": identity},
#                         record_ids=[source.record_id],
#                         source_files=[source.source.file_path],
#                     )
#                 )
#             if expected is None and self.settings.require_expected_output:
#                 result.rule_results.append(
#                     RuleResult(
#                         stage=self.stage,
#                         rule_id="INT-MISSING-EXPECTED-OUTPUT",
#                         status=ValidationStatus.FAIL,
#                         message="Approved Intermediate expected output is missing",
#                         actual={"identity": identity},
#                     )
#                 )

#             result.rule_results.extend(self._validate_actual_structure(target))
#             if actual is not None:
#                 result.rule_results.extend(
#                     validate_source_to_actual_direct_moves(
#                         source,
#                         actual,
#                         self.resolver,
#                         self.settings.source_to_target_fields,
#                         decimal_fields=set(self.settings.decimal_fields),
#                         scale=self.settings.decimal_scale,
#                     )
#                 )

#             if expected is not None and actual is not None:
#                 result.rule_results.extend(
#                     compare_expected_actual_fields(
#                         stage=self.stage,
#                         expected_record=expected,
#                         actual_record=actual,
#                         resolver=self.resolver,
#                         fields=self.settings.selected_fields,
#                         decimal_fields=set(self.settings.decimal_fields),
#                         decimal_scale=self.settings.decimal_scale,
#                         rule_prefix="INT-REGRESSION",
#                     )
#                 )
#             else:
#                 result.rule_results.append(
#                     RuleResult(
#                         stage=self.stage,
#                         rule_id="INT-GOLDEN-COMPARISON",
#                         status=ValidationStatus.NOT_APPLICABLE,
#                         message="Expected and actual Intermediate outputs were not both supplied; structural checks only",
#                         record_ids=[target.record_id],
#                     )
#                 )

#         unexpected_actual = sorted(str(key) for key in set(actual_index) - set(source_index))
#         if actuals:
#             result.rule_results.append(
#                 RuleResult(
#                     stage=self.stage,
#                     rule_id="INT-OUTPUT-RECONCILIATION",
#                     status=ValidationStatus.PASS if not unexpected_actual else ValidationStatus.FAIL,
#                     message="Intermediate output reconciles to source" if not unexpected_actual else "Unexpected Intermediate output records found",
#                     expected={"unexpected": 0},
#                     actual={"unexpected_identities": unexpected_actual},
#                 )
#             )
#         return result







from __future__ import annotations

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord, StageResult
from medpar_qa.normalization.dates import january_aligned_window
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.base import BaseStageProcessor
from medpar_qa.stages.common import (
    duplicate_identity_result,
    index_unique_records,
    record_identity,
    presence_result,
    split_records_by_role,
)
from medpar_qa.stages.comparison import compare_expected_actual_fields
from medpar_qa.stages.field_checks import required_fields_results

from .settings import IntermediateSettings
from .direct_fields import (
    validate_intermediate_direct_fields,
    validate_repeated_alignment,
)
from .legacy_discrepancies import (
    validate_admission_day,
    validate_bill_total_perdiem,
    validate_condition_switches,
    validate_revenue_indicator,
    validate_revenue_line_items,
    validate_source_to_actual_direct_moves,
)
from .structural import (
    validate_accommodation_totals,
    validate_age_and_ndc,
    validate_death_after_admission,
    validate_decimal_values,
    validate_diagnosis_structure,
    validate_procedure_structure,
)


class IntermediateProcessor(BaseStageProcessor):
    stage = Stage.INTERMEDIATE

    def __init__(
        self,
        resolver: FieldResolver,
        run_date,
        settings: IntermediateSettings | None = None,
    ) -> None:
        self.resolver = resolver
        self.run_date = run_date
        self.settings = settings or IntermediateSettings()

    def _validate_actual_structure(self, record: SourceRecord, source: SourceRecord | None = None) -> list[RuleResult]:
        start, end = january_aligned_window(
            self.run_date, self.settings.window_years
        )
        results = validate_decimal_values(
            record,
            self.resolver,
            self.settings.decimal_fields,
            self.settings.repeated_decimal_fields,
            self.settings.decimal_scale,
        )
        results.extend(
            validate_procedure_structure(record, self.resolver, start, end)
        )
        results.extend(validate_diagnosis_structure(record, self.resolver))
        results.extend(
            validate_intermediate_direct_fields(
                record, self.resolver, window_start=start, window_end=end
            )
        )
        results.extend(validate_repeated_alignment(record, self.resolver))
        results.append(validate_death_after_admission(record, self.resolver))
        results.extend(
            validate_age_and_ndc(record, self.resolver, self.settings.ndc_length)
        )
        results.append(
            validate_accommodation_totals(
                record, self.resolver, self.settings.decimal_scale
            )
        )
        results.append(
            validate_bill_total_perdiem(
                record, self.resolver, scale=self.settings.decimal_scale
            )
        )
        # ICU/CCU are care-type codes selected by accumulated source charges.
        # validate_business_rules checks them independently from the Stay input.
        # Organ acquisition is a two-character type, checked from source below.
        results.append(validate_admission_day(record, self.resolver))
        results.extend(
            validate_condition_switches(
                record, self.resolver, self.settings.condition_switch_map, source=source
            )
        )
        results.extend(
            validate_revenue_line_items(
                record, self.resolver, scale=self.settings.decimal_scale
            )
        )
        if self.settings.required_selected_fields:
            results.extend(
                required_fields_results(
                    stage=self.stage,
                    rule_prefix="INT-SELECTED",
                    record=record,
                    resolver=self.resolver,
                    fields=self.settings.required_selected_fields,
                )
            )
        return results

    def validate(self, records: list[SourceRecord]) -> StageResult:
        result = StageResult(stage=self.stage)
        by_role = split_records_by_role(records)
        sources = by_role.get(FileRole.SOURCE, [])
        actuals = by_role.get(FileRole.ACTUAL_OUTPUT, [])
        expecteds = by_role.get(FileRole.EXPECTED_OUTPUT, [])

        result.rule_results.append(
            presence_result(
                stage=self.stage,
                rule_id="INT-PRE-SOURCE",
                supplied=bool(sources),
                role_name="Intermediate source",
                required=True,
            )
        )
        if not sources:
            return result

        # Do not group missing identities: (None, provider, None, indicator)
        # is not evidence that two stays are duplicates.
        def complete_identity(records, role):
            complete, incomplete = [], []
            for record in records:
                identity = record_identity(record, self.resolver, self.settings.identity_fields)
                missing = [field for field, value in zip(self.settings.identity_fields, identity)
                           if value is None or value == ""]
                if missing:
                    incomplete.append((record, missing))
                else:
                    complete.append(record)
            result.rule_results.append(RuleResult(
                stage=self.stage,
                rule_id=f"INT-{role}-IDENTITY-COMPLETE",
                status=ValidationStatus.FAIL if incomplete else ValidationStatus.PASS,
                message=(f"{len(incomplete)} {role.lower()} records have incomplete identity"
                         if incomplete else f"All {role.lower()} record identities are complete"),
                expected="All configured identity components present",
                actual={"incomplete_count": len(incomplete),
                        "missing_fields_by_record": {r.record_id: fields for r, fields in incomplete}},
                record_ids=[r.record_id for r, _ in incomplete],
                source_files=sorted({r.source.file_path for r, _ in incomplete}),
            ))
            return complete

        sources = complete_identity(sources, "SOURCE")
        if actuals:
            actuals = complete_identity(actuals, "ACTUAL")
        if expecteds:
            expecteds = complete_identity(expecteds, "EXPECTED")

        actual_index, actual_duplicates = index_unique_records(
            actuals, self.resolver, self.settings.identity_fields
        )
        expected_index, expected_duplicates = index_unique_records(
            expecteds, self.resolver, self.settings.identity_fields
        )
        source_index, source_duplicates = index_unique_records(
            sources, self.resolver, self.settings.identity_fields
        )
        result.rule_results.append(
            duplicate_identity_result(
                stage=self.stage,
                rule_id="INT-SOURCE-DUPLICATE-IDENTITY",
                duplicates=source_duplicates,
                identity_fields=self.settings.identity_fields,
                role_name="Intermediate source",
            )
        )
        if actuals:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="INT-ACTUAL-DUPLICATE-IDENTITY",
                    duplicates=actual_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Intermediate actual-output",
                )
            )
        if expecteds:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="INT-EXPECTED-DUPLICATE-IDENTITY",
                    duplicates=expected_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Intermediate expected-output",
                )
            )

        for identity, source in source_index.items():
            actual = actual_index.get(identity)
            expected = expected_index.get(identity)
            target = actual or source
            if actual is None and (self.settings.require_actual_output or actuals):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="INT-MISSING-ACTUAL-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Intermediate actual output is missing",
                        actual={"identity": identity},
                        record_ids=[source.record_id],
                        source_files=[source.source.file_path],
                    )
                )
            if expected is None and (self.settings.require_expected_output or expecteds):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="INT-MISSING-EXPECTED-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Approved Intermediate expected output is missing",
                        actual={"identity": identity},
                    )
                )

            if actual is None and (self.settings.require_actual_output or actuals):
                # Report the missing output once; source fields are not output values.
                continue

            from .business_rules import validate_business_rules
            result.rule_results.extend(self._validate_actual_structure(target, source=source))
            result.rule_results.extend(validate_business_rules(source, target, self.resolver))
            from medpar_qa.stages.v3_fields import validate_whole_dollar_fields
            result.rule_results.extend(validate_whole_dollar_fields(source,target,self.resolver))
            if actual is not None:
                result.rule_results.extend(
                    validate_source_to_actual_direct_moves(
                        source,
                        actual,
                        self.resolver,
                        self.settings.source_to_target_fields,
                        decimal_fields=set(self.settings.decimal_fields),
                        scale=self.settings.decimal_scale,
                    )
                )

            if expected is not None and actual is not None:
                from medpar_qa.stages.v3_fields import compare_v3_fields
                result.rule_results.extend(compare_v3_fields(expected, actual, self.resolver))
                result.rule_results.extend(
                    compare_expected_actual_fields(
                        stage=self.stage,
                        expected_record=expected,
                        actual_record=actual,
                        resolver=self.resolver,
                        fields=self.settings.selected_fields,
                        decimal_fields=set(self.settings.decimal_fields),
                        decimal_scale=self.settings.decimal_scale,
                        rule_prefix="INT-REGRESSION",
                    )
                )
            else:
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="INT-GOLDEN-COMPARISON",
                        status=ValidationStatus.NOT_APPLICABLE,
                        message="Expected and actual Intermediate outputs were not both supplied; structural checks only",
                        record_ids=[target.record_id],
                    )
                )

        unexpected_actual = sorted(str(key) for key in set(actual_index) - set(source_index))
        if actuals:
            result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="INT-OUTPUT-RECONCILIATION",
                    status=ValidationStatus.PASS if not unexpected_actual else ValidationStatus.FAIL,
                    message="Intermediate output reconciles to source" if not unexpected_actual else "Unexpected Intermediate output records found",
                    expected={"unexpected": 0},
                    actual={"unexpected_identities": unexpected_actual},
                )
            )
        return result
