"""Small file navigation pages with the existing full validation-card format."""
import hashlib
import html
from collections import defaultdict, Counter


def e(value):
    return html.escape(str(value), quote=True)


def number_file_tables(body):
    """Number displayed file rows per table; retain stable serials during filtering."""
    import re
    def table(match):
        text=match.group(0)
        if 'data-file=' not in text: return text
        text=re.sub(r'(<tr[^>]*>)(<th>)', r'\1<th>No.</th>\2', text, count=1)
        serial=0
        def row(m):
            nonlocal serial
            serial+=1
            return m.group(0)+f'<td>{serial}</td>'
        return re.sub(r'<tr\s+data-file=[^>]+>',row,text)
    return re.sub(r'<table\b[^>]*>.*?</table>',table,body,flags=re.S)


def page(title, body):
    body=number_file_tables(body)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>body{{font:16px/1.5 system-ui;background:#f4f6f9;color:#172033;margin:24px}}main{{max-width:1400px;margin:auto}}article,section,details{{background:white;padding:16px;border:1px solid #d0d5dd;border-radius:8px;margin:12px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border:1px solid #d0d5dd;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;overflow:auto}}input{{padding:10px;width:min(90%,600px)}}a{{color:#1864ab}}[hidden]{{display:none!important}}summary{{cursor:pointer}}.three,.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}}.badge,.field{{display:inline-block;padding:4px 8px;border-radius:20px;font-weight:700}}.pass{{background:#d3f9d8}}.fail{{background:#ffe3e3}}.blocked{{background:#fff3bf}}</style></head><body><main><a href="index.html#stage-results">← Master report</a><h1>{e(title)}</h1>{body}</main><script>const fields=document.querySelectorAll('input');fields.forEach(field=>field.addEventListener('input',()=>{{document.querySelectorAll('tr[data-file]').forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(field.value.toLowerCase()));}}));</script></body></html>'''


def write_status_navigation(master, stage, checks, render, *, deferred_files=None):
    """Count checks once and provide full-file conclusions separately from status links."""
    files = defaultdict(list)
    for index, check in enumerate(checks, 1):
        for path in set(check.get('source_files', [])):
            files[str(path)].append((index, check))
    links = {}
    written_shared = set()
    rendered_cards = {}
    for path, items in files.items():
        filename = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
        links[path] = filename
        if path in (deferred_files or ()):
            continue  # Volume navigation writes the same complete input-file screen once.
        states = {check['status'] for _, check in items}
        conclusion = 'FAIL' if 'FAIL' in states else 'BLOCKED' if 'BLOCKED' in states else 'REVIEW DIFFERENCES' if 'KNOWN_DIFFERENCE' in states else 'Recorded applicable checks pass' if 'PASS' in states else 'Not assessed'
        cards = []
        for index, check in items:
            if len(check.get('source_files', [])) > 30:
                shared = f'{stage}_shared_{index}.html'
                if shared not in written_shared:
                    written_shared.add(shared)
                    (master / shared).write_text(page('Shared rule evidence', render(check, stage, index, stage+'-selected')), encoding='utf-8')
                cards.append(f'<details><summary>{e(check["status"])} · {e(check["rule_id"])}</summary><p>{e(check.get("message", ""))}</p><a href="{shared}">Full shared-check proof</a></details>')
            else:
                if index not in rendered_cards:
                    rendered_cards[index] = render(check, stage, index, stage+'-selected')
                cards.append(rendered_cards[index])
        totals = Counter(check['status'] for _, check in items)
        count_summary = ' · '.join(f'{status}: {totals[status]}' for status in ('PASS', 'FAIL', 'BLOCKED', 'NOT_APPLICABLE', 'KNOWN_DIFFERENCE'))
        body = f'<p><strong>Validations: {len(items)} · {count_summary}</strong></p><p>{e(path)}</p><p><strong>File conclusion: {conclusion}</strong> — based on all checks linked to this file, including failed and blocked checks. Stage-wide findings still affect acceptance; this is not physical-byte certification.</p>' + ''.join(cards)
        (master / filename).write_text(page(stage.replace('_', ' ').title()+' — File evidence', body), encoding='utf-8')
    for status in ('PASS', 'FAIL', 'BLOCKED'):
        matching = [check for check in checks if check['status'] == status]
        rows = []
        for path, items in sorted(files.items()):
            selected = [c for _, c in items if c['status'] == status]
            if not selected:
                continue
            examples = list(dict.fromkeys(c.get('message', '') for c in selected))[:3]
            rows.append(f'<tr data-file="{e(path)}"><td><a href="{links[path]}">{e(path)}</a></td><td>{len(selected)}</td><td>{e("; ".join(examples))}</td></tr>')
        global_checks = [c for c in matching if not c.get('source_files')]
        body = f'<p>{len(matching):,} matching checks · {len(rows):,} linked evidence files. A file can contain both passed and failed checks. Click its filename for the complete file conclusion and full proof. Counts are validation events, not exclusive file outcomes.</p><label>Search filename <input type="search" placeholder="Filename or path…"></label><table><tr><th>File — open full report</th><th>Matching checks</th><th>Explanation</th></tr>' + ''.join(rows) + '</table>'
        body += '<h2>Stage-wide checks without file attribution</h2>' + ''.join(render(c, stage, n, stage+'-global') for n,c in enumerate(global_checks,1))
        (master / f'{stage}_{status.lower()}_files.html').write_text(page(stage.replace('_',' ').title()+' — '+status+' file evidence', body),encoding='utf-8')


def write_volume_navigation(master, stage, checks, volume):
    """Link true input-file counts and explicit decisions to existing per-file proof."""
    by_file_ids = defaultdict(set)
    for check in checks:
        actual = check.get('actual') or {}
        if check.get('rule_id') == 'INGEST-READ-FILE' and isinstance(actual,dict) and actual.get('role') == 'source':
            for path in check.get('source_files',[]):
                by_file_ids[str(path)].update(str(record) for record in check.get('record_ids',[]))
    check_numbers_by_file = defaultdict(set)
    check_numbers_by_id = defaultdict(set)
    for number, check in enumerate(checks):
        for path in check.get('source_files', []):
            check_numbers_by_file[path].add(number)
        for record_id in check.get('record_ids', []):
            check_numbers_by_id[record_id].add(number)
    written=set()
    for key in ('files_in','files_passed','files_stopped','files_failed','files_blocked','records_in','kept','dropped','records_stopped')+ (('files_kept','files_dropped') if 'files_kept' in volume else ()):
        if key.startswith('files_'):
            paths = volume['file_sets'][key.removeprefix('files_')]
        elif key == 'records_in':
            paths = volume['file_sets']['in']
        else:
            outcome = {'kept':'KEEP','dropped':'DROP'}.get(key)
            paths = {path for path, ids in by_file_ids.items() if any(volume['decisions'].get(record) == outcome if outcome else record not in volume['decisions'] for record in ids)}
        rows = []
        for path in sorted(paths):
            filename = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
            ids = by_file_ids[path]
            if path in volume.get('disposition_evidence',{}) and path not in written:
                written.add(path)
                info=volume['disposition_evidence'][path]
                from .path_utils import relative_link
                numbers = set(check_numbers_by_file[path])
                for record_id in by_file_ids[path]:
                    numbers.update(check_numbers_by_id[record_id])
                linked = [checks[number] for number in sorted(numbers)]
                from .session_index import _render_raw_validation
                detail='<p><strong>Original source:</strong> '+e(info['origin'])+'</p><p><strong>File disposition: '+e(info['outcome'])+'</strong></p><p>'+e(info['reason'])+'</p><p><a href="'+e(relative_link(master,info['report']))+'">Stage result and stopping/transfer proof</a></p>'
                detail+='<details><summary>All business-group results for this input</summary><ul>'+''.join('<li><a href="'+e(relative_link(master,proof))+'">Group rule and handoff evidence</a></li>' for proof in info.get('reports',[info['report']]))+'</ul></details>'
                detail+='<p>Kept means this input contributed retained records. Dropped means all its records were removed. Stopped means the stage did not approve an output; passing individual checks do not establish a KEEP decision.</p>'
                result_counts=Counter(check.get('status') for check in linked)
                detail+='<p><strong>Distinct rules/check types: '+str(len({check.get('rule_id') for check in linked}))+'; validation events linked to this file: '+str(len(linked))+'</strong>. '+e(' · '.join(str(result_counts.get(status,0))+' '+status for status in ('PASS','FAIL','BLOCKED','NOT_APPLICABLE','KNOWN_DIFFERENCE')))+'</p><p>These are check counts, not file counts. Expand each rule below for its requirement, expected/observed result and explanation.</p>'
                detail+=''.join(_render_raw_validation(check,stage,n) for n,check in enumerate(linked,1))
                (master/filename).write_text(page('File evidence — '+info['origin'],detail),encoding='utf-8')
            selected = ids if key.startswith('files_') or key=='records_in' else {record for record in ids if volume['decisions'].get(record) == {'kept':'KEEP','dropped':'DROP'}.get(key)} if key != 'records_stopped' else ids - volume['decisions'].keys()
            rows.append(f'<tr data-file="{e(path)}"><td><a href="{filename}">{e(path)}</a></td><td>{len(selected)}</td><td>{e(", ".join(sorted(selected)))}</td></tr>')
        body = f'<p>Selected metric: {e(key.replace("_"," "))} — {volume[key] if volume[key] is not None else "Not recorded"}. Input files only; output and reference files are excluded. Open a filename for its complete proof. Global stage discrepancies still affect acceptance.</p><label>Search filename <input type="search"></label><table><tr><th>Input file</th><th>Linked records</th><th>Record IDs</th></tr>' + ''.join(rows) + '</table>'
        (master / f'{stage}_volume_{key}.html').write_text(page(stage.replace('_',' ').title()+' — '+key.replace('_',' '),body), encoding='utf-8')


def compact_file_index(stage, checks, master_base):
    """Keep large full reports searchable without duplicating thousands of rule cards."""
    from .stage_volume import summarize_stage_volume
    inputs = summarize_stage_volume(checks)['file_sets']['in']
    files=defaultdict(list)
    for check in checks:
        for path in set(check.get('source_files', [])) & inputs:
            files[str(path)].append(check)
    rows=[]
    for path, linked in sorted(files.items()):
        counts=defaultdict(int)
        for check in linked: counts[check['status']]+=1
        filename=stage+'_file_'+hashlib.sha256(path.encode()).hexdigest()[:20]+'.html'
        href=master_base+'/'+filename
        outcome='FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] else 'REVIEW DIFFERENCES' if counts['KNOWN_DIFFERENCE'] else 'Recorded applicable checks pass' if counts['PASS'] else 'Not assessed'
        rows.append(f'<tr data-file="{e(path)}"><td><a href="{e(href)}">{e(path)}</a></td><td>{outcome}</td><td>{counts["PASS"]} / {counts["FAIL"]} / {counts["BLOCKED"]}</td></tr>')
    return number_file_tables('<p>Open a filename for its complete rule-by-rule proof, including expected/observed values, explanations and all checks linked to that file in this stage.</p><label>Search filename <input class="compact-file-search" type="search" oninput="filterCompactFiles(this)"></label><div class="table-wrap"><table><tr><th>File — open full proof</th><th>Conclusion in this run</th><th>Pass / Fail / Blocked checks</th></tr>'+''.join(rows)+'</table></div><script>function filterCompactFiles(input){const scope=input.closest(".file-inventory-collapse");scope.querySelectorAll("tr[data-file]").forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(input.value.toLowerCase()));}</script>')
