from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class StaySettings:
    identity_fields: tuple[str, ...] = ("hicn", "provider_id", "admission_date", "split_year_indicator")
    sort_fields: tuple[str, ...] = (
        "hicn", "provider_id", "split_year_indicator",
        "stay_from_date", "stay_thru_date", "processing_date",
        "accrete_date", "source_sequence",
    )
    decimal_scale: Decimal = Decimal("0.001")
    require_actual_output: bool = False
    require_expected_output: bool = False
    condition_info_encounter_code: str = "04"
    condition_ma_teach_code: str = "69"
    sequestration_value_code: str = "73"
    selected_fields: tuple[str, ...] = (
        "medpar_dte_cr_ended_0220",
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
        "medpar_infor_enctr_ind_sw_0800",
        "medpar_ma_teach_ind_sw_0810",
        "medpar_snf_qual_from_date_0180",
        "medpar_snf_qual_thru_date_0190",
    )
    decimal_fields: tuple[str, ...] = (
        "medpar_tot_chrg_0400",
        "medpar_drg_price_0380",
        "medpar_sqstrtn_rdctn_amt_1130",
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "StaySettings":
        raw = raw or {}
        return cls(
            identity_fields=tuple(raw.get("identity_fields") or cls.identity_fields),
            sort_fields=tuple(raw.get("sort_fields") or cls.sort_fields),
            decimal_scale=Decimal(str(raw.get("decimal_scale", "0.001"))),
            require_actual_output=bool(raw.get("require_actual_output", False)),
            require_expected_output=bool(raw.get("require_expected_output", False)),
            condition_info_encounter_code=str(
                raw.get("condition_info_encounter_code", "04")
            ),
            condition_ma_teach_code=str(raw.get("condition_ma_teach_code", "69")),
            sequestration_value_code=str(raw.get("sequestration_value_code", "73")),
            selected_fields=tuple(raw.get("selected_fields") or cls.selected_fields),
            decimal_fields=tuple(raw.get("decimal_fields") or cls.decimal_fields),
        )
