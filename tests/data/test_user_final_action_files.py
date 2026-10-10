"""Regression tests and local fixtures for user final action files. Tests describe controlled
examples; passing them does not certify all production files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from medpar_qa.enums import RecordDecision, Stage, ValidationStatus
from medpar_qa.ingestion.readers import read_records
from medpar_qa.enums import FileRole
from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline


CASES = [
    ("claim_r2_a_1.yaml", 5),
    ("fa_t_cvm_cwfcb_d240404_t1438012-000000004.yaml", 1),
    ("filerule1rule2.yaml", 3),
]


@pytest.mark.input_data
@pytest.mark.regression
@pytest.mark.final_action
@pytest.mark.parametrize("manifest_name,expected_qc", CASES)
def test_uploaded_final_action_file_routes_through_rule_1(manifest_name, expected_qc):
    """Verify uploaded final action file routes through rule 1. The assertions below state exactly
    what this test proves for its fixtures.
    """
    manifest = load_manifest(Path("config/runs/final_action") / manifest_name)
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    result = Pipeline(manifest, resolver).run()[0]

    assert result.stage is Stage.FINAL_ACTION
    assert result.passed
    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision.rule_id == "FA-RULE-01"
    assert decision.decision is RecordDecision.KEEP
    assert f"QC={expected_qc}" in decision.reason


@pytest.mark.input_data
@pytest.mark.regression
@pytest.mark.final_action
def test_all_uploaded_final_action_files_pass_as_three_independent_groups():
    """Verify all uploaded final action files pass as three independent groups. The assertions
    below state exactly what this test proves for its fixtures.
    """
    manifest = load_manifest("config/runs/final_action/all_uploaded.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    result = Pipeline(manifest, resolver).run()[0]

    assert result.passed
    assert len(result.decisions) == 3
    assert {item.rule_id for item in result.decisions} == {"FA-RULE-01"}
    assert {item.decision for item in result.decisions} == {RecordDecision.KEEP}


@pytest.mark.input_data
@pytest.mark.final_action
def test_file_rule1_rule2_is_one_top_level_record_not_a_rule_2_group():
    """Verify file rule1 rule2 is one top level record not a rule 2 group. The assertions below
    state exactly what this test proves for its fixtures.
    """
    path = Path("data/user_inputs/final_action/source/FileRule1Rule2.json")
    records = read_records(path, Stage.FINAL_ACTION, FileRole.SOURCE, "json")

    assert len(records) == 1, (
        "Rule 2 requires three top-level records or three separate files with the same "
        "Final Action group key. This file currently contains one top-level claim."
    )
