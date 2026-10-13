"""Create a timestamped session with separate command, pytest and master directories."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .path_utils import PROJECT_ROOT, resolve_project_path, slugify, timestamp_folder_name


@dataclass(frozen=True)
class ReportSession:
    """One timestamped report session shared by stage, pytest, and master reports."""

    root: Path
    timestamp: str

    @classmethod
    def create(
        cls,
        reports_root: str | Path = "reports",
        *,
        session_path: str | Path | None = None,
        project_root: Path = PROJECT_ROOT,
        moment: datetime | None = None,
    ) -> "ReportSession":
        """Create the timestamped report session directories."""
        stamp = timestamp_folder_name(moment)
        if session_path is None:
            parent = resolve_project_path(reports_root, project_root=project_root)
            parent.mkdir(parents=True, exist_ok=True)
            base_stamp = stamp
            suffix = 1
            while True:
                stamp = base_stamp if suffix == 1 else f"{base_stamp}_{suffix:02d}"
                root = parent / stamp
                try:
                    root.mkdir()
                    break
                except FileExistsError:
                    suffix += 1
        else:
            root = resolve_project_path(session_path, project_root=project_root)
            stamp = root.name
            root.mkdir(parents=True, exist_ok=True)
        (root / "master").mkdir(parents=True, exist_ok=True)
        return cls(root=root, timestamp=stamp)

    def command_directory(self, stage: str, command_name: str) -> Path:
        """Create/return the report folder for one business command."""
        directory = self.root / slugify(stage, "other") / slugify(command_name)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def pytest_directory(self, command_name: str) -> Path:
        """Create/return the pytest artifact directory within the session."""
        return self.command_directory("pytest", command_name)

    @property
    def master_directory(self) -> Path:
        """Create/return the session master-index directory."""
        directory = self.root / "master"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
