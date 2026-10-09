from __future__ import annotations

import html
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from medpar_qa.models import RunManifest, RuleResult, StageResult
from medpar_qa.reporting.rule_catalog import conclusion_text, get_rule_metadata, stage_rule_catalog


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _pretty(value: Any) -> str:
    if value is None:
        return "Not supplied / not applicable"
    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except TypeError:
        return repr(value)


def _value_box(label: str, value: Any, kind: str) -> str:
    return (
        f'<section class="value-panel {kind}"><h5>{_esc(label)}</h5>'
        f'<pre>{_esc(_pretty(value))}</pre></section>'
    )


def _list(values: list[str], empty: str = "None") -> str:
    if not values:
        return f'<span class="muted">{_esc(empty)}</span>'
    return "<ul>" + "".join(f"<li>{_esc(value)}</li>" for value in values) + "</ul>"


def _counts(results: list[StageResult]) -> Counter[str]:
    values: Counter[str] = Counter()
    for stage in results:
        values.update(result.status.value for result in stage.rule_results)
    return values


def _validation_card(check: RuleResult, number: int) -> str:
    status = check.status.value
    metadata = get_rule_metadata(check.stage.value, check.rule_id, check.field_name)
    conclusion = conclusion_text(
        status=status,
        message=check.message,
        expected=check.expected,
        actual=check.actual,
        metadata=metadata,
    )
    validator = check.evidence.get("validator_function", "Not recorded")
    searchable = " ".join(
        [
            check.stage.value,
            status,
            check.rule_id,
            metadata.title,
            metadata.requirement,
            metadata.validation,
            check.field_name or "",
            check.message,
            " ".join(check.source_files),
        ]
    ).lower()
    recommended = (
        f'<div class="recommended"><strong>Recommended action:</strong> {_esc(metadata.remediation)}</div>'
        if status in {"FAIL", "BLOCKED"}
        else ""
    )
    return f"""
    <article class="validation-card status-{status.lower()}"
             data-status="{_esc(status)}" data-stage="{_esc(check.stage.value)}"
             data-search="{_esc(searchable)}">
      <div class="validation-topline">
        <div class="identity-line">
          <span class="sequence">#{number}</span>
          <span class="badge {status.lower()}">{_esc(status)}</span>
          <code class="rule-id">{_esc(check.rule_id)}</code>
          {f'<span class="field-chip">{_esc(check.field_name)}</span>' if check.field_name else ''}
        </div>
        <button class="copy-button" type="button" onclick="copyCard(this)">Copy validation</button>
      </div>

      <h3>{_esc(metadata.title)}</h3>

      <div class="explanation-grid">
        <section class="explanation-block requirement">
          <h4>1. Business requirement</h4>
          <p>{_esc(metadata.requirement)}</p>
        </section>
        <section class="explanation-block checked">
          <h4>2. What was validated</h4>
          <p>{_esc(metadata.validation)}</p>
          <p class="runtime-message"><strong>Execution message:</strong> {_esc(check.message)}</p>
        </section>
        <section class="explanation-block logic">
          <h4>3. How the result was evaluated</h4>
          <p>{_esc(metadata.logic)}</p>
        </section>
      </div>

      <div class="expected-actual-grid">
        {_value_box('4. Expected result', check.expected, 'expected')}
        {_value_box('5. Observed result', check.actual, 'actual')}
      </div>

      <section class="conclusion {status.lower()}">
        <h4>6. {('Why this is correct' if status == 'PASS' else 'Why this is wrong' if status == 'FAIL' else 'Why this is blocked' if status == 'BLOCKED' else 'Why this is not applicable')} — {_esc(status)}</h4>
        <p>{_esc(conclusion)}</p>
      </section>
      {recommended}

      <details class="traceability">
        <summary>7. Source evidence and technical traceability</summary>
        <div class="trace-grid">
          <section><h5>Stage</h5><code>{_esc(check.stage.value)}</code></section>
          <section><h5>Validator function</h5><code>{_esc(validator)}</code></section>
          <section><h5>Relative source files</h5>{_list(check.source_files)}</section>
          <section><h5>Record IDs</h5>{_list(check.record_ids)}</section>
          <section><h5>Claim/group key</h5><pre>{_esc(_pretty(check.group_key))}</pre></section>
          <section><h5>Technical evidence</h5><pre>{_esc(_pretty(check.evidence))}</pre></section>
        </div>
      </details>
    </article>
    """


def _stage_section(stage: StageResult, index: int) -> str:
    counts = stage.status_counts
    executed_rule_ids = {item.rule_id for item in stage.rule_results}
    catalogue_rows = "".join(
        f"<tr><td><code>{_esc(rule_id)}</code></td><td>{_esc(metadata.title)}</td><td><span class='catalogue-status {'executed' if rule_id in executed_rule_ids else 'not-triggered'}'>{'EXECUTED' if rule_id in executed_rule_ids else 'NOT TRIGGERED BY THIS DATA'}</span></td><td>{_esc(metadata.requirement)}</td></tr>"
        for rule_id, metadata in stage_rule_catalog(stage.stage.value)
    )
    catalogue = f"""<details class='rule-catalogue'><summary>Complete stage rule catalogue and coverage</summary><p><strong>Executed</strong> means the rule/function emitted a result for this run. <strong>Not triggered</strong> means its prerequisites did not occur in this input; it is not a hidden pass.</p><div class='table-wrap'><table><thead><tr><th>Rule ID</th><th>Rule / validation</th><th>Run state</th><th>Business requirement</th></tr></thead><tbody>{catalogue_rows}</tbody></table></div></details>"""
    cards = "".join(
        _validation_card(check, number)
        for number, check in enumerate(stage.rule_results, start=1)
    )
    decisions = ""
    if stage.decisions:
        rows = "".join(
            f"<tr><td>{_esc(item.record_id)}</td><td><span class='decision {item.decision.value.lower()}'>{_esc(item.decision.value)}</span></td><td>{_esc(item.rule_id)}</td><td>{_esc(item.reason)}</td></tr>"
            for item in stage.decisions
        )
        decisions = f"""
        <section class="decision-section">
          <h3>Record-level KEEP/DROP decisions</h3>
          <p>These are the final decisions produced by the applicable Final Action rule for each record.</p>
          <div class="table-wrap"><table><thead><tr><th>Record ID</th><th>Decision</th><th>Rule</th><th>Explanation</th></tr></thead><tbody>{rows}</tbody></table></div>
        </section>
        """
    open_attr = " open" if index == 1 or not stage.passed else ""
    return f"""
    <details class="stage-section"{open_attr} data-stage-container="{_esc(stage.stage.value)}">
      <summary>
        <span class="stage-number">Stage {index}</span>
        <span class="stage-name">{_esc(stage.stage.value.replace('_', ' ').title())}</span>
        <span class="stage-status {'pass' if stage.passed else 'fail'}">{'PASS' if stage.passed else 'FAIL / BLOCKED'}</span>
        <span class="stage-counts">{counts['PASS']} pass · {counts['FAIL']} fail · {counts['BLOCKED']} blocked · {counts['NOT_APPLICABLE']} N/A</span>
      </summary>
      <div class="stage-content">
        <div class="stage-intro">
          <strong>How to review this stage:</strong> Read validations in order. Each card states the business requirement, exact check, expected result, observed result, conclusion, and source evidence.
        </div>
        {catalogue}
        {cards}
        {decisions}
      </div>
    </details>
    """


def write_html_report(
    run_id: str,
    run_date: date | str,
    results: Iterable[StageResult],
    output_directory: str | Path,
    *,
    manifest: RunManifest | None = None,
    title: str = "MEDPAR QA Detailed Validation Report",
    filename: str = "report.html",
    parent_link: str | None = None,
) -> Path:
    stage_results = list(results)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / filename
    generated = datetime.now().astimezone()
    counts = _counts(stage_results)
    overall_passed = all(stage.passed for stage in stage_results)
    validation_count = sum(counts.values())
    decision_count = sum(len(stage.decisions) for stage in stage_results)

    navigation = (
        f'<a class="back-link" href="{_esc(parent_link)}">← Back to master report</a>'
        if parent_link
        else ""
    )

    manifest_block = ""
    if manifest is not None:
        rows = "".join(
            f"<tr><td>{_esc(item.stage.value)}</td><td>{_esc(item.role.value)}</td><td>{_esc(item.format or 'auto')}</td><td><code>{_esc(item.path)}</code></td></tr>"
            for item in manifest.files
        )
        manifest_block = f"""
        <details class="run-inputs">
          <summary>Run inputs and configuration</summary>
          <p>All paths below are project-relative paths.</p>
          <div class="table-wrap"><table><thead><tr><th>Stage</th><th>Role</th><th>Format</th><th>Relative path / wildcard</th></tr></thead><tbody>{rows}</tbody></table></div>
          <h3>Configured settings</h3><pre>{_esc(_pretty(manifest.settings))}</pre>
        </details>
        """

    failures = [
        check
        for stage in stage_results
        for check in stage.rule_results
        if check.status.value in {"FAIL", "BLOCKED"}
    ]
    failure_summary = (
        "<ul>"
        + "".join(
            f"<li><strong>{_esc(check.stage.value)}</strong> — {_esc(check.rule_id)}: {_esc(check.message)}</li>"
            for check in failures[:20]
        )
        + (f"<li>…and {len(failures)-20} more. Use the FAIL/BLOCKED filter.</li>" if len(failures) > 20 else "")
        + "</ul>"
        if failures
        else "<p>No failed or blocked validations were recorded.</p>"
    )

    stages_html = "".join(
        _stage_section(stage, index)
        for index, stage in enumerate(stage_results, start=1)
    )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} — {_esc(run_id)}</title>
<style>
:root{{--navy:#102a43;--navy2:#243b53;--ink:#172033;--muted:#667085;--line:#d0d5dd;--bg:#f4f6f9;--green:#087f5b;--red:#c92a2a;--amber:#b05a00;--blue:#1864ab;--purple:#5f3dc4}}
*{{box-sizing:border-box}} body{{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.48}}
header{{background:linear-gradient(135deg,var(--navy),var(--navy2));color:#fff;padding:30px 34px}} header h1{{margin:8px 0;font-size:30px}} header p{{margin:4px 0}} .back-link{{color:#fff;text-decoration:none;font-weight:700}}
.container{{max-width:1600px;margin:auto;padding:24px}} .overall-badge{{display:inline-block;margin-top:14px;padding:10px 18px;border-radius:999px;font-size:19px;font-weight:900;background:{'#d3f9d8' if overall_passed else '#ffe3e3'};color:{'#087f5b' if overall_passed else '#c92a2a'}}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}} .summary-card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:15px;box-shadow:0 2px 9px rgba(16,42,67,.06)}} .summary-card strong{{display:block;font-size:27px;margin-top:5px}}
.guide,.failure-overview,.run-inputs{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}} .guide h2,.failure-overview h2{{margin-top:0}} .guide ol{{columns:2;column-gap:36px}}
.toolbar{{position:sticky;top:0;z-index:20;display:flex;gap:9px;flex-wrap:wrap;padding:11px;background:#e9eef5;border:1px solid var(--line);border-radius:10px;margin:18px 0}} .toolbar input,.toolbar select,.toolbar button{{padding:9px 11px;border:1px solid #98a2b3;border-radius:7px;background:#fff}} .toolbar input{{flex:1;min-width:300px}}
.stage-section{{background:#fff;border:1px solid var(--line);border-radius:13px;margin:16px 0;overflow:hidden}} .stage-section>summary{{cursor:pointer;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:17px;background:#edf2f7;font-weight:800}} .stage-number{{color:var(--muted)}} .stage-name{{font-size:19px}} .stage-status{{margin-left:auto;padding:5px 10px;border-radius:999px}} .stage-status.pass{{background:#d3f9d8;color:var(--green)}} .stage-status.fail{{background:#ffe3e3;color:var(--red)}} .stage-counts{{color:var(--muted);font-weight:600}} .stage-content{{padding:2px 12px 18px}} .stage-intro{{margin:14px 2px;padding:12px;background:#eef6ff;border-left:5px solid var(--blue);border-radius:8px}}
.validation-card{{background:#fff;border:1px solid var(--line);border-left:7px solid #98a2b3;border-radius:11px;margin:14px 2px;padding:17px;box-shadow:0 2px 7px rgba(16,42,67,.04)}} .validation-card.status-pass{{border-left-color:var(--green)}} .validation-card.status-fail{{border-left-color:var(--red)}} .validation-card.status-blocked{{border-left-color:var(--amber)}} .validation-card.status-not_applicable{{border-left-color:var(--blue)}}
.validation-topline{{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}} .identity-line{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}} .sequence{{color:var(--muted)}} .badge,.field-chip,.decision{{display:inline-block;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:900}} .badge.pass,.decision.keep{{background:#d3f9d8;color:var(--green)}} .badge.fail,.decision.drop{{background:#ffe3e3;color:var(--red)}} .badge.blocked{{background:#fff3bf;color:#8d5500}} .badge.not_applicable{{background:#dbeafe;color:var(--blue)}} .field-chip{{background:#ede9fe;color:var(--purple)}} .rule-id{{font-weight:800}}
.copy-button{{border:1px solid #98a2b3;background:#fff;border-radius:7px;padding:7px 10px;cursor:pointer}} .validation-card h3{{margin:14px 0 10px;font-size:21px}}
.explanation-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:11px}} .explanation-block{{border:1px solid var(--line);border-radius:9px;padding:12px;background:#fafbfc}} .explanation-block h4{{margin:0 0 7px}} .runtime-message{{padding-top:7px;border-top:1px dashed var(--line)}}
.expected-actual-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;margin:12px 0}} .value-panel{{border:1px solid var(--line);border-radius:9px;overflow:hidden}} .value-panel h5{{margin:0;padding:10px 12px;background:#eef2f7;font-size:15px}} .value-panel.expected{{border-left:5px solid var(--blue)}} .value-panel.actual{{border-left:5px solid var(--amber)}} pre{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;background:#172033;color:#f8fafc;padding:12px;max-height:420px;overflow:auto}}
.conclusion{{border-radius:9px;padding:13px;margin:12px 0}} .conclusion h4{{margin:0 0 6px}} .conclusion.pass{{background:#e6fcf5;border:1px solid #96f2d7}} .conclusion.fail{{background:#fff0f0;border:1px solid #ffc9c9}} .conclusion.blocked{{background:#fff9db;border:1px solid #ffec99}} .conclusion.not_applicable{{background:#e7f5ff;border:1px solid #a5d8ff}} .recommended{{padding:12px;background:#fff4e6;border-left:5px solid var(--amber);border-radius:8px}}
.traceability{{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}} .traceability>summary{{cursor:pointer;font-weight:800}} .trace-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:10px}} .trace-grid section{{min-width:0;border:1px solid var(--line);border-radius:8px;padding:10px}} .trace-grid h5{{margin:0 0 7px}} ul{{margin:4px 0;padding-left:20px}} .muted{{color:var(--muted)}}
.table-wrap{{overflow:auto}} table{{width:100%;border-collapse:collapse}} th,td{{border:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}} th{{background:#edf2f7}} .rule-catalogue{{margin:14px 2px;padding:0 12px 12px;border:1px solid var(--line);border-radius:9px;background:#fafbfc}} .rule-catalogue>summary{{cursor:pointer;font-weight:800;padding:12px 0}} .catalogue-status{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800}} .catalogue-status.executed{{background:#d3f9d8;color:var(--green)}} .catalogue-status.not-triggered{{background:#f1f3f5;color:var(--muted)}} .decision-section{{margin:18px 2px}} .hidden{{display:none!important}} footer{{text-align:center;color:var(--muted);padding:30px}}
@media(max-width:800px){{.guide ol{{columns:1}}.stage-status{{margin-left:0}}}} @media print{{.toolbar,.copy-button{{display:none}}details{{display:block}}details>summary{{list-style:none}}.validation-card,.stage-section{{break-inside:avoid}}body{{background:#fff}}}}
</style></head>
<body><header>{navigation}<h1>{_esc(title)}</h1><p><strong>Run ID:</strong> {_esc(run_id)}</p><p><strong>Business run date:</strong> {_esc(run_date)}</p><p><strong>Generated:</strong> {_esc(generated.isoformat(timespec='seconds'))}</p><span class="overall-badge">OVERALL {'PASS' if overall_passed else 'FAIL / BLOCKED'}</span></header>
<main class="container">
<section class="summary-grid"><div class="summary-card">Stages<strong>{len(stage_results)}</strong></div><div class="summary-card">Validations<strong>{validation_count}</strong></div><div class="summary-card">Passed<strong>{counts['PASS']}</strong></div><div class="summary-card">Failed<strong>{counts['FAIL']}</strong></div><div class="summary-card">Blocked<strong>{counts['BLOCKED']}</strong></div><div class="summary-card">Not applicable<strong>{counts['NOT_APPLICABLE']}</strong></div><div class="summary-card">Record decisions<strong>{decision_count}</strong></div></section>
<section class="guide"><h2>How to read this report</h2><ol><li>Open the required stage.</li><li>Use status filters to focus on failures.</li><li>Read the business requirement and exact validation performed.</li><li>Compare Expected result with Observed result.</li><li>Read the conclusion explaining why it passed, failed, or was blocked.</li><li>Open source evidence for relative file paths, record IDs, group keys, and validator function.</li></ol></section>
<section class="failure-overview"><h2>Failure / blocked overview</h2>{failure_summary}</section>
<section class="toolbar"><input id="search" type="search" placeholder="Search stage, rule, field, requirement, source file..." oninput="applyFilters()"><select id="statusFilter" onchange="applyFilters()"><option value="ALL">All statuses</option><option>PASS</option><option>FAIL</option><option>BLOCKED</option><option>NOT_APPLICABLE</option></select><select id="stageFilter" onchange="applyFilters()"><option value="ALL">All stages</option>{''.join(f'<option value="{_esc(stage.stage.value)}">{_esc(stage.stage.value.replace("_"," ").title())}</option>' for stage in stage_results)}</select><button onclick="expandAll(true)">Expand all</button><button onclick="expandAll(false)">Collapse all</button><button onclick="window.print()">Print / Save PDF</button></section>
{manifest_block}{stages_html}</main><footer>Generated by MEDPAR QA Automation. All displayed file paths are relative to the project folder.</footer>
<script>
function applyFilters(){{const q=document.getElementById('search').value.toLowerCase();const status=document.getElementById('statusFilter').value;const stage=document.getElementById('stageFilter').value;document.querySelectorAll('.validation-card').forEach(card=>{{const okQ=!q||card.dataset.search.includes(q);const okS=status==='ALL'||card.dataset.status===status;const okStage=stage==='ALL'||card.dataset.stage===stage;card.classList.toggle('hidden',!(okQ&&okS&&okStage));}});}}
function expandAll(open){{document.querySelectorAll('details').forEach(item=>item.open=open);}}
function copyCard(button){{const card=button.closest('.validation-card');navigator.clipboard.writeText(card.innerText).then(()=>{{button.textContent='Copied';setTimeout(()=>button.textContent='Copy validation',1200);}});}}
</script></body></html>"""
    output.write_text(document, encoding="utf-8")
    return output
