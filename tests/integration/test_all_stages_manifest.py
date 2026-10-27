"""Regression tests and local fixtures for all stages manifest. Tests describe controlled examples;
passing them does not certify all production files.
"""
from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline


def test_all_stages_example_manifest_blocks_unapproved_physical_layout():
    """Verify all stages example manifest passes. The assertions below state exactly what this test
    proves for its fixtures.
    """
    manifest = load_manifest("config/run_manifest.all_stages.example.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    results = Pipeline(manifest, resolver).run()
    assert [result.stage.value for result in results] == [
        "final_action",
        "split",
        "stay",
        "intermediate",
        "final_medpar",
    ]
    assert all(result.passed for result in results[:-1])
    physical = [check for check in results[-1].rule_results if check.rule_id == 'FM-OVERFLOW-0520']
    assert physical and all(check.status.value == 'BLOCKED' for check in physical)
    assert not results[-1].passed
    assert not [check for check in results[-1].rule_results if check.status.value == 'FAIL' and check.rule_id != 'STAGE-FINAL-SUMMARY']
