"""MEDPAR QA stage-wise command runner.

Edit only the configuration sections below. All file paths must be relative to this
project folder. Each execution creates one timestamped folder under ``reports/``:

reports/<timestamp>/
    master/index.html
    final_action/<command>/report.html
    split/<command>/report.html
    stay/<command>/report.html
    intermediate/<command>/report.html
    final_medpar/<command>/report.html
    pytest/<command>/report.html

Within every stage you can enable individual-file runs, folder/wildcard runs, and
pytest marker runs independently. Set ``enabled`` to False or comment out an item.
Run everything enabled with:  python run_commands.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from medpar_qa.reporting.path_utils import (  # noqa: E402
    ensure_relative_user_path,
    relative_display,
    slugify,
)
from medpar_qa.reporting.run_layout import ReportSession  # noqa: E402
from medpar_qa.reporting.session_index import refresh_session_indexes  # noqa: E402

PYTHON = sys.executable
STOP_ON_FAILURE = False
REPORTS_ROOT = "reports"  # Relative path only.


# =============================================================================
# 1. STAGE-WISE BUSINESS FILE RUNS
# =============================================================================
# Each stage has two clear lists:
#   single_files: run named individual files
#   folder_paths: run complete folders/wildcards
# Paths may be JSON or Parquet. Repeat paths in source/actual/expected lists.

STAGE_RUNS: dict[str, dict[str, Any]] = {
    "final_action": {
        "enabled": True,
        "run_date": "2024-04-04",
        "single_files": [
            {
                "name": "Final Action - claim.r2.a single file",
                "enabled": True,
                "mode": "calculate",
                "source": ["data/user_inputs/final_action/source/claim.r2.a (1).json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Final Action - FA CVM single file",
                "enabled": False,
                "mode": "calculate",
                "source": ["data/user_inputs/final_action/source/FA_T.CVM.CWFCB.D240404.T1438012-000000004.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
        ],
        "folder_paths": [
            {
                "name": "Final Action - all JSON files",
                "enabled": True,
                "mode": "calculate",
                "source": ["data/user_inputs/final_action/source/*.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            }
        ],
    },
    "split": {
        "enabled": True,
        "run_date": "2024-04-04",
        "single_files": [
            {
                "name": "Split - Split01 single file",
                "enabled": True,
                "mode": "calculate",
                "source": ["data/user_inputs/split/source/Split01_claim.r1.a_20210103.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Split - known negative Split03 file",
                "enabled": False,
                "mode": "calculate",
                "source": ["data/user_inputs/split/source/Split03_claim.r1.b_20220103.json"],
                "actual": [],
                "expected": [],
                # This command is successful only when the validator detects a failure.
                "expected_exit_codes": (1,),
            },
        ],
        "folder_paths": [
            {
                "name": "Split - all uploaded JSON files including negative fixtures",
                "enabled": False,
                "mode": "calculate",
                "source": ["data/user_inputs/split/source/*.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (1,),
            }
        ],
    },
    "stay": {
        "enabled": True,
        "run_date": "2026-07-19",
        "single_files": [
            {
                "name": "Stay - sample source calculation",
                "enabled": True,
                "mode": "calculate",
                "source": ["sample_data/input/stay/source.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Stay - sample golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["sample_data/input/stay/source.json"],
                "actual": ["sample_data/actual/stay/actual.json"],
                "expected": ["sample_data/expected/stay/expected.json"],
                "expected_exit_codes": (0,),
            },
        ],
        "folder_paths": [
            {
                "name": "Stay - user folder golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["data/user_inputs/stay/source/*.json"],
                "actual": ["data/user_inputs/stay/actual_output/*.json"],
                "expected": ["data/user_inputs/stay/expected_output/*.json"],
                "expected_exit_codes": (0,),
            }
        ],
    },
    "intermediate": {
        "enabled": True,
        "run_date": "2026-07-19",
        "single_files": [
            {
                "name": "Intermediate - sample actual-output structural checks",
                "enabled": True,
                "mode": "calculate",
                "source": ["sample_data/actual/intermediate/actual.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Intermediate - sample golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["sample_data/input/intermediate/source.json"],
                "actual": ["sample_data/actual/intermediate/actual.json"],
                "expected": ["sample_data/expected/intermediate/expected.json"],
                "expected_exit_codes": (0,),
            },
        ],
        "folder_paths": [
            {
                "name": "Intermediate - user JSON folder golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["data/user_inputs/intermediate/source/*.json"],
                "actual": ["data/user_inputs/intermediate/actual_output/*.json"],
                "expected": ["data/user_inputs/intermediate/expected_output/*.json"],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Intermediate - user Parquet folder golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["data/user_inputs/intermediate/source/*.parquet"],
                "actual": ["data/user_inputs/intermediate/actual_output/*.parquet"],
                "expected": ["data/user_inputs/intermediate/expected_output/*.parquet"],
                "expected_exit_codes": (0,),
            },
        ],
    },
    "final_medpar": {
        "enabled": True,
        "run_date": "2026-07-19",
        "single_files": [
            {
                "name": "Final MEDPAR - sample actual-output and 3000-byte checks",
                "enabled": True,
                "mode": "calculate",
                "source": ["sample_data/actual/final_medpar/actual.json"],
                "actual": [],
                "expected": [],
                "expected_exit_codes": (0,),
            },
            {
                "name": "Final MEDPAR - sample golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["sample_data/input/final_medpar/source.json"],
                "actual": ["sample_data/actual/final_medpar/actual.json"],
                "expected": ["sample_data/expected/final_medpar/expected.json"],
                "expected_exit_codes": (0,),
            },
        ],
        "folder_paths": [
            {
                "name": "Final MEDPAR - user folder golden regression",
                "enabled": False,
                "mode": "golden",
                "source": ["data/user_inputs/final_medpar/source/*.json"],
                "actual": ["data/user_inputs/final_medpar/actual_output/*.json"],
                "expected": ["data/user_inputs/final_medpar/expected_output/*.json"],
                "expected_exit_codes": (0,),
            }
        ],
    },
}


# =============================================================================
# 2. ALL-STAGE MANIFEST RUNS
# =============================================================================
ALL_STAGE_RUNS = [
    {
        "name": "All five stages - complete example manifest",
        "enabled": False,
        "manifest": "config/run_manifest.all_stages.example.yaml",
        "expected_exit_codes": (0,),
    },
    {
        "name": "All five stages - user paths template",
        "enabled": False,
        "manifest": "config/runs/all_5_stages_user_template.yaml",
        "expected_exit_codes": (0,),
    },
]


# =============================================================================
# 3. PYTEST RUNS — STAGE WISE OR COMPLETE
# =============================================================================
PYTEST_RUNS = [
    {"name": "Pytest - Final Action", "enabled": False, "marker": "final_action"},
    {"name": "Pytest - Split", "enabled": False, "marker": "split"},
    {"name": "Pytest - Stay", "enabled": False, "marker": "stay"},
    {"name": "Pytest - Intermediate", "enabled": False, "marker": "intermediate"},
    {"name": "Pytest - Final MEDPAR", "enabled": False, "marker": "final_medpar"},
    {"name": "Pytest - Uploaded input data", "enabled": True, "marker": "input_data"},
    {"name": "Pytest - Complete regression", "enabled": False, "marker": "regression"},
    {"name": "Pytest - Complete project", "enabled": False, "marker": None},
]


@dataclass(frozen=True)
class Command:
    name: str
    stage: str
    command_id: str
    args: list[str]
    enabled: bool = True
    expected_exit_codes: tuple[int, ...] = (0,)


def _append_paths(args: list[str], flag: str, paths: list[str]) -> None:
    for path in paths:
        ensure_relative_user_path(path, flag)
        args.extend([flag, path])


def _stage_command(stage: str, run_date: str, item: dict[str, Any], report_session: str) -> Command:
    name = str(item["name"])
    command_id = slugify(name)
    args = [
        PYTHON,
        "scripts/run_stage.py",
        "--stage",
        stage,
        "--run-date",
        run_date,
        "--mode",
        str(item.get("mode", "calculate")),
        "--run-id",
        command_id,
        "--command-id",
        command_id,
        "--report-session",
        report_session,
        "--show-pass",
    ]
    _append_paths(args, "--source", list(item.get("source") or []))
    _append_paths(args, "--actual", list(item.get("actual") or []))
    _append_paths(args, "--expected", list(item.get("expected") or []))
    return Command(name, stage, command_id, args, bool(item.get("enabled", True)), tuple(item.get("expected_exit_codes", (0,))))


def build_commands(report_session: str = "reports/_configured_preview") -> list[Command]:
    ensure_relative_user_path(report_session, "report_session")
    commands: list[Command] = []
    for stage, stage_config in STAGE_RUNS.items():
        if not stage_config.get("enabled", True):
            continue
        run_date = str(stage_config["run_date"])
        for list_name in ("single_files", "folder_paths"):
            for item in stage_config.get(list_name, []):
                commands.append(_stage_command(stage, run_date, item, report_session))

    for item in ALL_STAGE_RUNS:
        manifest = str(item["manifest"])
        ensure_relative_user_path(manifest, "manifest")
        name = str(item["name"])
        command_id = slugify(name)
        commands.append(
            Command(
                name=name,
                stage="master",
                command_id=command_id,
                args=[PYTHON, "-m", "medpar_qa.cli", "--manifest", manifest, "--report-session", report_session, "--command-id", command_id],
                enabled=bool(item.get("enabled", True)),
                expected_exit_codes=tuple(item.get("expected_exit_codes", (0,))),
            )
        )

    for item in PYTEST_RUNS:
        name = str(item["name"])
        command_id = slugify(name)
        marker = item.get("marker")
        args = [PYTHON, "-m", "pytest", "-v"]
        if marker:
            args.extend(["-m", str(marker)])
        args.extend(["--medpar-report-session", report_session, "--medpar-report-name", command_id])
        commands.append(Command(name, str(marker or "pytest"), command_id, args, bool(item.get("enabled", True)), (0,)))
    return commands


# Kept for inspection/tests. main() builds a fresh list using the real timestamp session.
COMMANDS = build_commands()


def _command_text(args: list[str]) -> str:
    # Keep paths and command output project-relative. The Python executable is shown
    # as "python" instead of its machine-specific absolute virtualenv path.
    display_args = ["python", *args[1:]] if args and args[0] == PYTHON else list(args)
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in display_args)


def _command_output_directory(session: ReportSession, command: Command) -> Path:
    if command.stage == "master":
        directory = session.master_directory / command.command_id
    elif command.stage in {"final_action", "split", "stay", "intermediate", "final_medpar"}:
        directory = session.command_directory(command.stage, command.command_id)
    else:
        # Pytest plugin may infer a business stage from its marker. Use this fallback
        # for execution metadata; generated reports are discovered recursively.
        directory = session.command_directory("pytest", command.command_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def main() -> int:
    session = ReportSession.create(REPORTS_ROOT, project_root=PROJECT_ROOT)
    session_relative = relative_display(session.root, project_root=PROJECT_ROOT)
    commands = [command for command in build_commands(session_relative) if command.enabled]
    if not commands:
        print("No commands are enabled. Set enabled=True for at least one stage/file/folder/pytest item.")
        return 0

    executions: list[dict[str, Any]] = []
    unexpected_failures = 0
    print("=" * 118)
    print("MEDPAR QA STAGE-WISE COMMAND RUNNER")
    print(f"Report session: {session_relative}")
    print(f"Enabled commands: {len(commands)}")
    print("All configured input and report paths are relative to the project folder.")
    print("=" * 118)

    for index, command in enumerate(commands, start=1):
        print("\n" + "#" * 118)
        print(f"COMMAND {index}/{len(commands)}: {command.name}")
        print(f"CATEGORY/STAGE: {command.stage}")
        print(f"EXPECTED EXIT CODE(S): {command.expected_exit_codes}")
        text = _command_text(command.args)
        print(f"RELATIVE COMMAND: {text}")
        print("#" * 118)

        before = {path for path in session.root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            command.args,
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        output_text = completed.stdout or ""
        # Do not leak machine-specific project locations into shareable reports.
        output_text = output_text.replace(str(PROJECT_ROOT), ".")
        output_text = output_text.replace(str(PROJECT_ROOT).replace("/", "\\"), ".")
        print(output_text, end="" if output_text.endswith("\n") else "\n")
        after = {path for path in session.root.rglob("*") if path.is_file()}
        report_files = sorted(path for path in (after - before) if path.suffix.lower() in {".html", ".json", ".txt", ".xml"})

        expected = completed.returncode in command.expected_exit_codes
        outcome = "COMPLETED AS EXPECTED" if expected else "UNEXPECTED COMMAND RESULT"
        if not expected:
            unexpected_failures += 1
        command_dir = _command_output_directory(session, command)
        (command_dir / "console.log").write_text(output_text, encoding="utf-8")
        execution_payload = {
            "name": command.name,
            "stage": command.stage,
            "command": text,
            "returncode": completed.returncode,
            "expected_exit_codes": command.expected_exit_codes,
            "completed_as_expected": expected,
            "outcome": outcome,
            "report_files": [relative_display(path, project_root=PROJECT_ROOT) for path in report_files],
        }
        (command_dir / "execution.json").write_text(json.dumps(execution_payload, indent=2), encoding="utf-8")

        print(f"COMMAND OUTCOME: {outcome}")
        print(f"ACTUAL EXIT CODE: {completed.returncode}")
        if completed.returncode == 1 and expected:
            print("EXPLANATION: A business validation failure was expected and was detected correctly.")
        if report_files:
            print("GENERATED REPORT FILES:")
            for report in report_files:
                print(f"  - {relative_display(report, project_root=PROJECT_ROOT)}")

        executions.append(
            {
                "name": command.name,
                "stage": command.stage,
                "command": text,
                "returncode": completed.returncode,
                "expected_exit_codes": command.expected_exit_codes,
                "expected": expected,
                "outcome": outcome,
                "output": output_text,
                "report_files": report_files,
            }
        )
        if unexpected_failures and STOP_ON_FAILURE:
            break

    master = refresh_session_indexes(session.root, executions=executions)
    print("\n" + "=" * 118)
    print(f"FINISHED. Unexpected command results: {unexpected_failures}")
    print(f"Timestamped report folder: {session_relative}")
    print(f"Master HTML report: {relative_display(master, project_root=PROJECT_ROOT)}")
    print("Open master/index.html first, then navigate stage-wise.")
    print("=" * 118)
    return 1 if unexpected_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
