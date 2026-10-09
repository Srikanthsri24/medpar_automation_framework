from datetime import date

import pytest

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.stages.split.processor import SplitProcessor


@pytest.mark.unit
@pytest.mark.split
def test_split_processor_reports_missing_required_provider(resolver, make_record):
    record = make_record(
        {
            "claimCan": "C1",
            "claimCanNchEquatable": "H1",
            "stayFromDate": "20260101",
            "stayThruDate": "20260102",
            "transactionCode": 1,
        },
        stage=Stage.SPLIT,
        role=FileRole.SOURCE,
    )
    result = SplitProcessor(resolver, date(2026, 7, 19)).validate([record])
    missing = [r for r in result.rule_results if r.rule_id == "SP-PRE-REQUIRED-FIELD" and r.status is ValidationStatus.FAIL]
    assert any(r.field_name == "provider_id" for r in missing)
