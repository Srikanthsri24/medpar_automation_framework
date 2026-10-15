import json
from pathlib import Path
from medpar_qa.orchestration.connected import run_configured
from medpar_qa.reporting.run_layout import ReportSession


def run(tmp_path,wrong=False,bad_field=False,duplicate_candidates=False,both=False):
    import shutil
    (tmp_path/'config').mkdir();shutil.copy('config/field_aliases.yaml',tmp_path/'config/field_aliases.yaml')
    base=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    rows=[{**base,'claimCan':f'CAN{i}','claimCanNchEquatable':f'HICN{i}','internalControlNumber':f'ICN{i}'} for i in range(3)]
    kept=[{**r,'provider':{'providerId':'123456'}} for r in rows] if bad_field else rows
    if duplicate_candidates:
        kept=[{**r,'provider':{'providerId':'123456'}} for r in rows]*2+rows
    for name,data in [('original',rows),('keep',[] if wrong else kept),('drop',rows if wrong or both else [])]:
        (tmp_path/(name+'.json')).write_text(json.dumps(data))
    session=ReportSession.create('reports',project_root=tmp_path)
    configs={s:{'run_date':'2026-04-20'} for s in ('final_action','split','stay','intermediate','final_medpar')}
    configs['final_action']['single_files']=[dict(source=['original.json'],actual=['keep.json'],dropped=['drop.json'])]
    journeys,index=run_configured(tmp_path,session,configs,{'_row_selection':{'mode':'first_n_per_file','limit':2,'include_related_records':True}})
    return json.loads((session.root/'final_action/row_review.json').read_text()),journeys


def test_selected_rows_are_validated_with_original_numbers_and_outputs(tmp_path):
    audit,journeys=run(tmp_path)
    assert audit['original_rows']==3 and len(audit['rows'])==2
    assert audit['population_audit']['datasets']['original']['rows']==3
    assert audit['population_audit']['excess_output_occurrences']==0
    assert [r['row'] for r in audit['rows']]==[1,2]
    assert audit['comparison_rows']=={'keep':3,'drop':0}
    assert audit['full_count_conservation']=='PASS' and audit['comparison_status']=='PASS'
    assert all(journey['completed'] for journey,_ in journeys)
    assert all(r['decision']=='KEEP' and r['validation_counts']['PASS']>0 for r in audit['rows'])


def test_equal_counts_do_not_hide_wrong_keep_drop_membership(tmp_path):
    audit,_=run(tmp_path,wrong=True)
    assert audit['full_count_conservation']=='PASS'
    assert audit['comparison_status']=='FAIL'
    assert all(any(c['rule_id']=='ROW-OUTPUT-MEMBERSHIP' and c['status']=='FAIL' for c in r['checks']) for r in audit['rows'])


def test_matching_identity_and_count_still_detect_field_mismatch(tmp_path):
    audit,_=run(tmp_path,bad_field=True)
    assert audit['full_count_conservation']=='PASS' and audit['comparison_status']=='FAIL'
    assert all(r['validation_status']=='FAIL' for r in audit['rows'])
    for row in audit['rows']:
        assert any(c['rule_id']=='ROW-OUTPUT-MEMBERSHIP' and c['status']=='PASS' for c in row['checks'])
        assert any(c['rule_id']=='ROW-OUTPUT-FIELD-provider_id' and c['status']=='FAIL' for c in row['checks'])


def test_s3_original_keep_drop_objects_use_same_row_selection_flow(tmp_path,monkeypatch,capsys):
    import run_commands as runner
    import medpar_qa.ingestion.input_sources as sources
    from copy import deepcopy
    base=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    rows=[{**base,'claimCan':f'CAN{i}','claimCanNchEquatable':f'HICN{i}','internalControlNumber':f'ICN{i}'} for i in range(3)]
    objects={'original':json.dumps(rows).encode(),'keep':json.dumps(rows).encode(),'drop':b'[]'}
    class FakeS3:
        def head_object(self,Bucket,Key):return {'ContentLength':len(objects[Key])}
        def download_file(self,bucket,key,filename):Path(filename).write_bytes(objects[key])
    monkeypatch.setattr(sources,'aws_client',lambda path:FakeS3())
    plan=deepcopy(runner.SOURCE_RUN)
    plan.update(source_type='s3',start_stage='final_action',run_date='2026-04-20',row_selection={'mode':'first_n_per_file','limit':2,'include_related_records':True})
    plan['source_paths']['s3']['final_action']={role:{'files':['s3://medpar-demo-bucket/'+role],'folders':[]} for role in objects}
    monkeypatch.setattr(runner,'SOURCE_RUN',plan)
    assert runner.main([])==0
    import re
    output=capsys.readouterr().out
    master=runner.PROJECT_ROOT/re.search(r'Connected pipeline report: (.+)',output).group(1)
    audit=json.loads((master.parent.parent/'final_action/row_review.json').read_text())
    assert audit['original_rows']==3 and len(audit['rows'])==2
    assert audit['comparison_status']=='PASS'
    assert audit['comparison_rows']=={'keep':3,'drop':0}
    assert len(list(master.parent.parent.rglob('*.html')))==6


def test_final_row_report_keeps_explicit_bypass_drop_decision(tmp_path):
    import shutil
    (tmp_path/'config').mkdir();shutil.copy('config/field_aliases.yaml',tmp_path/'config/field_aliases.yaml')
    base=json.loads(Path('data/demo_connected/intermediate_candidate.json').read_text())[0]
    rows=[{**base,'claimCanNchEquatable':f'BYPASS-{days}','utilization_days':days,'medpar_lgth_stay_0260':2} for days in (2,3)]
    (tmp_path/'original.json').write_text(json.dumps(rows))
    session=ReportSession.create('reports',project_root=tmp_path)
    configs={s:{'run_date':'2026-04-20'} for s in ('final_action','split','stay','intermediate','final_medpar')}
    configs['final_medpar']['single_files']=[dict(source=['original.json'])]
    journeys,_=run_configured(tmp_path,session,configs,start_stage='final_medpar')
    assert journeys[0][0]['steps'][-1]['status']=='KEEP'
    audit=json.loads((session.root/'final_medpar/row_review.json').read_text())
    assert [r['decision'] for r in audit['rows']]==['KEEP','DROP']


def test_membership_failure_explains_wrong_output(tmp_path):
    audit,_=run(tmp_path,wrong=True)
    for row in audit['rows']:
        assert row['comparison_status']=='FAIL'
        assert any('wrong output' in reason for reason in row['comparison_reasons'])
    assert audit['decision_counts']=={'KEEP':2}
    assert audit['scoped_output_rows']=={'keep':0,'drop':2}
    assert audit['output_rows_outside_processed_identities']['drop']['rows']==1


def test_split_reconciles_exception_separately_from_keep_drop(tmp_path):
    import shutil
    (tmp_path/'config').mkdir();shutil.copy('config/field_aliases.yaml',tmp_path/'config/field_aliases.yaml')
    base=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    good={**base,'internalControlNumber':'GOOD','transactionCode':3,'stayFromDate':'20260101','stayThruDate':'20260103','admissionDate':'20260101'}
    bad={**good,'internalControlNumber':'BAD','transactionCode':6}
    for name,rows in [('original',[good,bad]),('keep',[{**good,'split_year_indicator':'Y00109'}]),('drop',[])]:
        (tmp_path/(name+'.json')).write_text(json.dumps(rows))
    session=ReportSession.create('reports',project_root=tmp_path)
    configs={s:{'run_date':'2026-04-20'} for s in ('final_action','split','stay','intermediate','final_medpar')}
    configs['split']['single_files']=[dict(source=['original.json'],actual=['keep.json'],dropped=['drop.json'])]
    run_configured(tmp_path,session,configs,{'_row_selection':{'mode':'all'}},start_stage='split')
    audit=json.loads((session.root/'split/row_review.json').read_text())
    assert audit['full_count_conservation']=='PASS'
    assert audit['count_balance']['original_rows']==2 and audit['count_balance']['exception_rows']==1
    assert audit['count_balance']['expected_keep_plus_drop_rows']==1
    exceptional=next(r for r in audit['rows'] if r['decision']=='STOPPED')
    assert exceptional['comparison_status']=='PASS'
    assert 'exception output' in exceptional['reason']


def test_searches_past_first_two_duplicate_identity_candidates(tmp_path):
    audit,_=run(tmp_path,duplicate_candidates=True)
    for row in audit['rows']:
        assert row['comparison_status']=='PASS'
        proof=next(c for c in row['checks'] if c['rule_id']=='ROW-OUTPUT-CANDIDATES')
        assert proof['evidence']['candidate_count']==3
        assert proof['actual']==1
        assert proof['evidence']['selected_reference']['row']>6
    assert audit['full_count_conservation']=='FAIL'  # Extra physical output rows remain visible.


def test_opposite_output_conflict_is_explicit_failure_not_duplicate_block(tmp_path):
    audit,_=run(tmp_path,both=True)
    for row in audit['rows']:
        assert row['comparison_status']=='FAIL'
        assert any('both KEEP and DROP' in reason for reason in row['comparison_reasons'])
        assert next(c for c in row['checks'] if c['rule_id']=='ROW-OUTPUT-CANDIDATES')['status']=='PASS'


def test_s3_sample_retains_source_totals_and_searches_complete_references(tmp_path):
    import io,shutil
    import pyarrow as pa
    import pyarrow.parquet as pq
    from medpar_qa.ingestion.input_sources import InputSources
    (tmp_path/'config').mkdir();shutil.copy('config/field_aliases.yaml',tmp_path/'config/field_aliases.yaml')
    base=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    rows=[{**base,'claimCan':f'CAN{i}','claimCanNchEquatable':f'HICN{i}','internalControlNumber':f'ICN{i}'} for i in range(25)]
    sink=pa.BufferOutputStream();pq.write_table(pa.Table.from_pylist(rows),sink,row_group_size=5)
    objects={'original':sink.getvalue().to_pybytes(),'keep.json':json.dumps(rows).encode(),'drop.json':b'[]'}
    class Fake:
        def head_object(self,Bucket,Key):return {'ContentLength':len(objects[Key]),'ETag':'v1'}
        def get_object(self,Bucket,Key,Range,IfMatch):
            assert IfMatch=='v1'
            start,end=map(int,Range[6:].split('-'));return {'Body':io.BytesIO(objects[Key][start:end+1])}
        def download_file(self,bucket,key,filename):Path(filename).write_bytes(objects[key])
    selection={'mode':'first_n_per_file','limit':2,'include_related_records':False}
    session=ReportSession.create('reports',project_root=tmp_path)
    resolver=InputSources(tmp_path,session.root,client=Fake(),s3_read_mode='sample_parquet',row_selection=selection)
    config={'final_action':{'run_date':'2026-04-20','single_files':[dict(source=['s3://medpar-demo-bucket/original'],actual=['s3://medpar-demo-bucket/keep.json'],dropped=['s3://medpar-demo-bucket/drop.json'])]}}
    for stage in ('split','stay','intermediate','final_medpar'):config[stage]={'run_date':'2026-04-20'}
    configured=resolver.prepare(config,connected=True)
    journeys,_=run_configured(tmp_path,session,configured,{'_row_selection':selection})
    audit=json.loads((session.root/'final_action/row_review.json').read_text())
    assert audit['original_rows']==25 and len(audit['rows'])==2
    assert audit['comparison_rows']=={'keep':25,'drop':0}
    assert audit['comparison_status']=='PASS'
    assert audit['population_audit'] is None and audit['partial_source_caches']
    assert 'Full-source identity-population audit: NOT ASSESSED' in (session.root/'final_action/row_review.html').read_text()
    assert audit['output_rows_outside_processed_identities']['keep']['rows']==23
    assert all(journey['completed'] for journey,_ in journeys)
