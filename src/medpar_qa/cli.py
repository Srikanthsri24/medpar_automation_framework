"""Manifest-based command line entry point: parse arguments, load aliases/manifest, run Pipeline,
write reports and return success/failure.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline
from medpar_qa.reporting.console_reporter import render_results_text
from medpar_qa.reporting.path_utils import ensure_relative_user_path, relative_display, relative_link, slugify
from medpar_qa.reporting.report_bundle import write_report_bundle
from medpar_qa.reporting.run_layout import ReportSession
from medpar_qa.reporting.session_index import refresh_session_indexes

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Define accepted command-line options and defaults; argparse rejects unsupported command
    syntax.
    """
    parser = argparse.ArgumentParser(description="Run one or all MEDPAR stages from a relative YAML manifest")
    parser.add_argument("--manifest", required=True, help="Relative YAML run-manifest path")
    parser.add_argument("--aliases", default="config/field_aliases.yaml")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--report-session", default=None, help="Relative timestamped report-session directory")
    parser.add_argument("--command-id", default=None)
    parser.add_argument("--failures-only", action="store_true")
    return parser


def main() -> int:
    """Run this script command-line workflow and return its process exit status. Manifest-based
    command line entry point: parse arguments, load aliases/manifest, run Pipeline, write
    reports and return success/failure.
    """
    args = build_parser().parse_args()
    for label, value in (("manifest", args.manifest), ("aliases", args.aliases), ("reports", args.reports)):
        ensure_relative_user_path(value, label)
    if args.report_session:
        ensure_relative_user_path(args.report_session, "report-session")

    manifest = load_manifest(PROJECT_ROOT / args.manifest)
    manifest.base_directory = PROJECT_ROOT
    resolver = FieldResolver.from_yaml(PROJECT_ROOT / args.aliases)
    results = Pipeline(manifest, resolver).run()
    command_id = args.command_id or slugify(manifest.run_id)
    session = ReportSession.create(args.reports, session_path=args.report_session, project_root=PROJECT_ROOT)

    # Create one detailed stage report per requested stage.
    for stage_result in results:
        stage_dir = session.command_directory(stage_result.stage.value, command_id)
        write_report_bundle(
            run_id=f"{manifest.run_id}_{stage_result.stage.value}",
            results=[stage_result],
            output_directory=stage_dir,
            manifest=manifest,
            title=f"MEDPAR {stage_result.stage.value.replace('_', ' ').title()} Detailed Validation Report",
            parent_link=relative_link(stage_dir, session.master_directory / "index.html"),
            context={"command_name": command_id.replace("_", " ").title(), "stage": stage_result.stage.value, "mode": "manifest"},
        )

    # Export distinct error, bypass and statistics files for Final Action.
    from medpar_qa.enums import Stage
    from medpar_qa.stages.final_action.audit import write_final_action_audit
    for stage_result in results:
        if stage_result.stage == Stage.FINAL_ACTION:
            write_final_action_audit(stage_result, session.command_directory(stage_result.stage.value, command_id))

    # Also create a single all-stage detailed report in master/all_stages.
    all_stage_dir = session.master_directory / command_id
    write_report_bundle(
        run_id=manifest.run_id,
        results=results,
        output_directory=all_stage_dir,
        manifest=manifest,
        title="MEDPAR All Five Stages — Detailed Master Validation Report",
        parent_link=relative_link(all_stage_dir, session.master_directory / "index.html"),
        context={"command_name": command_id.replace("_", " ").title(), "stage": "all_stages", "mode": "manifest"},
    )
    master = refresh_session_indexes(session.root)

    print(render_results_text(results, include_pass=not args.failures_only, include_not_applicable=not args.failures_only))
    print("\nGENERATED REPORT SESSION — RELATIVE PATHS")
    print(f"  Session: {relative_display(session.root, project_root=PROJECT_ROOT)}")
    print(f"  Master:  {relative_display(master, project_root=PROJECT_ROOT)}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
