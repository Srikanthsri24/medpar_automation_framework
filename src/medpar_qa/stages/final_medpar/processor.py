"""Coordinate final medpar validation: separate file roles, check prerequisites/structure, derive
source expectations, match output identities and compare available golden fields.
"""
from __future__ import annotations

import re

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
    split_records_by_role,
)
from medpar_qa.stages.comparison import compare_expected_actual_fields

from .byte_layout import validate_encoded_length, validate_field_layout
from .settings import FinalMedparSettings
from .business_rules import bypass_required, compare_final_bytes, validate_trailer_removal


class FinalMedparProcessor(BaseStageProcessor):
    """Implement this stage through the BaseStageProcessor validation interface and hold its
    resolver/settings.
    """
    stage = Stage.FINAL_MEDPAR

    def __init__(
        self,
        resolver: FieldResolver,
        settings: FinalMedparSettings | None = None,
    ) -> None:
        """Initialize this FinalMedparProcessor with the supplied dependencies/configuration and
        the assignments in its constructor.
        """
        self.resolver = resolver
        self.settings = settings or FinalMedparSettings()

    def _validate_record(self, record: SourceRecord) -> list[RuleResult]:
        """Run Final record classification, selected-field and optional physical-layout checks."""
        results: list[RuleResult] = []
        split_indicator = self.resolver.get(record.data, "split_year_indicator")
        split_valid = bool(
            split_indicator
            and re.fullmatch(r"Y(?:\d(?:0109|1012)|99999)", str(split_indicator).strip())
        )
        if not self.settings.split_indicator_in_output:
            split_valid = split_indicator in (None, "")
        results.append(
            RuleResult(
                stage=self.stage,
                rule_id="FM-SPLIT-YEAR-INDICATOR",
                status=ValidationStatus.PASS if split_valid else ValidationStatus.FAIL,
                message=("Final extract correctly omits the Intermediate routing indicator" if split_valid else "Final extract must omit the Intermediate routing indicator") if not self.settings.split_indicator_in_output else ("Split-year indicator is valid" if split_valid else "Split-year indicator is invalid"),
                expected="Absent from delivered Final extract; routing verified against Intermediate lineage" if not self.settings.split_indicator_in_output else "Y#0109, Y#1012, or Y99999",
                actual=split_indicator,
                field_name="split_year_indicator",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )

        classification = self.resolver.get(record.data, "medpar_ss_ls_snf_ind_0140")
        classification_valid = str(classification).strip() in self.settings.allowed_classifications
        results.append(
            RuleResult(
                stage=self.stage,
                rule_id="FM-CLASSIFICATION",
                status=ValidationStatus.PASS if classification_valid else ValidationStatus.FAIL,
                message="Final MEDPAR classification is valid" if classification_valid else "Final MEDPAR classification is invalid",
                expected=list(self.settings.allowed_classifications),
                actual=classification,
                field_name="medpar_ss_ls_snf_ind_0140",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )

        full_provider = self.resolver.get(record.data,"medpar_prvdr_full_num_1660")
        if full_provider not in (None, ""):
            provider=str(full_provider).strip()
            if len(provider)!=6:
                expected_class="Six-character provider number";provider_valid=False
            else:
                third=provider[2].upper()
                expected_class="N" if third in "56UWYZ" else "S" if third in "01STMR" else "L"
                provider_valid=str(classification).strip()==expected_class
            results.append(RuleResult(self.stage,"FM-PROVIDER-CLASSIFICATION",ValidationStatus.PASS if provider_valid else ValidationStatus.FAIL,
                "Final classification derived from original provider number",expected_class,classification,field_name="medpar_ss_ls_snf_ind_0140",record_ids=[record.record_id],source_files=[record.source.file_path],evidence={"specification":"V3 p26 / BxB provider-position rules", "provider_number":provider}))

        fixed_width = self.resolver.get(record.data, "fixed_width_record")
        if fixed_width is None:
            results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FM-BYTE-LENGTH",
                    status=(
                        ValidationStatus.FAIL
                        if self.settings.require_fixed_width
                        else ValidationStatus.NOT_APPLICABLE
                    ),
                    message=(
                        "Required fixed-width record text was not supplied"
                        if self.settings.require_fixed_width
                        else "Fixed-width record text was not supplied"
                    ),
                    expected=self.settings.expected_bytes,
                    actual=None,
                    field_name="fixed_width_record",
                    record_ids=[record.record_id],
                    source_files=[record.source.file_path],
                )
            )
        else:
            byte_result = validate_encoded_length(
                fixed_width,
                expected_bytes=self.settings.expected_bytes,
                encoding=self.settings.encoding,
            )
            byte_result.record_ids = [record.record_id]
            byte_result.source_files = [record.source.file_path]
            byte_result.field_name = "fixed_width_record"
            results.append(byte_result)
            for layout_result in validate_field_layout(
                fixed_width,
                field_layout=self.settings.field_layout,
                encoding=self.settings.encoding,
            ):
                layout_result.record_ids = [record.record_id]
                layout_result.source_files = [record.source.file_path]
                results.append(layout_result)

        for field_name in self.settings.selected_fields:
            value = self.resolver.get(record.data, field_name)
            populated = value is not None and (not isinstance(value, str) or bool(value.strip()))
            required = field_name in set(self.settings.required_selected_fields)
            results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FM-SELECTED-FIELD-PRESENCE",
                    status=(
                        ValidationStatus.PASS
                        if populated
                        else ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE
                    ),
                    message=(
                        f"Selected field {field_name} is populated"
                        if populated
                        else f"Required selected field {field_name} is not populated"
                        if required
                        else f"Selected field {field_name} is not populated and was not configured as mandatory"
                    ),
                    expected="Populated" if required else "Populated when applicable",
                    actual=value,
                    field_name=field_name,
                    record_ids=[record.record_id],
                    source_files=[record.source.file_path],
                )
            )
        return results

    def validate(self, records: list[SourceRecord]) -> StageResult:
        """Coordinate final medpar checks and return StageResult with auditable outcomes/decisions;
        source records remain distinct from actual/expected roles.
        """
        result = StageResult(stage=self.stage)
        result.rule_results.append(
            ld3137_sort_order_result(
                stage=self.stage,
                rule_id="FM-SORT-ORDER-LD3137",
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
                rule_id="FM-GROUP-CONTIGUITY-LD3137",
                records=sources,
                resolver=self.resolver,
                identity_fields=self.settings.identity_fields,
            )
        )

        result.rule_results.append(
            presence_result(
                stage=self.stage,
                rule_id="FM-PRE-SOURCE",
                supplied=bool(sources),
                role_name="Final MEDPAR source",
                required=True,
            )
        )
        if not sources:
            return result

        source_index, source_duplicates = index_unique_records(
            sources, self.resolver, self.settings.identity_fields
        )
        actual_index, actual_duplicates = index_unique_records(
            actuals, self.resolver, self.settings.identity_fields
        )
        expected_index, expected_duplicates = index_unique_records(
            expecteds, self.resolver, self.settings.identity_fields
        )
        result.rule_results.append(
            duplicate_identity_result(
                stage=self.stage,
                rule_id="FM-SOURCE-DUPLICATE-IDENTITY",
                duplicates=source_duplicates,
                identity_fields=self.settings.identity_fields,
                role_name="Final MEDPAR source",
            )
        )
        if actuals:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="FM-ACTUAL-DUPLICATE-IDENTITY",
                    duplicates=actual_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Final MEDPAR actual-output",
                )
            )
        if expecteds:
            result.rule_results.append(
                duplicate_identity_result(
                    stage=self.stage,
                    rule_id="FM-EXPECTED-DUPLICATE-IDENTITY",
                    duplicates=expected_duplicates,
                    identity_fields=self.settings.identity_fields,
                    role_name="Final MEDPAR expected-output",
                )
            )

        for identity, source in source_index.items():
            actual = actual_index.get(identity)
            expected = expected_index.get(identity)
            target = actual or source
            try:
                bypass = bypass_required(source, self.resolver)
            except (ValueError, TypeError, ArithmeticError) as exc:
                result.rule_results.append(RuleResult(stage=self.stage, rule_id="FM-BYPASS-OPERANDS",
                    status=ValidationStatus.FAIL, message=str(exc), record_ids=[source.record_id]))
                continue
            if bypass:
                result.rule_results.append(RuleResult(stage=self.stage, rule_id="FM-BYPASS-EXCEPTION",
                    status=ValidationStatus.FAIL if actual is not None else ValidationStatus.PASS,
                    message="Covered days exceed LOS: source belongs in Final bypass, absent from retained output",
                    expected="Absent from retained output", actual=actual.record_id if actual else None,
                    record_ids=[source.record_id], source_files=[source.source.file_path],
                    evidence={"route": "bypass"}))
                continue
            if actual is None and (self.settings.require_actual_output or actuals):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="FM-MISSING-ACTUAL-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Final MEDPAR actual output is missing",
                        actual={"identity": identity},
                        record_ids=[source.record_id],
                        source_files=[source.source.file_path],
                    )
                )
            if expected is None and (self.settings.require_expected_output or expecteds):
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="FM-MISSING-EXPECTED-OUTPUT",
                        status=ValidationStatus.FAIL,
                        message="Approved Final MEDPAR expected output is missing",
                        actual={"identity": identity},
                    )
                )

            if actual is None and (self.settings.require_actual_output or actuals):
                continue

            result.rule_results.extend(self._validate_record(target))
            if actual is not None:
                result.rule_results.append(validate_trailer_removal(source, actual, self.resolver, self.settings.encoding))
            if expected is not None and actual is not None:
                from medpar_qa.stages.v3_fields import compare_v3_fields
                result.rule_results.extend(compare_v3_fields(expected, actual, self.resolver))
                result.rule_results.append(compare_final_bytes(expected, actual, self.resolver, self.settings.encoding))
                result.rule_results.extend(
                    compare_expected_actual_fields(
                        stage=self.stage,
                        expected_record=expected,
                        actual_record=actual,
                        resolver=self.resolver,
                        fields=self.settings.selected_fields,
                        rule_prefix="FM-REGRESSION",
                    )
                )
            else:
                result.rule_results.append(
                    RuleResult(
                        stage=self.stage,
                        rule_id="FM-GOLDEN-COMPARISON",
                        status=ValidationStatus.NOT_APPLICABLE,
                        message="Expected and actual Final MEDPAR outputs were not both supplied; structural checks only",
                        record_ids=[target.record_id],
                    )
                )

        unexpected_actual = sorted(str(key) for key in set(actual_index) - set(source_index))
        if actuals:
            result.rule_results.append(
                RuleResult(
                    stage=self.stage,
                    rule_id="FM-OUTPUT-RECONCILIATION",
                    status=ValidationStatus.PASS if not unexpected_actual else ValidationStatus.FAIL,
                    message="Final MEDPAR output reconciles to source" if not unexpected_actual else "Unexpected Final MEDPAR output records found",
                    expected={"unexpected": 0},
                    actual={"unexpected_identities": unexpected_actual},
                )
            )
        return result
