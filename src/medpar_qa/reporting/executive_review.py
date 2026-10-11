"""Readable review entry point; original detailed evidence remains available."""
import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

STAGES = ('final_action', 'split', 'stay', 'intermediate', 'final_medpar')


def esc(value):
    return html.escape(str(value), quote=True)


def write_executive_review(entries, output, *, detail_link='details.html'):
    """Summarize recorded checks once, separating reference paths from input coverage."""
    output = Path(output)
    scope_path = output.parent.parent / "review_scope.json"
    scope = json.loads(scope_path.read_text()) if scope_path.exists() else {}
    scope_note = "<p><b>Scope:</b> " + esc(scope.get("description", "")) + "</p>" if scope else ""
    totals = Counter()
    stages = defaultdict(Counter)
    findings = defaultdict(list)
    runs = []
    for entry in entries:
        payload = entry['payload']
        context = payload.get('context') or {}
        name = context.get('command_name') or entry['command_folder'].replace('_', ' ')
        counts = Counter()
        for stage in payload.get('stages', []):
            for check in stage.get('rule_results', []):
                status = check.get('status', 'UNKNOWN')
                counts[status] += 1
                totals[status] += 1
                stages[stage['stage']][status] += 1
                if status in ('FAIL', 'BLOCKED', 'KNOWN_DIFFERENCE'):
                    findings[(stage['stage'], check.get('rule_id'), status)].append((check, entry))
        href = os.path.relpath(entry['path'].parent / 'report.html', output.parent)
        state = 'FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] else 'REVIEW DIFFERENCES' if counts['KNOWN_DIFFERENCE'] else 'CHECKS PASS' if counts['PASS'] else 'NOT ASSESSED'
        source_paths = context.get("source_paths")
        actual_paths = context.get("actual_paths")
        coverage = f"{len(source_paths)} configured input paths · {len(actual_paths or [])} comparison paths" if source_paths is not None else "Archive-wide evidence audit"
        runs.append(f'<tr><td><a href="{esc(href)}">{esc(name)}</a><br><span class="muted">{esc(coverage)}</span></td><td>{esc(payload.get("run_date") or "Not recorded")}</td><td>{state}</td><td>{counts["PASS"]:,}</td><td>{counts["FAIL"]:,}</td><td>{counts["BLOCKED"]:,}</td><td>{counts["NOT_APPLICABLE"]:,}</td><td>{counts["KNOWN_DIFFERENCE"]:,}</td></tr>')
    verdict = 'Action required' if totals['FAIL'] or totals['BLOCKED'] else 'Review required' if totals['KNOWN_DIFFERENCE'] else 'Recorded checks passed' if totals['PASS'] else 'No business results'
    rows = []
    for stage in STAGES:
        count = stages[stage]
        status = 'Not run' if not count else 'Failures found' if count['FAIL'] else 'Blocked' if count['BLOCKED'] else 'Review differences' if count['KNOWN_DIFFERENCE'] else 'Recorded checks pass'
        rows.append(f'<tr><td>{esc(stage.replace("_", " ").title())}</td><td>{status}</td><td>{count["PASS"]:,}</td><td>{count["FAIL"]:,}</td><td>{count["BLOCKED"]:,}</td><td>{count["NOT_APPLICABLE"]:,}</td><td>{count["KNOWN_DIFFERENCE"]:,}</td></tr>')
    cards = []
    for (stage, rule, status), items in sorted(findings.items(), key=lambda item: (('FAIL','BLOCKED','KNOWN_DIFFERENCE').index(item[0][2]), -len(item[1]))):
        check, entry = items[0]
        files = {str(path) for check, _ in items for path in check.get('source_files', [])}
        records = {str(record) for check, _ in items for record in check.get('record_ids', [])}
        href = os.path.relpath(entry['path'].parent / 'report.html', output.parent)
        meta = f'{len(items):,} recorded checks · {len(files):,} linked evidence files · {len(records):,} distinct record IDs'
        cards.append(f'<details class="finding"><summary><span class="tag {status.lower()}">{status.replace("_", " ")}</span> {esc(rule)} · {esc(stage.replace("_", " ").title())}</summary><p>{meta}</p><p><b>Example explanation:</b> {esc(check.get("message", ""))}</p><p>Open the full evidence for all affected records and expected/observed values. Linked evidence files can include references and outputs; they are not an input-file count.</p><a href="{esc(href)}">Review rule evidence and file filter →</a></details>')
    cards_html = ''.join(cards) or '<p>No failed, blocked or known-difference checks were recorded.</p>'
    output.write_text(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MEDPAR • Review overview</title><style>
body{{margin:0;background:#f3f6fa;color:#172c43;font:16px/1.6 system-ui}}header{{background:linear-gradient(120deg,#10263f,#214b69);color:white;padding:48px max(24px,calc((100vw - 1200px)/2))}}h1{{font-size:36px;margin:12px 0}}header p{{color:#d7e6f3}}main{{max-width:1200px;margin:auto;padding:24px}}.panel,.finding{{background:white;border:1px solid #dce4ee;border-radius:14px;padding:24px;margin:18px 0;box-shadow:0 3px 12px #152f4810}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:14px}}.metric{{background:white;border:1px solid #dce4ee;border-radius:12px;padding:20px}}.metric strong{{display:block;font-size:30px}}.muted{{color:#53677b}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:14px 10px;text-align:left;border-bottom:1px solid #e2e8f0;vertical-align:top}}th{{background:#f1f5fa;white-space:nowrap}}a{{color:#125d97}}summary{{cursor:pointer;font-weight:650}}.tag{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;background:#e7edf5;margin-right:8px}}.fail{{background:#ffe3e3;color:#a71b26}}.blocked{{background:#fff0ce;color:#835400}}.known_difference{{background:#eae4ff;color:#593c94}}input{{padding:12px;width:min(90%,550px);border:1px solid #a8b8ca;border-radius:8px}}[hidden]{{display:none!important}}nav a{{margin-right:24px;color:white}}@media print{{details{{display:block}}header{{padding:20px}}}}
</style></head><body><header><div>MEDPAR / VALIDATION REVIEW</div><h1>{verdict}</h1><p>Session {esc(output.parent.parent.name)} · Overview generated {esc(datetime.now().astimezone().strftime('%d %B %Y, %I:%M:%S %p %Z (%z)'))}</p><nav><a href="#stages">Stage results</a><a href="#findings">Findings</a><a href="#evidence">Evidence</a></nav></header><main>
<section class="panel"><h2>Overall conclusion</h2>{scope_note}<p>{'The recorded results contain discrepancies or missing prerequisites. Review the grouped findings below before acceptance.' if totals['FAIL'] or totals['BLOCKED'] else 'The recorded results must be read within the scope of the checks performed; successful checks alone do not establish full production acceptance.'}</p><p class="muted">This session reviews supplied data. Stages not run, N/A checks and known differences do not establish acceptance. A format check can pass while a separate business or reconciliation check fails.</p></section>
<div class="metrics">{''.join(f'<div class="metric">{label}<strong>{value:,}</strong></div>' for label,value in [('Business runs',len(entries)),('Checks passed',totals['PASS']),('Checks failed',totals['FAIL']),('Checks blocked',totals['BLOCKED']),('Not assessed / N/A',totals['NOT_APPLICABLE']),('Known differences',totals['KNOWN_DIFFERENCE'])])}</div>
<section class="panel" id="stages"><h2>Stage results</h2><p>Counts are individual validation events, not unique defective claims. Missing stages are shown explicitly.</p><div class="scroll"><table><tr><th>Stage</th><th>Conclusion</th><th>Pass</th><th>Fail</th><th>Blocked</th><th>N/A</th><th>Differences</th></tr>{''.join(rows)}</table></div></section>
<section class="panel" id="findings"><h2>What needs attention</h2><p>Repeated results are grouped by stage and rule. Each group links to the original proof.</p><label for="search">Search rule, stage or explanation</label><br><input id="search" type="search" placeholder="Search findings…"><p id="matches" class="muted"></p><div id="issues">{cards_html}</div></section>
<section class="panel" id="evidence"><h2>Run evidence</h2><p>Open a run to search filenames, inspect each rule and read each file conclusion. Processing dates below are distinct from the report generation date.</p><div class="scroll"><table><tr><th>Run / detailed evidence</th><th>Processing date</th><th>Result</th><th>Pass</th><th>Fail</th><th>Blocked</th><th>N/A</th><th>Differences</th></tr>{''.join(runs)}</table></div><p><a href="{esc(detail_link)}">All stage and file conclusions, metric definitions and software test reports →</a></p></section>
<details class="panel"><summary>How to interpret the results</summary><p>Business runs count report bundles. Validations count individual recorded checks. PASS means the check met its expectation; FAIL means a discrepancy; BLOCKED means a missing prerequisite prevents evaluation. N/A means not evaluated; inspect the reason. Known differences are disclosed deviations requiring review. These categories sum to {sum(totals.values()):,} recorded checks.</p><p>Software tests (pytest) verify the framework, including its response to intentionally invalid fixtures. They are separate from production acceptance. A valid business DROP is not automatically a software failure. File-level linked check counts must not be added together because one check can reference multiple files.</p></details></main><script>const search=document.getElementById('search');function filter(){{let n=0;document.querySelectorAll('.finding').forEach(el=>{{el.hidden=!el.textContent.toLowerCase().includes(search.value.toLowerCase());if(!el.hidden)n++;}});document.getElementById('matches').textContent=n+' finding groups shown';}}search.addEventListener('input',filter);filter();</script></body></html>''', encoding='utf-8')
    return output
