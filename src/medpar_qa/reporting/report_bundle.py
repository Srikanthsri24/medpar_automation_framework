from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from medpar_qa.models import RunManifest, StageResult
from medpar_qa.reporting.console_reporter import render_results_text
from medpar_qa.reporting.html_reporter import write_html_report
from medpar_qa.reporting.json_reporter import write_json_report


@dataclass(frozen=True)
class ReportBundle:
    html: Path
    json: Path
    text: Path


def write_report_bundle(
    *,
    run_id: str,
    results: Iterable[StageResult],
    output_directory: str | Path,
    manifest: RunManifest | None = None,
    title: str = "MEDPAR QA Detailed Validation Report",
    parent_link: str | None = None,
    context: dict[str, Any] | None = None,
) -> ReportBundle:
    stage_results = list(results)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)

    html_path = write_html_report(
        run_id,
        manifest.run_date if manifest else "Not supplied",
        stage_results,
        directory,
        manifest=manifest,
        title=title,
        filename="report.html",
        parent_link=parent_link,
    )
    json_path = write_json_report(
        run_id,
        stage_results,
        directory,
        run_date=manifest.run_date if manifest else None,
        filename="report.json",
        context=context,
    )
    text_path = directory / "report.txt"
    text_path.write_text(
        render_results_text(stage_results, include_pass=True, include_not_applicable=True),
        encoding="utf-8",
    )
    return ReportBundle(html=html_path, json=json_path, text=text_path)
