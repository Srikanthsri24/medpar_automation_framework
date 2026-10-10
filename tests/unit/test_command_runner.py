import runpy


def test_stage_script_uses_current_snf_and_final_class_contracts():
    from medpar_qa.enums import Stage
    namespace = runpy.run_path("scripts/run_stage.py", run_name="run_stage_test")
    settings = namespace["_stage_settings"]
    assert settings(Stage.SPLIT, "calculate")["split"]["skip_transaction_codes"] == []
    assert settings(Stage.FINAL_MEDPAR, "calculate")["final_medpar"]["allowed_classifications"] == ["S", "L", "N"]


def test_run_commands_file_loads_and_has_all_five_stages():
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
