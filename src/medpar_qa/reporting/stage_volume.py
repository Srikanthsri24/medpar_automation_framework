"""Separate input-file coverage, input records and explicit business decisions."""
from collections import Counter, defaultdict
import html


def summarize_stage_volume(checks, decisions=()):
    inputs = {}
    ids_by_file = defaultdict(set)
    for check in checks:
        actual = check.get('actual') or {}
        if check.get('rule_id') == 'INGEST-READ-FILE' and isinstance(actual, dict) and actual.get('role') == 'source' and check.get('status') == 'PASS':
            for path in check.get('source_files', []):
                inputs[str(path)] = max(inputs.get(str(path), 0), int(actual.get('record_count', 0)))
                ids_by_file[str(path)].update(str(record) for record in check.get('record_ids', []))
    problems = {str(path) for check in checks if check.get('status') in ('FAIL', 'BLOCKED') for path in check.get('source_files', [])}
    passed = set(inputs) - problems
    stopped = set(inputs) & problems
    decisions_by_id = {}
    for decision in decisions:
        record = str(decision.get('record_id'))
        outcome = decision.get('decision')
        if record in decisions_by_id and decisions_by_id[record] != outcome:
            decisions_by_id[record] = 'CONFLICT'
        else:
            decisions_by_id[record] = outcome
    counts = Counter(decisions_by_id.values())
    input_ids = set().union(*ids_by_file.values()) if ids_by_file else set()
    undecided = input_ids - decisions_by_id.keys()
    return dict(files_in=len(inputs), files_passed=len(passed), files_stopped=len(stopped),
                records_in=sum(inputs.values()), kept=counts['KEEP'] if decisions else None,
                dropped=counts['DROP'] if decisions else None,
                records_stopped=len(undecided) if decisions else None,
                file_sets={'in':set(inputs), 'passed':passed, 'stopped':stopped}, decisions=decisions_by_id)


def volume_strip(volume, href=None):
    """Render the two metric groups from the lead's reference, with honest missing counts."""
    cells = []
    for key, label in [('files_in','Files in'),('files_passed','Files passed'),('files_stopped','Files stopped'),('records_in','Records in'),('kept','Kept'),('dropped','Dropped'),('records_stopped','Stopped')]:
        value = volume[key]
        text = '—' if value is None else f'{value:,}'
        if href and value is not None:
            text = f'<a href="{html.escape(href(key),quote=True)}" onclick="event.stopPropagation()">{text}</a>'
        cells.append(f'<span class="volume-cell"><span>{label}</span><strong>{text}</strong></span>')
    return '<span class="volume-strip">' + ''.join(cells) + '</span>'
