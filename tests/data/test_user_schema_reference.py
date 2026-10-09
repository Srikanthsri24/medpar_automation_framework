from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.input_data
def test_uploaded_schema_is_reference_metadata_not_a_claim_input():
    schema = json.loads(
        Path("data/user_inputs/reference/schema.json").read_text(encoding="utf-8")
    )
    assert schema == {
        "CLM-TRANS-CD": "str",
        "Claim From Date": "str",
        "Claim Thru Date": "str",
        "Rectype": "str",
        "HICN": "str",
        "Provider": "str",
    }
