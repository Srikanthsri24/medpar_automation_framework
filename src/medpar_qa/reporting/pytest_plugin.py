"""Pytest hooks that capture each test outcome and emitted QA evidence, then write timestamped test
reports.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from .path_utils import PROJECT_ROOT, ensure_relative_user_path, relative_display, relative_link, slugify
from .rule_catalog import conclusion_text, get_rule_metadata
from .run_layout import ReportSession
from .session_index import refresh_session_indexes

STAGE_MARKERS = ("final_action", "split", "stay", "intermediate", "final_medpar")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the MedPAR-specific pytest report and selection options."""
    group = parser.getgroup("medpar-reporting")
    group.addoption("--medpar-report-dir", action="store", default="reports", help="Relative report root")
    group.addoption("--medpar-report-session", action="store", default=None, help="Relative shared timestamped report-session path")
    group.addoption("--medpar-report-name", action="store", default=None, help="Relative command/report folder name")


def _selection_name(config: pytest.Config) -> str:
    """Derive the human-readable pytest selection label for the session."""
    configured = config.getoption("--medpar-report-name")
    if configured:
        return slugify(configured, "pytest")
    markexpr = str(getattr(config.option, "markexpr", "") or "").strip()
    if markexpr:
        return "pytest_" + slugify(markexpr, "selection")
    return "pytest_complete_suite"


def _selection_stage(config: pytest.Config) -> str:
    """Map a pytest selection/test path to a report stage where possible."""
    markexpr = str(getattr(config.option, "markexpr", "") or "").lower()
    matched = [stage for stage in STAGE_MARKERS if stage in markexpr]
    return matched[0] if len(matched) == 1 else "pytest"


def pytest_configure(config: pytest.Config) -> None:
    """Initialize the pytest report session and hook state."""
    report_root = config.getoption("--medpar-report-dir")
    session_path = config.getoption("--medpar-report-session")
    ensure_relative_user_path(report_root, "medpar-report-dir")
    if session_path:
        ensure_relative_user_path(session_path, "medpar-report-session")
    session = ReportSession.create(report_root, session_path=session_path, project_root=PROJECT_ROOT)
    report_name = _selection_name(config)
    category = _selection_stage(config)
    report_dir = session.command_directory(category, report_name)

    config._medpar_test_reports = {}  # type: ignore[attr-defined]
    config._medpar_report_session = session  # type: ignore[attr-defined]
    config._medpar_report_dir_path = report_dir  # type: ignore[attr-defined]
    config._medpar_report_name_value = report_name  # type: ignore[attr-defined]
    config._medpar_report_category = category  # type: ignore[attr-defined]

    if hasattr(config.option, "htmlpath") and not config.option.htmlpath:
        config.option.htmlpath = str(report_dir / "pytest_standard.html")
        if hasattr(config.option, "self_contained_html"):
            config.option.self_contained_html = True


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    """Capture each pytest setup/call/teardown outcome and attach emitted validation events."""
    outcome = yield
    report = outcome.get_result()
    store = item.config._medpar_test_reports  # type: ignore[attr-defined]
    entry = store.setdefault(
        item.nodeid,
        {
            "nodeid": item.nodeid,
            "name": item.name,
            "markers": sorted(marker.name for marker in item.iter_markers()),
            "description": (item.function.__doc__ or "").strip() if hasattr(item, "function") else "",
            "duration": 0.0,
            "outcome": "passed",
            "stdout": [],
            "stderr": [],
            "longrepr": [],
            "events": [],
        },
    )
    entry["duration"] += float(getattr(report, "duration", 0.0))
    if getattr(report, "capstdout", ""):
        entry["stdout"].append(report.capstdout)
    if getattr(report, "capstderr", ""):
        entry["stderr"].append(report.capstderr)
    captured_events = getattr(item, "_medpar_validation_events", None)
    if captured_events is not None:
        entry["events"] = captured_events
    if report.failed:
        entry["outcome"] = "failed"
        entry["longrepr"].append(str(report.longrepr))
    elif report.skipped and entry["outcome"] != "failed":
        entry["outcome"] = "skipped"


def _esc(value: Any) -> str:
    """Escape text before placing it into HTML so data cannot alter report markup."""
    return html.escape(str(value))


def _pretty(value: Any) -> str:
    """Format values as readable escaped/text JSON for this reporter."""
    if value is None:
        return "Not supplied / not applicable"
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def _event_card(event: dict[str, Any], number: int) -> str:
    """Render one test-captured QA event with its rule/decision evidence."""
    event_type = event.get("event_type", "validation")
    if event_type == "decision":
        return f"<article class='event decision-event'><h4>Decision #{number}: {_esc(event.get('decision'))}</h4><p><strong>Record:</strong> {_esc(event.get('record_id'))}</p><p><strong>Rule:</strong> {_esc(event.get('rule_id'))}</p><p><strong>Explanation:</strong> {_esc(event.get('reason'))}</p></article>"

    stage = str(event.get("stage", "unknown"))
    rule_id = str(event.get("rule_id", "UNKNOWN"))
    status = str(event.get("status", "UNKNOWN"))
    field = event.get("field_name")
    message = str(event.get("message", ""))
    expected = event.get("expected")
    actual = event.get("actual")
    metadata = get_rule_metadata(stage, rule_id, field)
    conclusion = conclusion_text(status=status, message=message, expected=expected, actual=actual, metadata=metadata)
    remediation = f"<p class='remediation'><strong>Recommended action:</strong> {_esc(metadata.remediation)}</p>" if status in {"FAIL", "BLOCKED"} else ""
    return f"""
    <article class='event validation-event status-{_esc(status.lower())}'>
      <div><span class='event-badge {_esc(status.lower())}'>{_esc(status)}</span> <code>{_esc(rule_id)}</code> {f'<span class="field">{_esc(field)}</span>' if field else ''}</div>
      <h4>Validation #{number}: {_esc(metadata.title)}</h4>
      <div class='three'><section><strong>Business requirement</strong><p>{_esc(metadata.requirement)}</p></section><section><strong>What was checked</strong><p>{_esc(metadata.validation)}</p><p><strong>Execution:</strong> {_esc(message)}</p></section><section><strong>Logic</strong><p>{_esc(metadata.logic)}</p></section></div>
      <div class='two'><section><strong>Expected</strong><pre>{_esc(_pretty(expected))}</pre></section><section><strong>Observed</strong><pre>{_esc(_pretty(actual))}</pre></section></div>
      <p class='conclusion {_esc(status.lower())}'><strong>Conclusion:</strong> {_esc(conclusion)}</p>{remediation}
      <details><summary>Source evidence and validator</summary><pre>{_esc(_pretty({'source_files': event.get('source_files'), 'record_ids': event.get('record_ids'), 'group_key': event.get('group_key'), 'evidence': event.get('evidence')}))}</pre></details>
    </article>"""


def _render_test(entry: dict[str, Any], index: int) -> str:
    """Render the test result, failure output and captured rule evidence."""
    outcome = entry["outcome"]
    captured = "\n".join(entry["stdout"] + entry["stderr"]).strip()
    error = "\n".join(entry["longrepr"]).strip()
    markers = ", ".join(entry["markers"]) or "None"
    events = entry.get("events") or []
    event_html = "".join(_event_card(event, i) for i, event in enumerate(events, 1))
    search = " ".join([entry["nodeid"], outcome, markers, entry["description"], captured, error, json.dumps(events, default=str)]).lower()
    return f"""
    <article class="test-card {outcome}" data-status="{_esc(outcome)}" data-search="{_esc(search)}">
      <div class="test-head"><span>#{index}</span><span class="badge {outcome}">{outcome.upper()}</span><strong>{_esc(entry['nodeid'])}</strong><span class="duration">{entry['duration']:.3f}s</span></div>
      <p><strong>Markers:</strong> {_esc(markers)}</p>
      {f'<p><strong>Test purpose:</strong> {_esc(entry["description"])}</p>' if entry['description'] else ''}
      <h3>Business validation evidence emitted by this test</h3>
      {event_html or '<p class="notice">This test did not emit RuleResult evidence. Review the test assertion and captured output below.</p>'}
      <details><summary>Captured terminal/print output</summary><pre>{_esc(captured or 'No captured output.')}</pre></details>
      {f'<details open><summary>Pytest failure reason and traceback</summary><pre class="error">{_esc(error)}</pre></details>' if error else ''}
    </article>"""


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write the final pytest artifacts and refresh the session indexes."""
    config = session.config
    entries = list(config._medpar_test_reports.values())  # type: ignore[attr-defined]
    report_dir: Path = config._medpar_report_dir_path  # type: ignore[attr-defined]
    output = report_dir / "report.html"
    counts = {
        "passed": sum(item["outcome"] == "passed" for item in entries),
        "failed": sum(item["outcome"] == "failed" for item in entries),
        "skipped": sum(item["outcome"] == "skipped" for item in entries),
    }
    cards = "".join(_render_test(item, i) for i, item in enumerate(entries, 1))
    master_link = relative_link(report_dir, config._medpar_report_session.master_directory / "index.html")  # type: ignore[attr-defined]
    document = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MEDPAR Pytest Detailed Report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f9;color:#172033;margin:0;line-height:1.45}}header{{background:#102a43;color:#fff;padding:26px}}header a{{color:#fff}}main{{max-width:1600px;margin:auto;padding:22px}}.summary{{display:flex;gap:12px;flex-wrap:wrap;margin:15px 0}}.summary div{{background:#fff;border:1px solid #d0d5dd;border-radius:9px;padding:12px 18px}}.toolbar{{position:sticky;top:0;background:#e9eef5;padding:10px;border:1px solid #d0d5dd;border-radius:8px;z-index:2}}input,select{{padding:8px;border:1px solid #98a2b3;border-radius:6px}}input{{width:min(800px,70%)}}.test-card{{background:#fff;border:1px solid #d0d5dd;border-left:6px solid #087f5b;border-radius:9px;padding:15px;margin:12px 0}}.test-card.failed{{border-left-color:#c92a2a}}.test-card.skipped{{border-left-color:#d97706}}.test-head{{display:flex;gap:9px;align-items:center;flex-wrap:wrap}}.badge,.event-badge,.field{{padding:4px 9px;border-radius:999px;font-weight:800;font-size:12px}}.badge.passed,.event-badge.pass{{background:#d3f9d8;color:#087f5b}}.badge.failed,.event-badge.fail{{background:#ffe3e3;color:#c92a2a}}.badge.skipped,.event-badge.blocked{{background:#fff3bf;color:#8d5500}}.event-badge.not_applicable{{background:#dbeafe;color:#1864ab}}.field{{background:#ede9fe;color:#5f3dc4}}.duration{{margin-left:auto;color:#667085}}.event{{border:1px solid #d0d5dd;border-left:6px solid #98a2b3;border-radius:8px;padding:12px;margin:10px 0}}.event.status-pass{{border-left-color:#087f5b}}.event.status-fail{{border-left-color:#c92a2a}}.event.status-blocked{{border-left-color:#d97706}}.three,.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}}.three section,.two section{{border:1px solid #d0d5dd;border-radius:8px;padding:10px;min-width:0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#172033;color:#fff;padding:11px;border-radius:7px;max-height:500px;overflow:auto}}pre.error{{border-left:5px solid #c92a2a}}.conclusion{{padding:11px;border-radius:8px}}.conclusion.pass{{background:#e6fcf5}}.conclusion.fail{{background:#fff0f0}}.conclusion.blocked{{background:#fff9db}}.conclusion.not_applicable{{background:#e7f5ff}}.remediation{{background:#fff4e6;border-left:5px solid #d97706;padding:10px}}.hidden{{display:none}}.notice{{background:#eef6ff;padding:10px;border-left:5px solid #1864ab}}</style></head>
<body><header><a href='{_esc(master_link)}'>← Master report</a><h1>MEDPAR Pytest Detailed Report</h1><p>Selection: {_esc(config._medpar_report_name_value)}</p><p>Generated: {_esc(datetime.now().astimezone().isoformat(timespec='seconds'))}</p><p>Exit status: {exitstatus}</p></header><main>
<section class='summary'><div>Total <strong>{len(entries)}</strong></div><div>Passed <strong>{counts['passed']}</strong></div><div>Failed <strong>{counts['failed']}</strong></div><div>Skipped <strong>{counts['skipped']}</strong></div></section><div class='toolbar'><input id='q' placeholder='Search test, rule, field, expected, observed...' oninput='filterTests()'><select id='status' onchange='filterTests()'><option value='all'>All</option><option value='passed'>Passed</option><option value='failed'>Failed</option><option value='skipped'>Skipped</option></select></div>{cards}</main><script>function filterTests(){{const q=document.getElementById('q').value.toLowerCase();const s=document.getElementById('status').value;document.querySelectorAll('.test-card').forEach(c=>c.classList.toggle('hidden',!((!q||c.dataset.search.includes(q))&&(s==='all'||c.dataset.status===s))));}}</script></body></html>"""
    output.write_text(document, encoding="utf-8")
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "exit_status": exitstatus,
        "passed": exitstatus == 0,
        "summary": {"total": len(entries), **counts},
        "tests": entries,
    }
    (report_dir / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (report_dir / "report.txt").write_text("\n\n".join("\n".join(item["stdout"] + item["stderr"]) for item in entries), encoding="utf-8")
    config._medpar_detailed_report_path = output  # type: ignore[attr-defined]
    refresh_session_indexes(config._medpar_report_session.root)  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    """Print the paths and outcome summary of the generated pytest reports."""
    output = getattr(config, "_medpar_detailed_report_path", None)
    if output:
        terminalreporter.write_sep("=", f"MEDPAR detailed HTML report: {relative_display(output, project_root=PROJECT_ROOT)}")
    htmlpath = getattr(config.option, "htmlpath", None)
    if htmlpath:
        terminalreporter.write_line(f"Standard pytest HTML report: {relative_display(htmlpath, project_root=PROJECT_ROOT)}")
