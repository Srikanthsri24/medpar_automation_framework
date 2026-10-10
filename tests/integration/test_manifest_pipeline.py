"""Regression tests and local fixtures for manifest pipeline. Tests describe controlled examples;
passing them does not certify all production files.
"""
from pathlib import Path

import pytest

from medpar_qa.manifest import load_manifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline


@pytest.mark.integration
@pytest.mark.final_action
def test_example_manifest_loads_and_runs_final_action():
    """Verify example manifest loads and runs final action. The assertions below state exactly what
    this test proves for its fixtures.
    """
    manifest = load_manifest("config/run_manifest.example.yaml")
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")

    results = Pipeline(manifest, resolver).run()

    assert len(results) == 1
    assert results[0].passed
    assert results[0].decisions[0].decision.value == "KEEP"
