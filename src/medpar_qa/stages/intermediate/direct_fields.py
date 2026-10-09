from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.field_checks import (
    allowed_value_result,
    optional_date_result,
    pattern_result,
)


def _optional_scalar_result(
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    rule_id: str,
    *,
    max_length: int | None = None,
) -> RuleResult:
    value = resolver.get(record.data, field_name)
    if value is None or value == "":
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id=rule_id,
            status=ValidationStatus.NOT_APPLICABLE,
            message=f"Optional field {field_name} is not populated",
            expected=f"Non-blank value{f' <= {max_length} characters' if max_length else ''}",
            actual=value,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    text = str(value).strip()
    valid = bool(text) and (max_length is None or len(text) <= max_length)
    return RuleResult(
        stage=Stage.INTERMEDIATE,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=f"{field_name} format is valid" if valid else f"{field_name} exceeds configured length",
        expected=f"Non-blank value{f' <= {max_length} characters' if max_length else ''}",
        actual=text,
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )


def validate_intermediate_direct_fields(
    record: SourceRecord,
    resolver: FieldResolver,
    *,
    window_start: date,
    window_end: date,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    results.extend(
        [
            _optional_scalar_result(record, resolver, "medpar_adm_diag_code_0590", "INT-ADM-DIAG-CODE", max_length=10),
            _optional_scalar_result(record, resolver, "medpar_admtg_dgns_vrsn_cd", "INT-ADM-DIAG-VERSION", max_length=2),
            _optional_scalar_result(record, resolver, "medpar_mbi_id_1420", "INT-MBI", max_length=11),
            _optional_scalar_result(record, resolver, "medpar_prvdr_full_num_1660", "INT-PROVIDER-FULL-NUM", max_length=20),
            _optional_scalar_result(record, resolver, "medpar_primry_pyr_0540", "INT-PRIMARY-PAYER", max_length=10),
            _optional_scalar_result(record, resolver, "medpar_drg_code", "INT-DRG-CODE", max_length=8),
            _optional_scalar_result(record, resolver, "medpar_nch_clm_type_cd", "INT-CLAIM-TYPE-DIRECT-MOVE", max_length=4),
            _optional_scalar_result(record, resolver, "medpar_race_0050", "INT-RACE-DIRECT-MOVE", max_length=4),
            _optional_scalar_result(record, resolver, "medpar_dischg_status_0100", "INT-DISCHARGE-STATUS-DIRECT-MOVE", max_length=4),
            _optional_scalar_result(record, resolver, "medpar_bene_st_0071", "INT-BENE-STATE-DIRECT-MOVE", max_length=4),
            _optional_scalar_result(record, resolver, "medpar_zip_0080", "INT-ZIP-DIRECT-MOVE", max_length=12),
        ]
    )
    results.append(
        optional_date_result(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-SNF-QUAL-THRU-DATE",
            record=record,
            resolver=resolver,
            field_name="medpar_snf_qual_thru_date_0190",
            window_start=window_start,
            window_end=window_end,
        )
    )
    # Apply the calendar-aligned five-year window to every populated business date.
    for field_name in (
        "admission_date",
        "discharge_date",
        "date_of_death",
        "medpar_snf_qual_from_date_0180",
        "medpar_snf_qual_thru_date_0190",
        "medpar_hosp_home_from_dt_1630",
        "medpar_hosp_home_thru_dt_1640",
        "medpar_dte_cr_ended_0220",
    ):
        results.append(
            optional_date_result(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-CALENDAR-ALIGNED-DATE-WINDOW",
                record=record,
                resolver=resolver,
                field_name=field_name,
                window_start=window_start,
                window_end=window_end,
            )
        )
    return results


def validate_repeated_alignment(
    record: SourceRecord,
    resolver: FieldResolver,
) -> list[RuleResult]:
    charges = resolver.get(record.data, "medpar_accommodation_chrg_0460")
    days = resolver.get(record.data, "medpar_accommodation_days_0450")
    charge_values = charges if isinstance(charges, list) else ([] if charges is None else [charges])
    day_values = days if isinstance(days, list) else ([] if days is None else [days])
    if not charge_values and not day_values:
        return [
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id="INT-ACCOMMODATION-ARRAY-ALIGNMENT",
                status=ValidationStatus.NOT_APPLICABLE,
                message="Accommodation repeated fields are not populated",
                expected="Aligned charge/day arrays",
                actual={"charges": len(charge_values), "days": len(day_values)},
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        ]
    valid = len(charge_values) == len(day_values)
    invalid_days: list[Any] = []
    for value in day_values:
        try:
            if int(value) < 0:
                invalid_days.append(value)
        except (TypeError, ValueError):
            invalid_days.append(value)
    return [
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-ACCOMMODATION-ARRAY-ALIGNMENT",
            status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
            message="Accommodation charges and days align" if valid else "Accommodation charge/day array lengths differ",
            expected=len(charge_values),
            actual=len(day_values),
            field_name="medpar_accommodation_days_0450",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        ),
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-ACCOMMODATION-DAYS",
            status=ValidationStatus.PASS if not invalid_days else ValidationStatus.FAIL,
            message="Accommodation days are valid" if not invalid_days else "Accommodation days contain invalid values",
            expected="Non-negative integers",
            actual=invalid_days,
            field_name="medpar_accommodation_days_0450",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        ),
    ]
