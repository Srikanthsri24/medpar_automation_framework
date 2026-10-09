from datetime import date

import pytest

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.intermediate.direct_fields import (
    validate_intermediate_direct_fields,
    validate_repeated_alignment,
)
from medpar_qa.stages.intermediate.structural import (
    validate_death_after_admission,
    validate_diagnosis_structure,
    validate_procedure_structure,
)


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
def test_intermediate_direct_fields_and_january_window_pass(resolver, make_record):
    record = make_record(
        {
            "admissionDate": "20220101",
            "dateOfDeath": "20220102",
            "MEDPAR-ADM-DIAG-CODE-0590": "A001",
            "MEDPAR-ADMTG-DGNS-VRSN-CD": "10",
            "MEDPAR-MBI-ID-1420": "1EG4TE5MK73",
            "MEDPAR-PRVDR-FULL-NUM-1660": "P001",
            "MEDPAR-PRIMRY-PYR-0540": "A",
            "MEDPAR-SNF-QUAL-THRU-DATE-0190": "20220110",
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_intermediate_direct_fields(
        record,
        resolver,
        window_start=date(2022, 1, 1),
        window_end=date(2026, 7, 19),
    )
    assert not [r for r in results if r.status in {ValidationStatus.FAIL, ValidationStatus.BLOCKED}]


@pytest.mark.unit
@pytest.mark.intermediate
def test_intermediate_date_before_january_window_fails(resolver, make_record):
    record = make_record({"admissionDate": "20211231"}, stage=Stage.INTERMEDIATE)
    results = validate_intermediate_direct_fields(
        record,
        resolver,
        window_start=date(2022, 1, 1),
        window_end=date(2026, 7, 19),
    )
    admission_check = next(
        r for r in results
        if r.rule_id == "INT-CALENDAR-ALIGNED-DATE-WINDOW" and r.field_name == "admission_date"
    )
    assert admission_check.status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
def test_accommodation_repeated_arrays_align(resolver, make_record):
    record = make_record(
        {
            "MEDPAR-ACCOMMODATION-CHRG-0460": ["1.000", "2.000"],
            "MEDPAR-ACCOMMODATION-DAYS-0450": [1, 2],
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_repeated_alignment(record, resolver)
    assert all(r.status is ValidationStatus.PASS for r in results)


@pytest.mark.unit
@pytest.mark.intermediate
def test_accommodation_repeated_array_length_mismatch_fails(resolver, make_record):
    record = make_record(
        {
            "MEDPAR-ACCOMMODATION-CHRG-0460": ["1.000", "2.000"],
            "MEDPAR-ACCOMMODATION-DAYS-0450": [1],
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_repeated_alignment(record, resolver)
    assert results[0].status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.intermediate
def test_procedure_code_date_alignment_fails(resolver, make_record):
    record = make_record(
        {
            "MEDPAR-SURG-IND-0500": "Y",
            "MEDPAR-NO-SURG-CODES-0511": 2,
            "MEDPAR-NO-SURG-DATES-0512": 1,
            "MEDPAR-SRGCL-PRCDR-VRSN-CD": ["10", "10"],
            "MEDPAR-SURG-CODE-0513": ["0ABC", "0XYZ"],
            "MEDPAR-SURG-DATE-0514": ["20220101"],
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_procedure_structure(record, resolver, date(2022, 1, 1), date(2026, 7, 19))
    alignment = next(r for r in results if r.rule_id == "INT-PROC-CODE-DATE-ALIGNMENT")
    assert alignment.status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.intermediate
def test_diagnosis_poa_alignment_fails(resolver, make_record):
    record = make_record(
        {
            "MEDPAR-DIAG-CODE-0492": ["A01", "B02"],
            "MEDPAR-DGNS-VRSN-CD": ["10", "10"],
            "MEDPAR-NO-DIAG-CODES-0491": 2,
            "MEDPAR-POA-DGNS-CD-CNT": 1,
            "MEDPAR-POA-DGNS-IND-CD": ["Y"],
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_diagnosis_structure(record, resolver)
    alignment = next(r for r in results if r.rule_id == "INT-POA-DIAG-ALIGNMENT")
    assert alignment.status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
def test_death_after_admission_indicator(resolver, make_record):
    record = make_record(
        {
            "admissionDate": "20260101",
            "dateOfDeath": "20260102",
            "medparDeathAfterAdm0611": "Y",
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_death_after_admission(record, resolver)
    assert result.status is ValidationStatus.PASS
