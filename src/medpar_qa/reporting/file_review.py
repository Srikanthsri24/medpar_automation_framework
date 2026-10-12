"""Client-facing file navigation without duplicating or re-counting checks."""
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import json

from .rule_catalog import stage_rule_catalog, get_rule_metadata


def readable_time(value):
    """Format a timestamp with an explicit readable date/time and timezone."""
    try:
        timestamp = datetime.fromisoformat(str(value))
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(ZoneInfo("Asia/Kolkata"))
        return timestamp.strftime('%d %B %Y at %I:%M:%S %p') + ' (UTC' + timestamp.strftime('%z')[:3] + ':' + timestamp.strftime('%z')[3:] + ')'
    except (ValueError, TypeError):
        return str(value)


def file_review(stage, validations, anchor_prefix):
    """Group checks under unique source paths, preserving shared checks and unattributed stage
    results for honest file conclusions.
    """
    esc = lambda value: html.escape(str(value), quote=True)
    files = defaultdict(list)
    roles = defaultdict(set)
    read = set()
    for number, check in enumerate(validations, 1):
        evidence = check.get('evidence') or {}
        actual = check.get('actual')
        role = evidence.get('role') or (actual.get('role') if isinstance(actual, dict) else None)
        role = {'actual_output': 'actual', 'expected_output': 'expected'}.get(role, role)
        for path in set(check.get('source_files') or []):
            files[path].append((number, check))
            if role:
                roles[path].add(role)
            if check.get('rule_id') == 'INGEST-READ-FILE' and check.get('status') == 'PASS':
                read.add(path)
    sections = []
    for path, checks in sorted(files.items()):
        counts = Counter(c.get('status') for _, c in checks)
        if counts['FAIL']:
            outcome = 'FAIL — one or more linked checks found a discrepancy. Review the failed rules below.'
        elif counts['BLOCKED']:
            outcome = 'BLOCKED — missing inputs or prerequisites prevent a complete decision.'
        elif counts['KNOWN_DIFFERENCE']:
            outcome = 'Checks include a known difference; review the deviation and approval requirements before acceptance.'
        elif counts['PASS']:
            outcome = 'Recorded checks passed. This does not certify rules without file-level evidence or unresolved stage-wide checks.'
        else:
            outcome = 'No applicable passing check was recorded; file acceptance is not established.'
        rows = []
        for number, check in checks:
            rows.append(f"<tr><td><a href='#{esc(anchor_prefix)}-{number}'>{esc(check.get('rule_id'))}</a></td><td>{esc(check.get('status'))}</td><td>{esc(check.get('message'))}</td></tr>")
        rule_counts = defaultdict(Counter)
        for _, check in checks:
            rule_counts[check.get('rule_id')][check.get('status')] += 1
        catalog = ''.join(f"<tr><td>{esc(rule)}</td><td>{esc(metadata.title)}</td><td>{esc(', '.join(f'{k}: {v}' for k,v in rule_counts[rule].items()) if rule in rule_counts else 'No file-level result recorded; consult stage-wide results / prerequisites')}</td></tr>" for rule, metadata in stage_rule_catalog(stage))
        sections.append(f"<details class='file-review' data-file='{esc(path)}'><summary>{esc(path)} — {esc(', '.join(sorted(roles[path])) or 'Evidence file')} · PASS {counts['PASS']} / FAIL {counts['FAIL']} / BLOCKED {counts['BLOCKED']} / N/A {counts['NOT_APPLICABLE']}</summary><p><strong>Read status:</strong> {'Successfully read' if path in read else 'Successful read not recorded'}</p><table><thead><tr><th>Rule — open full explanation</th><th>Result</th><th>Reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table><details><summary>Complete stage rule coverage for this file</summary><table><tr><th>Rule</th><th>Requirement</th><th>File-level outcomes</th></tr>{catalog}</table></details><p class='file-conclusion'><strong>Final conclusion for this file:</strong> {esc(outcome)}</p></details>")
    unassigned = [(i,c) for i,c in enumerate(validations,1) if not c.get('source_files')]
    shared = ''.join(f"<li><a href='#{esc(anchor_prefix)}-{i}'>{esc(c.get('rule_id'))} — {esc(c.get('status'))}</a>: {esc(c.get('message'))}</li>" for i,c in unassigned)
    options = ''.join(f"<option value='{esc(path)}'>{esc(path)}</option>" for path in sorted(files))
    filters = f"<div class='file-toolbar'><label>Search file name or path <input class='file-search' type='search' placeholder='Type any part of a file name…' oninput='filterEvidence(this)'></label><label>Choose file <select class='file-select' onchange='filterEvidence(this)'><option value=''>All files</option>{options}</select></label><button type='button' onclick='resetEvidence(this)'>Reset file filter</button><p class='file-filter-count' aria-live='polite'>{len(files)} matching file(s).</p></div>"
    role_counts = Counter(role for path in files for role in roles[path])
    return f"<section class='file-inventory'><h3>Files reviewed in this stage</h3><p><strong>{len(files)} unique evidence files; {len(read)} successfully read.</strong> Source inputs: {role_counts['source']}; actual outputs: {role_counts['actual']}; expected reference files: {role_counts['expected']}.</p><p>Open a file to review its linked checks and conclusion. A check spanning several files appears under each relevant file; summary totals count that check only once. Stage-wide checks below also affect acceptance.</p>{filters}{''.join(sections) or '<p>No file-level evidence was recorded.</p>'}<details><summary>Stage-wide checks without an individual file attribution ({len(unassigned)})</summary><ul>{shared}</ul></details></section>"


def stage_conclusion(stage, validations):
    """Summarize unique files and checks; never infer acceptance from file reads."""
    esc = lambda value: html.escape(str(value), quote=True)
    counts = Counter(c.get('status') for c in validations)
    files = {p for c in validations for p in c.get('source_files', [])}
    read = {p for c in validations if c.get('rule_id') == 'INGEST-READ-FILE' and c.get('status') == 'PASS' for p in c.get('source_files', [])}
    failed_files = {p for c in validations if c.get('status') == 'FAIL' for p in c.get('source_files', [])}
    blocked_files = {p for c in validations if c.get('status') == 'BLOCKED' for p in c.get('source_files', [])}
    status = 'FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] else 'WITH KNOWN DIFFERENCES' if counts['KNOWN_DIFFERENCE'] else 'PASS' if counts['PASS'] else 'NOT ESTABLISHED'
    explanation = {
        'WITH KNOWN DIFFERENCES': 'Disclosed deviations remain. Applicable checks may continue, but these deviations are not passing validations or production approval.',
        'FAIL': 'This stage is not accepted because recorded checks found discrepancies. Correct the failed checks and resolve any blocked checks before acceptance.',
        'BLOCKED': 'This stage cannot be accepted yet because required inputs or prerequisites are missing. Supply them and rerun the blocked checks.',
        'PASS': 'All recorded applicable checks passed and no failures or blocks were recorded. This conclusion covers this run and its recorded checks; unexecuted rules and missing production certification remain outside this result.',
        'NOT ESTABLISHED': 'No applicable passing checks were recorded; stage acceptance has not been established.',
    }[status]
    groups = defaultdict(list)
    for check in validations:
        if check.get('status') in {'FAIL', 'BLOCKED'}:
            groups[(check['status'], check.get('rule_id'))].append(check)
    rows = []
    for (outcome, rule), checks in sorted(groups.items()):
        meta = get_rule_metadata(stage, rule, checks[0].get('field_name'))
        messages = list(dict.fromkeys(c.get('message', '') for c in checks))
        examples = '<ul>' + ''.join(f'<li>{esc(m)}</li>' for m in messages[:3]) + '</ul>'
        rows.append(f'<tr><td>{esc(outcome)} · {esc(rule)}<br>{esc(meta.title)}</td><td>{len(checks)}</td><td>{examples}</td><td>{esc(meta.remediation)}</td></tr>')
    issues = f"<details><summary>Why this stage failed or was blocked — all {len(groups)} finding categories</summary><table><tr><th>Outcome / rule</th><th>Check count</th><th>Explanation (representative messages)</th><th>Required action</th></tr>{''.join(rows)}</table><p>Open the corresponding file and full rule evidence for every affected record.</p></details>" if groups else '<p>No failed or blocked checks were recorded.</p>'
    return f"<section class='stage-conclusion'><h3>Final conclusion — {esc(stage.replace('_', ' ').title())}: {status}</h3><p><strong>{len(files)} unique evidence files; {len(read)} successfully read; {len(validations)} checks.</strong> PASS {counts['PASS']} · FAIL {counts['FAIL']} · BLOCKED {counts['BLOCKED']} · N/A {counts['NOT_APPLICABLE']} · KNOWN DIFFERENCE {counts['KNOWN_DIFFERENCE']}.</p><p>{esc(explanation)}</p><p>Files linked to failed checks: {len(failed_files)}. Files linked to blocked checks: {len(blocked_files)}. These sets may overlap. Stage-wide findings also affect acceptance even when no individual file is named. N/A and unexecuted rules are not passes.</p>{issues}</section>"


FILE_FILTER_SCRIPT = """<script>
function filterEvidence(control){
 const scope=control.closest('.command-report')||control.closest('.stage-content');
 const query=scope.querySelector('.file-search').value.trim().toLowerCase();
 const selected=scope.querySelector('.file-select').value;
 const match=path=>(!query||path.toLowerCase().includes(query))&&(!selected||path===selected);
 let shown=0;
 scope.querySelectorAll('.file-review').forEach(file=>{const visible=match(file.dataset.file);file.hidden=!visible;if(visible)shown++;});
 scope.querySelectorAll('article[data-files]').forEach(card=>{const paths=JSON.parse(card.dataset.files);card.hidden=paths.length>0&&!paths.some(match);});
 scope.querySelector('.file-filter-count').textContent=shown+' matching file(s). Stage-wide findings remain visible and conclusions still describe the full run.';
}
function resetEvidence(button){const scope=button.closest('.command-report')||button.closest('.stage-content');scope.querySelector('.file-search').value='';scope.querySelector('.file-select').value='';filterEvidence(button);}
</script>"""
