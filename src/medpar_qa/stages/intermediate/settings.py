from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class IntermediateSettings:
    identity_fields: tuple[str, ...] = (
        "hicn",
        "provider_id",
        "admission_date",
        "split_year_indicator",
    )
    decimal_scale: Decimal = Decimal("0.001")
    window_years: int = 5
    require_actual_output: bool = False
    require_expected_output: bool = False
    ndc_length: int = 10
    # Full 020X intensive-care revenue-code family. The newly reported missing
    # codes 0200 and 0201 are therefore always included.
    intensive_care_revenue_codes: tuple[str, ...] = tuple(f"020{i}" for i in range(10))
    # Organ-acquisition revenue-center family. Kept configurable so the team can
    # replace this list with the exact legacy list without changing Python code.
    organ_revenue_codes: tuple[str, ...] = tuple(f"081{i}" for i in range(10))
    condition_switch_mappings: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("medpar_infor_enctr_ind_sw_0800", ("04",)),
        ("medpar_ma_teach_ind_sw_0810", ("69",)),
        ("medpar_pr_repl_lifecyc_sw_0820", ("49",)),
        ("medpar_pr_repl_recall_sw_0830", ("50",)),
        ("medpar_no_pstv_test_sw_1560", ("ZA",)),
        ("medpar_expndd_acc_sw_1570", ("ZB", "90")),
        ("medpar_othr_clncl_tril_sw_1580", ("ZC",)),
    )
    selected_fields: tuple[str, ...] = (
        # Existing byte-by-byte fields
        "medpar_cov_chrg_0410",
        "medpar_service_charges_0470",
        "medpar_tot_dpt_chrg_0440",
        "medpar_accommodation_chrg_0460",
        "medpar_accommodation_days_0450",
        "medpar_tot_acc_chrg_0430",
        "medpar_adm_diag_code_0590",
        "medpar_admtg_dgns_vrsn_cd",
        "medpar_drg_price_0380",
        "medpar_mbi_id_1420",
        "medpar_prvdr_full_num_1660",
        "medpar_primry_pyr_0540",
        "medpar_snf_qual_thru_date_0190",
        "medpar_surg_ind_0500",
        "medpar_no_surg_codes_0511",
        "medpar_no_surg_dates_0512",
        "medpar_srgcl_prcdr_vrsn_cd",
        "medpar_surg_code_0513",
        "medpar_surg_date_0514",
        "medpar_age_0030",
        "medpar_rev_cntr_ndc_num_1550",
        "medpar_death_after_adm_0611",
        "medpar_dgns_vrsn_cd",
        "medpar_diag_code_0492",
        "medpar_no_diag_codes_0491",
        "medpar_poa_dgns_cd_cnt",
        "medpar_poa_dgns_ind_cd",
        # New discrepancy/user-story fields
        "medpar_tot_chrg_0400",
        "medpar_sqstrtn_rdctn_amt_1130",
        "medpar_dte_cr_ended_0220",
        "medpar_bill_tot_perdiem_0381",
        "medpar_intensive_care_ind_0481",
        "medpar_adm_day_0090",
        "medpar_organ_ind_0487",
        "medpar_drg_code",
        "medpar_nch_clm_type_cd",
        "medpar_race_0050",
        "medpar_dischg_status_0100",
        "medpar_hosp_home_from_dt_1630",
        "medpar_hosp_home_thru_dt_1640",
        "medpar_2_midnight_stay_ind_1280",
        "medpar_dgns_e_cd",
        "medpar_dgns_e_vrsn_cd",
        "medpar_poa_dgns_e_ind_cd",
        "medpar_pr_repl_lifecyc_sw_0820",
        "medpar_pr_repl_recall_sw_0830",
        "medpar_no_pstv_test_sw_1560",
        "medpar_expndd_acc_sw_1570",
        "medpar_othr_clncl_tril_sw_1580",
        "medpar_emer_use_sw_1590",
        "medpar_bene_st_0071",
        "medpar_zip_0080",
        "medpar_new_tech_add_on_amt_0860",
        "medpar_islet_addon_pmt_amt_1450",
        "medpar_val_q1_pmt_rdctn_amt_1470",
        "medpar_val_qb_pmt_adj_amt_1500",
        "medpar_disproportionate_0360",
        "medpar_ime_amount_0370",
        "medpar_vbp_adjstmt_amt_1160",
    )
    decimal_fields: tuple[str, ...] = (
        "medpar_cov_chrg_0410",
        "medpar_service_charges_0470",
        "medpar_tot_dpt_chrg_0440",
        "medpar_tot_acc_chrg_0430",
        "medpar_drg_price_0380",
        "medpar_tot_chrg_0400",
        "medpar_sqstrtn_rdctn_amt_1130",
        "medpar_bill_tot_perdiem_0381",
        "medpar_new_tech_add_on_amt_0860",
        "medpar_islet_addon_pmt_amt_1450",
        "medpar_val_q1_pmt_rdctn_amt_1470",
        "medpar_val_qb_pmt_adj_amt_1500",
        "medpar_disproportionate_0360",
        "medpar_ime_amount_0370",
        "medpar_vbp_adjstmt_amt_1160",
    )
    repeated_decimal_fields: tuple[str, ...] = (
        "medpar_accommodation_chrg_0460",
    )
    required_selected_fields: tuple[str, ...] = ()
    source_to_target_fields: tuple[str, ...] = (
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
        "medpar_dte_cr_ended_0220",
        "medpar_drg_code",
        "medpar_nch_clm_type_cd",
        "medpar_age_0030",
        "medpar_race_0050",
        "medpar_dischg_status_0100",
        "medpar_bene_st_0071",
        "medpar_zip_0080",
        "beneficiary_gender",
        "beneficiary_date_of_birth",
        "beneficiary_race",
        "beneficiary_zip_code",
        "county_code",
        "state_code",
        "medicare_status",
        "medical_record",
    )

    @property
    def condition_switch_map(self) -> dict[str, tuple[str, ...]]:
        return dict(self.condition_switch_mappings)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "IntermediateSettings":
        raw = raw or {}
        raw_switches = raw.get("condition_switch_mappings")
        if isinstance(raw_switches, Mapping):
            switch_mappings = tuple(
                (str(field), tuple(str(code) for code in (codes if isinstance(codes, (list, tuple)) else [codes])))
                for field, codes in raw_switches.items()
            )
        else:
            switch_mappings = cls.condition_switch_mappings
        return cls(
            identity_fields=tuple(raw.get("identity_fields") or cls.identity_fields),
            decimal_scale=Decimal(str(raw.get("decimal_scale", "0.001"))),
            window_years=int(raw.get("window_years", 5)),
            require_actual_output=bool(raw.get("require_actual_output", False)),
            require_expected_output=bool(raw.get("require_expected_output", False)),
            ndc_length=int(raw.get("ndc_length", 10)),
            intensive_care_revenue_codes=tuple(
                str(value) for value in (raw.get("intensive_care_revenue_codes") or cls.intensive_care_revenue_codes)
            ),
            organ_revenue_codes=tuple(
                str(value) for value in (raw.get("organ_revenue_codes") or cls.organ_revenue_codes)
            ),
            condition_switch_mappings=switch_mappings,
            selected_fields=tuple(raw.get("selected_fields") or cls.selected_fields),
            decimal_fields=tuple(raw.get("decimal_fields") or cls.decimal_fields),
            repeated_decimal_fields=tuple(
                raw.get("repeated_decimal_fields") or cls.repeated_decimal_fields
            ),
            required_selected_fields=tuple(raw.get("required_selected_fields") or ()),
            source_to_target_fields=tuple(
                raw.get("source_to_target_fields") or cls.source_to_target_fields
            ),
        )
