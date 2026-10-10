from __future__ import annotations

import pytest

from medpar_qa.enums import FileRole, RecordDecision, ValidationStatus
from medpar_qa.stages.final_action.processor import FinalActionProcessor


def base_claim(**overrides):
    data = {
        "claimCan": "CAN-1",
        "claimCanNchEquatable": "H-1",
        "provider": {"providerId": "P-1"},
        "stayFromDate": "20260101",
        "stayThruDate": "20260105",
        "transactionCode": 1,
        "queryCode": 1,
        "internalControlNumber": "I-1",
        "nchWeeklyProcessingDate": "20260110",
        "accreteDate": "20260111",
        "sourceSequence": 1,
        "actionCode": "A",
    }
    data.update(overrides)
    return data


def decisions_by_row(result):
    return {item.record_id: item.decision for item in result.decisions}


def selected_rule(result):
    return next(
        item.rule_id
        for item in result.rule_results
        if item.rule_id.startswith("FA-RULE") or item.rule_id in {"FA-ALL-QC0", "FA-DEFAULT"}
    )


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
@pytest.mark.parametrize(
    "qc,expected",
    [
        (0, RecordDecision.DROP),
        (1, RecordDecision.KEEP),
        (3, RecordDecision.KEEP),
        (5, RecordDecision.KEEP),
    ],
)
def test_rule1_routes_single_claim(resolver, make_record, qc, expected):
    processor = FinalActionProcessor(resolver)
    result = processor.validate_group([make_record(base_claim(queryCode=qc))])

    assert result.passed
    assert selected_rule(result) == "FA-RULE-01"
    assert result.decisions[0].decision == expected


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule1_rejects_unapproved_qc2(resolver, make_record):
    result = FinalActionProcessor(resolver).validate_group(
        [make_record(base_claim(queryCode=2))]
    )

    assert not result.passed
    assert any(item.rule_id == "FA-PRE-SCHEMA" for item in result.rule_results)


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
@pytest.mark.parametrize("oldest_qc", [1, 3])
def test_rule2_keeps_newest_qc5(resolver, make_record, oldest_qc):
    records = [
        make_record(
            base_claim(
                queryCode=oldest_qc,
                internalControlNumber="I-OLD",
                nchWeeklyProcessingDate="20260101",
                accreteDate="20260101",
            ),
            row=1,
        ),
        make_record(
            base_claim(
                queryCode=0,
                internalControlNumber="I-MID",
                nchWeeklyProcessingDate="20260102",
                accreteDate="20260102",
            ),
            row=2,
        ),
        make_record(
            base_claim(
                queryCode=5,
                internalControlNumber="I-NEW",
                nchWeeklyProcessingDate="20260103",
                accreteDate="20260103",
            ),
            row=3,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-02"
    decisions = decisions_by_row(result)
    assert decisions["record-3"] == RecordDecision.KEEP
    assert decisions["record-2"] == RecordDecision.DROP
    assert decisions["record-1"] == RecordDecision.DROP


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_all_qc0_group_is_dropped(resolver, make_record):
    records = [
        make_record(
            base_claim(queryCode=0, nchWeeklyProcessingDate="20260102"), row=1
        ),
        make_record(
            base_claim(queryCode=0, nchWeeklyProcessingDate="20260101"), row=2
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-ALL-QC0"
    assert all(item.decision == RecordDecision.DROP for item in result.decisions)


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule3_keeps_newest_per_unique_icn(resolver, make_record):
    records = [
        make_record(
            base_claim(
                queryCode=3,
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260101",
            ),
            row=1,
        ),
        make_record(
            base_claim(
                queryCode=3,
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260103",
            ),
            row=2,
        ),
        make_record(
            base_claim(
                queryCode=3,
                internalControlNumber="B",
                nchWeeklyProcessingDate="20260102",
            ),
            row=3,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-03"
    decisions = decisions_by_row(result)
    assert decisions["record-2"] == RecordDecision.KEEP
    assert decisions["record-1"] == RecordDecision.DROP
    assert decisions["record-3"] == RecordDecision.KEEP


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule5_keeps_newest_non_qc0_when_icns_differ(resolver, make_record):
    records = [
        make_record(
            base_claim(
                queryCode=1,
                internalControlNumber="C",
                nchWeeklyProcessingDate="20260101",
            ),
            row=1,
        ),
        make_record(
            base_claim(
                queryCode=0,
                internalControlNumber="B",
                nchWeeklyProcessingDate="20260102",
            ),
            row=2,
        ),
        make_record(
            base_claim(
                queryCode=3,
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260103",
            ),
            row=3,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-05"
    decisions = decisions_by_row(result)
    assert decisions["record-3"] == RecordDecision.KEEP
    assert decisions["record-2"] == RecordDecision.DROP
    assert decisions["record-1"] == RecordDecision.DROP


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule6_keeps_qc5_when_drop_both_condition_does_not_apply(resolver, make_record):
    records = [
        make_record(
            base_claim(
                queryCode=0,
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260102",
            ),
            row=1,
        ),
        make_record(
            base_claim(
                queryCode=5,
                internalControlNumber="B",
                nchWeeklyProcessingDate="20260101",
            ),
            row=2,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-06"
    decisions = decisions_by_row(result)
    assert decisions["record-2"] == RecordDecision.KEEP
    assert decisions["record-1"] == RecordDecision.DROP


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
@pytest.mark.parametrize("cancel_code", [4, 6])
def test_rule6_drops_both_for_same_icn_and_qc0_cancel_code(
    resolver, make_record, cancel_code
):
    records = [
        make_record(
            base_claim(
                queryCode=0,
                transactionCode=1,
                actionCode=str(cancel_code),
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260102",
            ),
            row=1,
        ),
        make_record(
            base_claim(
                queryCode=5,
                transactionCode=1,
                internalControlNumber="A",
                nchWeeklyProcessingDate="20260101",
            ),
            row=2,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-06"
    assert all(item.decision == RecordDecision.DROP for item in result.decisions)


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule7_drops_qc0_and_duplicate_icns(resolver, make_record):
    records = [
        make_record(
            base_claim(queryCode=0, internalControlNumber="X", nchWeeklyProcessingDate="20260104"),
            row=1,
        ),
        make_record(
            base_claim(queryCode=0, internalControlNumber="Y", nchWeeklyProcessingDate="20260103"),
            row=2,
        ),
        make_record(
            base_claim(queryCode=3, internalControlNumber="A", nchWeeklyProcessingDate="20260102"),
            row=3,
        ),
        make_record(
            base_claim(queryCode=1, internalControlNumber="A", nchWeeklyProcessingDate="20260101"),
            row=4,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-07"
    assert all(item.decision == RecordDecision.DROP for item in result.decisions)


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule8_keeps_unique_non_qc0_icns(resolver, make_record):
    qcs = [0, 3, 1, 3]
    icns = ["Z", "A", "B", "C"]
    records = [
        make_record(
            base_claim(
                queryCode=qc,
                internalControlNumber=icn,
                nchWeeklyProcessingDate=f"202601{5-index:02d}",
            ),
            row=index,
        )
        for index, (qc, icn) in enumerate(zip(qcs, icns), start=1)
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-08"
    assert sum(item.decision == RecordDecision.KEEP for item in result.decisions) == 3


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule9_keeps_unique_non_qc0_icns(resolver, make_record):
    qcs = [3, 1, 3, 0]
    icns = ["A", "B", "C", "D"]
    records = [
        make_record(
            base_claim(
                queryCode=qc,
                internalControlNumber=icn,
                nchWeeklyProcessingDate=f"202601{5-index:02d}",
            ),
            row=index,
        )
        for index, (qc, icn) in enumerate(zip(qcs, icns), start=1)
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-09"
    assert sum(item.decision == RecordDecision.KEEP for item in result.decisions) == 3


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule10a_uses_icn_comparison(resolver, make_record):
    qcs = [0, 0, 5, 1]
    icns = ["Z", "Y", "A", "B"]
    records = [
        make_record(
            base_claim(
                queryCode=qc,
                internalControlNumber=icn,
                nchWeeklyProcessingDate=f"2026010{5-index}",
            ),
            row=index,
        )
        for index, (qc, icn) in enumerate(zip(qcs, icns), start=1)
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-10A"
    assert sum(item.decision == RecordDecision.KEEP for item in result.decisions) == 2


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_rule10b_keeps_first_non_qc0_without_icn_comparison(resolver, make_record):
    qcs = [0, 5, 3]
    records = [
        make_record(
            base_claim(
                queryCode=qc,
                internalControlNumber="SAME",
                nchWeeklyProcessingDate=f"202601{5-index:02d}",
            ),
            row=index,
        )
        for index, qc in enumerate(qcs, start=1)
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert result.passed
    assert selected_rule(result) == "FA-RULE-10B"
    decisions = decisions_by_row(result)
    assert decisions["record-2"] == RecordDecision.KEEP
    assert decisions["record-1"] == RecordDecision.DROP
    assert decisions["record-3"] == RecordDecision.DROP


@pytest.mark.unit
@pytest.mark.final_action
def test_ambiguous_ordering_is_blocked(resolver, make_record):
    records = [
        make_record(
            base_claim(queryCode=3, internalControlNumber="A", sourceSequence=None),
            row=1,
        ),
        make_record(
            base_claim(queryCode=3, internalControlNumber="B", sourceSequence=None),
            row=2,
        ),
    ]
    result = FinalActionProcessor(resolver).validate_group(records)

    assert not result.passed
    assert result.rule_results[0].rule_id == "FA-PRE-ORDERING"
    assert result.rule_results[0].status == ValidationStatus.BLOCKED


@pytest.mark.unit
@pytest.mark.final_action
def test_invalid_stay_date_range_fails(resolver, make_record):
    record = make_record(
        base_claim(stayFromDate="20260106", stayThruDate="20260105")
    )
    result = FinalActionProcessor(resolver).validate_group([record])

    assert not result.passed
    assert any(item.field_name == "stay_date_range" for item in result.rule_results)


@pytest.mark.unit
@pytest.mark.final_action
@pytest.mark.regression
def test_actual_output_reconciliation_passes(resolver, make_record):
    source = make_record(base_claim(queryCode=1), row=1)
    actual = make_record(
        base_claim(queryCode=1),
        row=20,
        role=FileRole.ACTUAL_OUTPUT,
        file_name="actual.json",
    )

    result = FinalActionProcessor(resolver).validate([source, actual])

    assert result.passed
    reconciliation = next(
        item
        for item in result.rule_results
        if item.rule_id == "FA-ACTUAL-OUTPUT-RECONCILIATION"
    )
    assert reconciliation.status == ValidationStatus.PASS


@pytest.mark.unit
@pytest.mark.final_action
def test_actual_output_reconciliation_fails_for_unexpected_record(resolver, make_record):
    source = make_record(base_claim(queryCode=0), row=1)
    actual = make_record(
        base_claim(queryCode=0),
        row=20,
        role=FileRole.ACTUAL_OUTPUT,
        file_name="actual.json",
    )

    result = FinalActionProcessor(resolver).validate([source, actual])

    assert not result.passed
    reconciliation = next(
        item
        for item in result.rule_results
        if item.rule_id == "FA-ACTUAL-OUTPUT-RECONCILIATION"
    )
    assert reconciliation.status == ValidationStatus.FAIL
