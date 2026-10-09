from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def slugify(value: str, fallback: str = "run") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_")
    return text.lower() or fallback


def timestamp_folder_name(moment: datetime | None = None) -> str:
    value = moment or datetime.now().astimezone()
    return value.strftime("%Y%m%d_%H%M%S")


def resolve_project_path(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_root / candidate).resolve()


def relative_display(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> str:
    candidate = Path(path)
    try:
        absolute = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
        return absolute.relative_to(project_root.resolve()).as_posix()
    except (OSError, ValueError):
        return candidate.as_posix()


def relative_link(from_directory: str | Path, target: str | Path) -> str:
    return Path(os.path.relpath(Path(target), Path(from_directory))).as_posix()


def ensure_relative_user_path(path: str | Path, label: str) -> None:
    if Path(path).is_absolute():
        raise ValueError(
            f"{label} must be a relative project path, not an absolute path: {path}"
        )
