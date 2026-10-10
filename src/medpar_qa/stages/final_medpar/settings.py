"""Typed final medpar configuration defaults and mapping parser: identities, sort fields, domains,
precision, required output roles and selected field coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class FinalMedparSettings:
    """Store the typed FinalMedpar options. Defaults are declared in this class; from_mapping
    applies explicit manifest overrides.
    """
    identity_fields: tuple[str, ...] = (
        "hicn",
        "provider_id",
        "admission_date",
        "split_year_indicator",
    )
    sort_fields: tuple[str, ...] = (
        "hicn", "provider_id", "split_year_indicator",
        "medpar_ss_ls_snf_ind_0140",
    )
    expected_bytes: int = 3000
    encoding: str = "ascii"
    require_actual_output: bool = False
    require_expected_output: bool = False
    require_fixed_width: bool = False
    allowed_classifications: tuple[str, ...] = ("S", "L", "N")
    selected_fields: tuple[str, ...] = (
        "split_year_indicator",
        "medpar_ss_ls_snf_ind_0140",
        "medpar_bic",
        "provider_id",
        "date_of_death",
        "medpar_ssi_data",
        "medpar_q1_payment_reduction",
        "medpar_ssa_no_0021",
        "medpar_no_bills_0150",
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
        "medpar_dte_cr_ended_0220",
        "medpar_adm_day_0090",
        "medpar_organ_ind_0487",
        "medpar_drg_code",
        "medpar_bill_tot_perdiem_0381",
        "medpar_intensive_care_ind_0481",
        "medpar_emer_use_sw_1590",
        "medpar_bene_st_0071",
        "medpar_zip_0080",
        "medpar_hosp_home_from_dt_1630",
        "medpar_hosp_home_thru_dt_1640",
        "medpar_2_midnight_stay_ind_1280",
        "medpar_dgns_e_cd",
        "medpar_dgns_e_vrsn_cd",
        "medpar_poa_dgns_e_ind_cd",
        "medpar_bic_code_0022",
        "medpar_val_q1_pmt_rdctn_amt_1470",
        "medpar_ssi_data_0252",
        "medpar_himaster_dod_0230",
        "medpar_dod_ind_0240",
        "medpar_provider_0130",
        "warning_indicator_04",
        "warning_indicator_05",
        "warning_indicator_09",
        "warning_indicator_10",
        "warning_indicator_11",
        "warning_indicator_12",
        "warning_indicator_13",
        "warning_indicator_14",
        "warning_indicator_15",
        "warning_indicator_16",
        "warning_indicator_17",
    )
    required_selected_fields: tuple[str, ...] = ()
    field_layout: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "FinalMedparSettings":
        """Convert supplied stage options into typed settings, applying only the documented
        defaults for omitted options.
        """
        raw = raw or {}
        return cls(
            identity_fields=tuple(raw.get("identity_fields") or cls.identity_fields),
            sort_fields=tuple(raw.get("sort_fields") or cls.sort_fields),
            expected_bytes=int(raw.get("expected_bytes", 3000)),
            encoding=str(raw.get("encoding", "ascii")),
            require_actual_output=bool(raw.get("require_actual_output", False)),
            require_expected_output=bool(raw.get("require_expected_output", False)),
            require_fixed_width=bool(raw.get("require_fixed_width", False)),
            allowed_classifications=tuple(
                str(value) for value in (raw.get("allowed_classifications") or cls.allowed_classifications)
            ),
            selected_fields=tuple(raw.get("selected_fields") or cls.selected_fields),
            required_selected_fields=tuple(raw.get("required_selected_fields") or ()),
            field_layout=tuple(dict(item) for item in (raw.get("field_layout") or ())),
        )
