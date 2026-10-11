"""Connected execution and real FA/Split regressions; these are not CMS certification."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from medpar_qa.enums import Stage, ValidationStatus, RecordDecision
from medpar_qa.models import RuleResult, ClaimDecision
from medpar_qa.orchestration.connected import ConnectedPipeline, _failfast
from test_final_action import base_claim

DATES = {s.value: '2026-03-20' for s in Stage}


def setup_pipeline(tmp_path, resolver, records):
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(records), encoding='utf-8')
    return ConnectedPipeline(tmp_path, SimpleNamespace(root=tmp_path/'reports/session'), resolver), path


def test_failfast_stops_real_execution_and_resets_observer():
    visited = []
    class Processor:
        stage = Stage.FINAL_ACTION
        def validate(self, records):
            RuleResult(self.stage, 'FIRST', ValidationStatus.PASS, 'first')
            RuleResult(self.stage, 'SECOND', ValidationStatus.FAIL, 'stop')
            visited.append('must never execute')
    result = _failfast(Processor(), [])
    assert [r.rule_id for r in result.rule_results] == ['FIRST','SECOND']
    assert not visited
    RuleResult(Stage.SPLIT, 'OUTSIDE', ValidationStatus.FAIL, 'normal validation still works')


def test_drop_stops_all_later_stages(tmp_path, resolver):
    pipeline, source = setup_pipeline(tmp_path, resolver, [base_claim(queryCode=0)])
    journey, directory = pipeline.run_file(source, DATES)
    assert journey['steps'][0]['status'] == 'DROP'
    assert all(s['status'] == 'NOT_REACHED' for s in journey['steps'][1:])
    dropped = json.loads((directory/'final_action/dropped.json').read_text())
    assert dropped[0]['rule'] == 'FA-RULE-01'
    assert not list(directory.rglob('retained.json'))


def test_keep_forwards_generated_output_then_blocks_missing_stay_writer(tmp_path, resolver):
    pipeline, source = setup_pipeline(tmp_path, resolver, [base_claim(admissionDate='20260101')])
    journey, directory = pipeline.run_file(source, DATES)
    assert [s['status'] for s in journey['steps']] == ['KEEP','KEEP','BLOCKED','NOT_REACHED','NOT_REACHED']
    assert journey['steps'][1]['input'] == journey['steps'][0]['output']
    assert journey['steps'][2]['input'] == journey['steps'][1]['output']
    output = json.loads((directory/'split/retained.json').read_text())
    assert output[0]['split_year_indicator'] == 'Y00109'
    assert output[0]['internalControlNumber'] == 'I-1'
    assert (directory/'index.html').exists()
    assert all((directory/s.value/'report.html').exists() for s in Stage)


def test_failed_query_stops_before_selection(tmp_path, resolver):
    pipeline, source = setup_pipeline(tmp_path, resolver, [base_claim(queryCode=2)])
    journey, directory = pipeline.run_file(source, DATES)
    assert journey['steps'][0]['status'] == 'FAIL'
    result = json.loads((directory/'final_action/report.json').read_text())['stages'][0]
    schema = [r for r in result['rule_results'] if r['rule_id']=='FA-PRE-SCHEMA']
    assert schema[0]['expected'] == [0,1,3,5]
    assert not any(d for d in result['decisions'])
    assert all(s['status'] == 'NOT_REACHED' for s in journey['steps'][1:])


def test_mixed_keep_drop_forwards_only_kept_records(tmp_path, resolver):
    keep = base_claim(admissionDate='20260101')
    drop = base_claim(queryCode=0,provider={'providerId':'P-2'},admissionDate='20260101')
    pipeline, source = setup_pipeline(tmp_path, resolver, [keep,drop])
    journey,directory = pipeline.run_file(source,DATES)
    assert journey['steps'][0]['retained'] == 1
    assert journey['steps'][0]['dropped'] == 1
    assert journey['steps'][1]['input_records'] == 1


def test_missing_input_still_has_journey_report(tmp_path, resolver):
    pipeline,_ = setup_pipeline(tmp_path,resolver,[])
    journey,directory = pipeline.run_file(tmp_path/'missing.json',DATES)
    assert journey['steps'][0]['status'] == 'FAIL'
    assert (directory/'index.html').exists()


def test_all_five_stage_handoffs_with_validated_candidates(tmp_path, resolver, monkeypatch):
    """Orchestration contract test; real FA/Split are tested separately above."""
    from medpar_qa.orchestration.pipeline import Pipeline
    calls=[]
    class Processor:
        def __init__(self, stage):
            self.stage=stage
            self.resolver=resolver
        def validate(self, records):
            sources=[r for r in records if r.source.role.value=='source']
            actuals=[r for r in records if r.source.role.value=='actual_output']
            calls.append((self.stage, sources[0].data['marker']))
            RuleResult(self.stage, 'TEST-CHECK', ValidationStatus.PASS, 'controlled check')
            if self.stage in (Stage.FINAL_ACTION,Stage.SPLIT):
                for r in sources: ClaimDecision(r.record_id,RecordDecision.KEEP,'TEST-CHECK','keep')
        def calculate_indicator(self, record, last_thru=None): return 'Y00109'
        settings=SimpleNamespace(outside_window_indicator='Y99999')
    monkeypatch.setattr(Pipeline,'_processors',lambda self:{s:Processor(s) for s in Stage})
    outputs={}
    for stage,marker in [(Stage.STAY,'stay'),(Stage.INTERMEDIATE,'intermediate'),(Stage.FINAL_MEDPAR,'final')]:
        path=tmp_path/f'{stage.value}-candidate.json'
        path.write_text(json.dumps([base_claim(marker=marker)]))
        outputs[stage.value]=[path.name]
    pipeline,source=setup_pipeline(tmp_path,resolver,[base_claim(marker='claim')])
    journey,directory=pipeline.run_file(source,DATES,outputs)
    assert journey['completed']
    assert [s['status'] for s in journey['steps']]==['KEEP']*5
    assert calls==[(Stage.FINAL_ACTION,'claim'),(Stage.SPLIT,'claim'),(Stage.STAY,'claim'),
                   (Stage.INTERMEDIATE,'stay'),(Stage.FINAL_MEDPAR,'intermediate')]
    assert json.loads((directory/'final_medpar/retained.json').read_text())[0]['marker']=='final'


def test_blocked_candidate_is_never_forwarded(tmp_path, resolver, monkeypatch):
    from medpar_qa.orchestration.pipeline import Pipeline
    real=Pipeline._processors
    visited=[]
    class Stay:
        stage=Stage.STAY
        def validate(self, records):
            RuleResult(self.stage,'ST-CANDIDATE',ValidationStatus.BLOCKED,'cannot establish derivation')
            visited.append('later check')
    def processors(self):
        values=real(self); values[Stage.STAY]=Stay(); return values
    monkeypatch.setattr(Pipeline,'_processors',processors)
    pipeline,source=setup_pipeline(tmp_path,resolver,[base_claim(admissionDate='20260101')])
    (tmp_path/'candidate.json').write_text(json.dumps([base_claim()]))
    journey,directory=pipeline.run_file(source,DATES,{'stay':['candidate.json']})
    assert journey['steps'][2]['status']=='BLOCKED'
    assert journey['steps'][3]['status']=='NOT_REACHED'
    assert not (directory/'stay/retained.json').exists()
    assert not visited
