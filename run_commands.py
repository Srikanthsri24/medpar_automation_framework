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
import html
from collections import Counter
from datetime import datetime, timezone
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
DEFAULT_DATASET = "r65"  # Team demonstration: all supplied R65 stages.
CONNECTED_PIPELINE_ENABLED = True  # False restores independent STAGE_RUNS validation.
CONNECTED_SETTINGS: dict[str, Any] = {
    "split": {"current_year": 2025},
    "intermediate": {"deduplicate_filename_exports": True},
    "final_action": {"enforce_single_service_year": False, "enforce_legacy_table_limits": False},
}  # Optional stage settings; no code-domain overrides by default.
STOP_ON_FAILURE = False
REPORTS_ROOT = "reports"  # Relative path only.


# =============================================================================
# 1. STAGE-WISE BUSINESS FILE RUNS
# =============================================================================
# Each stage has two clear lists:
#   single_files: run named individual files
#   folder_paths: run complete folders/wildcards
# Paths may be JSON or Parquet. Repeat paths in source/actual/expected lists.

# Production data must be copied under PROJECT_ROOT/data/production/q61.
# Never commit it. Paths remain relative as required by the runner.
PRODUCTION_ROOT = Path("data/production/q61")


def _production_paths(*folders: str, suffixes: tuple[str, ...] = (".json", ".parquet"), data_root: Path = PRODUCTION_ROOT) -> list[str]:
    """Discover all nested stage files; deterministic and project-relative."""
    result: list[str] = []
    for folder in folders:
        directory = PROJECT_ROOT / data_root / folder
        if directory.is_dir():
            result.extend(
                path.relative_to(PROJECT_ROOT).as_posix()
                for path in directory.rglob("*")
                if path.is_file() and path.suffix.lower() in suffixes
            )
    return sorted(set(result))


def _production_run(name: str, folders: tuple[str, ...], *, enabled: bool = True,
                    suffixes: tuple[str, ...] = (".json", ".parquet"),
                    actual_folders: tuple[str, ...] = (), data_root: Path = PRODUCTION_ROOT) -> dict[str, Any]:
    """Create the configuration entry for a named production run, with its source/output paths and
    enabled flag.
    """
    paths = _production_paths(*folders, suffixes=suffixes, data_root=data_root)
    actual_paths = _production_paths(*actual_folders, suffixes=suffixes, data_root=data_root)
    return {
        "name": f"{name} ({len(paths)} files)",
        "enabled": enabled and bool(paths),
        "mode": "reconcile" if actual_folders else "calculate",
        "require_matching_snapshot": bool(actual_folders),
        "source": paths,
        "actual": actual_paths,
        "expected": [],
        "expected_exit_codes": (0,),
    }


STAGE_RUNS: dict[str, dict[str, Any]] = {
    "final_action": {
        "enabled": True,
        "run_date": "2026-03-20",
        "single_files": [],
        "folder_paths": [
            _production_run("Final Action - quarterly claims to retained output", ("1-quarterly-claims-parquet",), actual_folders=("2-final-action-rules-parquet",), enabled=False),
            {
                **_production_run("Final Action - retained files as connected starting input", ("2-final-action-rules-parquet",)),
                "pipeline_outputs": {
                    "stay": _production_paths("4-stay-processing", suffixes=(".json",)),
                    "intermediate": _production_paths("5-intermediate-processing", suffixes=(".json",)),
                    "final_medpar": _production_paths("6-final-processing", suffixes=(".json",), data_root=Path("data/production/r65")),
                },
            },
            _production_run("Final Action - dropped output structural checks", ("2-final-action-rules-dropped",), enabled=False),
        ],
    },
    "split": {
        "enabled": True,
        "run_date": "2026-03-20",
        "single_files": [],
        "folder_paths": [
            _production_run("Split - retained Final Action to 4-year output", ("2-final-action-rules-parquet",), actual_folders=("3-4yr-window-parquet",)),
            _production_run("Split - retained 4-year window structural checks", ("3-4yr-window-parquet",), enabled=False),
            _production_run("Split - dropped 4-year window structural checks", ("3-4yr-window-parquet-dropped",), enabled=False),
        ],
    },
    "stay": {
        "enabled": True,
        "run_date": "2026-05-14",
        "single_files": [],
        "folder_paths": [
            _production_run("Stay - split bills to merged JSON output", ("3-4yr-window-parquet",), actual_folders=("4-stay-processing",)),
            _production_run("Stay - output Parquet structural checks", ("4-stay-processing-parquet",), enabled=False),
        ],
    },
    "intermediate": {
        "enabled": True,
        "run_date": "2026-05-14",
        "single_files": [],
        "folder_paths": [
            _production_run("Intermediate - merged Stay to extracted JSON output", ("4-stay-processing",), actual_folders=("5-intermediate-processing",)),
            _production_run("Intermediate - output Parquet structural checks", ("5-intermediate-processing-parquet",), enabled=False),
        ],
    },
    "final_medpar": {
        "enabled": True,  # R65 contains extracted Final MEDPAR SS/SNF JSON outputs.
        "run_date": "2026-05-14",
        "single_files": [],
        "folder_paths": [
            _production_run("Final MEDPAR - R65 short-stay extracted output checks", ("6-final-processing/MEDPAR_FINAL_SS_FILES",), suffixes=(".json",), data_root=Path("data/production/r65")),
            _production_run("Final MEDPAR - R65 SNF extracted output checks", ("6-final-processing/MEDPAR_FINAL_SNF_FILES",), suffixes=(".json",), data_root=Path("data/production/r65")),
        ],
    },
}


def r65_stage_runs() -> dict[str, dict[str, Any]]:
    """Review every supplied R65 stage independently using its actual stage boundary."""
    root = Path("data/production/r65")
    boundaries = {
        "final_action": ("1-quarterly-claims", "2-final-action-rules"),
        "split": ("2-final-action-rules", "3-4yr-window"),
        "stay": ("3-4yr-window", "4-stay-processing"),
        "intermediate": ("4-stay-processing", "5-intermediate-processing"),
    }
    profile = {}
    for stage, (source, actual) in boundaries.items():
        item = _production_run(f"R65 {stage.replace('_', ' ').title()} - input/output reconciliation", (source,), actual_folders=(actual,), data_root=root)
        # R65 is a development export with no shared snapshot manifest. Check the
        # supplied records; disclose archive completeness independently in the audit.
        item["require_matching_snapshot"] = False
        item["split_current_year"] = 2024
        profile[stage] = {"enabled": True, "run_date": "2025-03-18", "single_files": [], "folder_paths": [item]}
    profile["final_medpar"] = {"enabled": True, "run_date": "2025-03-18", "single_files": [], "folder_paths": [
        _production_run("R65 Final MEDPAR short-stay output checks", ("6-final-processing/MEDPAR_FINAL_SS_FILES",), suffixes=(".json",), data_root=root),
        _production_run("R65 Final MEDPAR SNF output checks", ("6-final-processing/MEDPAR_FINAL_SNF_FILES",), suffixes=(".json",), data_root=root),
    ]}
    return profile



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
    {"name": "Pytest - Uploaded input data", "enabled": False, "marker": "input_data"},
    {"name": "Pytest - Complete regression", "enabled": False, "marker": "regression"},
    {"name": "Pytest - Complete project", "enabled": False, "marker": None},
]


@dataclass(frozen=True)
class Command:
    """Represent command with the fields and methods declared below. Declared fields document the
    component contract.
    """
    name: str
    stage: str
    command_id: str
    args: list[str]
    enabled: bool = True
    expected_exit_codes: tuple[int, ...] = (0,)


def _append_paths(args: list[str], flag: str, paths: list[str]) -> None:
    """Append configured file or folder arguments to a stage command without dropping prior
    entries.
    """
    for path in paths:
        ensure_relative_user_path(path, flag)
        args.extend([flag, path])


def _stage_command(stage: str, run_date: str, item: dict[str, Any], report_session: str) -> Command:
    """Translate one enabled stage run into the Python stage-runner argument list."""
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
    if stage == "final_medpar" and item.get("mode", "calculate") == "calculate":
        args.extend(["--per-file", "--final-extract"])
    if stage == "split":
        args.extend(["--split-current-year", str(item.get("split_current_year", 2025))])
    _append_paths(args, "--source", list(item.get("source") or []))
    _append_paths(args, "--actual", list(item.get("actual") or []))
    _append_paths(args, "--expected", list(item.get("expected") or []))
    if item.get("per_file"):
        args.append("--per-file")
    if item.get("require_matching_snapshot"):
        args.append("--require-matching-snapshot")
    return Command(name, stage, command_id, args, bool(item.get("enabled", True)), tuple(item.get("expected_exit_codes", (0,))))


def build_commands(report_session: str = "reports/_configured_preview", stage_runs=None) -> list[Command]:
    """Expand enabled STAGE_RUNS entries into business command definitions and append requested
    pytest commands.
    """
    ensure_relative_user_path(report_session, "report_session")
    commands: list[Command] = []
    for stage, stage_config in (STAGE_RUNS if stage_runs is None else stage_runs).items():
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
    """Render the argument list as readable shell command text for execution evidence."""
    display_args = ["python", *args[1:]] if args and args[0] == PYTHON else list(args)
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in display_args)


def _command_output_directory(session: ReportSession, command: Command) -> Path:
    """Choose the isolated report directory for this command inside its session."""
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


def write_quality_summary(session_root: Path, executions: list[dict[str, Any]]) -> None:
    """Generate a self-contained, honest execution dashboard and machine-readable audit."""
    rows = []
    for item in executions:
        expected_codes = tuple(item["expected_exit_codes"])
        code = item["returncode"]
        if code == 0:
            result = "PASS" if item["expected"] else "UNEXPECTED_PASS"
        elif code == 1 and 1 in expected_codes:
            result = "EXPECTED_VALIDATION_FAILURE"
        else:
            result = "FAIL" if code == 1 else "ERROR"
        rows.append({
            "name": item["name"], "stage": item["stage"],
            "command": item["command"], "exit_code": code,
            "expected_exit_codes": list(expected_codes), "result": result,
            "reports": [relative_display(x, project_root=PROJECT_ROOT) for x in item["report_files"]],
            "console_log": item["output"][-20000:],
        })
    counts = Counter(row["result"] for row in rows)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "execution_counts": dict(counts), "total_commands": len(rows),
        "business_compliance_verified": False,
        "disclaimer": "Passing execution checks does not prove V3 rule or field-level compliance. A calculate-only run without actual output is not an end-to-end comparison.",
        "executions": rows,
    }
    (session_root / "quality_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    table_rows = []
    for row in rows:
        links = " ".join(f'<a href="{html.escape(str(Path(r).relative_to(Path(session_root).relative_to(PROJECT_ROOT))), quote=True)}">report</a>' for r in row["reports"] if Path(r).is_relative_to(Path(session_root).relative_to(PROJECT_ROOT)))
        cells = [row["stage"], row["name"], row["result"], str(row["exit_code"])]
        table_rows.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+'<td>'+links+'</td></tr>')
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MEDPAR Run Quality Summary</title><style>body{font:15px system-ui,Arial;margin:36px auto;max-width:1200px;padding:0 20px;color:#182536;background:#f7f9fc}h1{font-size:28px}section{background:white;padding:24px;border:1px solid #dce4ee;border-radius:12px;margin:18px 0}table{border-collapse:collapse;width:100%}th,td{padding:12px;text-align:left;border-bottom:1px solid #e5eaf1}th{background:#edf3f9}a{color:#1359ac}.warning{border-left:5px solid #bb7722;padding:12px;background:#fff6e6}</style><h1>MEDPAR QA — Execution Quality Summary</h1><section><h2>Run overview</h2><p>Commands: __TOTAL__</p><p>__COUNTS__</p><p class="warning">Execution success is not proof of MEDPAR V3 compliance. Expected validation failures are reported separately from passing validations. Runs without actual outputs cannot verify final extract correctness.</p></section><section><h2>Stage and command results</h2><table><thead><tr><th>Stage</th><th>Command</th><th>Result</th><th>Exit</th><th>Details</th></tr></thead><tbody>__ROWS__</tbody></table></section><section><h2>Next verification steps</h2><p>Compare source JSON with actual output JSON for every stage; verify approved decision-tree outcomes, field derivations, record-level reconciliation, external lookup inputs, and exception counts. Unresolved specification conflicts remain unverified.</p><p><a href="master/index.html">Existing master report</a> · <a href="quality_summary.json">Machine-readable summary</a></p></section></html>"""
    page = page.replace("__TOTAL__", str(len(rows))).replace("__COUNTS__", html.escape(', '.join(f'{k}: {v}' for k,v in sorted(counts.items())))).replace("__ROWS__", ''.join(table_rows))
    (session_root / "quality_summary.html").write_text(page, encoding="utf-8")


def execution_args(command: Command, session: ReportSession) -> list[str]:
    """Keep stage process launches short even with hundreds of long production paths."""
    if command.args[1:2] != ["scripts/run_stage.py"]:
        return command.args
    directory = session.root / "command_arguments"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{command.command_id}.json"
    path.write_text(json.dumps(command.args[2:], ensure_ascii=False, indent=2), encoding="utf-8")
    return [command.args[0], command.args[1], "--arguments-file",
            relative_display(path, project_root=PROJECT_ROOT)]


def main() -> int:
    """Run this script command-line workflow and return its process exit status. The team entry
    point. STAGE_RUNS selects enabled business runs, paths, dates and validation options;
    commands run sequentially and their reports are combined into a session.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Run connected MEDPAR validation or one configured stage")
    parser.add_argument('--stage', choices=tuple(STAGE_RUNS), help="Validate only this configured stage independently")
    parser.add_argument("--dataset", choices=("q61", "r65"), default=DEFAULT_DATASET, help="Dataset profile (default: R65 all-stage review; Q61 explicitly selects connected mode)")
    options = parser.parse_args()
    selected_stage = options.stage
    configured_stages = r65_stage_runs() if options.dataset == "r65" else STAGE_RUNS
    print(f"Selected dataset: {options.dataset.upper()}", flush=True)
    print("Run mode: independent review of all supplied R65 stage boundaries" if options.dataset == "r65" else "Run mode: configured Q61 validation", flush=True)
    session = ReportSession.create(REPORTS_ROOT, project_root=PROJECT_ROOT)
    session_relative = relative_display(session.root, project_root=PROJECT_ROOT)
    if options.dataset == "r65":
        (session.root / "review_scope.json").write_text(json.dumps({"dataset": "R65", "description": "All five supplied stage boundaries reviewed independently. Later supplied outputs are checked even when earlier stages fail. This is not a completed connected journey. Business processing date: 18 March 2025; Split Y0: 2024. No shared snapshot manifest or approved golden physical-byte outputs supplied."}, indent=2), encoding="utf-8")
    if CONNECTED_PIPELINE_ENABLED and selected_stage is None and options.dataset != "r65":
        from medpar_qa.orchestration.connected import run_configured
        journeys, index = run_configured(PROJECT_ROOT, session, STAGE_RUNS, CONNECTED_SETTINGS)
        print(f"Connected pipeline report: {relative_display(index, project_root=PROJECT_ROOT)}")
        for payload, directory in journeys:
            print(f"{payload['source_file']}: {payload['conclusion']}")
        return 1 if any(any(step['status'] in ('FAIL', 'BLOCKED') for step in payload['steps'])
                        for payload, _ in journeys) else 0
    commands = [command for command in build_commands(session_relative, configured_stages) if command.enabled and (selected_stage is None or command.stage == selected_stage)]
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
        launch_args = execution_args(command, session)
        text = _command_text(launch_args)
        print(f"RELATIVE COMMAND: {text}")
        print("#" * 118)

        print("Executing stage validation. Results will appear when this stage finishes; large folders may take time.", flush=True)
        before = {path for path in session.root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            launch_args,
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

    if (selected_stage == "final_medpar" or options.dataset == "r65" and selected_stage is None) and (PROJECT_ROOT / "data/production/r65").is_dir():
        from scripts.run_r65_audit import run_audit
        audit = run_audit(session)
        audit_code = 0 if audit.passed else 1
        unexpected_failures += int(not audit.passed)
        executions.append({"name": "R65 Final lineage, routing and reconciliation audit", "stage": "final_medpar",
            "command": "python scripts/run_r65_audit.py",
            "returncode": audit_code, "expected_exit_codes": (0,), "expected": audit.passed,
            "outcome": "COMPLETED AS EXPECTED" if audit.passed else "BUSINESS FAIL / BLOCKED",
            "output": f"Archive validation counts: {audit.status_counts}",
            "report_files": [relative_display(session.root / "final_medpar/r65_lineage_routing_reconciliation" / name, project_root=PROJECT_ROOT) for name in ("report.html", "report.json")]})
    master = refresh_session_indexes(session.root, executions=executions)
    write_quality_summary(session.root, executions)
    print("\n" + "=" * 118)
    print(f"FINISHED. Unexpected command results: {unexpected_failures}")
    print(f"Timestamped report folder: {session_relative}")
    print(f"Master HTML report: {relative_display(master, project_root=PROJECT_ROOT)}")
    print("Open quality_summary.html for execution overview, then master/index.html for stage details.")
    print("=" * 118)
    return 1 if unexpected_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
