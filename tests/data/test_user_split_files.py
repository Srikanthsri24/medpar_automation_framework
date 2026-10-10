"""Regression tests and local fixtures for user split files. Tests describe controlled examples;
passing them does not certify all production files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline


CASES = [
    ("split01_claim_r1_a_20210103.yaml", True, "Y99999", "Y99999"),
    ("split02_claim_r1_a_20230103.yaml", True, "Y20109", "Y20109"),
    ("split03_claim_r1_b_20220103.yaml", True, "Y30109", "Y30109"),
    ("split04_claim_r1_b_20200104.yaml", True, "Y99999", "Y99999"),
    (
        "split_drop_t_cvm_cwfcb_d240404_t1438012-000000001.yaml",
        True,
        "Y00109",
        "Y00109",
    ),
]


@pytest.mark.input_data
@pytest.mark.regression
@pytest.mark.split
@pytest.mark.parametrize(
    "manifest_name,expected_stage_pass,expected_indicator,actual_indicator", CASES
)
def test_uploaded_split_file(
    manifest_name,
    expected_stage_pass,
    expected_indicator,
    actual_indicator,
):
    """Verify uploaded split file. The assertions below state exactly what this test proves for its
    fixtures.
    """
    manifest = load_manifest(Path("config/runs/split") / manifest_name)
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    result = Pipeline(manifest, resolver).run()[0]

    assert result.stage is Stage.SPLIT
    assert result.passed is expected_stage_pass

    indicator = next(
        item for item in result.rule_results if item.rule_id == "SP-RULE-INDICATOR"
    )
    assert indicator.expected == expected_indicator
    assert str(indicator.actual) == actual_indicator
    assert indicator.status is (
        ValidationStatus.PASS if expected_stage_pass else ValidationStatus.FAIL
    )


@pytest.mark.input_data
@pytest.mark.regression
@pytest.mark.split
def test_positive_uploaded_suite_passes():
    """Verify positive uploaded suite passes. The assertions below state exactly what this test
    proves for its fixtures.
    """
    manifest = load_manifest("config/runs/positive_uploaded_suite.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    results = Pipeline(manifest, resolver).run()

    assert [result.stage for result in results] == [Stage.FINAL_ACTION, Stage.SPLIT]
    assert all(result.passed for result in results)


@pytest.mark.input_data
@pytest.mark.regression
@pytest.mark.split
def test_previous_negative_split_suite_matches_corrected_years_back():
    """Verify previous negative split suite matches corrected years back. The assertions below
    state exactly what this test proves for its fixtures.
    """
    manifest = load_manifest("config/runs/negative_uploaded_split_suite.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    result = Pipeline(manifest, resolver).run()[0]

    assert result.passed
    mismatches = [
        item
        for item in result.rule_results
        if item.rule_id == "SP-RULE-INDICATOR"
        and item.status is ValidationStatus.FAIL
    ]
    assert not mismatches
