"""Combine saved business and pytest reports into per-stage and master indexes, metric definitions
and overall conclusions.
"""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .file_review import file_review, readable_time, stage_conclusion, FILE_FILTER_SCRIPT
from .path_utils import relative_link
from .stage_volume import summarize_stage_volume, volume_strip
from .rule_catalog import conclusion_text, get_rule_metadata


def _esc(value: Any) -> str:
    """Escape text before placing it into HTML so data cannot alter report markup."""
    return html.escape(str(value))


def _pretty(value: Any) -> str:
    """Format values as readable escaped/text JSON for this reporter."""
    if value is None:
        return "Not supplied / not applicable"
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a saved JSON report for index generation, honoring the existing malformed/missing-
    report handling.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _business_report_entries(session_root: Path) -> list[dict[str, Any]]:
    """Discover saved business-run report entries in the session."""
    entries: list[dict[str, Any]] = []
    for path in sorted(session_root.glob("*/*/report.json")):
        if path.parts[-3] in {"master", "pytest"}:
            continue
        payload = _read_json(path)
        if payload and "stages" in payload:
            entries.append({"path": path, "payload": payload, "stage_folder": path.parts[-3], "command_folder": path.parts[-2]})
    return entries


def _pytest_report_entries(session_root: Path) -> list[dict[str, Any]]:
    """Discover saved pytest-run entries in the session."""
    entries: list[dict[str, Any]] = []
    for path in sorted(session_root.glob("pytest/*/report.json")):
        payload = _read_json(path)
        if payload:
            entries.append({"path": path, "payload": payload, "stage_folder": "pytest", "command_folder": path.parts[-2]})
    return entries


def _report_summary(payload: dict[str, Any]) -> dict[str, int]:
    """Summarize a saved business report, keeping validation counts separate from command exit
    status.
    """
    summary = payload.get("summary") or {}
    return {
        "pass": int(summary.get("pass", summary.get("passed", 0)) or 0),
        "fail": int(summary.get("fail", summary.get("failed", 0)) or 0),
        "blocked": int(summary.get("blocked", 0) or 0),
        "not_applicable": int(summary.get("not_applicable", summary.get("skipped", 0)) or 0),
        "validation_count": int(summary.get("validation_count", summary.get("total", 0)) or 0),
    }


def write_stage_index(session_root: str | Path, stage_name: str) -> Path:
    """Write a stage index combining its run/file summaries and links."""
    root = Path(session_root)
    stage_dir = root / stage_name
    stage_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    for report_json in sorted(stage_dir.glob("*/report.json")):
        payload = _read_json(report_json)
        if payload:
            reports.append({"json": report_json, "payload": payload})

    rows: list[str] = []
    total = Counter()
    for item in reports:
        payload = item["payload"]
        summary = _report_summary(payload)
        total.update(summary)
        command_name = (payload.get("context") or {}).get("command_name") or item["json"].parent.name.replace("_", " ").title()
        passed = bool(payload.get("passed"))
        link = relative_link(stage_dir, item["json"].parent / "report.html")
        rows.append(
            f"<tr><td><a href='{_esc(link)}'>{_esc(command_name)}</a></td><td><span class='status {'pass' if passed else 'fail'}'>{'PASS' if passed else 'FAIL / BLOCKED'}</span></td><td>{summary['validation_count']}</td><td>{summary['pass']}</td><td>{summary['fail']}</td><td>{summary['blocked']}</td><td>{summary['not_applicable']}</td></tr>"
        )

    master_link = relative_link(stage_dir, root / "master" / "index.html")
    document = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{_esc(stage_name)} reports</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f9;color:#172033}}header{{background:#102a43;color:#fff;padding:26px}}main{{max-width:1400px;margin:auto;padding:24px}}a{{color:#1864ab}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid #d0d5dd;padding:10px;text-align:left}}th{{background:#edf2f7}}.summary{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}.summary div{{background:#fff;border:1px solid #d0d5dd;border-radius:9px;padding:12px 18px}}.status{{padding:4px 9px;border-radius:999px;font-weight:800}}.status.pass{{background:#d3f9d8;color:#087f5b}}.status.fail{{background:#ffe3e3;color:#c92a2a}}.file-review{{border:1px solid #d0d5dd;border-radius:10px;margin:10px 0;padding:12px;overflow-wrap:anywhere}}.file-review summary{{cursor:pointer;font-weight:700}}.file-conclusion{{padding:14px;background:#edf2f7;border-radius:8px}}.file-inventory table{{table-layout:fixed}}.file-inventory td{{overflow-wrap:anywhere}}
.volume-strip{{display:grid;grid-template-columns:repeat(7,minmax(70px,1fr));gap:12px;margin-top:14px}}.volume-cell span{{display:block;font-size:12px;font-weight:400}}.volume-cell strong{{display:block;font-size:22px}}.volume-cell:nth-child(3){{border-right:1px solid #cbd5e1}}.volume-cell:nth-child(2) strong,.volume-cell:nth-child(5) strong{{color:#087f5b}}.volume-cell:nth-child(3) strong,.volume-cell:nth-child(7) strong{{color:#c92a2a}}.volume-cell:nth-child(6) strong{{color:#996600}}.volume-cell a{{color:inherit}}@media(max-width:700px){{.volume-strip{{grid-template-columns:repeat(3,1fr)}}}}.file-toolbar,.stage-conclusion,.overall-conclusion{{padding:16px;margin:16px 0;background:#eef6ff;border:1px solid #b6c9de;border-radius:10px}}.file-toolbar input,.file-toolbar select{{padding:9px;max-width:100%;margin:8px;border:1px solid #98a2b3;border-radius:6px}}.file-toolbar select{{width:100%}}.stage-conclusion td{{overflow-wrap:anywhere}}[hidden]{{display:none!important}}
</style></head>
<body><header><a style='color:white' href='{_esc(master_link)}'>← Master report</a><h1>{_esc(stage_name.replace('_',' ').title())} — Stage Report Index</h1><p>Timestamped session: {_esc(root.name)}</p></header><main>
<section class='summary'><div>Runs <strong>{len(reports)}</strong></div><div>Validations <strong>{total['validation_count']}</strong></div><div>Pass <strong>{total['pass']}</strong></div><div>Fail <strong>{total['fail']}</strong></div><div>Blocked <strong>{total['blocked']}</strong></div></section>
<table><thead><tr><th>Stage command / file selection</th><th>Status</th><th>Validations</th><th>Pass</th><th>Fail</th><th>Blocked</th><th>N/A</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="7">No reports generated for this stage.</td></tr>'}</tbody></table></main><script>function openEvidence(){{if(!location.hash)return;const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(target){{if(target.tagName==='DETAILS')target.open=true;for(let p=target.parentElement;p;p=p.parentElement){{if(p.tagName==='DETAILS')p.open=true;}}target.classList.remove('hidden');target.scrollIntoView({{block:'start'}});}}}}window.addEventListener('hashchange',openEvidence);window.addEventListener('load',openEvidence);</script>{FILE_FILTER_SCRIPT}</body></html>"""
    output = stage_dir / "index.html"
    output.write_text(document, encoding="utf-8")
    return output


def _render_raw_validation(validation: dict[str, Any], stage: str, number: int, prefix: str = "check") -> str:
    """Render a saved validation payload in the master report without requiring live processor
    objects.
    """
    status = str(validation.get("status", "UNKNOWN"))
    rule_id = str(validation.get("rule_id", "UNKNOWN"))
    field = validation.get("field_name")
    metadata = get_rule_metadata(stage, rule_id, field)
    expected = validation.get("expected")
    actual = validation.get("actual")
    message = str(validation.get("message", ""))
    conclusion = conclusion_text(
        status=status,
        message=message,
        expected=expected,
        actual=actual,
        metadata=metadata,
    )
    remediation = f"<p><strong>Recommended action:</strong> {_esc(metadata.remediation)}</p>" if status in {"FAIL", "BLOCKED"} else ""
    return f"""
    <article id='{_esc(prefix)}-{number}' data-files='{_esc(json.dumps(validation.get('source_files') or []))}' class='validation status-{_esc(status.lower())}'>
      <div><span class='badge {_esc(status.lower())}'>{_esc(status)}</span> <code>{_esc(rule_id)}</code> {f'<span class="field">{_esc(field)}</span>' if field else ''}</div>
      <h4>#{number} {_esc(metadata.title)}</h4>
      <div class='three'><section><strong>Business requirement</strong><p>{_esc(metadata.requirement)}</p></section><section><strong>What was checked</strong><p>{_esc(metadata.validation)}</p></section><section><strong>Evaluation logic</strong><p>{_esc(metadata.logic)}</p></section></div>
      <div class='two'><section><strong>Expected</strong><pre>{_esc(_pretty(expected))}</pre></section><section><strong>Observed</strong><pre>{_esc(_pretty(actual))}</pre></section></div>
      <div class='conclusion {_esc(status.lower())}'><strong>Conclusion:</strong> {_esc(conclusion)}</div>{remediation}
      <details><summary>Source evidence</summary><pre>{_esc(_pretty({'source_files': validation.get('source_files'), 'record_ids': validation.get('record_ids'), 'group_key': validation.get('group_key'), 'evidence': validation.get('evidence')}))}</pre></details>
    </article>"""


def write_master_index(session_root: str | Path, executions: list[dict[str, Any]] | None = None) -> Path:
    """Write the session dashboard, metric definitions, command outcomes, all-stage conclusions and
    rule evidence.
    """
    root = Path(session_root)
    master = root / "master"
    master.mkdir(parents=True, exist_ok=True)
    business_entries = _business_report_entries(root)
    pytest_entries = _pytest_report_entries(root)

    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals = Counter()
    for entry in business_entries:
        for stage_payload in entry["payload"].get("stages", []):
            stage = str(stage_payload.get("stage", entry["stage_folder"]))
            by_stage[stage].append({"entry": entry, "stage": stage_payload})
            for result in stage_payload.get("rule_results", []):
                totals[str(result.get("status", "UNKNOWN")).lower()] += 1
                totals["validations"] += 1

    try:
        session_started = datetime.strptime(root.name, "%Y%m%d_%H%M%S").strftime("%d %B %Y at %I:%M:%S %p")
    except ValueError:
        session_started = "Not recorded in session ID"
    scope_payload = _read_json(root / "review_scope.json") or {}
    scope_note = f"<p><strong>Review scope:</strong> {_esc(scope_payload.get('description', ''))}</p>" if scope_payload else ""
    command_cards: list[str] = []
    if executions:
        for index, item in enumerate(executions, start=1):
            execution_expected = item.get("expected", False)
            business_payloads = []
            pytest_payloads = []
            unique_paths = []
            for path in item.get("report_files", []):
                path = Path(path)
                if not path.exists() or path in unique_paths:
                    continue
                unique_paths.append(path)
                if path.name == "report.json":
                    payload = _read_json(path) or {}
                    if "stages" in payload:
                        business_payloads.append(payload)
                    elif "tests" in payload:
                        pytest_payloads.append(payload)
            if business_payloads:
                business_passed = all(bool(payload.get("passed")) for payload in business_payloads)
                result_label = "BUSINESS PASS" if business_passed else "BUSINESS FAIL / BLOCKED"
                result_class = "pass" if business_passed else "fail"
            elif pytest_payloads:
                business_passed = all(bool(payload.get("passed")) for payload in pytest_payloads)
                result_label = "TESTS PASS" if business_passed else "TESTS FAIL"
                result_class = "pass" if business_passed else "fail"
            else:
                result_label = "NO BUSINESS REPORT FOUND"
                result_class = "neutral"
            report_links = "".join(
                f"<li><a href='{_esc(relative_link(master, path))}'>{_esc(relative_link(root, path))}</a></li>"
                for path in unique_paths
                if not (path == master / "index.html")
            ) or "<li>No detailed report was generated.</li>"
            console_output = str(item.get('output', ''))
            if len(console_output) > 20000:
                console_output = console_output[:20000] + "\n[Console preview shortened. Complete rule results are shown below; the full console.log remains in the command report folder.]"
            execution_label = "EXECUTION COMPLETED AS EXPECTED" if execution_expected else "UNEXPECTED EXECUTION RESULT"
            command_cards.append(
                f"<details class='command {'pass' if execution_expected else 'fail'}'><summary>#{index} — {_esc(item.get('name','Command'))} · {_esc(execution_label)} · {_esc(result_label)}</summary><p><strong>Execution status:</strong> {_esc(execution_label)} (exit {_esc(item.get('returncode'))}; expected {_esc(item.get('expected_exit_codes'))})</p><p><strong>Business/test status:</strong> <span class='business-status {result_class}'>{_esc(result_label)}</span></p><p><strong>Category:</strong> {_esc(item.get('stage','other'))}</p><p><strong>Relative command:</strong> <code>{_esc(item.get('command',''))}</code></p><p><strong>Generated reports:</strong></p><ul>{report_links}</ul><details><summary>Console output</summary><pre>{_esc(console_output)}</pre></details></details>"
            )

    stage_blocks = {}
    for stage in sorted(by_stage, key=lambda name: ['final_action', 'split', 'stay', 'intermediate', 'final_medpar'].index(name) if name in ['final_action', 'split', 'stay', 'intermediate', 'final_medpar'] else 99):
        items = by_stage[stage]
        command_sections: list[str] = []
        stage_count = Counter()
        for command_index, item in enumerate(items, 1):
            entry = item["entry"]
            stage_payload = item["stage"]
            validations = stage_payload.get("rule_results", [])
            for validation in validations:
                stage_count[str(validation.get("status", "UNKNOWN")).lower()] += 1
            report_link = relative_link(master, entry["path"].parent / "report.html")
            command_name = (entry["payload"].get("context") or {}).get("command_name") or entry["command_folder"].replace("_", " ").title()
            cards = "" if len(validations) >= 1000 else "".join(
                _render_raw_validation(validation, stage, number, f"{stage}-{command_index}")
                for number, validation in enumerate(validations, start=1)
            )
            inline_files = f"<p><a href='{stage}_pass_files.html'>Passed-check files</a> · <a href='{stage}_fail_files.html'>Failed-check files</a> · <a href='{stage}_blocked_files.html'>Blocked-check files</a></p>" + (file_review(stage, validations, stage + '-' + str(command_index)) if len(validations) < 1000 else '')
            if len(validations) >= 1000:
                cards = f"<a href='{_esc(report_link)}'>Open complete original rule report</a> — or use the file links above for individual file proof."
            run_info = f"<p><strong>Business processing date:</strong> {_esc(entry['payload'].get('run_date', 'Not recorded'))} · <strong>Validation generated:</strong> {_esc(readable_time(entry['payload'].get('generated_at', 'Not recorded')))}</p>"
            command_sections.append(
                f"<details class='command-report'><summary>{_esc(command_name)} — {'PASS' if stage_payload.get('passed') else 'FAIL / BLOCKED'} · {len(validations)} validations</summary><p><a href='{_esc(report_link)}'>Open full report</a></p>{run_info}{inline_files}<details><summary>Full rule explanations and evidence — open any rule link above</summary>{cards}</details></details>"
            )
        from .status_navigation import write_status_navigation
        all_stage_checks = [c for item in items for c in item['stage'].get('rule_results', [])]
        write_status_navigation(master, stage, all_stage_checks, _render_raw_validation)
        stage_index_link = relative_link(master, root / stage / "index.html")
        volume = summarize_stage_volume(all_stage_checks, [d for item in items for d in item['stage'].get('decisions', [])])
        stage_volume_strip = volume_strip(volume, lambda key: f'{stage}_volume_{key}.html')
        from .status_navigation import write_volume_navigation
        write_volume_navigation(master, stage, all_stage_checks, volume)
        stage_blocks[stage] = (
            f"<details id='stage-{_esc(stage)}' class='stage'><summary><span class='stage-title'>{_esc(stage.replace('_',' ').title())}</span>{stage_volume_strip}</summary><p><a href='{_esc(stage_index_link)}'>Open stage report index</a></p>{''.join(command_sections)}{stage_conclusion(stage, all_stage_checks)}</details>"
        )

    ordered_stages = ['final_action', 'split', 'stay', 'intermediate', 'final_medpar']
    stage_sections = [stage_blocks.get(stage, f"<details id='stage-{_esc(stage)}' class='stage'><summary>{_esc(stage.replace('_',' ').title())} — Not run</summary><p>No recorded stage report; no file or record acceptance result is available.</p></details>") for stage in ordered_stages]
    from .transfers import independent_transfers
    transfer_table = independent_transfers(master, by_stage)
    overall_conclusions = ''.join(stage_conclusion(stage, [c for item in items for c in item['stage'].get('rule_results', [])]) for stage, items in by_stage.items())
    missing_stages = [stage for stage in ['final_action', 'split', 'stay', 'intermediate', 'final_medpar'] if stage not in by_stage]
    missing_stage_notes = ''.join(f"<p><strong>{_esc(stage.replace('_', ' ').title())}: NOT RUN / NO RESULT.</strong> No stage validation report was included in this session; acceptance cannot be established.</p>" for stage in missing_stages)
    overall_state = 'FAIL' if totals['fail'] else 'BLOCKED' if totals['blocked'] else 'WITH KNOWN DIFFERENCES' if totals['known_difference'] else 'PASS' if totals['pass'] else 'NOT ESTABLISHED'
    pytest_rows = ""
    for entry in pytest_entries:
        summary = entry["payload"].get("summary", {})
        link = relative_link(master, entry["path"].parent / "report.html")
        pytest_rows += f"<tr><td><a href='{_esc(link)}'>{_esc(entry['command_folder'].replace('_',' ').title())}</a></td><td>{_esc(summary.get('passed',0))}</td><td>{_esc(summary.get('failed',0))}</td><td>{_esc(summary.get('skipped',0))}</td></tr>"

    document = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MEDPAR Master Report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f9;color:#172033;line-height:1.45}}header{{background:linear-gradient(135deg,#102a43,#243b53);color:#fff;padding:30px}}main{{max-width:1650px;margin:auto;padding:24px}}.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}.summary div{{background:#fff;border:1px solid #d0d5dd;border-radius:10px;padding:15px}}.summary strong{{display:block;font-size:26px}}details.stage,details.command,details.command-report{{background:#fff;border:1px solid #d0d5dd;border-radius:10px;margin:12px 0;padding:0 14px 14px}}summary{{cursor:pointer;font-weight:800;padding:14px 0}}.command.pass{{border-left:6px solid #087f5b}}.command.fail{{border-left:6px solid #c92a2a}}.business-status{{display:inline-block;padding:4px 8px;border-radius:999px;font-weight:800}}.business-status.pass{{background:#d3f9d8;color:#087f5b}}.business-status.fail{{background:#ffe3e3;color:#c92a2a}}.business-status.neutral{{background:#f1f3f5;color:#667085}}.validation{{border:1px solid #d0d5dd;border-left:6px solid #98a2b3;border-radius:9px;padding:14px;margin:12px 0}}.validation.status-pass{{border-left-color:#087f5b}}.validation.status-fail{{border-left-color:#c92a2a}}.validation.status-blocked{{border-left-color:#d97706}}.validation.status-not_applicable{{border-left-color:#1864ab}}.badge,.field{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:800}}.badge.pass{{background:#d3f9d8;color:#087f5b}}.badge.fail{{background:#ffe3e3;color:#c92a2a}}.badge.blocked{{background:#fff3bf;color:#8d5500}}.badge.not_applicable{{background:#dbeafe;color:#1864ab}}.field{{background:#ede9fe;color:#5f3dc4}}.three,.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin:10px 0}}.three section,.two section{{border:1px solid #d0d5dd;border-radius:8px;padding:10px;min-width:0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#172033;color:#fff;padding:11px;border-radius:7px;max-height:400px;overflow:auto}}.conclusion{{padding:12px;border-radius:8px}}.conclusion.pass{{background:#e6fcf5}}.conclusion.fail{{background:#fff0f0}}.conclusion.blocked{{background:#fff9db}}.conclusion.not_applicable{{background:#e7f5ff}}a{{color:#1864ab}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid #d0d5dd;padding:9px;text-align:left}}th{{background:#edf2f7}}.file-review{{border:1px solid #d0d5dd;border-radius:10px;margin:10px 0;padding:12px;overflow-wrap:anywhere}}.file-review summary{{cursor:pointer;font-weight:700}}.file-conclusion{{padding:14px;background:#edf2f7;border-radius:8px}}.file-inventory table{{table-layout:fixed}}.file-inventory td{{overflow-wrap:anywhere}}
.volume-strip{{display:grid;grid-template-columns:repeat(7,minmax(70px,1fr));gap:12px;margin-top:14px}}.volume-cell span{{display:block;font-size:12px;font-weight:400}}.volume-cell strong{{display:block;font-size:22px}}.volume-cell:nth-child(3){{border-right:1px solid #cbd5e1}}.volume-cell:nth-child(2) strong,.volume-cell:nth-child(5) strong{{color:#087f5b}}.volume-cell:nth-child(3) strong,.volume-cell:nth-child(7) strong{{color:#c92a2a}}.volume-cell:nth-child(6) strong{{color:#996600}}.volume-cell a{{color:inherit}}@media(max-width:700px){{.volume-strip{{grid-template-columns:repeat(3,1fr)}}}}.file-toolbar,.stage-conclusion,.overall-conclusion{{padding:16px;margin:16px 0;background:#eef6ff;border:1px solid #b6c9de;border-radius:10px}}.file-toolbar input,.file-toolbar select{{padding:9px;max-width:100%;margin:8px;border:1px solid #98a2b3;border-radius:6px}}.file-toolbar select{{width:100%}}.stage-conclusion td{{overflow-wrap:anywhere}}[hidden]{{display:none!important}}
</style></head>
<body><header><h1>MEDPAR QA — Master Report</h1><p><strong>Session ID:</strong> {_esc(root.name)}</p><p><strong>Session started (local time):</strong> {_esc(session_started)}</p><p>Report page generated: {_esc(readable_time(datetime.now().astimezone().isoformat(timespec='seconds')))}</p><p>This page contains all generated stage validations, rule outcomes, expected/observed values, explanations, command outputs, and links.</p>{scope_note}</header><main>
<details class='guide'><summary>How to read file, record and validation counts</summary><p><strong>Business runs:</strong> validation report runs in this session; one run may review many files. <strong>Validations:</strong> individual recorded checks across all stages, including ingestion and stage-summary checks; this is not the number of files or claims.</p><p><strong>Pass:</strong> the recorded check met its expected condition. <strong>Fail:</strong> the check found a discrepancy. <strong>Blocked:</strong> the check could not reach a decision because a required input, reference or prerequisite was missing. <strong>N/A:</strong> the check did not apply to the records or circumstances reviewed; it is not a pass.</p><p><strong>Pytest runs:</strong> automated software test sessions included here, separate from production business validation. Zero means no pytest report was included in this session. Known differences are disclosed deviations and do not count as passing checks. Validations = Pass + Fail + Blocked + N/A + Known differences. Counts may overlap records; they are not unique defective claim counts. The stage headers count successfully read source inputs only; output/reference files are excluded. File pass means no file-attributed failure/block, not stage acceptance. Record KEEP/DROP counts require explicit decisions; — means no disposition was recorded. Each stage may be reviewed independently.</p></details>
<h2 id="stage-results">Files and records by stage</h2>{''.join(stage_sections) or '<p>No business-stage report JSON files were found.</p>'}
{transfer_table}
<details class='overall-conclusion'><summary>Overall conclusion — all stages: {overall_state}</summary><p>{len(by_stage)} stages have recorded results. Acceptance requires every required stage to pass its applicable checks. Stages absent from this session have no acceptance result. File filters do not change the full-run conclusions or dashboard totals.</p>{overall_conclusions}{missing_stage_notes}</details><details><summary>Pytest report index</summary><table><thead><tr><th>Pytest selection</th><th>Passed</th><th>Failed</th><th>Skipped</th></tr></thead><tbody>{pytest_rows or '<tr><td colspan="4">No pytest reports found.</td></tr>'}</tbody></table></details>
<details class='command'><summary>Command execution summary</summary>{''.join(command_cards) or '<p>No command execution metadata supplied.</p>'}</details></main><script>function openEvidence(){{if(!location.hash)return;const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(target){{if(target.tagName==='DETAILS')target.open=true;for(let p=target.parentElement;p;p=p.parentElement){{if(p.tagName==='DETAILS')p.open=true;}}target.classList.remove('hidden');target.scrollIntoView({{block:'start'}});}}}}window.addEventListener('hashchange',openEvidence);window.addEventListener('load',openEvidence);</script>{FILE_FILTER_SCRIPT}</body></html>"""
    output = master / "index.html"
    (master / "details.html").write_text(document, encoding="utf-8")
    output.write_text(document, encoding="utf-8")
    from .executive_review import write_executive_review
    write_executive_review(business_entries, master / "overview.html", detail_link="index.html")
    return output


def refresh_session_indexes(session_root: str | Path, executions: list[dict[str, Any]] | None = None) -> Path:
    """Refresh stage and master indexes after artifacts have been written."""
    root = Path(session_root)
    for child in sorted(root.iterdir() if root.exists() else []):
        if child.is_dir() and child.name not in {"master", "pytest"}:
            write_stage_index(root, child.name)
    if (root / "pytest").exists():
        write_stage_index(root, "pytest")
    return write_master_index(root, executions=executions)
