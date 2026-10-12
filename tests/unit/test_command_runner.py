"""Regression tests and local fixtures for command runner. Tests describe controlled examples;
passing them does not certify all production files.
"""
import runpy


def test_stage_script_uses_current_snf_and_final_class_contracts():
    """Verify stage script uses current snf and final class contracts. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.enums import Stage
    namespace = runpy.run_path("scripts/run_stage.py", run_name="run_stage_test")
    settings = namespace["_stage_settings"]
    assert settings(Stage.SPLIT, "calculate")["split"]["skip_transaction_codes"] == []
    assert settings(Stage.FINAL_MEDPAR, "calculate")["final_medpar"]["allowed_classifications"] == ["S", "L", "N"]


def test_run_commands_file_loads_and_has_all_five_stages():
    """Verify run commands file loads and has all five stages. The assertions below state exactly
    what this test proves for its fixtures.
    """
    namespace = runpy.run_path("run_commands.py", run_name="run_commands_test")
    commands = namespace["COMMANDS"]
    stages = {
        command.args[command.args.index("--stage") + 1]
        for command in commands
        if "--stage" in command.args
    }
    configured = namespace["STAGE_RUNS"]
    assert set(configured) == {"final_action", "split", "stay", "intermediate", "final_medpar"}
    assert stages == {stage for stage,item in configured.items() if item.get("enabled", True)}


def test_long_stage_command_round_trips_through_arguments_file(tmp_path, monkeypatch):
    import json
    import subprocess
    from types import SimpleNamespace
    import run_commands as runner
    stage = runpy.run_path("scripts/run_stage.py", run_name="run_stage_args_test")
    parser = stage["parse_stage_args"]
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setitem(parser.__globals__, "PROJECT_ROOT", tmp_path)
    paths = [f"data/production/folder with spaces/claim_{i}_" + "x" * 180 + ".parquet"
             for i in range(400)]
    command = runner._stage_command("final_action", "2026-03-20", {
        "name": "Long production run", "source": paths,
        "actual": ["data/actual/éxtract.json"], "mode": "reconcile",
        "require_matching_snapshot": True,
    }, "reports/session")
    assert len(subprocess.list2cmdline(command.args)) > 32767
    launch = runner.execution_args(command, SimpleNamespace(root=tmp_path / "reports/session"))
    assert len(subprocess.list2cmdline(launch)) < 1000
    assert json.loads((tmp_path / launch[-1]).read_text(encoding="utf-8")) == command.args[2:]
    parsed = parser(launch[2:])
    assert parsed.source == paths
    assert parsed.actual == ["data/actual/éxtract.json"]
    assert parsed.require_matching_snapshot
    assert parsed.mode == "reconcile"
    assert parsed.report_session == "reports/session"


def test_non_stage_commands_keep_their_arguments(tmp_path):
    from types import SimpleNamespace
    import run_commands as runner
    command = runner.Command("Tests", "pytest", "tests", [runner.PYTHON, "-m", "pytest"])
    assert runner.execution_args(command, SimpleNamespace(root=tmp_path)) == command.args


def test_r65_profile_uses_own_stage_boundaries_and_business_year():
    import run_commands as runner
    profile = runner.r65_stage_runs()
    commands = [c for c in runner.build_commands('reports/test', profile) if c.enabled]
    assert {c.stage for c in commands} == set(profile)
    assert all('q61' not in ' '.join(c.args) for c in commands)
    assert '--modern-final-action' in next(c for c in commands if c.stage == 'final_action').args
    split = next(c for c in commands if c.stage == 'split')
    assert split.args[split.args.index('--split-current-year') + 1] == '2024'
    assert all(item['run_date'] == '2025-03-18' for item in profile.values())
    assert all(not item['require_matching_snapshot'] for config in profile.values() for item in config['folder_paths'] if item['mode'] == 'reconcile')


def test_plain_runner_command_selects_r65_profile(tmp_path, monkeypatch, capsys):
    import sys
    import run_commands as runner
    captured = []
    profile = {'final_action': {'enabled': True}}
    monkeypatch.setattr(runner, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(runner, 'REPORTS_ROOT', 'reports')
    monkeypatch.setattr(runner, 'r65_stage_runs', lambda: profile)
    monkeypatch.setattr(runner, 'build_commands', lambda session, stages: captured.append(stages) or [])
    monkeypatch.setattr(sys, 'argv', ['run_commands.py'])
    assert runner.main() == 0
    assert captured == [profile]
    assert 'Selected dataset: R65' in capsys.readouterr().out
