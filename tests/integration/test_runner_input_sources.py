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
