"""Read JSON/Parquet into SourceRecord objects, normalize nested values and attach file, row, role,
stage and record ID lineage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from medpar_qa.enums import FileRole, Stage
from medpar_qa.exceptions import InputReadError
from medpar_qa.models import SourceLocation, SourceRecord




def _display_path(path: Path, display_base: Path | None) -> str:
    """Convert the physical file path into a readable project-relative lineage path when possible."""
    if display_base is None:
        return str(path)
    try:
        return path.resolve().relative_to(display_base.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _record_id(path: Path, row_number: int, data: dict[str, Any]) -> str:
    """Build a stable record ID from business data when present, otherwise use file/row lineage."""
    content = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{path}:{row_number}:{content}".encode("utf-8")).hexdigest()
    return digest[:20]


def _normalize_json_payload(payload: Any) -> list[dict[str, Any]]:
    """Accept the supported JSON root shapes and produce a sequence of record dictionaries; reject
    unsupported roots.
    """
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
    """Read a JSON payload, normalize its records and attach source lineage to every record."""
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


def _nested_to_python(value: Any) -> Any:
    """Recursively convert Parquet/numpy nested values into ordinary Python values."""
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, dict):
        return {str(key): _nested_to_python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_nested_to_python(item) for item in value]
    try:
        import pandas as pd
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def read_parquet_records(
    path: Path,
    stage: Stage,
    role: FileRole,
    *,
    display_base: Path | None = None,
) -> list[SourceRecord]:
    """Read Parquet columns and nested values, then create SourceRecord objects with file/row
    lineage.
    """
    try:
        import pyarrow.parquet as pq
        # Read the file directly. A pandas -> Arrow round trip duplicated nested
        # structures and memory; partition values are injected explicitly below.
        raw_records = pq.ParquetFile(path).read().to_pylist()
    except Exception as exc:
        raise InputReadError(
            f"Unable to read Parquet file {_display_path(path, display_base)}. Install pyarrow and verify the file: {exc}"
        ) from exc

    # Hive partition columns can live only in directory names. Reading a single
    # parquet file does not load them, so preserve their literal values and lineage.
    from urllib.parse import unquote
    partitions = {}
    for part in path.parent.parts:
        if "=" in part:
            key, value = part.split("=", 1)
            if key and value != "__HIVE_DEFAULT_PARTITION__":
                partitions[unquote(key)] = unquote(value)
    for item in raw_records:
        for key, value in partitions.items():
            matches = [name for name in item if "".join(c.lower() for c in name if c.isalnum()) == "".join(c.lower() for c in key if c.isalnum())]
            if matches:
                existing = item[matches[0]]
                if existing is not None and str(existing).strip() != value.strip():
                    raise InputReadError(f"Parquet partition {key} conflicts with row value in {_display_path(path, display_base)}")
                if existing is None:
                    item[matches[0]] = value
            else:
                item[key] = value
    from .schema_metadata import parquet_schema
    metadata={'parquet_schema':parquet_schema(path)}
    return [
        SourceRecord(
            data=dict(item),
            metadata=metadata,
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
    """Choose the JSON or Parquet reader from the explicit format or file suffix; reject an
    unsupported format.
    """
    file_format = (declared_format or path.suffix.lstrip(".")).lower()
    if file_format == "json":
        return read_json_records(path, stage, role, display_base=display_base)
    if file_format in {"parquet", "pq"}:
        return read_parquet_records(path, stage, role, display_base=display_base)
    raise InputReadError(
        f"Unsupported input format '{file_format}' for {_display_path(path, display_base)}"
    )
