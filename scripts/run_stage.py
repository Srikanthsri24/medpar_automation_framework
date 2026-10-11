"""Run one stage from relative file/folder paths, construct its manifest/settings and publish stage
evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from medpar_qa.enums import FileRole, Stage  # noqa: E402
from medpar_qa.models import ManifestFile, RunManifest, StageResult  # noqa: E402
from medpar_qa.normalization.fields import FieldResolver  # noqa: E402
from medpar_qa.orchestration.pipeline import Pipeline  # noqa: E402
from medpar_qa.reporting.console_reporter import render_results_text  # noqa: E402
from medpar_qa.reporting.path_utils import (  # noqa: E402
    ensure_relative_user_path,
    relative_display,
    relative_link,
    slugify,
)
from medpar_qa.reporting.report_bundle import write_report_bundle  # noqa: E402
from medpar_qa.reporting.run_layout import ReportSession  # noqa: E402
from medpar_qa.reporting.session_index import refresh_session_indexes  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """Define accepted command-line options and defaults; argparse rejects unsupported command
    syntax.
    """
    parser = argparse.ArgumentParser(
        description="Run one MEDPAR stage against one file, multiple files, or a relative wildcard."
    )
    parser.add_argument("--stage", required=True, choices=[stage.value for stage in Stage])
    parser.add_argument("--run-date", required=True, help="Business date in YYYY-MM-DD format")
    parser.add_argument("--source", action="append", required=True, help="Relative source file or wildcard. Repeat as needed.")
    parser.add_argument("--actual", action="append", default=[], help="Relative actual-output file or wildcard")
    parser.add_argument("--expected", action="append", default=[], help="Relative expected/golden file or wildcard")
    parser.add_argument("--mode", choices=("calculate", "reconcile", "golden"), default="calculate")
    parser.add_argument("--require-matching-snapshot", action="store_true", help="Block reconciliation when extraction snapshot metadata differs or is unavailable")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--command-id", default=None, help="Folder name for this command inside the stage folder")
    parser.add_argument("--aliases", default="config/field_aliases.yaml")
    parser.add_argument("--reports", default="reports", help="Relative root used when no report session is supplied")
    parser.add_argument("--report-session", default=None, help="Relative timestamped report-session directory shared by commands")
    parser.add_argument("--final-extract", action="store_true", help="Final delivered JSON omits Intermediate Split-Year Indicator")
    parser.add_argument("--split-current-year", type=int, help="Explicit Split Y0 business year")
    parser.add_argument("--per-file", action="store_true", help="Independent source-only checks; do not group identities across files")
    parser.add_argument("--show-pass", action="store_true", help="PASS validations are printed by default; retained for compatibility")
    parser.add_argument("--failures-only", action="store_true", help="Terminal only: hide PASS and N/A checks")
    return parser


def parse_stage_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Load UTF-8 JSON arguments when the runner uses a compact Windows-safe command."""
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "--arguments-file":
        if len(values) != 2:
            raise SystemExit("--arguments-file requires exactly one file path")
        ensure_relative_user_path(values[1], "arguments-file")
        values = json.loads((PROJECT_ROOT / values[1]).read_text(encoding="utf-8"))
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise SystemExit("Arguments file must contain a JSON list of strings")
    return build_parser().parse_args(values)


def _manifest_files(stage: Stage, role: FileRole, paths: list[str]) -> list[ManifestFile]:
    """Convert stage CLI source/actual/expected arguments into typed manifest file entries."""
    return [ManifestFile(path=path, stage=stage, role=role) for path in paths]


def _stage_settings(stage: Stage, mode: str) -> dict:
    """Construct the selected stage settings from approved defaults and explicit CLI options."""
    require_actual = mode in {"reconcile", "golden"}
    require_expected = mode == "golden"
    all_settings: dict[str, dict] = {
        "final_action": {
            "rule1_keep_qcs": [1, 3, 5],
            "allowed_query_codes": [0, 1, 3, 5],
            "allowed_transaction_codes": [0, 1, 2, 3, 4],
            "block_ambiguous_ordering": True,
            "rule6_enabled": True,
        },
        "split": {"window_years": 4, "skip_transaction_codes": [], "require_actual_output": require_actual},
        "stay": {"decimal_scale": "0.001", "require_actual_output": require_actual, "require_expected_output": require_expected},
        "intermediate": {"window_years": 5, "decimal_scale": "0.001", "require_actual_output": require_actual, "require_expected_output": require_expected, "ndc_length": 11},
        "final_medpar": {"expected_bytes": 3000, "encoding": "ascii", "require_actual_output": require_actual, "require_expected_output": require_expected, "allowed_classifications": ["S", "L", "N"]},
    }
    return {stage.value: all_settings[stage.value]}


def _validate_relative_paths(args: argparse.Namespace) -> None:
    """Reject absolute user-supplied business paths so the configuration can be shared across
    machines.
    """
    for label, values in (("source", args.source), ("actual", args.actual), ("expected", args.expected)):
        for value in values:
            ensure_relative_user_path(value, label)
    ensure_relative_user_path(args.aliases, "aliases")
    ensure_relative_user_path(args.reports, "reports")
    if args.report_session:
        ensure_relative_user_path(args.report_session, "report-session")


def main() -> int:
    """Run this script command-line workflow and return its process exit status. Run one stage from
    relative file/folder paths, construct its manifest/settings and publish stage evidence.
    """
    args = parse_stage_args()
    _validate_relative_paths(args)
    stage = Stage(args.stage)
    run_date = date.fromisoformat(args.run_date)
    if args.mode in {"reconcile", "golden"} and not args.actual:
        raise SystemExit(f"--mode {args.mode} requires at least one --actual path")
    if args.mode == "golden" and not args.expected:
        raise SystemExit("--mode golden requires at least one --expected path")

    files = [
        *_manifest_files(stage, FileRole.SOURCE, args.source),
        *_manifest_files(stage, FileRole.ACTUAL_OUTPUT, args.actual),
        *_manifest_files(stage, FileRole.EXPECTED_OUTPUT, args.expected),
    ]
    run_id = args.run_id or f"{stage.value}_{run_date.isoformat()}"
    command_id = args.command_id or slugify(run_id)
    settings = _stage_settings(stage, args.mode)
    if stage == Stage.INTERMEDIATE:
        settings[stage.value]["deduplicate_filename_exports"] = True
    if args.final_extract:
        if stage != Stage.FINAL_MEDPAR:
            raise ValueError("--final-extract is for Final MEDPAR only")
        settings[stage.value]["split_indicator_in_output"] = False
        settings[stage.value]["identity_fields"] = ["hicn", "provider_id", "admission_date"]
    if args.split_current_year is not None:
        if stage != Stage.SPLIT:
            raise ValueError("--split-current-year is for Split only")
        settings[stage.value]["current_year"] = args.split_current_year
    settings[stage.value]["require_matching_snapshot"] = args.require_matching_snapshot
    manifest = RunManifest(
        run_id=run_id,
        run_date=run_date,
        files=files,
        settings=settings,
        base_directory=PROJECT_ROOT,
    )

    session = ReportSession.create(
        args.reports,
        session_path=args.report_session,
        project_root=PROJECT_ROOT,
    )
    output_directory = session.command_directory(stage.value, command_id)
    parent_link = relative_link(output_directory, session.master_directory / "index.html")

    resolver = FieldResolver.from_yaml(PROJECT_ROOT / args.aliases)
    if args.per_file:
        if args.mode != "calculate" or args.actual or args.expected:
            raise ValueError("--per-file supports source-only calculate checks")
        from medpar_qa.ingestion.discovery import discover_files
        results_by_stage = {}
        for source in files:
            paths = discover_files(source.path, PROJECT_ROOT)
            for path in paths or [PROJECT_ROOT / source.path]:
                single = RunManifest(run_id=run_id, run_date=run_date,
                    files=[ManifestFile(path=relative_display(path, project_root=PROJECT_ROOT), stage=stage, role=FileRole.SOURCE)],
                    settings=settings, base_directory=PROJECT_ROOT)
                for result in Pipeline(single, resolver).run():
                    combined = results_by_stage.setdefault(result.stage, StageResult(result.stage))
                    combined.rule_results.extend(result.rule_results)
                    combined.decisions.extend(result.decisions)
        results = list(results_by_stage.values())
    else:
        results = Pipeline(manifest, resolver).run()
    bundle = write_report_bundle(
        run_id=run_id,
        results=results,
        output_directory=output_directory,
        manifest=manifest,
        title=f"MEDPAR {stage.value.replace('_', ' ').title()} Detailed Validation Report",
        parent_link=parent_link,
        context={
            "command_name": command_id.replace("_", " ").title(),
            "stage": stage.value,
            "mode": args.mode,
            "source_paths": args.source,
            "actual_paths": args.actual,
            "expected_paths": args.expected,
        },
    )
    if stage == Stage.FINAL_ACTION:
        from medpar_qa.stages.final_action.audit import write_final_action_audit
        for result in results:
            if result.stage == Stage.FINAL_ACTION:
                write_final_action_audit(result, output_directory)
    master = refresh_session_indexes(session.root)

    print("\n" + "=" * 118)
    print(f"RUN ID: {run_id}")
    print(f"STAGE: {stage.value}")
    print(f"MODE: {args.mode}")
    print(f"REPORT SESSION: {relative_display(session.root, project_root=PROJECT_ROOT)}")
    print("=" * 118)
    print(
        render_results_text(
            results,
            include_pass=not args.failures_only,
            include_not_applicable=not args.failures_only,
        )
    )
    print("\nGENERATED REPORTS — RELATIVE PATHS")
    print(f"  Stage HTML: {relative_display(bundle.html, project_root=PROJECT_ROOT)}")
    print(f"  Stage JSON: {relative_display(bundle.json, project_root=PROJECT_ROOT)}")
    print(f"  Stage text: {relative_display(bundle.text, project_root=PROJECT_ROOT)}")
    print(f"  Master HTML: {relative_display(master, project_root=PROJECT_ROOT)}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
