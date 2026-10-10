"""Explicit JSON reference-feed adapters. No external lookup is fabricated."""
from __future__ import annotations
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.normalization.decimal_values import to_decimal


def ssi_days(admission: date, discharge: date, flags: dict[str, Any]) -> int:
    if discharge < admission:
        raise ValueError("SSI discharge date precedes admission")
    days = 0
    current = admission
    while current < discharge:
        next_month = date(current.year+1,1,1) if current.month==12 else date(current.year,current.month+1,1)
        end = min(next_month,discharge)
        if to_decimal(flags.get(current.strftime("%Y-%m"),0)) > 0:
            days += (end-current).days
        current=end
    return days


class ReferenceData:
    def __init__(self, config: dict[str, Any], base: Path):
        self.dod: dict[str, dict[str, Any]] = {}
        self.ssi: dict[str, dict[str, int]] = {}
        self.loaded: set[str] = set()
        for kind in ("dod", "ssi"):
            if kind not in config:
                continue
            path = Path(config[kind])
            if not path.is_absolute():
                path = base / path
            rows = json.loads(path.read_text())
            if not isinstance(rows, list):
                raise ValueError(f"{kind} reference must be a JSON array")
            for row in rows:
                if kind == "dod":
                    key = str(row["hicn"])
                    parsed = parse_date(row["date_of_death"],allow_none=False)
                    if parsed.year <= 1997:
                        continue
                    normalized = {"date_of_death": parsed.isoformat(), "verify_switch": row.get("verify_switch")}
                    if key in self.dod and self.dod[key] != normalized:
                        raise ValueError("Conflicting duplicate DOD reference key")
                    self.dod[key] = normalized
                else:
                    key = str(row["ssa_no"])
                    flags = self.ssi.setdefault(key,{})
                    for month, flag in row["months"].items():
                        date.fromisoformat(str(month)+"-01")
                        flags[month] = max(flags.get(month,0),int(to_decimal(flag)>0))
            self.loaded.add(kind)

    def enrich(self, data: dict[str,Any], resolver: FieldResolver) -> dict[str,Any]:
        result = deepcopy(data)
        if "dod" in self.loaded:
            match = self.dod.get(str(resolver.get(data,"hicn")))
            result["dod_reference_available"] = True
            result["dod_reference_matched"] = match is not None
            result["matched_date_of_death"] = match["date_of_death"] if match else None
            result["matched_dod_verify_switch"] = match["verify_switch"] if match else None
        if "ssi" in self.loaded:
            key = resolver.get(data,"medpar_ssa_no_0021") or resolver.get(data,"ssa_no")
            result["ssi_reference_available"] = True
            result["ssi_reference_matched"] = str(key) in self.ssi
            result["ssi_month_flags"] = self.ssi.get(str(key),{})
        return result
