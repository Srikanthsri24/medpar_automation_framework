from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SplitSettings:
    window_years: int = 4
    identity_fields: tuple[str, ...] = (
        "claim_can",
        "hicn",
        "provider_id",
        "stay_from_date",
        "stay_thru_date",
    )
    skip_transaction_codes: tuple[int, ...] = (0, 4)
    outside_window_indicator: str = "Y99999"
    require_actual_output: bool = False
    sort_fields: tuple[str, ...] = (
        "hicn", "provider_id", "stay_from_date", "stay_thru_date",
        "processing_date", "accrete_date", "source_sequence",
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "SplitSettings":
        raw = raw or {}
        return cls(
            window_years=int(raw.get("window_years", 4)),
            identity_fields=tuple(raw.get("identity_fields") or cls.identity_fields),
            skip_transaction_codes=tuple(
                int(value) for value in (raw.get("skip_transaction_codes") or (0, 4))
            ),
            outside_window_indicator=str(
                raw.get("outside_window_indicator", "Y99999")
            ),
            require_actual_output=bool(raw.get("require_actual_output", False)),
            sort_fields=tuple(raw.get("sort_fields") or cls.sort_fields),
        )
