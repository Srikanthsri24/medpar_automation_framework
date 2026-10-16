"""Validate Intermediate dates/windows, repeated amounts, procedure/diagnosis structure, DOD day
count, age/NDC and accommodation totals.
"""
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
    """Validate populated scalar and repeated Intermediate amounts with finite Decimal precision
    checks.
    """
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
    """Check procedure repeated collection shapes, counts and aligned dates/versions."""
    codes = nonblank_values(resolver.get(record.data, "medpar_surg_code_0513"))
    dates = nonblank_values(resolver.get(record.data, "medpar_surg_date_0514"))
    versions = nonblank_values(
        resolver.get(record.data, "medpar_srgcl_prcdr_vrsn_cd")
    )
    actual_code_count = resolver.get(record.data, "medpar_no_surg_codes_0511")
    actual_date_count = resolver.get(record.data, "medpar_no_surg_dates_0512")
    actual_indicator = resolver.get(record.data, "medpar_surg_ind_0500")
    # CMS CR14 p142 procedure switch is 1/0, not Y/N.
    expected_indicator = "1" if codes else "0"
    actual_indicator = str(actual_indicator).strip() if actual_indicator is not None else None

    def normalized_count(value):
        """Convert a declared repeated-field count to a comparable integer while honoring this
        validator missing-value policy.
        """
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
    """Check diagnosis and POA arrays for matching occurrence counts and valid structure."""
    diagnoses = nonblank_values(resolver.get(record.data, "medpar_diag_code_0492"))
    versions = nonblank_values(resolver.get(record.data, "medpar_dgns_vrsn_cd"))
    poa = nonblank_values(resolver.get(record.data, "medpar_poa_dgns_ind_cd"))
    def normalized_count(value):
        """Convert a declared repeated-field count to a comparable integer while honoring this
        validator missing-value policy.
        """
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
    """Validate the output death-day count against available dates, without replacing the
    independent source DOD checks.
    """
    admission_raw = resolver.get(record.data, "admission_date")
    death_raw = resolver.get(record.data, "date_of_death")
    actual = resolver.get(record.data, "medpar_death_after_adm_0611")
    try:
        admission = parse_date(admission_raw, allow_none=False)
        death = parse_date(death_raw, allow_none=True)
        from .business_rules import death_after_admission
        expected = death_after_admission(admission, death)
        normalized = None if actual in (None, "") else int(actual)
        status = ValidationStatus.PASS if normalized == expected else ValidationStatus.FAIL
        message = "Death-after-admission day count matches" if status == ValidationStatus.PASS else "Death-after-admission day count mismatch"
        if death is None and normalized in (None, 0):
            status = ValidationStatus.NOT_APPLICABLE
            message = "No populated death date; day-count calculation requires matched DOD reference"
    except (TypeError, ValueError) as exc:
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
    """Check populated age and NDC fields, including independent numeric NDC content/width and
    occurrence limits.
    """
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
        values = ndc if isinstance(ndc, list) else [ndc]
        normalized_values = [str(value).strip() for value in values]
        ndc_valid = bool(values) and len(values) <= 10 and all(value.isdigit() and len(value) == ndc_length for value in normalized_values)
        normalized_ndc = normalized_values if isinstance(ndc, list) else normalized_values[0]
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
    """Reconcile repeated accommodation amount groups with the configured total and rounding
    behavior.
    """
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
        expected = min(quantize_decimal(sum(rounded_charges, Decimal("0")), scale=scale), Decimal("999999999"))
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



def validate_warning_summary(record, resolver):
    """0640 concatenates warning 01..17; negative 0611 requires death warning 08."""
    results = []
    days = resolver.get(record.data, 'medpar_death_after_adm_0611')
    wi08 = resolver.get(record.data, 'warning_indicator_08')
    try:
        negative = days not in (None, '') and int(days) < 0
    except (ValueError, TypeError):
        negative = False  # The independent numeric rule reports malformed day counts.
    if negative:
        valid = str(wi08) in ('2', '3')
        results.append(RuleResult(Stage.INTERMEDIATE, 'INT-DEATH-WARNING-08',
            ValidationStatus.PASS if valid else ValidationStatus.FAIL,
            'Negative 0611 requires death-before-admission warning 08 = 2 or 3',
            expected=['2', '3'], actual=wi08, record_ids=[record.record_id],
            source_files=[record.source.file_path]))
    observed = resolver.get(record.data, 'medpar_warning_ind_0640')
    if observed not in (None, ''):
        flags = [resolver.get(record.data, f'warning_indicator_{n:02}') for n in range(1, 18)]
        complete = all(value is not None and len(str(value)) == 1 for value in flags)
        expected = ''.join(str(value) for value in flags) if complete else 'All 17 one-character warning operands'
        results.append(RuleResult(Stage.INTERMEDIATE, 'INT-WARNING-SUMMARY-0640',
            ValidationStatus.PASS if complete and observed == expected else ValidationStatus.FAIL if complete else ValidationStatus.BLOCKED,
            '0640 must equal warning indicators 01 through 17 in order',
            expected=expected, actual=observed, record_ids=[record.record_id],
            source_files=[record.source.file_path]))
    return results
