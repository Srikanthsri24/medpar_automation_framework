"""Resolve canonical field names against aliases, punctuation/case variants and nested paths.
Ambiguous conflicting aliases must not be silently selected.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=65536)
def _key_form(value: str) -> str:
    """Case/separator insensitive lookup for external Parquet and COBOL names."""
    return "".join(character.lower() for character in str(value) if character.isalnum())


@lru_cache(maxsize=2048)
def _key_index(keys: tuple) -> dict[str, tuple]:
    """Cache key shapes only. Read values from the current dictionary on every lookup.

    A changed key set/order has a different cache key, so added aliases and
    collisions are never hidden by a stale record/value cache.
    """
    index = {}
    for key in keys:
        normalized = _key_form(key)
        index.setdefault(normalized, []).append(key)
    return {key: tuple(matches) for key, matches in index.items()}


def nested_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Read a dotted path through nested dictionaries, returning the default when any part is
    absent.
    """
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        if part in current:
            current = current[part]
            continue
        matches = _key_index(tuple(current)).get(_key_form(part), ())
        if len(matches) != 1:
            return default
        current = current[matches[0]]
    return current


class FieldResolver:
    """Represent field resolver with the fields and methods declared below. This class groups the
    related operations below.
    """
    def __init__(self, aliases: dict[str, list[str]]) -> None:
        """Initialize this FieldResolver with the supplied dependencies/configuration and the
        assignments in its constructor.
        """
        self.aliases = aliases

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FieldResolver":
        """Load the approved alias definitions and construct a FieldResolver."""
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        aliases = {
            str(canonical): [str(alias) for alias in values]
            for canonical, values in raw.items()
        }
        return cls(aliases)

    def get(self, data: dict[str, Any], canonical_name: str, default: Any = None) -> Any:
        """Read the resolved field from the supplied record. Alias resolution and missing-value
        handling follow the code below.
        """
        candidates = [canonical_name, *self.aliases.get(canonical_name, [])]
        for candidate in candidates:
            value = nested_get(data, candidate, default=None)
            if value is not None:
                if canonical_name == "hicn" and _key_form(candidate) == "claimcannchequatable":
                    # Some claim extracts carry only EQ-BIC in this field.
                    # Join it to the nine-character account; keep full HICNs intact.
                    bic = str(value).strip()
                    if len(bic) in (1, 2):
                        account = self.get(data, "claim_can")
                        if account is not None and len(str(account).strip()) == 9:
                            return str(account).strip() + bic
                        continue
                return value
        if canonical_name == "hicn":
            ssa = self.get(data,"medpar_ssa_no_0021")
            bic = self.get(data,"medpar_bic_code_0022")
            if ssa not in (None,"") and bic not in (None,""):
                return str(ssa).strip()+str(bic).strip()
        return default

    def require(self, data: dict[str, Any], canonical_name: str) -> Any:
        """Resolve a field and raise when its required value is missing."""
        marker = object()
        value = self.get(data, canonical_name, marker)
        if value is marker:
            raise KeyError(canonical_name)
        return value
