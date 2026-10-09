from __future__ import annotations

from decimal import Decimal
from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import quantize_decimal
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.field_checks import (
    collection_structure_result,
    date_order_result,
    decimal_field_result,
    optional_date_result,
    required_fields_results,
)


def validate_stay_source_record(
    record: SourceRecord,
    resolver: FieldResolver,
    *,
    decimal_scale: Decimal,
) -> list[RuleResult]:
    results = required_fields_results(
        stage=Stage.STAY,
        rule_prefix="ST-PRE",
        record=record,
        resolver=resolver,
        fields=("hicn", "provider_id", "stay_from_date", "stay_thru_date"),
    )
    results.append(
        date_order_result(
            stage=Stage.STAY,
            rule_id="ST-STAY-DATE-ORDER",
            record=record,
            resolver=resolver,
            start_field="stay_from_date",
            end_field="stay_thru_date",
            allow_missing=False,
        )
    )
    results.append(
        optional_date_result(
            stage=Stage.STAY,
            rule_id="ST-ADMISSION-DATE",
            record=record,
            resolver=resolver,
            field_name="admission_date",
        )
    )
    for collection_name in (
        "condition_codes",
        "occurrence_span_lines",
        "occurrence_codes",
        "value_lines",
        "revenue_lines",
    ):
        results.append(
            collection_structure_result(
                stage=Stage.STAY,
                rule_id="ST-CODE-COLLECTION-STRUCTURE",
                record=record,
                resolver=resolver,
                field_name=collection_name,
            )
        )
    for amount_field in (
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
        "reimbursement_amount",
        "primary_payment_amount",
        "therapy_reduction_amount",
        "reduce_coinsurance",
    ):
        results.append(
            decimal_field_result(
                stage=Stage.STAY,
                rule_id="ST-DECIMAL-PRECISION",
                record=record,
                resolver=resolver,
                field_name=amount_field,
                scale=decimal_scale,
            )
        )
    return results


def validate_stay_output_record(
    record: SourceRecord,
    resolver: FieldResolver,
    *,
    decimal_scale: Decimal,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    results.append(
        optional_date_result(
            stage=Stage.STAY,
            rule_id="ST-DTE-CR-ENDED-0220-FORMAT",
            record=record,
            resolver=resolver,
            field_name="medpar_dte_cr_ended_0220",
        )
    )
    results.append(
        optional_date_result(
            stage=Stage.STAY,
            rule_id="ST-SNF-QUAL-FROM-DATE-FORMAT",
            record=record,
            resolver=resolver,
            field_name="medpar_snf_qual_from_date_0180",
        )
    )
    results.append(
        optional_date_result(
            stage=Stage.STAY,
            rule_id="ST-SNF-QUAL-THRU-DATE-FORMAT",
            record=record,
            resolver=resolver,
            field_name="medpar_snf_qual_thru_date_0190",
        )
    )
    results.append(
        date_order_result(
            stage=Stage.STAY,
            rule_id="ST-SNF-QUAL-DATE-ORDER",
            record=record,
            resolver=resolver,
            start_field="medpar_snf_qual_from_date_0180",
            end_field="medpar_snf_qual_thru_date_0190",
            allow_missing=True,
        )
    )
    for amount_field in (
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
    ):
        results.append(
            decimal_field_result(
                stage=Stage.STAY,
                rule_id="ST-SELECTED-DECIMAL-PRECISION",
                record=record,
                resolver=resolver,
                field_name=amount_field,
                scale=decimal_scale,
            )
        )

    bill_count = resolver.get(record.data, "bill_count")
    if bill_count in (None, ""):
        results.append(
            RuleResult(
                stage=Stage.STAY,
                rule_id="ST-BILL-COUNT",
                status=ValidationStatus.NOT_APPLICABLE,
                message="Bill count is not populated",
                expected="Positive integer when applicable",
                actual=bill_count,
                field_name="bill_count",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    else:
        try:
            normalized = int(bill_count)
            valid = normalized >= 0
        except (TypeError, ValueError):
            normalized = bill_count
            valid = False
        results.append(
            RuleResult(
                stage=Stage.STAY,
                rule_id="ST-BILL-COUNT",
                status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
                message="Bill count is valid" if valid else "Bill count must be a non-negative integer",
                expected=">= 0",
                actual=normalized,
                field_name="bill_count",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    return results


def derive_latest_nonblank(
    records: list[SourceRecord],
    resolver: FieldResolver,
    field_name: str,
) -> Any:
    def sort_key(record: SourceRecord):
        processing = parse_date(resolver.get(record.data, "processing_date"), allow_none=True)
        accrete = parse_date(resolver.get(record.data, "accrete_date"), allow_none=True)
        return processing or parse_date("00010101"), accrete or parse_date("00010101")

    for record in sorted(records, key=sort_key, reverse=True):
        value = resolver.get(record.data, field_name)
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return None


def validate_latest_selected_value(
    *,
    source_group: list[SourceRecord],
    actual: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    rule_id: str,
    decimal_scale: Decimal | None = None,
) -> RuleResult:
    expected = derive_latest_nonblank(source_group, resolver, field_name)
    actual_value = resolver.get(actual.data, field_name)
    if expected is None:
        return RuleResult(
            stage=Stage.STAY,
            rule_id=rule_id,
            status=ValidationStatus.NOT_APPLICABLE,
            message=f"No source value was available to derive {field_name}",
            expected=None,
            actual=actual_value,
            field_name=field_name,
            record_ids=[r.record_id for r in source_group] + [actual.record_id],
            source_files=sorted({r.source.file_path for r in source_group} | {actual.source.file_path}),
        )
    try:
        if decimal_scale is not None:
            normalized_expected = quantize_decimal(expected, scale=decimal_scale)
            normalized_actual = quantize_decimal(actual_value, scale=decimal_scale)
        else:
            normalized_expected = expected
            normalized_actual = actual_value
        valid = normalized_expected == normalized_actual
    except ValueError as exc:
        return RuleResult(
            stage=Stage.STAY,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected=expected,
            actual=actual_value,
            field_name=field_name,
            record_ids=[r.record_id for r in source_group] + [actual.record_id],
            source_files=sorted({r.source.file_path for r in source_group} | {actual.source.file_path}),
        )
    return RuleResult(
        stage=Stage.STAY,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=f"Latest-record value for {field_name} matches" if valid else f"Latest-record value for {field_name} mismatch",
        expected=str(normalized_expected) if isinstance(normalized_expected, Decimal) else normalized_expected,
        actual=str(normalized_actual) if isinstance(normalized_actual, Decimal) else normalized_actual,
        field_name=field_name,
        record_ids=[r.record_id for r in source_group] + [actual.record_id],
        source_files=sorted({r.source.file_path for r in source_group} | {actual.source.file_path}),
    )
