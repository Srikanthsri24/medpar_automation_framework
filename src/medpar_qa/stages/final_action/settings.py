"""Typed final action configuration defaults and mapping parser: identities, sort fields, domains,
precision, required output roles and selected field coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class FinalActionSettings:
    """Business configuration for the Final Action stage."""

    rule1_keep_qcs: tuple[int, ...] = (1, 3, 5)
    allowed_query_codes: tuple[int, ...] = (0, 1, 3, 5)
    allowed_transaction_codes: tuple[int, ...] = (0, 1, 2, 3, 4)
    require_accrete_date: bool = False
    block_ambiguous_ordering: bool = True
    rule6_enabled: bool = True
    # Oct 9 clarification places covered-days/LOS bypass at Final, not FA.
    bypass_direction: str | None = None
    enforce_single_service_year: bool = True
    max_continuation_records: int = 900
    max_hold_records: int = 875
    rule6_drop_codes: tuple[str, ...] = ("4", "6")
    identity_fields: tuple[str, ...] = (
        "claim_can",
        "icn",
        "query_code",
        "processing_date",
        "accrete_date",
    )
    # LD-3137: admission_date must never be added to this list.
    sort_fields: tuple[str, ...] = (
        "hicn",
        "provider_id",
        "stay_from_date",
        "stay_thru_date",
        "processing_date",
        "accrete_date",
        "source_sequence",
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "FinalActionSettings":
        """Convert supplied stage options into typed settings, applying only the documented
        defaults for omitted options.
        """
        values = dict(raw or {})
        return cls(
            rule1_keep_qcs=tuple(int(value) for value in values.get("rule1_keep_qcs", cls.rule1_keep_qcs)),
            allowed_query_codes=tuple(
                int(value) for value in values.get("allowed_query_codes", cls.allowed_query_codes)
            ),
            allowed_transaction_codes=tuple(
                int(value) for value in values.get("allowed_transaction_codes", cls.allowed_transaction_codes)
            ),
            require_accrete_date=bool(values.get("require_accrete_date", False)),
            block_ambiguous_ordering=bool(values.get("block_ambiguous_ordering", True)),
            rule6_enabled=bool(values.get("rule6_enabled", True)),
            bypass_direction=values.get("bypass_direction"),
            enforce_single_service_year=bool(values.get("enforce_single_service_year", True)),
            max_continuation_records=int(values.get("max_continuation_records", 900)),
            max_hold_records=int(values.get("max_hold_records", 875)),
            rule6_drop_codes=tuple(str(value) for value in values.get("rule6_drop_codes", cls.rule6_drop_codes)),
            identity_fields=tuple(str(value) for value in values.get("identity_fields", cls.identity_fields)),
            sort_fields=tuple(str(value) for value in values.get("sort_fields", cls.sort_fields)),
        )
