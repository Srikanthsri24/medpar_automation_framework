"""Real Intermediate-to-Final ticket regression, including compact evidence routes."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import pytest
from medpar_qa.enums import Stage
from medpar_qa.processing.writers import stay
from medpar_qa.stages.stay.processor import StayProcessor
from medpar_qa.orchestration.connected import ConnectedPipeline
from medpar_qa.reporting.compact import compact_reports


@pytest.mark.parametrize('death,expected,indicator,days,wi08',[
    ('20270101','', '', '', '0'),
    ('20190209','2019040','V',-2518,'2'),
])
def test_cutoff_and_signed_fields_move_through_real_processors(tmp_path,resolver,make_record,death,expected,indicator,days,wi08):
    source=json.loads(Path('data/demo_source_only/claims.json').read_text())[0]
    source['split_year_indicator']='Y00109'
    source['fiscalIntermediary']={'id':'01234','approvedDate':20260101}
    source['cacheDataInternal']={'deathDate':death,'isDeathDateVerified':'Y','bic_api_match_found':True}
    # A completed Stay is the input of this particular connected test.
    from medpar_qa.stages.stay.settings import StaySettings
    settings=StaySettings(dod_data_cutoff_date='2026-04-20')
    rows,_=stay([make_record(source)],StayProcessor(resolver,settings=settings))
    path=tmp_path/'stay.json';path.write_text(json.dumps(rows))
    session=SimpleNamespace(root=tmp_path/'reports/test')
    pipeline=ConnectedPipeline(tmp_path,session,resolver,settings={'intermediate':{'dod_data_cutoff_date':'2026-04-20'}})
    assert pipeline.settings['stay']['dod_data_cutoff_date']=='2026-04-20'
    dates={stage.value:'2026-04-20' for stage in Stage}
    journey,directory=pipeline.run_file(path,dates,start_stage='intermediate',generate_outputs=True)
    assert journey['completed'],[(s['stage'],s.get('reason')) for s in journey['steps']]
    intermediate=json.loads((tmp_path/journey['steps'][3]['output']).read_text())[0]
    final=json.loads((tmp_path/journey['steps'][4]['output']).read_text())[0]
    for row in (intermediate,final):
        assert resolver.get(row,'medpar_himaster_dod_0230')==expected
        assert resolver.get(row,'medpar_dod_ind_0240')==indicator
        assert resolver.get(row,'medpar_death_after_adm_0611')==days
        assert resolver.get(row,'medpar_intmd_num_0580')=='01234'
        assert resolver.get(row,'warning_indicator_08')==wi08
    assert intermediate['cacheDataInternal']==source['cacheDataInternal']
    assert 'cacheDataInternal' not in final
    assert journey['steps'][3]['input_records']==journey['steps'][4]['input_records']==1
    report=json.loads((directory/'final_medpar/report.json').read_text())
    checks=report['stages'][0]['rule_results']
    assert any(c['rule_id']=='FM-CARRY-0611' and c['status']=='PASS' for c in checks)
    compact_reports(session.root)
    assert len(list(session.root.rglob('*.html')))==6


def test_cutoff_conflict_rejected_without_mutating_callers_config(tmp_path,resolver):
    config={'stay':{'dod_data_cutoff_date':'2026-04-20'},'intermediate':{'dod_data_cutoff_date':'2026-03-31'}}
    before=deepcopy(config)
    with pytest.raises(ValueError,match='must agree'):
        ConnectedPipeline(tmp_path,SimpleNamespace(root=tmp_path/'reports'),resolver,config)
    assert config==before
