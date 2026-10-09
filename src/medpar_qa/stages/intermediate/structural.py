from __future__ import annotations

from decimal import Decimal
from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.decimal_values import quantize_decimal
from medpar_qa.normalization.dates import in_date_window, parse_date
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.common import nonblank_values, normalize_collection


def validate_decimal_values(
    record: SourceRecord,
    resolver: FieldResolver,
    fields: tuple[str, ...],
    repeated_fields: tuple[str, ...],
    scale: Decimal,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    for field_name in fields:
        value = resolver.get(record.data, field_name)
        if value is None:
            continue
        try:
            normalized = quantize_decimal(value, scale=scale)
            status = ValidationStatus.PASS
            message = "Decimal value is valid at configured precision"
            actual: Any = str(normalized)
        except ValueError as exc:
            status = ValidationStatus.FAIL
            message = str(exc)
            actual = value
        results.append(
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-DECIMAL-PRECISION",
                status=status,
                message=message,
                expected=f"Valid Decimal quantized to {scale}",
                actual=actual,
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )

    for field_name in repeated_fields:
        raw_values = resolver.get(record.data, field_name)
        if raw_values is None:
            continue
        values = normalize_collection(raw_values)
        invalid: list[Any] = []
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(quantize_decimal(value, scale=scale)))
            except ValueError:
                invalid.append(value)
        results.append(
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-REPEATED-DECIMAL-PRECISION",
                status=ValidationStatus.PASS if not invalid else ValidationStatus.FAIL,
                message=(
                    "Repeated Decimal values are valid"
                    if not invalid
                    else "Invalid repeated Decimal values"
                ),
                expected=f"Every value quantized to {scale}",
                actual={"normalized": normalized, "invalid": invalid},
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    return results


def validate_procedure_structure(
    record: SourceRecord,
    resolver: FieldResolver,
    window_start,
    window_end,
) -> list[RuleResult]:
    codes = nonblank_values(resolver.get(record.data, "medpar_surg_code_0513"))
    dates = nonblank_values(resolver.get(record.data, "medpar_surg_date_0514"))
    versions = nonblank_values(
        resolver.get(record.data, "medpar_srgcl_prcdr_vrsn_cd")
    )
    actual_code_count = resolver.get(record.data, "medpar_no_surg_codes_0511")
    actual_date_count = resolver.get(record.data, "medpar_no_surg_dates_0512")
    actual_indicator = resolver.get(record.data, "medpar_surg_ind_0500")
    expected_indicator = "Y" if codes else "N"

    def normalized_count(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    actual_code_count = normalized_count(actual_code_count)
    actual_date_count = normalized_count(actual_date_count)

    checks = [
        (
            "INT-PROC-CODE-COUNT",
            "medpar_no_surg_codes_0511",
            len(codes),
            actual_code_count,
        ),
        (
            "INT-PROC-DATE-COUNT",
            "medpar_no_surg_dates_0512",
            len(dates),
            actual_date_count,
        ),
        (
            "INT-PROC-VERSION-ALIGNMENT",
            "medpar_srgcl_prcdr_vrsn_cd",
            len(codes),
            len(versions),
        ),
        (
            "INT-PROC-CODE-DATE-ALIGNMENT",
            "medpar_surg_date_0514",
            len(codes),
            len(dates),
        ),
        (
            "INT-PROC-SURGICAL-INDICATOR",
            "medpar_surg_ind_0500",
            expected_indicator,
            actual_indicator,
        ),
    ]
    results: list[RuleResult] = []
    for rule_id, field_name, expected, actual in checks:
        status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
        results.append(
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id=rule_id,
                status=status,
                message="Procedure field matches" if status == ValidationStatus.PASS else "Procedure field mismatch",
                expected=expected,
                actual=actual,
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )

    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-MAX-25",
            status=ValidationStatus.PASS if len(codes) <= 25 else ValidationStatus.FAIL,
            message=(
                "Procedure group count is within the 25-entry MEDPAR limit"
                if len(codes) <= 25
                else "Procedure group exceeds the 25-entry MEDPAR limit"
            ),
            expected="0..25 populated procedure groups",
            actual=len(codes),
            field_name="medpar_surg_code_0513",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
            evidence={
                "requirement": "Save up to 25 procedure code/version/date groups from the combined Stay, not only the first or last bill"
            },
        )
    )

    invalid_dates: list[Any] = []
    for value in dates:
        try:
            if not in_date_window(value, window_start, window_end):
                invalid_dates.append(value)
        except ValueError:
            invalid_dates.append(value)
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-DATE-WINDOW",
            status=ValidationStatus.PASS if not invalid_dates else ValidationStatus.FAIL,
            message="Procedure dates are valid" if not invalid_dates else "Procedure dates outside the allowed window",
            expected=f"{window_start} through {window_end}",
            actual=invalid_dates,
            field_name="medpar_surg_date_0514",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )
    return results


def validate_diagnosis_structure(
    record: SourceRecord,
    resolver: FieldResolver,
) -> list[RuleResult]:
    diagnoses = nonblank_values(resolver.get(record.data, "medpar_diag_code_0492"))
    versions = nonblank_values(resolver.get(record.data, "medpar_dgns_vrsn_cd"))
    poa = nonblank_values(resolver.get(record.data, "medpar_poa_dgns_ind_cd"))
    def normalized_count(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    checks = [
        (
            "INT-DIAG-COUNT",
            "medpar_no_diag_codes_0491",
            len(diagnoses),
            normalized_count(resolver.get(record.data, "medpar_no_diag_codes_0491")),
        ),
        (
            "INT-DIAG-VERSION-ALIGNMENT",
            "medpar_dgns_vrsn_cd",
            len(diagnoses),
            len(versions),
        ),
        (
            "INT-POA-COUNT",
            "medpar_poa_dgns_cd_cnt",
            len(poa),
            normalized_count(resolver.get(record.data, "medpar_poa_dgns_cd_cnt")),
        ),
        (
            "INT-POA-DIAG-ALIGNMENT",
            "medpar_poa_dgns_ind_cd",
            len(diagnoses),
            len(poa),
        ),
    ]
    results: list[RuleResult] = []
    for rule_id, field_name, expected, actual in checks:
        status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
        results.append(
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id=rule_id,
                status=status,
                message="Diagnosis/POA structure matches" if status == ValidationStatus.PASS else "Diagnosis/POA structure mismatch",
                expected=expected,
                actual=actual,
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    return results


def validate_death_after_admission(
    record: SourceRecord,
    resolver: FieldResolver,
) -> RuleResult:
    admission_raw = resolver.get(record.data, "admission_date")
    death_raw = resolver.get(record.data, "date_of_death")
    actual = resolver.get(record.data, "medpar_death_after_adm_0611")
    try:
        admission = parse_date(admission_raw, allow_none=False)
        death = parse_date(death_raw, allow_none=True)
        expected = "Y" if death is not None and death >= admission else "N"
        status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
        message = "Death-after-admission indicator matches" if status == ValidationStatus.PASS else "Death-after-admission indicator mismatch"
    except ValueError as exc:
        expected = "Valid admission/death dates"
        status = ValidationStatus.FAIL
        message = str(exc)
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id="INT-DEATH-AFTER-ADMISSION",
        status=status,
        message=message,
        expected=expected,
        actual=actual,
        field_name="medpar_death_after_adm_0611",
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )


def validate_age_and_ndc(
    record: SourceRecord,
    resolver: FieldResolver,
    ndc_length: int,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    age = resolver.get(record.data, "medpar_age_0030")
    try:
        normalized_age = int(age)
        age_valid = 0 <= normalized_age <= 120
    except (TypeError, ValueError):
        normalized_age = age
        age_valid = False
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-AGE",
            status=ValidationStatus.PASS if age_valid else ValidationStatus.FAIL,
            message="Age is valid" if age_valid else "Age must be an integer from 0 through 120",
            expected="0..120",
            actual=normalized_age,
            field_name="medpar_age_0030",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )

    ndc = resolver.get(record.data, "medpar_rev_cntr_ndc_num_1550")
    if ndc is None:
        ndc_valid = False
        normalized_ndc = None
    else:
        normalized_ndc = "".join(character for character in str(ndc) if character.isdigit())
        normalized_ndc = normalized_ndc.zfill(ndc_length)
        ndc_valid = len(normalized_ndc) == ndc_length
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-NDC",
            status=ValidationStatus.PASS if ndc_valid else ValidationStatus.FAIL,
            message="NDC format is valid" if ndc_valid else "NDC format is invalid",
            expected=f"{ndc_length} numeric characters",
            actual=normalized_ndc,
            field_name="medpar_rev_cntr_ndc_num_1550",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )
    return results


def validate_accommodation_totals(
    record: SourceRecord,
    resolver: FieldResolver,
    scale: Decimal,
) -> RuleResult:
    raw_charges = nonblank_values(
        resolver.get(record.data, "medpar_accommodation_chrg_0460")
    )
    raw_total = resolver.get(record.data, "medpar_tot_acc_chrg_0430")
    if not raw_charges and raw_total in (None, ""):
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-ACCOMMODATION-TOTAL",
            status=ValidationStatus.NOT_APPLICABLE,
            message="Accommodation charges and total are not populated",
            expected="Round each charge before summing when populated",
            actual=None,
            field_name="medpar_tot_acc_chrg_0430",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        rounded_charges = [quantize_decimal(value, scale=scale) for value in raw_charges]
        expected = quantize_decimal(sum(rounded_charges, Decimal("0")), scale=scale)
        actual = quantize_decimal(raw_total, scale=scale)
        status = ValidationStatus.PASS if expected == actual else ValidationStatus.FAIL
        message = (
            "Each accommodation charge was rounded before summation"
            if status == ValidationStatus.PASS
            else "Total accommodation charge does not equal the sum of individually rounded charges"
        )
    except ValueError as exc:
        rounded_charges = []
        expected = "Valid Decimal accommodation charges and total"
        actual = raw_total
        status = ValidationStatus.FAIL
        message = str(exc)
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id="INT-ACCOMMODATION-TOTAL",
        status=status,
        message=message,
        expected=str(expected),
        actual=str(actual),
        field_name="medpar_tot_acc_chrg_0430",
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
        evidence={
            "raw_charges": [str(value) for value in raw_charges],
            "individually_rounded_charges": [str(value) for value in rounded_charges],
            "formula": "sum(quantize(each accommodation charge, 0.001))",
            "known_discrepancy": "Legacy rounds every accommodation charge before summing; summing raw values first is incorrect",
        },
    )

