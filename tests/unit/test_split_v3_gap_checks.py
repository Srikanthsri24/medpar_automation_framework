from datetime import date
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.split.processor import SplitProcessor


def _record(make_record, code, i=0):
    return make_record({
        "claimCan": f"CLAIM{i:05d}", "hicn": "H123", "providerId": "P123",
        "admissionDate": "20260403", "stayFromDate": "20260403",
        "stayThruDate": "20260405", "transactionCode": code,
    }, stage=Stage.SPLIT)


def test_split_v3_invalid_transaction_code_is_failure(resolver, make_record):
    result = SplitProcessor(resolver, date(2026, 7, 19)).validate([_record(make_record, 6)])
    matches = [r for r in result.rule_results if r.rule_id == 'SP-INVALID-TRANSACTION-CODE']
    assert len(matches) == 1
    assert matches[0].status == ValidationStatus.FAIL


def test_split_v3_more_than_75_bills_audited_without_rejection(resolver, make_record):
    records = [_record(make_record, 1, i) for i in range(76)]
    result = SplitProcessor(resolver, date(2026, 7, 19)).validate(records)
    matches = [r for r in result.rule_results if r.rule_id == 'SP-STAY-BILL-LIMIT']
    assert len(matches) == 1
    assert matches[0].status == ValidationStatus.PASS


def test_split_v3_exactly_75_bills_no_limit_failure(resolver, make_record):
    records = [_record(make_record, 1, i) for i in range(75)]
    result = SplitProcessor(resolver, date(2026, 7, 19)).validate(records)
    assert not [r for r in result.rule_results if r.rule_id == 'SP-STAY-BILL-LIMIT']
