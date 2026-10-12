from pathlib import Path
import json
from medpar_qa.reporting.stage_volume import summarize_stage_volume
from medpar_qa.reporting.session_index import write_master_index
from medpar_qa.reporting.html_reporter import write_html_report
from medpar_qa.models import StageResult, RuleResult, ClaimDecision
from medpar_qa.enums import Stage, ValidationStatus, RecordDecision


def test_volume_counts_only_unique_source_files_and_explicit_decisions():
    checks = [dict(rule_id='INGEST-READ-FILE',status='PASS',actual={'role':'source','record_count':2},source_files=['a.json'],record_ids=['one','two']),dict(rule_id='INGEST-READ-FILE',status='PASS',actual={'role':'actual','record_count':3},source_files=['output.json'],record_ids=['other']),dict(rule_id='A',status='FAIL',source_files=['a.json','output.json']),dict(rule_id='B',status='FAIL',source_files=['a.json'])]
    decisions=[dict(record_id='one',decision='KEEP'),dict(record_id='one',decision='KEEP')]
    volume=summarize_stage_volume(checks,decisions)
    assert volume['files_in']==1 and volume['files_stopped']==1 and volume['files_passed']==0
    assert volume['records_in']==2 and volume['kept']==1 and volume['dropped']==0 and volume['records_stopped']==1
    assert summarize_stage_volume(checks)['kept'] is None


def test_master_reference_removes_top_widgets_and_collapses_stages(tmp_path):
    folder=tmp_path/'final_action/run';folder.mkdir(parents=True)
    check=dict(rule_id='INGEST-READ-FILE',status='PASS',message='Loaded',actual={'role':'source','record_count':1},source_files=['a.json'],record_ids=['one'])
    (folder/'report.json').write_text(json.dumps({'stages':[{'stage':'final_action','rule_results':[check],'decisions':[dict(record_id='one',decision='KEEP')]}]}))
    page=write_master_index(tmp_path).read_text()
    assert "<section class='summary'>" not in page
    assert "<details id='stage-final_action' class='stage'>" in page
    assert 'final_action_volume_files_passed.html' in page
    assert 'final_action_volume_kept.html' in page
    nav=(tmp_path/'master/final_action_volume_kept.html').read_text()
    assert 'one' in nav and 'a.json' in nav


def test_full_report_reference_moves_overview_last_and_collapses_decisions(tmp_path):
    result=StageResult(Stage.FINAL_ACTION,rule_results=[RuleResult(Stage.FINAL_ACTION,'A',ValidationStatus.FAIL,'mismatch')],decisions=[ClaimDecision('one',RecordDecision.KEEP,'FA-RULE-01','kept')])
    output=write_html_report('reference','2025-03-18',[result],tmp_path)
    page=output.read_text()
    assert '<details class="stage-section" data-stage-container=' in page
    assert '<details class="decision-section">' in page
    assert 'KEEP 1 · DROP 0' in page
    assert '<details class="failure-overview">' in page
    assert page.index('Failure / blocked overview')>page.index('Record-level KEEP/DROP decisions')


def test_leads_eleven_rule6_scenarios():
    from scripts.verify_rule6 import verify
    result=verify()
    assert result['passed'] and len(result['scenarios'])==11
    case9=next(s for s in result['scenarios'] if s['case']==9)
    assert case9['rule']=='FA-RULE-06' and case9['observed']=='DROP_BOTH'


def test_large_full_report_keeps_searchable_file_proof_without_duplicating_cards(tmp_path):
    result=StageResult(Stage.STAY,rule_results=[RuleResult(Stage.STAY,'ST-TOTAL-CHARGE',ValidationStatus.PASS,'matched',1,1,source_files=['a.json']) for _ in range(1000)])
    output=write_html_report('large','2025-03-18',[result],tmp_path,parent_link='../../master/index.html')
    page=output.read_text()
    assert 'Search filename' in page and '../../master/stay_file_' in page
    assert 'id="stage-1-1000"' not in page
    assert 'Complete rule explanations are available' in page
