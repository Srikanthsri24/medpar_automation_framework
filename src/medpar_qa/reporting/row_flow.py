"""Report record transfers using executed stage handoffs, never file lineage counts."""
import json
from collections import Counter,defaultdict
from .status_navigation import page,e
from .path_utils import relative_link

STAGES=('final_action','split','stay','intermediate','final_medpar')


def write_row_flow(master,journeys,audits):
    """Keep input-row decisions distinct from generated output/received row counts."""
    evidence=defaultdict(list);produced=Counter();forwarded=Counter();verified_received=Counter();handoff_errors=Counter()
    for journey,directory in journeys:
        steps=journey['steps']
        for i,step in enumerate(steps):
            if step['status'] in ('BEFORE_START','NOT_REACHED'):continue
            stage=step['stage'];produced[stage]+=step.get('retained',0)
            following=steps[i+1] if i+1<len(steps) else None
            moved=bool(following and step.get('output') and following.get('input')==step['output'] and following['status'] not in ('BEFORE_START','NOT_REACHED'))
            count=following.get('input_records',0) if moved else 0
            if moved and count!=step.get('retained',0):handoff_errors[stage]+=1
            if following and step['status']=='KEEP' and step.get('output') and not moved:handoff_errors[stage]+=1
            forwarded[stage]+=count
            if moved:verified_received[following['stage']]+=count
            report=relative_link(master,directory/stage/'report.html')
            proof={k:step.get(k) for k in ('input','input_files','input_records','output','retained','dropped','status','reason')}
            evidence[stage].append('<details><summary>Group '+str(len(evidence[stage])+1)+' — '+str(step.get('input_records',0))+' input rows; '+str(step.get('retained',0))+' output rows; '+str(count)+' forwarded rows</summary><p>'+e(step.get('reason',''))+'</p><a href="'+e(report)+'">Rule and decision evidence</a><pre>'+e(json.dumps(proof,default=str))+'</pre><p>Transfer proof: '+('Next stage read this generated output: '+str(count)+' rows.' if moved else 'No next-stage read occurred.')+'</p></details>')
    table=[];transfers=[];metrics=[]
    for stage in STAGES:
        sources=audits.get(stage,[]);decisions=Counter();started=received=0
        for audit,_ in sources:
            n=len(audit.get('rows',[]));decisions.update(audit.get('decision_counts',{}))
            if audit.get('input_kind')=='supplied_original':started+=n
            else:received+=n
        total=started+received;kept=decisions['KEEP'];dropped=decisions['DROP'];stopped=sum(v for k,v in decisions.items() if k not in ('KEEP','DROP'))
        count_ok=total==kept+dropped+stopped
        transfer_ok=received==verified_received[stage]
        row=dict(stage=stage,started_rows=started,received_rows=received,input_rows=total,kept_input_rows=kept,dropped_input_rows=dropped,stopped_input_rows=stopped,generated_output_rows=produced[stage],forwarded_rows=forwarded[stage],input_balance_verified=count_ok,received_verified=transfer_ok,output_handoff_verified=not handoff_errors[stage])
        metrics.append(row)
        filename=stage+'_row_flow.html'
        links=''.join('<p><a href="'+e(relative_link(master,p))+'">Open file inventory, row decisions and comparison evidence</a></p>' for _,p in sources)
        body='<p>Input rows: '+str(total)+' = '+str(started)+' started here + '+str(received)+' received. Input decisions: '+str(kept)+' KEEP + '+str(dropped)+' DROP + '+str(stopped)+' STOPPED.</p><p>Generated output rows: '+str(produced[stage])+'. Rows read by next stage: '+str(forwarded[stage])+'. Stay merging and derived records can change output row counts; source rows and output rows are reported separately.</p>'+links+''.join(evidence[stage])
        (master/filename).write_text(page(stage.replace('_',' ').title()+' — row transfer evidence',body),encoding='utf-8')
        def cell(n):return '<td><a href="'+filename+'">'+f'{n:,}'+'</a></td>'
        state='Not run' if not total else 'Verified counts' if count_ok and transfer_ok and not handoff_errors[stage] else 'Count discrepancy — inspect evidence'
        table.append('<tr><td>'+e(stage.replace('_',' ').title())+'</td>'+''.join(cell(n) for n in (started,received,total,kept,dropped,stopped))+'</tr>')
        next_stage=STAGES[STAGES.index(stage)+1].replace('_',' ').title() if stage!=STAGES[-1] else 'End of workflow'
        transfers.append('<tr><td>'+e(stage.replace('_',' ').title())+'</td>'+cell(produced[stage])+cell(forwarded[stage])+'<td>'+next_stage+'</td><td>'+state+'</td></tr>')
    (master/'row_flow.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    return '<section id="stage-transfers"><h2>Rows processed and forwarded by stage</h2><p>Files are input containers. KEEP/DROP decisions apply to their rows. Only generated retained output rows enter the next stage. Started here counts processed rows supplied directly for that stage, including selected context. Received counts generated rows read from the previous stage.</p><table><tr>'+''.join('<th>'+h+'</th>' for h in ('Stage','Started here','Received rows','Processed input rows','KEEP input rows','DROP input rows','STOPPED input rows'))+'</tr>'+''.join(table)+'</table><h3>Generated rows and next-stage handoff</h3><table><tr><th>Stage</th><th>Generated output rows</th><th>Rows forwarded</th><th>Next stage</th><th>Count reconciliation</th></tr>'+''.join(transfers)+'</table><p>For every stage: Started here + Received = Processed; KEEP + DROP + STOPPED = Processed. Generated output and forwarded counts can differ from KEEP input rows when a stage merges records. Click any number for transfer proof and row evidence. Verified counts describe arithmetic and handoff reconciliation, not a passing business-validation result.</p></section>'
