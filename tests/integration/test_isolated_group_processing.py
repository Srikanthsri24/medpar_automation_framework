"""A bad group stops independently while cross-file related records stay together."""
import json
from pathlib import Path
from datetime import date
from medpar_qa.orchestration.connected import ConnectedPipeline,processing_components,run_configured
from medpar_qa.reporting.run_layout import ReportSession
from medpar_qa.enums import Stage


def test_related_cancellation_claims_connect_even_across_admission_dates(resolver,make_record):
    data=dict(hicn='TEST',providerId='990999',stayFromDate='20260101',stayThruDate='20260103',transactionCode=1,queryCode=0,internalControlNumber='A')
    records=[make_record({**data,'admissionDate':'20260101'}),make_record({**data,'admissionDate':'20260102','queryCode':5},row=2)]
    assert len(processing_components(records,resolver,'final_action',{}))==1


def test_invalid_claim_does_not_stop_an_unrelated_valid_flow(tmp_path):
    from medpar_qa.normalization.fields import FieldResolver
    from medpar_qa.orchestration.connected import run_configured
    resolver=FieldResolver.from_yaml('config/field_aliases.yaml')
    base=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    import shutil
    (tmp_path/'config').mkdir()
    shutil.copy('config/field_aliases.yaml',tmp_path/'config/field_aliases.yaml')
    source=tmp_path/'claims.json'
    source.write_text(json.dumps([{**base,'hicn':'GOOD'},{**base,'hicn':'BAD','queryCode':2}]))
    session=ReportSession.create('reports',project_root=tmp_path)
    configs={stage:{'run_date':'2026-04-20'} for stage in ('final_action','split','stay','intermediate','final_medpar')}
    configs['final_action'].update(single_files=[{'source':['claims.json']}])
    journeys,index=run_configured(tmp_path,session,configs)
    assert len(journeys)==2
    assert sum(journey['completed'] for journey,_ in journeys)==1
    good=next(journey for journey,_ in journeys if journey['completed'])
    bad=next(journey for journey,_ in journeys if not journey['completed'])
    assert [s['status'] for s in good['steps']]==['KEEP']*5
    assert bad['steps'][0]['status']=='FAIL'
    for left,right in zip(good['steps'],good['steps'][1:]):assert left['output']==right['input']
