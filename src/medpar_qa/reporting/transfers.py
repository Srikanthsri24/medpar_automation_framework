"""Stage handoff navigation; never infer execution from a passing validation."""
import hashlib
from .status_navigation import e, page, number_file_tables
from .stage_volume import summarize_stage_volume

STAGES = ('final_action', 'split', 'stay', 'intermediate', 'final_medpar')


def independent_transfers(master, by_stage):
    """Verify saved-run boundary files and reuse explicit record-lineage audit proof."""
    import json
    import os
    from pathlib import Path
    from datetime import datetime
    project = next((p for p in master.resolve().parents if (p / 'run_commands.py').exists()), master.resolve().parent)
    def local(path):
        p = Path(path)
        return p if p.is_absolute() else project / p
    def paths(stage, role):
        return sorted({str(path) for item in by_stage.get(stage, []) for path in item['entry']['payload'].get('context', {}).get(role, [])})
    def link(path):
        return os.path.relpath(local(path), master.resolve()).replace(os.sep, '/')
    rows, verification = [], []
    for number, stage in enumerate(STAGES):
        next_stage = STAGES[number + 1] if number + 1 < len(STAGES) else None
        title = stage.replace('_', ' ').title()
        detail_rows, proofs = [], []
        outputs = paths(stage, 'actual_paths')
        next_inputs = paths(next_stage, 'source_paths') if next_stage else []
        destination = {local(path).resolve(): path for path in next_inputs}
        verified = 0
        for path in outputs:
            file = local(path)
            target = destination.get(file.resolve())
            digest = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
            # Successful reader checks demonstrate that the configured input actually ran.
            read_checks = [c for item in by_stage.get(next_stage, []) for c in item['stage'].get('rule_results', []) if c.get('rule_id') == 'INGEST-READ-FILE' and c.get('status') == 'PASS' and isinstance(c.get('actual'), dict) and c['actual'].get('role') == 'source' and target in c.get('source_files', [])] if target else []
            ok = bool(digest and read_checks)
            verified += ok
            status = 'PASS — output used as next-stage input' if ok else 'FAIL — next-stage input read not established'
            proofs.append(dict(output_file=path, next_input=target, sha256=digest, status='PASS' if ok else 'FAIL', next_stage_read_checks=len(read_checks)))
            detail_rows.append(f'<tr data-file="{e(path)}"><td><a href="{e(link(path))}">{e(path)}</a></td><td>{e(target or "No matching next-stage input")}</td><td>{e(status)}</td><td><code>{e(digest or "File unavailable")}</code></td></tr>')
        # Intermediate transforms into Final; exact field-preservation audit is the proof,
        # rather than assuming that their differently shaped files have the same bytes.
        lineage = [c for item in by_stage.get('final_medpar', []) for c in item['stage'].get('rule_results', []) if c.get('rule_id') == 'FM-ARCHIVE-EXACT-LINEAGE'] if stage == 'intermediate' else []
        if lineage:
            detail_rows = []
            for c in lineage:
                evidence_path = next((str(p) for p in c.get('source_files', []) if str(p) in paths('final_medpar', 'source_paths')), str(c.get('source_files', [''])[0]))
                proof_link = 'final_medpar_file_' + hashlib.sha256(evidence_path.encode()).hexdigest()[:20] + '.html'
                detail_rows.append(f'<tr data-file="{e(evidence_path)}"><td><a href="{proof_link}">{e(evidence_path)}</a></td><td>{e(json.dumps(c.get("actual"), ensure_ascii=False))}</td><td>{e(c["status"])}</td><td>{e(c["message"])}</td></tr>')
            verified = sum(c['status'] == 'PASS' for c in lineage)
            summary = f'{verified:,} / {len(lineage):,} Final files — exact Intermediate lineage verified' if verified == len(lineage) else f'{verified:,} / {len(lineage):,} Final files — lineage discrepancies found'
            headings = '<th>Final file — full proof</th><th>Matching source and fingerprint</th><th>Result</th><th>Verification</th>'
            proofs = lineage
        else:
            summary = f'{verified:,} / {len(outputs):,} output files — next-stage input verified' if outputs and verified == len(outputs) else f'{verified:,} / {len(outputs):,} output files — transfer discrepancies found' if outputs else 'No retained-output handoff recorded'
            headings = '<th>Output file</th><th>Next-stage input</th><th>Verification result</th><th>SHA-256 fingerprint</th>'
        if next_stage is None:
            summary = 'Final stage — workflow ends here'
        checks = [c for item in by_stage.get(stage, []) for c in item['stage'].get('rule_results', [])]
        volume = summarize_stage_volume(checks)
        input_rows = []
        for path in sorted(volume['file_sets']['in']):
            selected = [c for c in checks if path in c.get('source_files', [])]
            counts = {status: sum(c.get('status') == status for c in selected) for status in ('PASS', 'FAIL', 'BLOCKED')}
            proof = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
            result = 'FAIL / BLOCKED' if path in volume['file_sets']['stopped'] else 'File checks passed'
            input_rows.append(f'<tr data-file="{e(path)}"><td><a href="{proof}">{e(path)}</a></td><td>{result}</td><td>{len(selected)}</td><td>{counts["PASS"]}</td><td>{counts["FAIL"]}</td><td>{counts["BLOCKED"]}</td></tr>')
        input_summary = f'{volume["files_in"]:,} input files · {volume["files_passed"]:,} passed · {volume["files_failed"]:,} failed · {volume["files_blocked"]:,} blocked'
        filename = f'{stage}_transfers.html'
        body = f'<p><strong>Input-file results: {e(input_summary)}</strong></p><details><summary>Output-to-input verification — {e(summary)}</summary><p><strong>Conclusion: {e(summary)}</strong></p><p>Verification uses the saved run configuration, successful next-stage file-read checks and current local file fingerprints. Exact lineage checks verify transformed Final records against Intermediate. Boundary verification establishes which supplied outputs were used in the next stage. Open the stage reports for business-rule results and acceptance conclusions.</p>'
        body += f'<p><a href="index.html#stage-{stage}">Source-stage validation and original input-file evidence</a>' + (f' · <a href="index.html#stage-{next_stage}">Next-stage validation evidence</a>' if next_stage else '') + ' · <a href="transfer_verification.json">Download verification evidence</a></p>'
        body += '</details><label>Search input filename <input type="search" placeholder="Filename or path…"></label><details><summary>Input files — open a filename for its complete validation report</summary><table><tr><th>Input file</th><th>Result</th><th>Validations</th><th>Pass</th><th>Fail</th><th>Blocked</th></tr>' + ''.join(input_rows) + '</table></details><details><summary>Boundary file matches and fingerprints</summary><label>Search filename <input type="search" placeholder="Filename or path…"></label><table><tr>' + headings + '</tr>' + ''.join(detail_rows) + '</table></details>'
        (master / filename).write_text(page(title + ' — Stage boundary verification', body), encoding='utf-8')
        next_received = summarize_stage_volume([c for item in by_stage.get(next_stage, []) for c in item['stage'].get('rule_results', [])])['files_in'] if next_stage else None
        forwarded_sources = {path for c in lineage if c['status'] == 'PASS' for path in c.get('source_files', []) if path in outputs} if lineage else set()
        movement = f'{len(forwarded_sources) if lineage else verified:,} / {len(outputs):,}' if next_stage and outputs else '—'
        verification.append(dict(stage=stage, next_stage=next_stage, input_files=volume['files_in'], output_files=len(outputs), output_files_forwarded=len(forwarded_sources) if lineage else verified, next_stage_input_files=next_received, conclusion=summary, evidence=proofs))
        rows.append(f'<tr><td>{e(title)}</td><td>{e(next_stage.replace("_", " ").title()) if next_stage else "End of workflow"}</td><td>{volume["files_in"]:,}</td><td>{movement}</td><td>{next_received if next_received is not None else "End"}</td><td><a href="{filename}">{e(input_summary)}</a><details><summary>Transfer verification</summary>{e(summary)}</details></td></tr>')
    (master / 'transfer_verification.json').write_text(json.dumps(dict(verified_at=datetime.now().astimezone().isoformat(), boundaries=verification), indent=2), encoding='utf-8')
    return '<details id="stage-transfers"><summary>Stage transfer verification — input-file results</summary><p>Click a result for output-to-input file matches, fingerprints and validation evidence. Input counts are unique source files read in each stage. Movement counts are verified output files read by the next stage; merges and splits can change the file count. Original input files and transformed output files are counted separately.</p><table><tr><th>From stage</th><th>To stage</th><th>Input files received</th><th>Output files verified in next stage</th><th>Next-stage input files received</th><th>Result — open proof</th></tr>' + ''.join(rows) + '</table></details>'


def transfer_count_link(index,stage,metric,entries,scope=''):
    """A count routes to exactly its supporting physical-file events, including zero."""
    from .path_utils import relative_link
    index.parent.mkdir(parents=True,exist_ok=True)
    suffix='_'+hashlib.sha256(scope.encode()).hexdigest()[:12] if scope else ''
    filename=stage+'_movement_'+metric+suffix+'.html'
    rows=[]
    for label,proof,extra in entries:
        links='<a href="'+e(relative_link(index.parent,proof))+'">File / stage rule evidence</a>'
        if extra:links+=' · <a href="'+e(relative_link(index.parent,extra))+'">Transfer output / next-stage proof</a>'
        rows.append('<tr data-file="'+e(label)+'"><td>'+e(label)+'</td><td>'+links+'</td></tr>')
    body='<p>'+str(len(entries))+' physical file event(s). This list supports the clicked count; it is not a validation count. Kept/dropped/stopped are file dispositions. Open evidence for per-file rule counts, outcomes and explanations.</p><p><a href="'+e(index.name)+'#stage-transfers">Back to main report</a></p><table><tr><th>File / original location</th><th>Evidence</th></tr>'+''.join(rows)+'</table>'
    if not rows:body+='<p>No files match this count. No movement or acceptance is inferred.</p>'
    (index.parent/filename).write_text(page(stage.replace('_',' ').title()+' — '+metric.replace('_',' '),body),encoding='utf-8')
    return '<a href="'+filename+'">'+str(len(entries))+'</a>'


def connected_transfers(journeys, index):
    """Show original inputs, new entries and verified physical handoffs separately."""
    import json
    from .path_utils import relative_link
    from .stage_volume import connected_dispositions
    rows=[]
    metric_files={stage:{key:[] for key in ('started','received','inputs','kept','dropped','stopped','moved')} for stage in STAGES}
    totals={stage:{key:0 for key in ('started','received','inputs','kept','dropped','stopped','moved')} for stage in STAGES}
    for journey,directory in journeys:
        originals=journey.get('source_files',[journey['source_file']])
        inventory_path=directory.parent.parent/'input_sources.json'
        inventory=json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
        origin_map={row['local_path']:row['origin'] for row in inventory.get('files',[])}
        display_originals=[origin_map.get(path,path) for path in originals]
        original_list=[]
        for path,display in zip(originals,display_originals):
            file_page=journey.get('start_stage','final_action')+'_file_'+hashlib.sha256(path.encode()).hexdigest()[:20]+'.html'
            original_list.append('<li>'+('<a href="'+file_page+'">'+e(display)+'</a>' if (index.parent/file_page).exists() else e(display))+'</li>')
        inventory_link='<p><a href="'+relative_link(index.parent,inventory_path.with_suffix('.html'))+'">Original locations, file sizes and SHA-256 evidence</a></p>' if inventory_path.exists() else ''
        origin='<details><summary>'+str(len(originals))+' original input files — '+e(journey.get('start_stage','final_action').replace('_',' ').title())+' entry</summary><ol>'+''.join(original_list)+'</ol>'+inventory_link+'</details>'
        relative=relative_link(index.parent,directory)
        for number,step in enumerate(journey['steps']):
            if step['status'] in ('BEFORE_START','NOT_REACHED'):continue
            following=journey['steps'][number+1] if number+1<len(journey['steps']) else None
            previous=journey['steps'][number-1] if number else None
            executed=step['status']!='NOT_REACHED'
            moved=bool(following and step.get('output') and following['status'] not in ('NOT_REACHED','BEFORE_START') and following.get('input')==step['output'] and following.get('input_records',1)>0)
            received=bool(executed and previous and previous.get('output') and step.get('input')==previous['output'] and step.get('input_records',1)>0)
            inputs=len(step.get('input_files',[])) if executed else 0
            started=inputs if executed and step['stage']==journey.get('start_stage','final_action') else 0
            counts={'files_kept':0,'files_dropped':0,'files_stopped':0}
            path=directory/step['stage']/'report.json'
            if executed and path.exists():
                payload=json.loads(path.read_text());stage_payload=payload['stages'][0]
                volume=summarize_stage_volume(stage_payload.get('rule_results',[]))
                counts=connected_dispositions([{'entry':{'path':path,'payload':payload},'stage':stage_payload}],volume)
            state='Moved to next stage' if moved else 'Completed final stage' if executed and not following and step['status']=='KEEP' else 'Not reached' if not executed else 'Stopped — not moved' if step['status'] in ('FAIL','BLOCKED') else 'Dropped' if step['status']=='DROP' else 'Retained — transfer not verified'
            if executed and step['status']=='KEEP' and not following:state='Completed final stage'
            links='<a href="'+relative+'/'+step['stage']+'/report.html">Stage rules and evidence</a>' if executed else ''
            if moved:links+=' · <a href="'+relative+'/'+following['stage']+'/report.html">Next stage proof</a> · <a href="'+relative+'/'+step['stage']+'/retained.json">Transferred output</a>'
            proof='<details><summary>'+e(state)+' — '+e(step['status'])+'</summary><p>'+e(step.get('reason',''))+'</p><p>'+str(step.get('input_records',0))+' records read; '+str(step.get('retained',0))+' retained record(s); '+str(step.get('dropped',0))+' dropped.</p><p>'+links+'</p></details>'
            for key,value in dict(started=started,received=int(received),inputs=inputs,kept=counts['files_kept'],dropped=counts['files_dropped'],stopped=counts['files_stopped'],moved=int(moved)).items():totals[step['stage']][key]+=value
            report_file=directory/step['stage']/'report.html'
            current_files=step.get('input_files',[]) if executed else []
            events={key:[] for key in metric_files[step['stage']]}
            for path in current_files:
                file_page=index.parent/(step['stage']+'_file_'+hashlib.sha256(path.encode()).hexdigest()[:20]+'.html')
                event=(origin_map.get(path,path),file_page if file_page.exists() else report_file,None)
                events['inputs'].append(event)
                if started:events['started'].append(event)
                if received:events['received'].append((origin_map.get(path,path),report_file,directory/previous['stage']/'report.html'))
                for key in ('kept','dropped','stopped'):
                    if path in counts.get('file_sets',{}).get(key,set()):events[key].append(event)
            if moved:events['moved'].append((step['output'],directory/following['stage']/'report.html',directory/step['stage']/'retained.json'))
            for key in events:metric_files[step['stage']][key]+=events[key]
            count_cells=[transfer_count_link(index,step['stage'],key,events[key],str(directory)) for key in ('started','received','inputs','kept','dropped','stopped','moved')]
            values=[origin,e(step['stage'].replace('_',' ').title()),e(following['stage'].replace('_',' ').title()) if following else 'End',*count_cells,proof]
            rows.append('<tr data-file="'+e(' '.join(display_originals))+'">'+''.join('<td>'+value+'</td>' for value in values)+'</tr>')
    for stage,metrics in metric_files.items():
        for key,events in metrics.items():metrics[key]=list({event[0]:event for event in events}.values())
        kept_labels={event[0] for event in metrics['kept']}
        metrics['stopped']=[event for event in metrics['stopped'] if event[0] not in kept_labels]
        stopped_labels={event[0] for event in metrics['stopped']}
        metrics['dropped']=[event for event in metrics['dropped'] if event[0] not in kept_labels|stopped_labels]
    overview=[]
    for stage,values in totals.items():
        number=STAGES.index(stage);next_stage=STAGES[number+1].replace('_',' ').title() if number+1<len(STAGES) else 'End of workflow'
        stage_link='#stage-'+stage if index.parent.name=='master' else next((relative_link(index.parent,directory/stage/'report.html') for journey,directory in journeys if any(step['stage']==stage and step['status'] not in ('BEFORE_START','NOT_REACHED') for step in journey['steps'])), '#transfer-detail')
        overview.append('<tr><td>'+e(stage.replace('_',' ').title())+'</td><td>'+e(next_stage)+'</td>'+''.join('<td>'+transfer_count_link(index,stage,key,metric_files[stage][key])+'</td>' for key in ('started','received','inputs','kept','dropped','stopped','moved'))+'<td><a href="'+e(stage_link)+'">Stage file evidence</a> · <a href="#transfer-detail">Journey evidence</a></td></tr>')
    summary='<table><tr>'+''.join('<th>'+e(label)+'</th>' for label in ('From stage','To stage','Started here','Received from previous','Input files','Kept','Dropped','Stopped','Files moved','Evidence'))+'</tr>'+''.join(overview)+'</table>'
    headings=['Original source files','From stage','To stage','Started here','Received from previous','Input files','Kept','Dropped','Stopped','Files moved','Evidence']
    return number_file_tables('<details id="stage-transfers"><summary>Moved to next stage — file status</summary><p>All counts in this table are physical files. Started here counts supplied source files; Received counts generated files from the previous stage. A generated output may combine many source files: one transferred file can contain many retained records. Kept means at least one record survives; Dropped means all records were dropped; Stopped means no stage output was approved. File disposition counts add up to input files. Open original sources for filenames, then the movement evidence for stage reports and record counts.</p>'+summary+'<details id="transfer-detail"><summary>Individual input journeys and original-source evidence</summary><label>Search original filename <input id="transfer-search" type="search"></label><div class="scroll"><table id="transfer-table"><tr>'+''.join('<th>'+e(h)+'</th>' for h in headings)+'</tr>'+''.join(rows)+'</table></div></details></details><script>document.getElementById("transfer-search").addEventListener("input",function(){document.querySelectorAll("#transfer-table tr[data-file]").forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(this.value.toLowerCase()));});</script>')
