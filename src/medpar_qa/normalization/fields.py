from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def nested_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


class FieldResolver:
    def __init__(self, aliases: dict[str, list[str]]) -> None:
        self.aliases = aliases

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FieldResolver":
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        aliases = {
            str(canonical): [str(alias) for alias in values]
            for canonical, values in raw.items()
        }
        return cls(aliases)

    def get(self, data: dict[str, Any], canonical_name: str, default: Any = None) -> Any:
        candidates = [canonical_name, *self.aliases.get(canonical_name, [])]
        for candidate in candidates:
            value = nested_get(data, candidate, default=None)
            if value is not None:
                return value
        return default

    def require(self, data: dict[str, Any], canonical_name: str) -> Any:
        marker = object()
        value = self.get(data, canonical_name, marker)
        if value is marker:
            raise KeyError(canonical_name)
        return value
