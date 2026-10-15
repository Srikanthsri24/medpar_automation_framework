"""Original/keep/drop row reconciliation and file/row rule evidence."""
import html,json
from collections import Counter,defaultdict
from pathlib import Path
from medpar_qa.enums import Stage,FileRole
from medpar_qa.ingestion.row_selection import iter_records
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.reporting.status_navigation import page
from medpar_qa.reporting.path_utils import relative_link
from medpar_qa.reporting.row_dashboard import row_browser, render_overview, BROWSER_SCRIPT, unmapped_leaves


def show(value):
    """Escape structured expected/observed evidence for an HTML text block."""
    return html.escape(json.dumps(value,default=str,ensure_ascii=False))


def write_row_report(root,session,journeys,settings,start_stage,items,selected_records=None,selection_override=None,source_origins=None):
    """Attach real rule events to source rows and reconcile separately supplied outputs."""
    from medpar_qa.stages.common import record_identity
    from importlib import import_module
    cls=getattr(import_module('medpar_qa.stages.'+start_stage+'.settings'),''.join(p.title() for p in start_stage.split('_'))+'Settings')
    config=cls.from_mapping(settings.get(start_stage,{}))
    resolver=FieldResolver.from_yaml(Path(root)/'config/field_aliases.yaml')
    fields=tuple(settings.get('comparison_identity_fields',config.identity_fields))
    def identity(record):
        values=record_identity(record,resolver,fields)
        return tuple(str(value).strip() for value in values) if all(value not in (None,'') for value in values) else None
    inventory_path=session.root/'row_selection.json'
    selection=selection_override if selection_override is not None else json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
    source_origins=source_origins or {}
    provenance_path=session.root/'input_sources.json'
    provenance=json.loads(provenance_path.read_text(encoding='utf-8')) if provenance_path.exists() else {}
    origins={row['local_path']:row['origin'] for row in provenance.get('files',[])}
    checks=defaultdict(list);decisions={};reasons={};reports={};file_checks=defaultdict(list);file_reports=defaultdict(list);expected_outputs=defaultdict(list);coalesced_sources=False
    for journey,directory in journeys:
        target=directory/start_stage/'report.json'
        if not target.exists():continue
        if next(s for s in journey['steps'] if s['stage']==start_stage)['status'] in ('BEFORE_START','NOT_REACHED'):continue
        payload=json.loads(target.read_text())
        step=next(s for s in journey['steps'] if s['stage']==start_stage)
        if step.get('output'):
            for expected_row in iter_records(Path(root)/step['output'],Stage(start_stage),FileRole.SOURCE,root):expected_outputs[identity(expected_row)].append(expected_row)
        if (directory/start_stage/'source_segments.json').exists():coalesced_sources=True
        dropped_path=directory/start_stage/'dropped.json'
        if dropped_path.exists():
            for dropped_row in json.loads(dropped_path.read_text(encoding='utf-8')):
                if dropped_row.get('source_record_id'):decisions[dropped_row['source_record_id']]='DROP'
        for path in step.get('input_files',[]):file_reports[path].append(target.with_suffix('.html'))
        for stage in payload['stages']:
            for event_number,original_check in enumerate(stage.get('rule_results',[]),1):
                check={**original_check,'event_id':str(target)+'#check-'+str(event_number)}
                for record_id in check.get('record_ids',[]):checks[record_id].append(check)
                if not check.get('record_ids'):
                    for path in check.get('source_files',[]) or step.get('input_files',[]):file_checks[path].append(check)
            for decision in stage.get('decisions',[]):decisions[decision['record_id']]=decision.get('decision')
        for check in payload['stages'][0].get('rule_results',[]):
            for rid in check.get('record_ids',[]):
                reasons[rid]=step['reason'];reports[rid]=target.with_suffix('.html')
                if step['status'] in ('FAIL','BLOCKED'):decisions[rid]='STOPPED'
                elif rid not in decisions:decisions[rid]='KEEP' if step['status']=='KEEP' else 'DROP'
    if selected_records is None:
        files=list(dict.fromkeys(f for j,_ in journeys for f in j.get('source_files',[j['source_file']])))
        selected_records=[r for f in files for r in iter_records(Path(root)/f,Stage(start_stage),FileRole.SOURCE,root)]
    wanted={identity(r) for r in selected_records};wanted.discard(None)
    role_counts={};role_matches={};role_files={};role_paths={};role_records={};outside_scope={}
    for role,key in (('keep','actual'),('drop','dropped')):
        paths=list(dict.fromkeys(p for item in items for p in item.get(key,[])))
        counts=Counter();locations=defaultdict(list);file_counts=[];matching_records=defaultdict(list);unmatched=0;examples=[]
        for path in paths:
            total=0
            for record in iter_records(Path(root)/path,Stage(start_stage),FileRole.SOURCE,root):
                total+=1
                if isinstance(record.data.get('record'),dict):record.data=record.data['record']
                value=identity(record)
                if value in wanted:
                    counts[value]+=1
                    if len(matching_records[value])<2:
                        matching_records[value].append(record);locations[value].append({'file':path,'row':record.source.row_number})
                else:
                    unmatched+=1
                    if len(examples)<10:examples.append({'file':path,'row':record.source.row_number,'identity':value})
            file_counts.append({'file':path,'origin':origins.get(path,path),'rows':total})
        outside_scope[role]={'rows':unmatched,'examples':examples}
        role_counts[role]=sum(r['rows'] for r in file_counts) if paths else None
        role_matches[role]=counts;role_files[role]=file_counts;role_paths[role]=locations;role_records[role]=matching_records
    originals=selection.get('files',[])
    total_original=sum(f['total_rows'] for f in originals) if originals else len(selected_records)
    population=None
    if selection_override is None and any(role_files.values()):
        from .population_audit import audit_populations
        population=audit_populations(root,start_stage,{'original':[f['file'] for f in originals],'keep':[f['file'] for f in role_files['keep']],'drop':[f['file'] for f in role_files['drop']]},identity)

    conservation='NOT PROVIDED'
    if all(role_counts[r] is not None for r in ('keep','drop')):
        conservation=('PASS' if total_original==sum(role_counts.values()) else 'FAIL') if start_stage in ('final_action','split') else 'NOT APPLICABLE — this stage can merge or derive rows; equal row counts are not an acceptance rule'
    count_balance={'original_rows':total_original,'keep_plus_drop_rows':sum(role_counts.values()) if all(v is not None for v in role_counts.values()) else None}
    count_balance['difference']=count_balance['keep_plus_drop_rows']-total_original if count_balance['keep_plus_drop_rows'] is not None else None
    by_file=defaultdict(list);row_payload=[];sample_targets=set(selection.get('target_record_ids',[r.record_id for r in selected_records]))
    duplicate_keys=Counter(identity(r) for r in selected_records)
    for record in selected_records:
        key=identity(record);outcome=decisions.get(record.record_id,'NOT ASSESSED');linked=checks[record.record_id]
        match_checks=[]
        supplied=any(role_counts[r] is not None for r in ('keep','drop'))
        if supplied:
            observed={r:role_matches[r][key] if key is not None else 0 for r in ('keep','drop')}
            if key is None or (duplicate_keys[key]>1 and start_stage!='stay' and not (start_stage=='intermediate' and coalesced_sources)) or any(count>1 for count in observed.values()):
                status='BLOCKED';message=f'Missing or duplicate comparison identity: source matches={duplicate_keys[key] if key is not None else 0}, keep matches={observed["keep"]}, drop matches={observed["drop"]}. A unique output row cannot be assigned safely; source locations show up to two examples per output.'
            elif outcome not in ('KEEP','DROP'):
                status='BLOCKED';message='The business rules did not approve a KEEP/DROP decision; output membership alone cannot establish acceptance.'
            elif role_counts[outcome.lower()] is None or start_stage in ('final_action','split') and any(role_counts[r] is None for r in ('keep','drop')):
                status='BLOCKED';message='The required comparison output was not supplied.'
            else:
                expected=outcome.lower();opposite='drop' if expected=='keep' else 'keep'
                status='PASS' if observed[expected]==1 and observed[opposite]==0 else 'FAIL'
                message=(f'Calculated {outcome}: exactly one row found in {expected} and none in {opposite}.' if status=='PASS' else f'Calculated {outcome}, but supplied outputs contain {observed[expected]} matching {expected} row(s) and {observed[opposite]} matching {opposite} row(s). '+('The row is in the wrong output.' if observed[opposite] else 'The required output row is missing.'))
            match_checks=[dict(rule_id='ROW-OUTPUT-MEMBERSHIP',status=status,message=message,expected=outcome,actual=observed,evidence={r:role_paths[r].get(key,[]) for r in ('keep','drop')})]
            if match_checks[0]['status']=='PASS':
                from medpar_qa.stages.comparison import compare_values
                from medpar_qa.normalization.dates import parse_date
                from dataclasses import asdict
                expected_rows=expected_outputs.get(key,[])
                expected_row=record if outcome=='DROP' or start_stage=='final_action' else expected_rows[0] if len(expected_rows)==1 else None
                actual_row=role_records[outcome.lower()][key][0]
                if expected_row is None:
                    match_checks.append(dict(rule_id='ROW-OUTPUT-FIELDS',status='BLOCKED',message='A unique calculated output is required to compare transformed field values.',expected='Unique generated output identity',actual=len(expected_rows)))
                else:
                    compare_fields=list(dict.fromkeys([*fields,*resolver.aliases,*getattr(config,'selected_fields',('hicn','provider_id','stay_from_date','stay_thru_date','query_code','action_code')),*(('split_year_indicator','transaction_code') if start_stage=='split' and outcome=='KEEP' else ())]))
                    for name in compare_fields:
                        expected=resolver.get(expected_row.data,name);actual=resolver.get(actual_row.data,name)
                        if expected is None and actual is None:continue
                        if expected is None:
                            match_checks.append(dict(rule_id='ROW-OUTPUT-FIELD-'+name,status='BLOCKED',message='No calculated expected value is available for this populated output field; null is not assumed to be the required value.',expected='Calculated or approved expected value',actual=actual,field_name=name))
                            continue
                        if name.endswith('_date'):
                            try:expected=parse_date(expected).isoformat() if expected is not None else None;actual=parse_date(actual).isoformat() if actual is not None else None
                            except (ValueError,AttributeError):pass
                        elif name in fields:
                            expected=str(expected).strip() if expected is not None else None;actual=str(actual).strip() if actual is not None else None
                        result=compare_values(stage=Stage(start_stage),rule_id='ROW-OUTPUT-FIELD-'+name,field_name=name,expected=expected,actual=actual,record_ids=[record.record_id],source_files=[record.source.file_path,actual_row.source.file_path],decimal_scale=getattr(config,'decimal_scale',None) if name in getattr(config,'decimal_fields',()) else None)
                        match_checks.append(asdict(result))
                    if start_stage=='final_action' or outcome=='DROP':
                        from medpar_qa.normalization.fields import nested_get
                        for name,expected in unmapped_leaves(expected_row.data,resolver):
                            actual=nested_get(actual_row.data,name)
                            result=compare_values(stage=Stage(start_stage),rule_id='ROW-OUTPUT-DATA-'+name,field_name=name,expected=expected,actual=actual,record_ids=[record.record_id],source_files=[record.source.file_path,actual_row.source.file_path])
                            match_checks.append(asdict(result))
        for number,check in enumerate(match_checks):check['event_id']=record.record_id+'/comparison/'+str(number)
        events=linked+match_checks
        counts=Counter(c['status'] for c in events)
        validation_status='FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] or outcome in ('STOPPED','NOT ASSESSED') else 'PASS' if counts['PASS'] else 'NOT ASSESSED'
        item=dict(validation_status=validation_status,input_row=record.data,file=record.source.file_path,row=record.source.row_number,record_id=record.record_id,selection='selected' if record.record_id in sample_targets else 'related context',decision=outcome,validation_counts=dict(counts),checks=events,reason=reasons.get(record.record_id,'No row-specific decision was emitted; inspect shared file/group evidence.'))
        item['comparison_status']='FAIL' if any(c['status']=='FAIL' for c in match_checks) else 'BLOCKED' if any(c['status']=='BLOCKED' for c in match_checks) else 'PASS' if match_checks else 'NOT PROVIDED'
        item['comparison_reasons']=[c.get('message','') for c in match_checks if c['status']!='PASS']
        row_payload.append(item);by_file[item['file']].append(item)
    output=session.root/start_stage/'row_review.html';output.parent.mkdir(parents=True,exist_ok=True)
    inventory={r['file']:r for r in originals};sections=[];file_summaries=[]
    for path in inventory:by_file.setdefault(path,[])
    for number,(path,rows) in enumerate(by_file.items(),1):
        unique={json.dumps(c,sort_keys=True,default=str) for r in rows for c in r['checks']}
        unique.update(json.dumps(c,sort_keys=True,default=str) for c in file_checks[path])
        totals=Counter(json.loads(c)['status'] for c in unique)
        cards=[]
        for row in rows:
            rules=''.join('<details><summary>'+html.escape(c['status']+' '+c['rule_id'])+'</summary><p>'+html.escape(c.get('message',''))+'</p><p>Expected</p><pre>'+show(c.get('expected'))+'</pre><p>Observed</p><pre>'+show(c.get('actual'))+'</pre><details><summary>Source evidence</summary><pre>'+show(c.get('evidence',{}))+'</pre></details></details>' for c in row['checks'])
            report=reports.get(row['record_id']);link='<a href="'+html.escape(relative_link(output.parent,report))+'">Full stage / group rule evidence</a>' if report else ''
            cards.append('<details data-row="'+str(row['row'])+'"><summary>Row '+str(row['row'])+' · '+row['selection']+' · '+row['decision']+' · Validation '+row['validation_status']+' · Output comparison '+row['comparison_status']+' · '+str(len(row['checks']))+' validations</summary><p>'+html.escape(row['reason'])+'</p><pre>'+show(row['validation_counts'])+'</pre>'+link+'<details><summary>Input row values</summary><pre>'+show(row['input_row'])+'</pre></details>'+rules+'</details>')
        info=inventory.get(path,{});total=info.get('total_rows',len(rows));selected=sum(r['selection']=='selected' for r in rows)
        row_statuses=Counter(r['validation_status'] for r in rows)
        file_summaries.append(dict(decisions=dict(Counter(r['decision'] for r in rows)),comparison_outcomes=dict(Counter(r['comparison_status'] for r in rows)),file=path,not_processed_rows=max(total-len(rows),0),total_rows=total,selected_rows=selected,context_rows=len(rows)-selected,processed_rows=len(rows),validation_events=len(unique),event_statuses=dict(totals),row_statuses=dict(row_statuses)))
        shared='<details><summary>File-wide / shared group checks</summary><pre>'+show(file_checks[path])+'</pre></details>'
        file_links='<details><summary>All stage/group reports for this file</summary>'+''.join('<p><a href="'+html.escape(relative_link(output.parent,report))+'">Group '+str(i)+' — complete evidence</a></p>' for i,report in enumerate(dict.fromkeys(file_reports[path]),1))+'</details>'
        sections.append('<details><summary>#'+str(number)+' '+html.escape(origins.get(path,path))+' — '+str(total)+' total rows; '+str(selected)+' selected; '+str(len(rows)-selected)+' context; '+str(max(total-len(rows),0))+' not processed</summary><p>Original source files for this generated input: '+show([origins.get(p,p) for p in source_origins.get(path,[path])])+'</p><p>File validation totals (unique events; shared group events can apply to multiple rows): '+str(len(unique))+'</p><pre>'+show(totals)+'</pre>'+shared+file_links+row_browser(number,rows,cards)+'<p>Row validation outcomes: '+show(row_statuses)+'</p><p>File conclusion: '+str(sum(r['decision']=='KEEP' for r in rows))+' kept; '+str(sum(r['decision']=='DROP' for r in rows))+' dropped; '+str(sum(r['decision'] not in ('KEEP','DROP') for r in rows))+' stopped or not assessed among processed rows.</p></details>')
    comparison_events=[c for r in row_payload for c in r['checks'] if c['rule_id'].startswith('ROW-OUTPUT-')]
    comparison_status='FAIL' if (selection.get('full_dataset',False) and any(v['rows'] for v in outside_scope.values())) or conservation=='FAIL' or any(c['status']=='FAIL' for c in comparison_events) else 'BLOCKED' if any(c['status']=='BLOCKED' for c in comparison_events) else 'PASS' if comparison_events else 'NOT PROVIDED'
    decision_counts=dict(Counter(r['decision'] for r in row_payload))
    comparison_outcomes=dict(Counter(r['comparison_status'] for r in row_payload))
    scoped_outputs={role:sum(role_matches[role].values()) for role in ('keep','drop')}
    data=dict(population_audit=population,output_rows_outside_processed_identities=outside_scope,decision_counts=decision_counts,comparison_outcomes=comparison_outcomes,scoped_output_rows=scoped_outputs,count_balance=count_balance,row_statuses=dict(Counter(r['validation_status'] for r in row_payload)),files=file_summaries,source_origins=source_origins,input_kind='generated_previous_stage' if selection_override is not None else 'supplied_original',comparison_status=comparison_status,stage=start_stage,selection=selection,identity_fields=fields,original_rows=total_original,comparison_rows=role_counts,comparison_files=role_files,full_count_conservation=conservation,rows=row_payload,assessment_scope='A limited sample is not full-dataset acceptance. Related rows are processed as context, not counted as selected targets. Source-only generated outputs are not independent golden evidence.')
    output.with_suffix('.json').write_text(json.dumps(data,separators=(',',':'),default=str),encoding='utf-8')
    overview=render_overview(data)+'<details><summary>Output rows outside processed identities</summary><p>'+('Unexpected output identities: the complete original dataset was processed.' if selection.get('full_dataset',False) else 'Outside sampled identities: these output rows are not individually assessed by this sample.')+'</p><pre>'+show(outside_scope)+'</pre></details>'
    if population:
        from .population_audit import render_population
        overview+=render_population(population)
    body=overview+'<h2>Record-based validation — '+html.escape(start_stage.replace('_',' ').title())+'</h2><p>Input files: '+str(len(by_file))+' · Original rows: '+str(total_original)+' · Selected targets: '+str(selection.get('target_rows',len(selected_records)))+' · Related context: '+str(selection.get('context_rows',0))+'</p><p>'+html.escape(data['assessment_scope'])+'</p><details><summary>Original / keep / drop row reconciliation</summary><p>Keep files: '+str(len(role_files['keep']))+' · Drop files: '+str(len(role_files['drop']))+'</p><p>Original rows: '+str(total_original)+' · Keep rows: '+(str(role_counts['keep']) if role_counts['keep'] is not None else 'Not supplied')+' · Drop rows: '+(str(role_counts['drop']) if role_counts['drop'] is not None else 'Not supplied')+'</p><p>Output membership result: '+comparison_status+'</p><p>Count conservation: '+html.escape(conservation)+'</p><p>Count evidence (whole supplied datasets, not just sampled rows): '+show(count_balance)+'</p><p>For Final Action/Split, a difference means the supplied keep/drop populations do not balance against the supplied original population; verify that all three inputs describe the same extraction. This is separate from individual rule and field results.</p><p>Comparison identity: '+html.escape(', '.join(fields))+'</p><pre>'+show(role_files)+'</pre></details><label>Search file / row / rule <input oninput="document.querySelectorAll(\'main>details\').forEach(el=>el.hidden=!el.textContent.toLowerCase().includes(this.value.toLowerCase()))"></label>'+''.join(sections)
    main_root=session.root.parent.parent if session.root.parent.name=='entries' else session.root
    document=page('Record-based validation',body).replace('href="index.html#stage-results"','href="'+html.escape(relative_link(output.parent,main_root/'master/index.html'))+'#stage-results"')
    document=document.replace('</body>',BROWSER_SCRIPT+'</body>')
    output.write_text(document,encoding='utf-8')
    if population:
        print(f"Original / keep / drop verification — {start_stage}: {total_original} original rows; {role_counts['keep']} keep rows; {role_counts['drop']} drop rows; comparison {comparison_status}. Evidence: {output}")


def write_forwarded_row_reports(root,session,journeys,settings,start_stage):
    """Report transformed downstream rows separately, retaining original-source references."""
    stages=['final_action','split','stay','intermediate','final_medpar']
    parent_path=session.root/'row_selection.json'
    parent=json.loads(parent_path.read_text()) if parent_path.exists() else {}
    for stage in stages[stages.index(start_stage)+1:]:
        files={}
        for journey,directory in journeys:
            step=next(s for s in journey['steps'] if s['stage']==stage)
            if step['status'] not in ('BEFORE_START','NOT_REACHED') and step.get('input'):
                files[step['input']]=journey.get('source_files',[journey['source_file']])
        if not files:continue
        records=[];inventory=[]
        for path in files:
            rows=list(iter_records(Path(root)/path,Stage(stage),FileRole.SOURCE,root))
            records.extend(rows);inventory.append(dict(file=path,total_rows=len(rows),selected_rows=len(rows),context_rows=0))
        scope=dict(selection={'mode':'forwarded_from_selected_originals'},files=inventory,target_record_ids=[r.record_id for r in records],target_rows=len(records),context_rows=0,processed_rows=len(records),full_dataset=parent.get('full_dataset',True),parent_selection=parent.get('selection',{'mode':'all'}))
        write_row_report(root,session,journeys,settings,stage,[],records,scope,files)
