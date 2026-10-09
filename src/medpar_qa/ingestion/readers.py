from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from medpar_qa.enums import FileRole, Stage
from medpar_qa.exceptions import InputReadError
from medpar_qa.models import SourceLocation, SourceRecord




def _display_path(path: Path, display_base: Path | None) -> str:
    if display_base is None:
        return str(path)
    try:
        return path.resolve().relative_to(display_base.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _record_id(path: Path, row_number: int, data: dict[str, Any]) -> str:
    content = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{path}:{row_number}:{content}".encode("utf-8")).hexdigest()
    return digest[:20]


def _normalize_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if not all(isinstance(item, dict) for item in payload):
            raise InputReadError("JSON list must contain only objects")
        return payload

    if isinstance(payload, dict):
        for common_key in ("records", "claims", "data", "items"):
            value = payload.get(common_key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
        return [payload]

    raise InputReadError("JSON root must be an object or an array of objects")


def read_json_records(
    path: Path,
    stage: Stage,
    role: FileRole,
    *,
    display_base: Path | None = None,
) -> list[SourceRecord]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputReadError(
            f"Unable to read JSON file {_display_path(path, display_base)}: {exc}"
        ) from exc

    records = _normalize_json_payload(payload)
    return [
        SourceRecord(
            data=dict(item),
            source=SourceLocation(
                file_path=(
                    _display_path(path, display_base)
                ),
                row_number=index,
                file_format="json",
                stage=stage,
                role=role,
            ),
            record_id=_record_id(path, index, item),
        )
        for index, item in enumerate(records, start=1)
    ]


def read_parquet_records(
    path: Path,
    stage: Stage,
    role: FileRole,
    *,
    display_base: Path | None = None,
) -> list[SourceRecord]:
    try:
        import pandas as pd

        frame = pd.read_parquet(path)
    except Exception as exc:  # pandas exposes engine-specific exception types
        raise InputReadError(
            f"Unable to read Parquet file {_display_path(path, display_base)}. Install pyarrow and verify the file: {exc}"
        ) from exc

    raw_records = frame.where(frame.notna(), None).to_dict(orient="records")
    return [
        SourceRecord(
            data=dict(item),
            source=SourceLocation(
                file_path=(
                    _display_path(path, display_base)
                ),
                row_number=index,
                file_format="parquet",
                stage=stage,
                role=role,
            ),
            record_id=_record_id(path, index, item),
        )
        for index, item in enumerate(raw_records, start=1)
    ]


def read_records(
    path: Path,
    stage: Stage,
    role: FileRole,
    declared_format: str | None = None,
    *,
    display_base: Path | None = None,
) -> list[SourceRecord]:
    file_format = (declared_format or path.suffix.lstrip(".")).lower()
    if file_format == "json":
        return read_json_records(path, stage, role, display_base=display_base)
    if file_format in {"parquet", "pq"}:
        return read_parquet_records(path, stage, role, display_base=display_base)
    raise InputReadError(
        f"Unsupported input format '{file_format}' for {_display_path(path, display_base)}"
    )
