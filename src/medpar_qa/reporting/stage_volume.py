"""Separate input-file coverage, input records and explicit business decisions."""
from collections import Counter, defaultdict
import html


def summarize_stage_volume(checks, decisions=()):
    inputs = {}
    ids_by_file = defaultdict(set)
    read_inputs = set()
    for check in checks:
        actual = check.get('actual') or {}
        role = actual.get('role') if isinstance(actual,dict) else None
        role = role or (check.get('evidence') or {}).get('role')
        if check.get('rule_id') == 'INGEST-DISCOVERY' and role == 'source' and check.get('status') == 'PASS':
            for path in check.get('source_files', []): inputs.setdefault(str(path),0)
        if check.get('rule_id') == 'INGEST-READ-FILE' and role == 'source':
            for path in check.get('source_files', []):
                inputs[str(path)] = max(inputs.get(str(path), 0), int(actual.get('record_count', 0)))
                if check.get('status')=='PASS': read_inputs.add(str(path))
                ids_by_file[str(path)].update(str(record) for record in check.get('record_ids', []))
    problems = {str(path) for check in checks if check.get('status') in ('FAIL', 'BLOCKED') for path in check.get('source_files', [])}
    problems |= set(inputs) - read_inputs
    passed = set(inputs) - problems
    stopped = set(inputs) & problems
    failed = set(inputs) & {str(path) for check in checks if check.get('status') == 'FAIL' for path in check.get('source_files', [])}
    blocked = stopped - failed
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
    return dict(files_failed=len(failed), files_blocked=len(blocked), files_in=len(inputs), files_passed=len(passed), files_stopped=len(stopped),
                records_in=sum(inputs.values()), kept=counts['KEEP'] if decisions else None,
                dropped=counts['DROP'] if decisions else None,
                records_stopped=len(undecided) if decisions else None,
                file_sets={'in':set(inputs), 'passed':passed, 'stopped':stopped, 'failed':failed, 'blocked':blocked}, decisions=decisions_by_id)


def volume_strip(volume, href=None):
    """Render the two metric groups from the lead's reference, with honest missing counts."""
    cells = []
    if 'files_kept' in volume:
        keys=[('files_in','Input files'),('files_kept','Kept'),('files_dropped','Dropped'),('files_stopped','Stopped')]
        for key,label in keys:
            value=str(volume[key]);value=f'<a href="{html.escape(href(key),quote=True)}" onclick="event.stopPropagation()">{value}</a>' if href else value
            cells.append(f'<span class="volume-cell"><span>{label}</span><strong>{value}</strong></span>')
        return '<span class="volume-strip">'+''.join(cells)+'</span>'
    file_cells = [('files_in', 'Input files'), ('files_passed', 'Files passed')] + ([('files_failed', 'Files failed'), ('files_blocked', 'Files blocked')] if 'files_failed' in volume else [('files_stopped', 'Files stopped')])
    for key, label in file_cells + [('records_in','Records in'),('kept','Kept'),('dropped','Dropped'),('records_stopped','Stopped')]:
        value = volume[key]
        text = '—' if value is None else f'{value:,}'
        if href and value is not None:
            text = f'<a href="{html.escape(href(key),quote=True)}" onclick="event.stopPropagation()">{text}</a>'
        cells.append(f'<span class="volume-cell"><span>{label}</span><strong>{text}</strong></span>')
    return '<span class="volume-strip">' + ''.join(cells) + '</span>'


def connected_dispositions(items, volume):
    """Classify physical inputs by executed handoff, not by isolated passing checks.

    Files containing both kept and dropped records count as kept. Only files whose
    entire input was dropped count as dropped. A gated stage stop stops all inputs.
    """
    import json
    kept,dropped,stopped=set(),set(),set()
    explanations={}
    for item in items:
        entry=item['entry'];step=entry['payload'].get('context',{}).get('handoff')
        if not step:continue
        inputs=summarize_stage_volume(item['stage'].get('rule_results',[]))['file_sets']['in']
        ids={}
        for check in item['stage'].get('rule_results',[]):
            if check.get('rule_id')=='INGEST-READ-FILE':
                for path in check.get('source_files',[]):ids.setdefault(path,set()).update(check.get('record_ids',[]))
        inventory_path=entry['path'].parents[3]/'input_sources.json' if len(entry['path'].parents)>3 else entry['path'].parent/'input_sources.json'
        inventory=json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
        origins={row['local_path']:row['origin'] for row in inventory.get('files',[])}
        drop_ids={d['record_id'] for d in item['stage'].get('decisions',[]) if d.get('decision')=='DROP'}
        drop_file=entry['path'].parent/'dropped.json'
        if drop_file.exists():
            drop_ids.update(row.get('source_record_id') for row in json.loads(drop_file.read_text()) if row.get('source_record_id'))
        for path in inputs:
            status=step['status']
            if status in ('FAIL','BLOCKED'):
                stopped.add(path);outcome='Stopped'
            elif status=='DROP' or ids.get(path) and ids[path]<=drop_ids:
                dropped.add(path);outcome='Dropped'
            else:
                kept.add(path);outcome='Kept'
            explanations[path]={'outcome':outcome,'reason':step.get('reason',''), 'origin':origins.get(path,path), 'report':entry['path'].parent/'report.html'}
    # A file reviewed multiple times has a conservative single outcome.
    kept-=stopped;dropped-=stopped;kept-=dropped
    volume.update(files_kept=len(kept),files_dropped=len(dropped),files_stopped=len(stopped),disposition_evidence=explanations)
    volume['file_sets'].update(kept=kept,dropped=dropped,stopped=stopped)
    return volume
