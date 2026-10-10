from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import quantize_decimal, to_decimal
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.common import normalize_collection
from medpar_qa.stages.comparison import compare_values


def _line_code(line: Any) -> str | None:
    if isinstance(line, dict):
        for key in ("code", "revenueCode", "revCntrCd", "REV-CNTR-CD"):
            value = line.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().zfill(4)
        return None
    if line is None or not str(line).strip():
        return None
    return str(line).strip().zfill(4)


def _source_trace(record: SourceRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "source_file": record.source.file_path,
        "source_row": record.source.row_number,
    }


def validate_bill_total_perdiem(
    record: SourceRecord,
    resolver: FieldResolver,
    *,
    scale: Decimal,
) -> RuleResult:
    """Validate legacy rounding order for MEDPAR-BILL-TOT-PERDIEM-0381.

    Legacy/MM rule: round passThruPerDiem first, then multiply by utilization days.
    Rounding only after multiplication is a known byte-by-byte discrepancy.
    """
    raw_per_diem = resolver.get(record.data, "pass_thru_per_diem")
    raw_days = resolver.get(record.data, "utilization_days")
    raw_actual = resolver.get(record.data, "medpar_bill_tot_perdiem_0381")
    if raw_per_diem in (None, "") or raw_days in (None, "") or raw_actual in (None, ""):
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-BILL-TOT-PERDIEM-ROUNDING",
            status=ValidationStatus.NOT_APPLICABLE,
            message=(
                "Per-diem rounding validation requires passThruPerDiem, utilizationDays, "
                "and MEDPAR-BILL-TOT-PERDIEM-0381"
            ),
            expected="All three fields populated",
            actual={
                "pass_thru_per_diem": raw_per_diem,
                "utilization_days": raw_days,
                "medpar_bill_tot_perdiem_0381": raw_actual,
            },
            field_name="medpar_bill_tot_perdiem_0381",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        from .business_rules import whole_dollars
        rounded_per_diem = quantize_decimal(raw_per_diem, scale=Decimal("1"))
        days_decimal = to_decimal(raw_days)
        days = int(days_decimal)
        if days < 0 or days_decimal != Decimal(days):
            raise ValueError("utilizationDays must be a non-negative integer")
        expected = whole_dollars(rounded_per_diem * Decimal(days))
        actual = to_decimal(raw_actual)
    except (TypeError, ValueError) as exc:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-BILL-TOT-PERDIEM-ROUNDING",
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected="round(passThruPerDiem) * utilizationDays",
            actual={
                "pass_thru_per_diem": raw_per_diem,
                "utilization_days": raw_days,
                "medpar_bill_tot_perdiem_0381": raw_actual,
            },
            field_name="medpar_bill_tot_perdiem_0381",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    valid = expected == actual
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id="INT-BILL-TOT-PERDIEM-ROUNDING",
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=(
            "Pass-through per diem was rounded before multiplication"
            if valid
            else "Per-diem total does not match round-per-diem-before-multiplication logic"
        ),
        expected=str(expected),
        actual=str(actual),
        field_name="medpar_bill_tot_perdiem_0381",
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
        evidence={
            "raw_pass_thru_per_diem": str(raw_per_diem),
            "rounded_pass_thru_per_diem": str(rounded_per_diem),
            "utilization_days": days,
            "formula": "quantize(passThruPerDiem, 0.001) * utilizationDays",
        },
    )


def validate_revenue_indicator(
    record: SourceRecord,
    resolver: FieldResolver,
    *,
    field_name: str,
    rule_id: str,
    search_codes: Iterable[str],
    positive_value: str = "Y",
    negative_value: str = "N",
) -> RuleResult:
    configured = tuple(sorted({str(code).strip().zfill(4) for code in search_codes if str(code).strip()}))
    actual = resolver.get(record.data, field_name)
    lines = normalize_collection(resolver.get(record.data, "revenue_lines"))
    source_codes = [code for code in (_line_code(line) for line in lines) if code]
    if not configured:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id=rule_id,
            status=ValidationStatus.BLOCKED,
            message=f"Approved revenue-code list for {field_name} is not configured",
            expected="Business-approved legacy revenue-code list",
            actual={"field_value": actual, "revenue_codes": source_codes},
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    if actual in (None, "") and not lines:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id=rule_id,
            status=ValidationStatus.NOT_APPLICABLE,
            message=f"{field_name} and revenue-center lines are not populated",
            expected=f"{positive_value} when any configured code exists, otherwise {negative_value}",
            actual=actual,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
            evidence={"configured_search_codes": list(configured)},
        )
    matched = sorted(set(source_codes) & set(configured))
    expected = positive_value if matched else negative_value
    normalized_actual = None if actual is None else str(actual).strip().upper()
    valid = normalized_actual == expected
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=(
            f"{field_name} matches revenue-code derivation"
            if valid
            else f"{field_name} does not match revenue-code derivation"
        ),
        expected=expected,
        actual=normalized_actual,
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
        evidence={
            "configured_search_codes": list(configured),
            "source_revenue_codes": source_codes,
            "matched_codes": matched,
        },
    )


def admission_day_code(admission: date) -> int:
    """Legacy-compatible day code: Sunday=1, Monday=2, ... Saturday=7."""
    return ((admission.weekday() + 1) % 7) + 1


def validate_admission_day(record: SourceRecord, resolver: FieldResolver) -> RuleResult:
    raw_admission = resolver.get(record.data, "admission_date")
    raw_actual = resolver.get(record.data, "medpar_adm_day_0090")
    if raw_admission in (None, "") and raw_actual in (None, ""):
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-ADMISSION-DAY-0090",
            status=ValidationStatus.NOT_APPLICABLE,
            message="Admission date and medparAdmDay0090 are not populated",
            expected="Day code derived from admissionDate",
            actual=None,
            field_name="medpar_adm_day_0090",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        admission = parse_date(raw_admission, allow_none=False)
        expected = admission_day_code(admission)
        if raw_actual in (None, ""):
            return RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-ADMISSION-DAY-0090",
                status=ValidationStatus.NOT_APPLICABLE,
                message="Admission day was calculated, but medparAdmDay0090 is not populated in this execution mode",
                expected=expected,
                actual=raw_actual,
                field_name="medpar_adm_day_0090",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
                evidence={"admission_date": admission.isoformat(), "mapping": "Sunday=1 through Saturday=7"},
            )
        actual = int(raw_actual)
    except (TypeError, ValueError) as exc:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-ADMISSION-DAY-0090",
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected="Integer 1..7 derived from admissionDate (Sunday=1)",
            actual=raw_actual,
            field_name="medpar_adm_day_0090",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    valid = expected == actual
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id="INT-ADMISSION-DAY-0090",
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message="Admission day code matches admission date" if valid else "Admission day code mismatch",
        expected=expected,
        actual=actual,
        field_name="medpar_adm_day_0090",
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
        evidence={
            "admission_date": admission.isoformat(),
            "mapping": "Sunday=1, Monday=2, Tuesday=3, Wednesday=4, Thursday=5, Friday=6, Saturday=7",
        },
    )


def validate_condition_switches(
    record: SourceRecord,
    resolver: FieldResolver,
    mappings: Mapping[str, tuple[str, ...]],
) -> list[RuleResult]:
    lines = normalize_collection(resolver.get(record.data, "condition_codes"))
    codes: set[str] = set()
    for line in lines:
        if isinstance(line, dict):
            value = line.get("code", line.get("conditionCode"))
        else:
            value = line
        if value is not None and str(value).strip():
            codes.add(str(value).strip().upper())
    results: list[RuleResult] = []
    for field_name, mapped_codes in mappings.items():
        actual = resolver.get(record.data, field_name)
        if actual in (None, "") and not lines:
            results.append(
                RuleResult(
                    stage=Stage.INTERMEDIATE,
                    rule_id="INT-CONDITION-SWITCH",
                    status=ValidationStatus.NOT_APPLICABLE,
                    message=f"{field_name} and condition codes are not populated",
                    expected="Y/N derived from configured condition codes",
                    actual=actual,
                    field_name=field_name,
                    record_ids=[record.record_id],
                    source_files=[record.source.file_path],
                )
            )
            continue
        expected = "Y" if codes & {str(code).upper() for code in mapped_codes} else "N"
        normalized_actual = None if actual is None else str(actual).strip().upper()
        results.append(
            compare_values(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-CONDITION-SWITCH",
                field_name=field_name,
                expected=expected,
                actual=normalized_actual,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
        results[-1].evidence.update(
            {
                "configured_condition_codes": list(mapped_codes),
                "source_condition_codes": sorted(codes),
            }
        )
    return results


def validate_revenue_line_items(record: SourceRecord, resolver: FieldResolver, *, scale: Decimal) -> list[RuleResult]:
    lines = normalize_collection(resolver.get(record.data, "revenue_lines"))
    if not lines:
        return [
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-REVENUE-LINE-ITEMS",
                status=ValidationStatus.NOT_APPLICABLE,
                message="Revenue-center lines are not populated",
                expected="Field-level validation when revenue lines are present",
                actual=0,
                field_name="revenue_lines",
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        ]
    invalid: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    amount_keys = (
        "revCntrTotChrgAmt", "REV-CNTR-TOT-CHRG-AMT", "totalCharge", "charge",
        "revCntrNcvrChrgAmt", "REV-CNTR-NCVR-CHRG-AMT", "nonCoveredCharge",
        "revCntrPtntAddOnPmtAmt", "REV-CNTR-PTNT-ADD-ON-PMT-AMT",
        "revCntrModelReimbrsmtAmt", "REV-CNTR-MODEL-REIMBRSMT-AMT",
    )
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            invalid.append({"index": index, "reason": "line is not an object", "value": line})
            continue
        code = _line_code(line)
        if not code:
            invalid.append({"index": index, "reason": "missing revenue code", "value": line})
            continue
        if not code.isdigit() or not (1 <= int(code) <= 999 or 9000 <= int(code) <= 9044):
            invalid.append({"index": index, "reason": "revenue code outside 0001..0999 or RUG 9000..9044", "value": code})
        units = next((line.get(key) for key in ("revCntrUnitCnt", "REV-CNTR-UNIT-CNT", "units", "unitCount") if line.get(key) is not None), None)
        if units not in (None, ""):
            try:
                if int(units) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                invalid.append({"index": index, "reason": "invalid unit count", "value": units})
        amounts: dict[str, str] = {}
        for key in amount_keys:
            if key in line and line[key] not in (None, ""):
                try:
                    amounts[key] = str(quantize_decimal(line[key], scale=scale))
                except ValueError:
                    invalid.append({"index": index, "reason": f"invalid amount {key}", "value": line[key]})
        normalized.append({"index": index, "code": code, "units": units, "amounts": amounts})
    return [
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-REVENUE-LINE-ITEMS",
            status=ValidationStatus.PASS if not invalid else ValidationStatus.FAIL,
            message="Revenue-center line sub-fields are valid" if not invalid else "Revenue-center line sub-field errors found",
            expected="Every line has a revenue code; units are non-negative integers; amounts are valid Decimals",
            actual={"line_count": len(lines), "invalid": invalid},
            field_name="revenue_lines",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
            evidence={"normalized_lines": normalized},
        )
    ]


def validate_source_to_actual_direct_moves(
    source: SourceRecord,
    actual: SourceRecord,
    resolver: FieldResolver,
    fields: Iterable[str],
    *,
    decimal_fields: set[str],
    scale: Decimal,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    for field_name in fields:
        expected = resolver.get(source.data, field_name)
        if expected is None:
            continue
        if field_name in decimal_fields:
            from .business_rules import whole_dollars
            try:
                expected = whole_dollars(expected)
            except ValueError:
                pass  # compare_values reports the malformed amount.
        observed = resolver.get(actual.data, field_name)
        results.append(
            compare_values(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-SOURCE-TO-TARGET",
                field_name=field_name,
                expected=expected,
                actual=observed,
                record_ids=[source.record_id, actual.record_id],
                source_files=[source.source.file_path, actual.source.file_path],
                decimal_scale=scale if field_name in decimal_fields else None,
            )
        )
        results[-1].evidence.update(
            {
                "source_record": _source_trace(source),
                "actual_record": _source_trace(actual),
                "transfer_rule": "Value must be preserved or populated into Intermediate output when present in source",
            }
        )
    return results
