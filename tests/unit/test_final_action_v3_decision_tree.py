"""Regression tests and local fixtures for final action v3 decision tree. Tests describe controlled
examples; passing them does not certify all production files.
"""
from __future__ import annotations

import pytest
from medpar_qa.enums import RecordDecision, ValidationStatus
from medpar_qa.stages.final_action.processor import FinalActionProcessor
from medpar_qa.stages.final_action.settings import FinalActionSettings
from test_final_action import base_claim


def make_group(make_record, qcs, icns, *, actions=None, accretes=None):
    """Test helper for make group. It constructs or summarizes controlled fixture data for the
    assertions in this file.
    """
    actions = actions or ["A"] * len(qcs)
    accretes = accretes or ["20260111"] * len(qcs)
    return [make_record(base_claim(queryCode=qc, internalControlNumber=icn,
        actionCode=actions[i], accreteDate=accretes[i],
        nchWeeklyProcessingDate=f"202601{20-i:02d}", sourceSequence=i), row=i+1)
        for i, (qc, icn) in enumerate(zip(qcs, icns))]


def decisions(result):
    """Test helper for decisions. It constructs or summarizes controlled fixture data for the
    assertions in this file.
    """
    return [x.decision for x in result.decisions]


def rule(result):
    """Test helper for rule. It constructs or summarizes controlled fixture data for the assertions
    in this file.
    """
    return next(x for x in result.rule_results if x.rule_id.startswith("FA-RULE") or x.rule_id in ("FA-ALL-QC0", "FA-DEFAULT"))


def test_rule5_excludes_nonzero_with_qc0_icn(resolver, make_record):
    """Verify rule5 excludes nonzero with qc0 icn. The assertions below state exactly what this
    test proves for its fixtures.
    """
    result = FinalActionProcessor(resolver).validate_group(make_group(make_record, [3,0,1], ["CANCELLED","CANCELLED","LIVE"]))
    assert rule(result).rule_id == "FA-RULE-05"
    assert decisions(result) == [RecordDecision.DROP, RecordDecision.DROP, RecordDecision.KEEP]


def test_rule5_all_icns_same_drops(resolver, make_record):
    """Verify rule5 all icns same drops. The assertions below state exactly what this test proves
    for its fixtures.
    """
    result = FinalActionProcessor(resolver).validate_group(make_group(make_record, [3,0,1], ["A","A","A"]))
    assert result.passed
    assert decisions(result) == [RecordDecision.DROP]*3


def test_rule6_transaction_code_does_not_substitute_action_code(resolver, make_record):
    """Verify rule6 transaction code does not substitute action code. The assertions below state
    exactly what this test proves for its fixtures.
    """
    records = make_group(make_record, [0,5], ["A","A"], actions=["1","A"])
    records[0].data["transactionCode"] = 4
    result = FinalActionProcessor(resolver).validate_group(records)
    assert result.passed
    assert decisions(result).count(RecordDecision.KEEP) == 1


def test_rule6_missing_action_blocks(resolver, make_record):
    """Verify rule6 missing action blocks. The assertions below state exactly what this test proves
    for its fixtures.
    """
    records = make_group(make_record, [0,5], ["A","A"])
    records[0].data.pop("actionCode")
    result = FinalActionProcessor(resolver).validate_group(records)
    assert rule(result).status == ValidationStatus.BLOCKED
    assert not result.decisions


def test_rule2_requires_newest_accretion(resolver, make_record):
    """Verify rule2 requires newest accretion. The assertions below state exactly what this test
    proves for its fixtures.
    """
    records = make_group(make_record, [5,0,3], ["A","B","C"], accretes=["20260101","20260103","20260102"])
    result = FinalActionProcessor(resolver).validate_group(records)
    assert rule(result).rule_id != "FA-RULE-02"


def test_invalid_transaction_six_rejected(resolver, make_record):
    """Verify invalid transaction six rejected. The assertions below state exactly what this test
    proves for its fixtures.
    """
    result = FinalActionProcessor(
        resolver, FinalActionSettings(validate_transaction_codes=True)
    ).validate_group([make_record(base_claim(transactionCode=6))])
    assert not result.passed
    assert any(x.rule_id == "FA-PRE-SCHEMA" for x in result.rule_results)


def test_rule2_invalid_accretion_must_not_fall_through_to_rule10b(resolver, make_record):
    """Verify rule2 invalid accretion must not fall through to rule10b. The assertions below state
    exactly what this test proves for its fixtures.
    """
    records = make_group(make_record, [5, 0, 3], ["A", "B", "C"],
                         accretes=["20260101", "20260103", "20260102"])
    result = FinalActionProcessor(resolver).validate_group(records)
    assert any(x.rule_id == "FA-RULE-02-PRECONDITION" and x.status == ValidationStatus.BLOCKED
               for x in result.rule_results)
    assert not result.decisions


def test_rule2_missing_accretion_must_not_fall_through_to_rule10b(resolver, make_record):
    """Verify rule2 missing accretion must not fall through to rule10b. The assertions below state
    exactly what this test proves for its fixtures.
    """
    records = make_group(make_record, [5, 0, 1], ["A", "B", "C"])
    records[1].data.pop("accreteDate")
    result = FinalActionProcessor(resolver).validate_group(records)
    assert any(x.rule_id == "FA-RULE-02-PRECONDITION" and x.status == ValidationStatus.BLOCKED
               for x in result.rule_results)
    assert not result.decisions


@pytest.mark.parametrize("code", [5, 6, "C", "H", None, ""])
def test_transaction_validation_disabled_routes_by_query_code(resolver, make_record, code):
    processor = FinalActionProcessor(resolver)
    record = make_record(base_claim(transactionCode=code, queryCode=5))
    result = processor.validate([record])
    assert not any(x.rule_id in {"FA-PRE-SCHEMA", "FA-PRE-GROUPING"} for x in result.rule_results)
    assert result.decisions[0].decision == RecordDecision.KEEP
    assert processor.group_key(record)[0].startswith("UNCLASSIFIED:")


def test_disabled_transaction_check_preserves_distinct_claim_types(resolver, make_record):
    processor = FinalActionProcessor(resolver)
    keys = [processor.group_key(make_record(base_claim(transactionCode=code)))
            for code in [0, 1, 5, 6, "C", "H"]]
    assert len(set(keys)) == len(keys)


def test_transaction_check_setting_can_be_reenabled():
    assert not FinalActionSettings.from_mapping({}).validate_transaction_codes
    assert FinalActionSettings.from_mapping({"validate_transaction_codes": True}).validate_transaction_codes


@pytest.mark.parametrize("query", [2, "2", 6, "6"])
@pytest.mark.parametrize("entrypoint", ["validate", "validate_group"])
def test_query_code_failure_reports_allowed_values(resolver, make_record, query, entrypoint):
    from medpar_qa.reporting.rule_catalog import conclusion_text, get_rule_metadata
    processor = FinalActionProcessor(resolver)
    result = getattr(processor, entrypoint)([make_record(base_claim(queryCode=query, actionCode=6))])
    failure = next(x for x in result.rule_results if x.rule_id == "FA-PRE-SCHEMA")
    assert failure.field_name == "query_code"
    assert failure.expected == [0, 1, 3, 5]
    assert failure.actual == query
    text = conclusion_text(status="FAIL", message=failure.message, expected=failure.expected,
                           actual=failure.actual, metadata=get_rule_metadata("final_action", failure.rule_id))
    assert "Expected None" not in text
    assert "[0, 1, 3, 5]" in text


@pytest.mark.parametrize("action", [4, "4", 6, "6"])
def test_action_codes_do_not_fail_query_code_validation(resolver, make_record, action):
    records = make_group(make_record, [5, 0], ["A", "A"], actions=[1, action])
    result = FinalActionProcessor(resolver).validate_group(records)
    assert result.passed
    assert rule(result).rule_id == "FA-RULE-06"
    assert all(x.decision == RecordDecision.DROP for x in result.decisions)


@pytest.mark.parametrize("query", [0, "0", 1, "1", 3, "3", 5, "5"])
def test_numeric_and_string_query_codes_are_equivalent(resolver, make_record, query):
    result = FinalActionProcessor(resolver).validate_group([make_record(base_claim(queryCode=query))])
    assert result.passed
    assert result.decisions[0].decision == (RecordDecision.DROP if int(query) == 0 else RecordDecision.KEEP)


@pytest.mark.parametrize("qcs", [[0, 5], [5, 0]])
@pytest.mark.parametrize("matching", [True, False])
@pytest.mark.parametrize("action", [4, 6, "4", "6", 4.0, 6.0, "1", None, "", "  "])
def test_rule6_documented_icn_action_matrix(resolver, make_record, qcs, matching, action):
    icns = ["A", "A"] if matching else ["A", "B"]
    actions = [action if qc == 0 else "6" for qc in qcs]
    result = FinalActionProcessor(resolver).validate_group(make_group(make_record, qcs, icns, actions=actions))
    selected = rule(result)
    assert selected.rule_id == "FA-RULE-06"
    if matching and (action is None or str(action).strip() == ""):
        assert selected.status == ValidationStatus.BLOCKED
        assert not result.decisions
    elif matching and action in [4, 6, "4", "6", 4.0, 6.0]:
        assert [x.decision for x in result.decisions] == [RecordDecision.DROP, RecordDecision.DROP]
    else:
        assert {x.record_id: x.decision for x in result.decisions} == {
            f"record-{qcs.index(5) + 1}": RecordDecision.KEEP,
            f"record-{qcs.index(0) + 1}": RecordDecision.DROP,
        }


def test_rule6_coverage_explains_extra_records(resolver, make_record):
    result = FinalActionProcessor(resolver).validate(make_group(make_record, [0, 0, 0, 5, 5, 5], ["A"] * 6))
    coverage = next(x for x in result.rule_results if x.rule_id == "FA-RULE-06-COVERAGE")
    assert coverage.status == ValidationStatus.NOT_APPLICABLE
    assert coverage.actual["eligible_valid_source_episodes"] == 0
    assert coverage.actual["group_sizes"] == {6: 1}


def test_rule6_coverage_records_execution(resolver, make_record):
    result = FinalActionProcessor(resolver).validate(make_group(make_record, [0, 5], ["A", "A"], actions=[6, 1]))
    coverage = next(x for x in result.rule_results if x.rule_id == "FA-RULE-06-COVERAGE")
    assert coverage.actual["evaluated_episodes"] == 1
    assert coverage.actual["eligible_valid_source_episodes"] == 1
