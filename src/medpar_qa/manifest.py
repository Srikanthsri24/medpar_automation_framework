from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .enums import FileRole, Stage
from .exceptions import ManifestError
from .models import ManifestFile, RunManifest


def _find_project_root(manifest_path: Path) -> Path:
    """Find the nearest project root so manifests may live in nested folders."""
    for candidate in (manifest_path.parent, *manifest_path.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    # Backward-compatible fallback for manifests stored directly under config/.
    return manifest_path.parent.parent


def load_manifest(path: str | Path) -> RunManifest:
    manifest_path = Path(path).resolve()
    if not manifest_path.exists():
        raise ManifestError(f"Manifest does not exist: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    try:
        run_id = str(raw["run_id"])
        run_date = date.fromisoformat(str(raw["run_date"]))
        entries = raw["files"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError("Manifest requires run_id, ISO run_date, and files") from exc

    if not isinstance(entries, list) or not entries:
        raise ManifestError("Manifest files must be a non-empty list")

    files: list[ManifestFile] = []
    for index, entry in enumerate(entries, start=1):
        try:
            files.append(
                ManifestFile(
                    path=str(entry["path"]),
                    stage=Stage(str(entry["stage"])),
                    role=FileRole(str(entry["role"])),
                    format=str(entry["format"]) if entry.get("format") else None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"Invalid manifest file entry #{index}: {entry}") from exc

    configured_base = raw.get("base_directory")
    if configured_base:
        base_directory = Path(str(configured_base))
        if not base_directory.is_absolute():
            base_directory = (manifest_path.parent / base_directory).resolve()
    else:
        base_directory = _find_project_root(manifest_path)

    return RunManifest(
        run_id=run_id,
        run_date=run_date,
        files=files,
        settings=dict(raw.get("settings") or {}),
        base_directory=base_directory,
    )
