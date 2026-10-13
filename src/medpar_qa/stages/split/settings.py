"""Typed split configuration defaults and mapping parser: identities, sort fields, domains,
precision, required output roles and selected field coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SplitSettings:
    """Store the typed Split options. Defaults are declared in this class; from_mapping applies
    explicit manifest overrides.
    """
    window_years: int = 4
    current_year: int | None = None
    processing_quarter: str | None = None
    allowed_transaction_codes: tuple[int, ...] = (0, 1, 2, 3, 4)
    maximum_bills_per_stay: int = 75
    identity_fields: tuple[str, ...] = (
        "claim_can",
        "icn",
        "query_code",
        "hicn",
        "provider_id",
        "stay_from_date",
        "stay_thru_date",
    )
    skip_transaction_codes: tuple[int, ...] = ()
    outside_window_indicator: str = "Y99999"
    require_actual_output: bool = False
    sort_fields: tuple[str, ...] = (
        "hicn", "provider_id", "stay_from_date", "stay_thru_date",
        "processing_date", "accrete_date", "source_sequence",
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "SplitSettings":
        """Convert supplied stage options into typed settings, applying only the documented
        defaults for omitted options.
        """
        raw = raw or {}
        return cls(
            processing_quarter=raw.get("processing_quarter"),
            window_years=int(raw.get("window_years", 4)),
            current_year=int(raw["current_year"]) if raw.get("current_year") is not None else None,
            allowed_transaction_codes=tuple(int(v) for v in raw.get("allowed_transaction_codes", (0, 1, 2, 3, 4))),
            maximum_bills_per_stay=int(raw.get("maximum_bills_per_stay", 75)),
            identity_fields=tuple(raw.get("identity_fields") or cls.identity_fields),
            skip_transaction_codes=tuple(
                int(value) for value in raw.get("skip_transaction_codes", ())
            ),
            outside_window_indicator=str(
                raw.get("outside_window_indicator", "Y99999")
            ),
            require_actual_output=bool(raw.get("require_actual_output", False)),
            sort_fields=tuple(raw.get("sort_fields") or cls.sort_fields),
        )
