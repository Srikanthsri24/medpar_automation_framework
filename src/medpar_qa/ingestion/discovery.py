from __future__ import annotations

from glob import glob
from pathlib import Path


def discover_files(pattern: str, base_directory: Path) -> list[Path]:
    candidate = Path(pattern)
    if not candidate.is_absolute():
        candidate = base_directory / candidate

    matches = sorted(Path(item).resolve() for item in glob(str(candidate), recursive=True))
    return [path for path in matches if path.is_file()]
