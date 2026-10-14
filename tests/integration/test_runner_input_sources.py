"""Exercise mocked S3 downloads through the real command runner and stage validator."""
import json
from pathlib import Path
import re
import sys
import pytest


@pytest.mark.integration
def test_s3_input_reaches_real_final_action_report(tmp_path,monkeypatch,capsys):
    import run_commands as runner
    import medpar_qa.ingestion.input_sources as sources
    downloads=[]
    content=(runner.PROJECT_ROOT/'data/demo_connected/claims.json').read_bytes()
    class FakeS3:
        def head_object(self,**kwargs):return {'ContentLength':len(content),'ETag':'mock-etag'}
        def download_file(self,bucket,key,filename):
            downloads.append((bucket,key));Path(filename).write_bytes(content)
    monkeypatch.setattr(sources,'aws_client',lambda path:FakeS3())
    configuration={'connected_pipeline_enabled':False,'stage_runs':{'final_action':{'enabled':True,'run_date':'2026-04-20','single_files':[{'name':'Mock S3 end-to-end','source':['s3://medpar-demo-bucket/claims.json'],'mode':'calculate'}]}}}
    path=tmp_path/'stage-runs.json';path.write_text(json.dumps(configuration))
    monkeypatch.setattr(sys,'argv',['run_commands.py','--config',str(path)])
    assert runner.main()==0
    output=capsys.readouterr().out
    assert downloads==[('medpar-demo-bucket','claims.json')]
    master=runner.PROJECT_ROOT/re.search(r'Master HTML report: (.+)',output).group(1)
    assert '../input_sources.html' in master.read_text()
    inventory=json.loads((master.parent.parent/'input_sources.json').read_text())
    assert inventory['resolved_files']==1
    assert inventory['files'][0]['origin']=='s3://medpar-demo-bucket/claims.json'
    result=json.loads(next(master.parent.parent.glob('final_action/*/report.json')).read_text())
    assert any(c['rule_id']=='FA-RULE-01' and c['status']=='PASS' for s in result['stages'] for c in s['rule_results'])
    assert [d['decision'] for s in result['stages'] for d in s['decisions']]==['KEEP']
    assert not any(c['status'] in ('FAIL','BLOCKED') for s in result['stages'] for c in s['rule_results'])


@pytest.mark.integration
@pytest.mark.parametrize('remote',[False,True],ids=['local','s3-folder'])
def test_connected_runner_forwards_same_outputs_through_all_stages(tmp_path,monkeypatch,capsys,remote):
    import run_commands as runner
    import medpar_qa.ingestion.input_sources as sources
    objects={('medpar-demo-bucket','seed/claims.json'):(runner.PROJECT_ROOT/'data/demo_connected/claims.json').read_bytes()}
    for stage in ('stay','intermediate','final_medpar'):
        objects[('medpar-demo-bucket',f'{stage}/candidate.json')]=(runner.PROJECT_ROOT/f'data/demo_connected/{stage}_candidate.json').read_bytes()
    class FakeS3:
        def get_paginator(self,operation):return self
        def paginate(self,Bucket,Prefix):
            for (bucket,key),content in objects.items():
                if bucket==Bucket and key.startswith(Prefix):yield {'Contents':[{'Key':key,'Size':len(content)}]}
        def download_file(self,bucket,key,filename):Path(filename).write_bytes(objects[(bucket,key)])
    monkeypatch.setattr(sources,'aws_client',lambda path:FakeS3())
    item={'source':['s3://medpar-demo-bucket/seed/' if remote else 'data/demo_connected/claims.json'],
          'pipeline_outputs':{stage:[f's3://medpar-demo-bucket/{stage}/' if remote else f'data/demo_connected/{stage}_candidate.json'] for stage in ('stay','intermediate','final_medpar')}}
    # Old configuration selected independent mode. Explicit override must restore forwarding.
    config={'connected_pipeline_enabled':False,'stage_runs':{'final_action':{'run_date':'2026-04-20','single_files':[item]}}}
    path=tmp_path/'flow.json';path.write_text(json.dumps(config),encoding='utf-8-sig')
    monkeypatch.setattr(sys,'argv',['run_commands.py','--config',str(path),'--flow','connected'])
    assert runner.main()==0
    output=capsys.readouterr().out
    index=runner.PROJECT_ROOT/re.search(r'Connected pipeline report: (.+)',output).group(1)
    journey=json.loads(next(index.parent.glob('*/journey.json')).read_text())
    assert journey['completed']
    assert [step['status'] for step in journey['steps']]==['KEEP']*5
    for current,following in zip(journey['steps'],journey['steps'][1:]):
        assert current['output']==following['input']
        assert (runner.PROJECT_ROOT/current['output']).exists()
    assert '../input_sources.html' in index.read_text()


@pytest.mark.integration
def test_source_only_connected_flow_generates_without_comparison_files(tmp_path,monkeypatch,capsys):
    import run_commands as runner
    config={'stage_runs':{'final_action':{'run_date':'2026-04-20','single_files':[{'source':['data/demo_connected/claims.json']}]}}}
    path=tmp_path/'source-only.json';path.write_text(json.dumps(config))
    monkeypatch.setattr(sys,'argv',['run_commands.py','--config',str(path)])
    assert runner.main()==0
    index=runner.PROJECT_ROOT/re.search(r'Connected pipeline report: (.+)',capsys.readouterr().out).group(1)
    journey=json.loads(next(index.parent.glob('*/journey.json')).read_text())
    assert [step['status'] for step in journey['steps']]==['KEEP']*5
    assert journey['steps'][0]['output']==journey['steps'][1]['input']
    assert journey['steps'][1]['output']==journey['steps'][2]['input']
    assert all(step['output_origin']=='source_generated' for step in journey['steps'][2:])
    assert journey['completed']


@pytest.mark.integration
@pytest.mark.parametrize('start_stage', ['final_action','split','stay','intermediate','final_medpar'])
@pytest.mark.parametrize('remote', [False,True], ids=['local','s3'])
def test_source_only_any_start_stage_generates_remaining_stages(tmp_path,monkeypatch,capsys,start_stage,remote):
    import run_commands as runner
    import medpar_qa.ingestion.input_sources as sources
    fixture='intermediate_candidate.json' if start_stage=='final_medpar' else 'stay_candidate.json' if start_stage=='intermediate' else 'claims.json'
    content=(runner.PROJECT_ROOT/'data/demo_connected'/fixture).read_bytes()
    if start_stage=='stay':
        rows=json.loads(content)
        for row in rows:row['split_year_indicator']='Y00109'  # Split output is the Stay input contract.
        content=json.dumps(rows).encode()
    class FakeS3:
        def get_paginator(self,operation):return self
        def paginate(self,**kwargs):yield {'Contents':[{'Key':'input/source.json','Size':len(content)}]}
        def download_file(self,bucket,key,filename):Path(filename).write_bytes(content)
    monkeypatch.setattr(sources,'aws_client',lambda path:FakeS3())
    folder=tmp_path/'inputs';folder.mkdir();(folder/'source.json').write_bytes(content)
    source='s3://medpar-demo-bucket/input/' if remote else str(folder)
    monkeypatch.setattr(sys,'argv',['run_commands.py','--source',source,'--start-stage',start_stage,'--run-date','2026-04-20'])
    assert runner.main()==0
    index=runner.PROJECT_ROOT/re.search(r'Connected pipeline report: (.+)',capsys.readouterr().out).group(1)
    path=next(index.parent.glob('*/journey.json'));journey=json.loads(path.read_text())
    order=['final_action','split','stay','intermediate','final_medpar'];start=order.index(start_stage)
    assert [s['status'] for s in journey['steps']]==['BEFORE_START']*start+['KEEP']*(5-start)
    assert journey['completed'] and journey['start_stage']==start_stage
    for stage in order[start:]:assert (path.parent/stage/'retained.json').exists()
    for stage in order[:start]:assert not (path.parent/stage/'retained.json').exists()
    final=json.loads((path.parent/'final_medpar/retained.json').read_text())
    assert 'split_year_indicator' not in final[0]
    assert 'BEFORE_START' in index.read_text() or start==0


@pytest.mark.integration
def test_cross_file_rule6_cancellation_is_grouped_before_forwarding(tmp_path,monkeypatch,capsys):
    import run_commands as runner
    content=json.loads((runner.PROJECT_ROOT/'data/demo_connected/claims.json').read_text())[0]
    folder=tmp_path/'claims';folder.mkdir()
    for qc in (0,5):
        (folder/f'{qc}.json').write_text(json.dumps([{**content,'queryCode':qc,'actionCode':4}]))
    monkeypatch.setattr(sys,'argv',['run_commands.py','--source',str(folder),'--run-date','2026-04-20'])
    assert runner.main()==0
    index=runner.PROJECT_ROOT/re.search(r'Connected pipeline report: (.+)',capsys.readouterr().out).group(1)
    path=next(index.parent.glob('*/journey.json'));journey=json.loads(path.read_text())
    assert journey['source_file_count']==2 and journey['steps'][0]['status']=='DROP'
    assert len(json.loads((path.parent/'final_action/dropped.json').read_text()))==2
    assert all(step['status']=='NOT_REACHED' for step in journey['steps'][1:])
    report=json.loads((path.parent/'final_action/report.json').read_text())
    rule=next(c for stage in report['stages'] for c in stage['rule_results'] if c['rule_id']=='FA-RULE-06')
    assert rule['status']=='PASS' and len(rule['source_files'])==2
