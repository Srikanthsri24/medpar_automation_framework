"""Regression tests and local fixtures for 2026 discrepancy updates. Tests describe controlled
examples; passing them does not certify all production files.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.stages.common import ld3137_sort_order_result, record_identity
from medpar_qa.stages.final_action.grouping import group_records
from medpar_qa.stages.final_action.settings import FinalActionSettings
from medpar_qa.stages.final_medpar.settings import FinalMedparSettings
from medpar_qa.stages.intermediate.legacy_discrepancies import (
    validate_admission_day,
    validate_bill_total_perdiem,
    validate_revenue_indicator,
)
from medpar_qa.stages.intermediate.settings import IntermediateSettings
from medpar_qa.stages.intermediate.structural import (
    validate_accommodation_totals,
    validate_procedure_structure,
)
from medpar_qa.stages.split.settings import SplitSettings
from medpar_qa.stages.stay.processor import StayProcessor
from medpar_qa.stages.stay.settings import StaySettings


def _fa_claim(*, admission: str, row: int) -> dict:
    """Test helper for fa claim. It constructs or summarizes controlled fixture data for the
    assertions in this file.
    """
    return {
        "claimCan": f"C-{row}",
        "claimCanNchEquatable": "H-1",
        "provider": {"providerId": "P-1"},
        "admissionDate": admission,
        "stayFromDate": "20260101",
        "stayThruDate": "20260105",
        "transactionCode": 1,
        "queryCode": 3,
        "internalControlNumber": f"ICN-{row}",
        "nchWeeklyProcessingDate": f"2026010{row}",
        "accreteDate": f"2026010{row}",
        "sourceSequence": row,
        "actionCode": "1",
    }


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.byte_by_byte
def test_total_accommodation_rounds_each_charge_before_sum(resolver, make_record):
    """Verify total accommodation rounds each charge before sum. The assertions below state exactly
    what this test proves for its fixtures.
    """
    record = make_record(
        {
            "MEDPAR-ACCOMMODATION-CHRG-0460": ["1.2345", "1.2345"],
            "MEDPAR-TOT-ACC-CHRG-0430": "2.470",
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_accommodation_totals(record, resolver, Decimal("0.001"))

    assert result.status is ValidationStatus.PASS
    assert result.expected == "2.470"
    assert result.evidence["individually_rounded_charges"] == ["1.235", "1.235"]
    assert Decimal("1.2345") + Decimal("1.2345") == Decimal("2.4690")


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.byte_by_byte
def test_total_accommodation_detects_sum_before_rounding_defect(resolver, make_record):
    """Verify total accommodation detects sum before rounding defect. The assertions below state
    exactly what this test proves for its fixtures.
    """
    record = make_record(
        {
            "MEDPAR-ACCOMMODATION-CHRG-0460": ["1.2345", "1.2345"],
            "MEDPAR-TOT-ACC-CHRG-0430": "2.469",
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_accommodation_totals(record, resolver, Decimal("0.001"))

    assert result.status is ValidationStatus.FAIL
    assert result.expected == "2.470"
    assert result.actual == "2.469"


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.byte_by_byte
def test_bill_total_perdiem_rounds_before_multiplication(resolver, make_record):
    """Verify bill total perdiem rounds before multiplication. The assertions below state exactly
    what this test proves for its fixtures.
    """
    record = make_record(
        {
            "passThruPerDiem": "1.2345",
            "utilizationDays": 2,
            "MEDPAR-BILL-TOT-PERDIEM-0381": "2",
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_bill_total_perdiem(record, resolver, scale=Decimal("0.001"))

    assert result.status is ValidationStatus.PASS
    assert result.expected == "2"
    assert result.evidence["rounded_pass_thru_per_diem"] == "1"


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.parametrize("revenue_code", ["0200", "0201"])
def test_intensive_care_indicator_includes_0200_and_0201(
    resolver, make_record, revenue_code
):
    """Verify intensive care indicator includes 0200 and 0201. The assertions below state exactly
    what this test proves for its fixtures.
    """
    record = make_record(
        {
            "revenueLines": [{"revCntrCd": revenue_code, "totalAmount": 100}],
            "MEDPAR-INTENSIVE-CARE-IND-0481": revenue_code[-1],
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_revenue_indicator(
        record,
        resolver,
        field_name="medpar_intensive_care_ind_0481",
        rule_id="INT-INTENSIVE-CARE-IND-0481",
        search_codes=IntermediateSettings().intensive_care_revenue_codes,
    )

    assert result.status is ValidationStatus.PASS
    assert revenue_code in result.evidence["matched_codes"]


@pytest.mark.unit
@pytest.mark.intermediate
def test_organ_indicator_uses_configured_legacy_revenue_codes(resolver, make_record):
    """Verify organ indicator uses configured legacy revenue codes. The assertions below state
    exactly what this test proves for its fixtures.
    """
    record = make_record(
        {
            "revenueLines": [{"REV-CNTR-CD": "0810"}],
            "MEDPAR-ORGAN-IND-0487": "K1",
        },
        stage=Stage.INTERMEDIATE,
    )
    result = validate_revenue_indicator(
        record,
        resolver,
        field_name="medpar_organ_ind_0487",
        rule_id="INT-ORGAN-IND-0487",
        search_codes=IntermediateSettings().organ_revenue_codes,
    )

    assert result.status is ValidationStatus.PASS
    assert result.evidence["matched_codes"] == ["0810"]


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.parametrize(
    "admission,expected",
    [
        ("20260802", 1),  # Sunday
        ("20260803", 2),  # Monday
        ("20260808", 7),  # Saturday
    ],
)
def test_admission_day_0090_is_derived_from_admission_date(
    resolver, make_record, admission, expected
):
    """Verify admission day 0090 is derived from admission date. The assertions below state exactly
    what this test proves for its fixtures.
    """
    record = make_record(
        {"admissionDate": admission, "medparAdmDay0090": expected},
        stage=Stage.INTERMEDIATE,
    )
    result = validate_admission_day(record, resolver)

    assert result.status is ValidationStatus.PASS
    assert result.expected == expected


@pytest.mark.unit
@pytest.mark.intermediate
def test_procedure_groups_cannot_exceed_25(resolver, make_record):
    """Verify procedure groups cannot exceed 25. The assertions below state exactly what this test
    proves for its fixtures.
    """
    codes = [f"P{i:02d}" for i in range(26)]
    dates = ["20260101"] * 26
    versions = ["10"] * 26
    record = make_record(
        {
            "MEDPAR-SURG-IND-0500": "Y",
            "MEDPAR-NO-SURG-CODES-0511": 26,
            "MEDPAR-NO-SURG-DATES-0512": 26,
            "MEDPAR-SRGCL-PRCDR-VRSN-CD": versions,
            "MEDPAR-SURG-CODE-0513": codes,
            "MEDPAR-SURG-DATE-0514": dates,
        },
        stage=Stage.INTERMEDIATE,
    )
    results = validate_procedure_structure(
        record, resolver, date(2022, 1, 1), date(2026, 8, 1)
    )
    max_check = next(item for item in results if item.rule_id == "INT-PROC-MAX-25")

    assert max_check.status is ValidationStatus.FAIL
    assert max_check.actual == 26


@pytest.mark.unit
@pytest.mark.stay
def test_stay_span_code_consolidation_is_limited_to_10(resolver, make_record):
    """Verify stay span code consolidation is limited to 10. The assertions below state exactly
    what this test proves for its fixtures.
    """
    spans = [
        {"spanCode": f"{index:02d}", "fromDate": "20260101", "thruDate": "20260102"}
        for index in range(12)
    ]
    source = make_record(
        {
            "claimCanNchEquatable": "H-1",
            "provider": {"providerId": "P-1"},
            "splitYearIndicator": "Y60109",
            "stayFromDate": "20260101",
            "stayThruDate": "20260102",
            "nchWeeklyProcessingDate": "20260103",
            "accreteDate": "20260103",
            "occurrenceSpanLines": spans,
        },
        stage=Stage.STAY,
    )
    results = StayProcessor(resolver)._validate_latest_code_collections([source], None)
    limit = next(item for item in results if item.rule_id == "ST-SPAN-CODE-LIMIT")

    assert limit.status is ValidationStatus.PASS
    assert limit.actual == {"unique_source_codes": 12, "selected_output_count": 10}


@pytest.mark.unit
@pytest.mark.regression
def test_ld3137_excludes_admission_date_from_four_affected_stage_sort_orders():
    """Verify ld3137 excludes admission date from four affected stage sort orders. The assertions
    below state exactly what this test proves for its fixtures.
    """
    stage_settings = (
        (Stage.FINAL_ACTION, FinalActionSettings().sort_fields),
        (Stage.SPLIT, SplitSettings().sort_fields),
        (Stage.STAY, StaySettings().sort_fields),
        (Stage.FINAL_MEDPAR, FinalMedparSettings().sort_fields),
    )
    for stage, sort_fields in stage_settings:
        result = ld3137_sort_order_result(
            stage=stage,
            rule_id=f"{stage.value}-LD3137",
            sort_fields=sort_fields,
        )
        assert result.status is ValidationStatus.PASS
        assert "admission_date" not in sort_fields


@pytest.mark.unit
@pytest.mark.final_action
def test_final_action_groups_claims_contiguously_when_only_admission_dates_differ(
    resolver, make_record
):
    """Verify final action groups claims contiguously when only admission dates differ. The
    assertions below state exactly what this test proves for its fixtures.
    """
    records = [
        make_record(_fa_claim(admission="20251231", row=1), row=1),
        make_record(_fa_claim(admission="20260101", row=2), row=2),
    ]
    grouped = group_records(records, resolver)

    assert len(grouped) == 1
    assert len(next(iter(grouped.values()))) == 2


@pytest.mark.unit
@pytest.mark.regression
def test_stay_and_final_identities_preserve_admission_date(resolver, make_record):
    """Verify stay and final identities preserve admission date. The assertions below state exactly
    what this test proves for its fixtures.
    """
    base = {
        "claimCanNchEquatable": "H-1",
        "provider": {"providerId": "P-1"},
        "splitYearIndicator": "Y60109",
    }
    first = make_record({**base, "admissionDate": "20260101"}, row=1, stage=Stage.STAY)
    second = make_record({**base, "admissionDate": "20260102"}, row=2, stage=Stage.STAY)

    assert record_identity(first, resolver, StaySettings().identity_fields) != record_identity(
        second, resolver, StaySettings().identity_fields
    )
    assert record_identity(first, resolver, FinalMedparSettings().identity_fields) != record_identity(
        second, resolver, FinalMedparSettings().identity_fields
    )


@pytest.mark.unit
@pytest.mark.regression
def test_missing_field_registry_contains_reported_numbered_and_line_item_fields():
    """Verify missing field registry contains reported numbered and line item fields. The
    assertions below state exactly what this test proves for its fixtures.
    """
    aliases = yaml.safe_load(Path("config/field_aliases.yaml").read_text())
    required_canonical_fields = {
        "medpar_bic_code_0022",
        "medpar_val_q1_pmt_rdctn_amt_1470",
        "medpar_ssi_data_0252",
        "medpar_himaster_dod_0230",
        "medpar_dod_ind_0240",
        "medpar_provider_0130",
        "medpar_hosp_home_from_dt_1630",
        "medpar_hosp_home_thru_dt_1640",
        "medpar_2_midnight_stay_ind_1280",
        "medpar_dgns_e_cd",
        "medpar_dgns_e_vrsn_cd",
        "medpar_poa_dgns_e_ind_cd",
        "hac_reduction_indicator_switch",
        "hrr_adjustment_percent",
        "vbp_adjustment_percent",
        "bundled_m1_percent",
        "care_improvement_model",
        "low_volume_payment_amount",
        "investigational_device_exemption",
        "cancel_only_adjustment_code",
        "beneficiary_date_of_birth",
        "beneficiary_gender",
        "beneficiary_race",
        "beneficiary_zip_code",
        "benefits_exhausted_date",
        "county_code",
        "state_code",
        "fiscal_intermediary",
        "medicare_status",
        "medical_record",
        "host_site",
        "forwarded_date",
        "hcfa_received",
        "patient_first_initial",
        "patient_surname",
        "patient_relationship",
        "pro_approval",
        "rev_cntr_cd",
        "rev_cntr_ide_ndc_upc_num",
        "rev_cntr_tot_chrg_amt",
        "rev_cntr_unit_cnt",
        "rev_cntr_ncvr_chrg_amt",
        "rev_cntr_ptnt_add_on_pmt_amt",
        "rev_cntr_rp_ind_cd",
        "rev_cntr_model_reimbrsmt_amt",
    }

    assert not (required_canonical_fields - set(aliases))


@pytest.mark.unit
@pytest.mark.intermediate
def test_known_typographical_field_aliases_are_resolved(resolver):
    """Verify known typographical field aliases are resolved. The assertions below state exactly
    what this test proves for its fixtures.
    """
    data = {
        "MEDPAR-TOT-ACC-CHRG-043": "10.000",
        "MEDPAR-SQSTRTN-RDCTN-AMT-113": "2.000",
        "MEDPAR-INTERSIVE-CARE-IND-0481": "Y",
    }

    assert resolver.get(data, "medpar_tot_acc_chrg_0430") == "10.000"
    assert resolver.get(data, "medpar_sqstrtn_rdctn_amt_1130") == "2.000"
    assert resolver.get(data, "medpar_intensive_care_ind_0481") == "Y"

@pytest.mark.unit
@pytest.mark.regression
def test_golden_comparison_does_not_false_pass_when_both_values_are_missing(
    resolver, make_record
):
    """Verify golden comparison does not false pass when both values are missing. The assertions
    below state exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.comparison import compare_expected_actual_fields

    expected = make_record({}, row=1, stage=Stage.FINAL_MEDPAR, role=FileRole.EXPECTED_OUTPUT)
    actual = make_record({}, row=2, stage=Stage.FINAL_MEDPAR, role=FileRole.ACTUAL_OUTPUT)
    result = compare_expected_actual_fields(
        stage=Stage.FINAL_MEDPAR,
        expected_record=expected,
        actual_record=actual,
        resolver=resolver,
        fields=["medpar_organ_ind_0487"],
        rule_prefix="FM-REGRESSION",
    )[0]

    assert result.status is ValidationStatus.NOT_APPLICABLE
    assert result.evidence["coverage_status"] == "NOT_TESTED_NO_EXPECTED_VALUE"

@pytest.mark.unit
@pytest.mark.final_medpar
def test_final_required_selected_field_can_be_enforced(resolver, make_record):
    """Verify final required selected field can be enforced. The assertions below state exactly
    what this test proves for its fixtures.
    """
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor

    settings = FinalMedparSettings(
        selected_fields=("medpar_organ_ind_0487",),
        required_selected_fields=("medpar_organ_ind_0487",),
        allowed_classifications=("SS", "LS", "SNF"),
    )
    record = make_record(
        {
            "claimCanNchEquatable": "H1",
            "provider": {"providerId": "P1"},
            "splitYearIndicator": "Y60109",
            "MEDPAR-SS-LS-SNF-IND-0140": "SS",
        },
        stage=Stage.FINAL_MEDPAR,
    )
    result = FinalMedparProcessor(resolver, settings)._validate_record(record)
    presence = next(item for item in result if item.field_name == "medpar_organ_ind_0487")

    assert presence.status is ValidationStatus.FAIL
