from __future__ import annotations

import runpy
from pathlib import Path


def test_stage_wise_runner_has_single_and_folder_lists_for_all_stages():
    namespace = runpy.run_path("run_commands.py", run_name="run_commands_config_test")
    stage_runs = namespace["STAGE_RUNS"]
    assert set(stage_runs) == {"final_action", "split", "stay", "intermediate", "final_medpar"}
    for stage, configuration in stage_runs.items():
        assert "single_files" in configuration, stage
        assert "folder_paths" in configuration, stage
        assert isinstance(configuration["single_files"], list)
        assert isinstance(configuration["folder_paths"], list)


def test_every_configured_business_path_is_relative():
    namespace = runpy.run_path("run_commands.py", run_name="run_commands_paths_test")
    for configuration in namespace["STAGE_RUNS"].values():
        for list_name in ("single_files", "folder_paths"):
            for item in configuration[list_name]:
                for role in ("source", "actual", "expected"):
                    for value in item.get(role, []):
                        assert not Path(value).is_absolute(), value
