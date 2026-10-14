"""The team runner has exactly one input configuration and no dataset presets."""
import runpy


def test_runner_has_only_one_editable_source_list():
    namespace=runpy.run_path('run_commands.py',run_name='runner_config_test')
    plan=namespace['SOURCE_RUN']
    assert isinstance(plan['source_paths'],dict) and set(plan['source_paths'])==set(namespace['STAGE_ORDER'])
    assert 'paths' not in plan and 'source_type' not in plan
    assert 'STAGE_RUNS' not in namespace and 'PRODUCTION_ROOT' not in namespace


def test_all_entry_stages_reuse_the_same_source_paths():
    namespace=runpy.run_path('run_commands.py',run_name='runner_paths_test')
    plan=namespace['SOURCE_RUN']
    for stage in namespace['STAGE_ORDER']:
        _,config,_=namespace['source_run_configuration'](plan,start_stage=stage)
        assert list(config)==[stage]
        assert config[stage]['single_files'][0]['source']==plan['source_paths'][stage]
