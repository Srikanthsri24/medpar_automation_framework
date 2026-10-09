from __future__ import annotations

import pytest
from medpar_qa.enums import RecordDecision, ValidationStatus
from medpar_qa.stages.final_action.processor import FinalActionProcessor
from test_final_action import base_claim


def make_group(make_record, qcs, icns, *, actions=None, accretes=None):
    actions = actions or ["A"] * len(qcs)
    accretes = accretes or ["20260111"] * len(qcs)
    return [make_record(base_claim(queryCode=qc, internalControlNumber=icn,
        actionCode=actions[i], accreteDate=accretes[i],
        nchWeeklyProcessingDate=f"202601{20-i:02d}", sourceSequence=i), row=i+1)
        for i, (qc, icn) in enumerate(zip(qcs, icns))]


def decisions(result):
    return [x.decision for x in result.decisions]


def rule(result):
    return next(x for x in result.rule_results if x.rule_id.startswith("FA-RULE") or x.rule_id in ("FA-ALL-QC0", "FA-DEFAULT"))


def test_rule5_excludes_nonzero_with_qc0_icn(resolver, make_record):
    result = FinalActionProcessor(resolver).validate_group(make_group(make_record, [3,0,1], ["CANCELLED","CANCELLED","LIVE"]))
    assert rule(result).rule_id == "FA-RULE-05"
    assert decisions(result) == [RecordDecision.DROP, RecordDecision.DROP, RecordDecision.KEEP]


def test_rule5_all_icns_same_drops(resolver, make_record):
    result = FinalActionProcessor(resolver).validate_group(make_group(make_record, [3,0,1], ["A","A","A"]))
    assert result.passed
    assert decisions(result) == [RecordDecision.DROP]*3


def test_rule6_transaction_code_does_not_substitute_action_code(resolver, make_record):
    records = make_group(make_record, [0,5], ["A","A"], actions=["1","A"])
    records[0].data["transactionCode"] = 4
    result = FinalActionProcessor(resolver).validate_group(records)
    assert result.passed
    assert decisions(result).count(RecordDecision.KEEP) == 1


def test_rule6_missing_action_blocks(resolver, make_record):
    records = make_group(make_record, [0,5], ["A","A"])
    records[0].data.pop("actionCode")
    result = FinalActionProcessor(resolver).validate_group(records)
    assert rule(result).status == ValidationStatus.BLOCKED
    assert not result.decisions


def test_rule2_requires_newest_accretion(resolver, make_record):
    records = make_group(make_record, [5,0,3], ["A","B","C"], accretes=["20260101","20260103","20260102"])
    result = FinalActionProcessor(resolver).validate_group(records)
    assert rule(result).rule_id != "FA-RULE-02"


def test_invalid_transaction_six_rejected(resolver, make_record):
    result = FinalActionProcessor(resolver).validate_group([make_record(base_claim(transactionCode=6))])
    assert not result.passed
    assert any(x.rule_id == "FA-PRE-SCHEMA" for x in result.rule_results)


def test_rule2_invalid_accretion_must_not_fall_through_to_rule10b(resolver, make_record):
    records = make_group(make_record, [5, 0, 3], ["A", "B", "C"],
                         accretes=["20260101", "20260103", "20260102"])
    result = FinalActionProcessor(resolver).validate_group(records)
    assert any(x.rule_id == "FA-RULE-02-PRECONDITION" and x.status == ValidationStatus.BLOCKED
               for x in result.rule_results)
    assert not result.decisions


def test_rule2_missing_accretion_must_not_fall_through_to_rule10b(resolver, make_record):
    records = make_group(make_record, [5, 0, 1], ["A", "B", "C"])
    records[1].data.pop("accreteDate")
    result = FinalActionProcessor(resolver).validate_group(records)
    assert any(x.rule_id == "FA-RULE-02-PRECONDITION" and x.status == ValidationStatus.BLOCKED
               for x in result.rule_results)
    assert not result.decisions
