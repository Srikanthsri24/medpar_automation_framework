"""Real follow-up defects and reporting/performance regressions."""
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import pytest
from medpar_qa.enums import Stage,ValidationStatus
from medpar_qa.processing.writers import final_medpar
from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
from medpar_qa.stages.output_contracts import carry_forward_contracts,intermediary_type
from medpar_qa.stages.intermediate.structural import validate_age_and_ndc
from medpar_qa.reporting.row_diagnostics import diagnose_row


def test_generated_final_converts_legacy_0580_but_references_still_fail(resolver,make_record):
    data={'providerId':'990999','medparIntmdNum0580':{'id':'01234','approvedDate':20260101},'other':{'amount':21}}
    source=make_record(data,stage=Stage.FINAL_MEDPAR);before=deepcopy(data)
    rows,notes,dropped=final_medpar([source],FinalMedparProcessor(resolver))
    assert len(rows)==1 and not dropped
    assert resolver.get(rows[0],'medpar_intmd_num_0580')=='01234'
    assert source.data==before
    assert rows[0]['other']==before['other']
    target=make_record(rows[0],stage=Stage.FINAL_MEDPAR)
    assert carry_forward_contracts(source,target,resolver)[0].status==ValidationStatus.PASS
    assert intermediary_type(source,resolver,Stage.FINAL_MEDPAR).status==ValidationStatus.FAIL
    assert intermediary_type(target,resolver,Stage.FINAL_MEDPAR).status==ValidationStatus.PASS
    assert any('QA-REG-02' in note for note in notes)


def test_missing_age_with_zero_birth_date_is_blocked_not_invented(resolver,make_record):
    source=make_record({'beneficiary_date_of_birth':0,'admissionDate':'20260101'})
    target=make_record({})
    result=validate_age_and_ndc(target,resolver,11,source=source)[0]
    assert result.status==ValidationStatus.BLOCKED
    assert result.evidence['source_birth_date']==0
    assert target.data=={}
    source.data['beneficiary_date_of_birth']='19500101'
    assert validate_age_and_ndc(target,resolver,11,source=source)[0].status==ValidationStatus.FAIL
    target.data['medparAge0030']=250
    assert validate_age_and_ndc(target,resolver,11,source=source)[0].status==ValidationStatus.FAIL


def test_row_diagnosis_separates_group_stop_from_individual_code(resolver,make_record):
    record=make_record({'queryCode':1,'actionCode':6})
    check={'rule_id':'PIPELINE-GROUP-STOP','status':'BLOCKED','message':'Related query code 2 is invalid',
           'expected':[0,1,3,5],'actual':2,'evidence':{'blocking_rule':'FA-PRE-SCHEMA'}}
    issue=diagnose_row(record,[check],resolver,'final_action')[0]
    assert issue['source_facts']['row_query_code']==1
    assert issue['observed']==2
    assert 'not proof' in issue['scope']
    assert issue['source_file']=='fixture.json' and issue['source_row']==1


def test_report_refresh_discovers_saved_business_reports_once(tmp_path,monkeypatch):
    import medpar_qa.reporting.session_index as indexes
    calls=[];stages=[]
    entries=[{'stage_folder':'final_action'},{'stage_folder':'split'}]
    monkeypatch.setattr(indexes,'_business_report_entries',lambda root:calls.append(root) or entries)
    monkeypatch.setattr(indexes,'write_stage_index',lambda root,name,**kwargs:stages.append((name,kwargs['business_entries'])))
    monkeypatch.setattr(indexes,'write_master_index',lambda root,**kwargs:kwargs['business_entries'])
    (tmp_path/'final_action').mkdir()
    assert indexes.refresh_session_indexes(tmp_path)==entries
    assert len(calls)==1
    assert [s[0] for s in stages]==['final_action','split']
    assert all(s[1] is entries for s in stages)


def test_not_executed_stage_does_not_fabricate_per_rule_results():
    from medpar_qa.orchestration.connected import _not_reached
    from medpar_qa.models import StageResult,RuleResult
    result=StageResult(Stage.INTERMEDIATE)
    _not_reached(result,'Upstream source stopped')
    assert result.rule_results==[]
    result.rule_results.append(RuleResult(Stage.INTERMEDIATE,'INT-AGE',ValidationStatus.BLOCKED,'Missing birth date'))
    _not_reached(result,'Missing birth date')
    assert len(result.rule_results)==1
    assert result.rule_results[0].evidence['rules_not_reached']


def test_shape_index_reads_current_values_and_does_not_hide_new_collisions():
    from medpar_qa.normalization.fields import nested_get
    first={'Outer':{'Some_Value':1}}
    second={'Outer':{'Some_Value':2}}
    assert nested_get(first,'outer.someValue')==1
    assert nested_get(second,'outer.someValue')==2
    first['Outer']['Some_Value']=3
    assert nested_get(first,'outer.someValue')==3
    first['Outer']['Some-Value']=4
    assert nested_get(first,'outer.someValue') is None  # Conflicting normalized aliases.
    del first['Outer']['Some-Value']
    assert nested_get(first,'outer.someValue')==3


def test_not_executed_stage_link_points_to_journey_not_missing_stage_index(tmp_path):
    from medpar_qa.models import StageResult
    from medpar_qa.reporting.report_bundle import write_report_bundle
    bundle=write_report_bundle(run_id='not-executed',results=[StageResult(Stage.STAY)],
        output_directory=tmp_path/'stay',parent_link='../index.html',
        context={'handoff':{'status':'NOT_REACHED','reason':'Source row stopped'}})
    text=bundle.html.read_text()
    assert 'href="../index.html"' in text
    assert 'href="index.html#stage-results"' not in text
    assert 'no rows were processed' in text
