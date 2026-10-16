"""Write the coordinated text/JSON/HTML and audit artifacts for one business run."""
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
    """Represent report bundle with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
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
    """Write coordinated report artifacts and indexes for the business-run result."""
    stage_results = list(results)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    from .stage_audit import write_stage_audit
    for result in stage_results:
        write_stage_audit(result, directory)

    handoff = (context or {}).get('handoff', {})
    if handoff.get('status') in ('BEFORE_START', 'NOT_REACHED'):
        # No validators ran. Retain the route and reason without rendering hundreds
        # of duplicate, inapplicable rule cards for every downstream group.
        import html
        from .status_navigation import page
        state = handoff['status']
        body = '<p><strong>' + html.escape(state) + '</strong> — no rows were processed in this stage.</p>'
        body += '<p>' + html.escape(handoff.get('reason', 'Stage not requested')) + '</p>'
        if parent_link:
            body += '<p><a href="' + html.escape(parent_link, quote=True) + '">Open input journey and upstream stopping evidence</a></p>'
        html_path = directory / 'report.html'
        document = page(title, body)
        if parent_link:
            document = document.replace('href="index.html#stage-results"', 'href="' + html.escape(parent_link, quote=True) + '"')
        html_path.write_text(document, encoding='utf-8')
    else:
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
