import run_commands as runner
from medpar_qa.stages.final_action.settings import FinalActionSettings

def test_stage_runs_is_authoritative():
    commands = runner.build_commands("reports/approved_config_test")
    assert any(c.stage == "final_action" for c in commands)
    assert not hasattr(runner, "INPUT_PATH")

def test_approved_fa01_direction():
    assert FinalActionSettings().bypass_direction == "covered_gt_los"
    assert FinalActionSettings.from_mapping({}).bypass_direction == "covered_gt_los"

def test_approved_qcs_and_rule6():
    s = FinalActionSettings()
    assert s.allowed_query_codes == (0, 1, 3, 5)
    assert s.rule6_enabled
