"""Client-facing file navigation without duplicating or re-counting checks."""
from collections import Counter, defaultdict
from datetime import datetime
import html

from .rule_catalog import stage_rule_catalog


def readable_time(value):
    try:
        timestamp = datetime.fromisoformat(str(value))
        return timestamp.strftime('%d %B %Y at %I:%M:%S %p') + ' (UTC' + timestamp.strftime('%z')[:3] + ':' + timestamp.strftime('%z')[3:] + ')'
    except (ValueError, TypeError):
        return str(value)


def file_review(stage, validations, anchor_prefix):
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
        sections.append(f"<details class='file-review'><summary>{esc(path)} — {esc(', '.join(sorted(roles[path])) or 'Evidence file')} · PASS {counts['PASS']} / FAIL {counts['FAIL']} / BLOCKED {counts['BLOCKED']} / N/A {counts['NOT_APPLICABLE']}</summary><p><strong>Read status:</strong> {'Successfully read' if path in read else 'Successful read not recorded'}</p><table><thead><tr><th>Rule — open full explanation</th><th>Result</th><th>Reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table><details><summary>Complete stage rule coverage for this file</summary><table><tr><th>Rule</th><th>Requirement</th><th>File-level outcomes</th></tr>{catalog}</table></details><p class='file-conclusion'><strong>Final conclusion for this file:</strong> {esc(outcome)}</p></details>")
    unassigned = [(i,c) for i,c in enumerate(validations,1) if not c.get('source_files')]
    shared = ''.join(f"<li><a href='#{esc(anchor_prefix)}-{i}'>{esc(c.get('rule_id'))} — {esc(c.get('status'))}</a>: {esc(c.get('message'))}</li>" for i,c in unassigned)
    role_counts = Counter(role for path in files for role in roles[path])
    return f"<section class='file-inventory'><h3>Files reviewed in this stage</h3><p><strong>{len(files)} unique evidence files; {len(read)} successfully read.</strong> Source inputs: {role_counts['source']}; actual outputs: {role_counts['actual']}; expected reference files: {role_counts['expected']}.</p><p>Open a file to review its linked checks and conclusion. A check spanning several files appears under each relevant file; summary totals count that check only once. Stage-wide checks below also affect acceptance.</p>{''.join(sections) or '<p>No file-level evidence was recorded.</p>'}<details><summary>Stage-wide checks without an individual file attribution ({len(unassigned)})</summary><ul>{shared}</ul></details></section>"
