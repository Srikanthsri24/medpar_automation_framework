"""Regression tests and local fixtures for stage runs approved fa. Tests describe controlled
examples; passing them does not certify all production files.
"""
import run_commands as runner
from medpar_qa.stages.final_action.settings import FinalActionSettings

def test_stage_runs_is_authoritative():
    """Verify stage runs is authoritative. The assertions below state exactly what this test proves
    for its fixtures.
    """
    commands = runner.build_commands("reports/approved_config_test")
    assert any(c.stage == "final_action" for c in commands)
    assert not hasattr(runner, "INPUT_PATH")

def test_approved_fa01_direction():
    """Verify approved fa01 direction. The assertions below state exactly what this test proves for
    its fixtures.
    """
    assert FinalActionSettings().bypass_direction is None
    assert FinalActionSettings.from_mapping({}).bypass_direction is None

def test_approved_qcs_and_rule6():
    """Verify approved qcs and rule6. The assertions below state exactly what this test proves for
    its fixtures.
    """
    s = FinalActionSettings()
    assert s.allowed_query_codes == (0, 1, 3, 5)
    assert s.rule6_enabled
