from __future__ import annotations

from medpar_qa.enums import ValidationStatus, RecordDecision
from medpar_qa.stages.final_action.processor import FinalActionProcessor
from medpar_qa.stages.final_action.settings import FinalActionSettings
from medpar_qa.stages.final_action.audit import write_final_action_audit
from test_final_action import base_claim


def record(make_record, **overrides):
    return make_record(base_claim(**overrides), row=int(overrides.get("queryCode", 0)) + 1)


def test_rule6_enabled_by_default_and_cancellation_4(resolver, make_record):
    group = [record(make_record, queryCode=0, internalControlNumber='MATCH', actionCode=4),
             record(make_record, queryCode=5, internalControlNumber='MATCH', actionCode=1, nchWeeklyProcessingDate='20260119')]
    result = FinalActionProcessor(resolver).validate_group(group)
    assert result.passed
    assert len(result.decisions) == 2
    assert all(d.decision == RecordDecision.DROP for d in result.decisions)


def test_rule6_cancel_6(resolver, make_record):
    group = [record(make_record, queryCode=0, internalControlNumber='MATCH', actionCode=6),
             record(make_record, queryCode=5, internalControlNumber='MATCH', actionCode=1, nchWeeklyProcessingDate='20260119')]
    result = FinalActionProcessor(resolver).validate_group(group)
    assert result.passed
    assert all(d.decision == RecordDecision.DROP for d in result.decisions)


def test_rule6_non_cancel_keeps_qc5(resolver, make_record):
    group = [record(make_record, queryCode=0, internalControlNumber='MATCH', actionCode=2),
             record(make_record, queryCode=5, internalControlNumber='MATCH', actionCode=1, nchWeeklyProcessingDate='20260119')]
    result = FinalActionProcessor(resolver).validate_group(group)
    assert result.passed
    assert [d.decision for d in result.decisions].count(RecordDecision.KEEP) == 1


def test_table_limit_detected(resolver, make_record):
    group = [record(make_record, queryCode=1, internalControlNumber=f'I{i}',
                    nchWeeklyProcessingDate=f'202601{(i%28)+1:02d}') for i in range(901)]
    for item in group:
        item.data['record_table_type'] = 'continuation'
    result = FinalActionProcessor(resolver).validate_group(group)
    assert any(r.rule_id == 'FA-PRE-TABLE-LIMIT' and r.status == ValidationStatus.FAIL
               for r in result.rule_results)


def test_invalid_bypass_policy_fails_closed(resolver, make_record):
    processor = FinalActionProcessor(resolver, FinalActionSettings(bypass_direction='nonsense'))
    import pytest
    with pytest.raises(ValueError):
        processor.validate_group([record(make_record)])


def test_bypass_exception_file(resolver, make_record, tmp_path):
    settings = FinalActionSettings(bypass_direction='covered_gt_los')
    r = record(make_record)
    r.data['covered_days'] = 999
    result = FinalActionProcessor(resolver, settings).validate_group([r])
    assert not result.passed
    assert any(x.rule_id == 'FA-BYPASS-EXCEPTION' for x in result.rule_results)
    paths = write_final_action_audit(result, tmp_path)
    assert 'FA-BYPASS-EXCEPTION' in paths['bypass'].read_text()
    assert not result.decisions


def test_unmatched_rule_is_error_file(resolver, make_record, tmp_path):
    group = [record(make_record, queryCode=1, internalControlNumber='A', nchWeeklyProcessingDate='20260125'),
             record(make_record, queryCode=3, internalControlNumber='B', nchWeeklyProcessingDate='20260124')]
    group = [record(make_record, queryCode=0, internalControlNumber='MATCH', actionCode=4),
             record(make_record, queryCode=5, internalControlNumber='MATCH', actionCode=1, nchWeeklyProcessingDate='20260119')]
    result = FinalActionProcessor(resolver, FinalActionSettings(rule6_enabled=False)).validate_group(group)
    assert any(x.rule_id == 'FA-RULE-06' and x.status == ValidationStatus.BLOCKED
               for x in result.rule_results)
    paths = write_final_action_audit(result, tmp_path)
    assert 'FA-RULE-06' in paths['errors'].read_text()
