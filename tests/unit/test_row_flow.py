import json
from medpar_qa.reporting.row_flow import write_row_flow


def test_merging_source_rows_are_distinct_from_forwarded_rows(tmp_path):
    master=tmp_path/'master';master.mkdir();group=tmp_path/'connected/g1';group.mkdir(parents=True)
    steps=[dict(stage=s,status='BEFORE_START') for s in ('final_action','split')]+[
        dict(stage='stay',status='KEEP',input='source.json',input_records=3,retained=1,dropped=0,output='stay/retained.json'),
        dict(stage='intermediate',status='KEEP',input='stay/retained.json',input_records=1,retained=1,dropped=0,output='intermediate/retained.json'),
        dict(stage='final_medpar',status='BLOCKED',input='intermediate/retained.json',input_records=1,retained=0,dropped=0)]
    def audit(n,decision,kind):return dict(rows=[{}]*n,decision_counts={decision:n},input_kind=kind)
    audits={s:[(audit(n,d,k),tmp_path/s/'row_review.html')] for s,n,d,k in [('stay',3,'KEEP','supplied_original'),('intermediate',1,'KEEP','generated_previous_stage'),('final_medpar',1,'STOPPED','generated_previous_stage')]}
    body=write_row_flow(master,[({'steps':steps},group)],audits)
    data=json.loads((master/'row_flow.json').read_text());stay=data[2]
    assert stay['kept_input_rows']==3 and stay['generated_output_rows']==1 and stay['forwarded_rows']==1
    assert data[3]['received_rows']==1 and data[3]['received_verified']
    assert data[4]['stopped_input_rows']==1
    assert all(r['input_balance_verified'] and r['received_verified'] for r in data)
    assert 'Files moved' not in body and 'Rows forwarded' in body


def test_inconsistent_received_rows_are_not_reported_verified(tmp_path):
    body=write_row_flow(tmp_path,[],{'split':[(dict(rows=[{}],input_kind='generated_previous_stage',decision_counts={'KEEP':1}),tmp_path/'row_review.html')]})
    assert 'Count discrepancy' in body
    assert not json.loads((tmp_path/'row_flow.json').read_text())[1]['received_verified']


def test_output_and_next_input_row_difference_is_flagged(tmp_path):
    steps=[dict(stage='final_action',status='KEEP',input_records=2,retained=2,output='kept.json'),dict(stage='split',status='DROP',input='kept.json',input_records=1,retained=0)]
    audits={'final_action':[(dict(rows=[{},{}],decision_counts={'KEEP':2},input_kind='supplied_original'),tmp_path/'source.html')],'split':[(dict(rows=[{}],decision_counts={'DROP':1},input_kind='generated_previous_stage'),tmp_path/'next.html')]}
    body=write_row_flow(tmp_path,[({'steps':steps},tmp_path)],audits)
    data=json.loads((tmp_path/'row_flow.json').read_text())
    assert not data[0]['output_handoff_verified']
    assert 'Count discrepancy' in body


def test_started_here_separates_file_count_targets_and_context(tmp_path):
    group=tmp_path/'connected/g1';group.mkdir(parents=True)
    rows=[dict(file='a.json',decision='KEEP' if i<3 else 'DROP',checks=[]) for i in range(5)]
    files=[dict(file='a.json',total_rows=100,selected_rows=3,context_rows=2,decisions={'KEEP':3,'DROP':2}),dict(file='b.json',total_rows=7,selected_rows=0,context_rows=0,decisions={})]
    audit=dict(rows=rows,files=files,decision_counts={'KEEP':3,'DROP':2},input_kind='supplied_original',selection={'target_rows':3,'context_rows':2})
    steps=[dict(stage='final_action',status='KEEP',input_records=5,retained=3,output='kept.json'),dict(stage='split',status='FAIL',input='kept.json',input_records=3,retained=0)]
    forwarded=dict(rows=[{}]*3,files=[],decision_counts={'STOPPED':3},input_kind='generated_previous_stage')
    body=write_row_flow(tmp_path,[({'steps':steps},group)],{'final_action':[(audit,tmp_path/'final_action/row_review.html')],'split':[(forwarded,tmp_path/'split/row_review.html')]})
    metrics=json.loads((tmp_path/'row_flow.json').read_text())[0]
    assert metrics['supplied_input_files']==2 and metrics['selected_target_rows']==3 and metrics['context_rows']==2
    assert '2 supplied files' in body and '3 target rows + 2 context = 5 starting rows' in body
    assert 'a.json' in body and 'b.json' in body
    assert 'KEEP and DROP comparison with supplied paths' in body
