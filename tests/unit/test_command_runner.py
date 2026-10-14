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
    assert namespace["STAGE_ORDER"] == ("final_action", "split", "stay", "intermediate", "final_medpar")
    assert "STAGE_RUNS" not in namespace and "PRODUCTION_ROOT" not in namespace
    stage,configured,_ = namespace["source_run_configuration"](namespace["SOURCE_RUN"])
    assert list(configured)==[stage]


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


def test_runner_has_no_hidden_dataset_configuration():
    import run_commands as runner
    assert not hasattr(runner,'r65_stage_runs')
    assert not hasattr(runner,'_production_paths')
    assert not hasattr(runner,'ALL_STAGE_RUNS')
    assert not hasattr(runner,'PYTEST_RUNS')


def test_connected_configuration_inherits_dates_and_actual_paths(tmp_path,monkeypatch):
    import json,sys
    import run_commands as runner
    import medpar_qa.ingestion.input_sources as sources
    import medpar_qa.orchestration.connected as connected
    captured=[]
    class Resolver:
        files={}
        def __init__(self,*args,**kwargs):pass
        def prepare(self,config,**kwargs):captured.append(config);return config
    monkeypatch.setattr(sources,'InputSources',Resolver)
    monkeypatch.setattr(connected,'run_configured',lambda root,session,config,settings:([],session.root/'connected/index.html'))
    configuration={'stage_runs':{'final_action':{'run_date':'2026-04-20','single_files':[{'source':['source.json']}]},'stay':{'folder_paths':[{'actual':'s3://medpar-demo-bucket/stay/'}]}}}
    path=tmp_path/'config.json';path.write_text(json.dumps(configuration))
    monkeypatch.setattr(sys,'argv',['run_commands.py','--config',str(path)])
    assert runner.main()==0
    result=captured[0]
    assert all(entry['run_date']=='2026-04-20' for entry in result.values())
    assert result['final_action']['single_files'][0]['pipeline_outputs']['stay']==['s3://medpar-demo-bucket/stay/']
