"""The editable source plan selects one stage's multiple paths without comparison inputs."""
from copy import deepcopy
import pytest
import run_commands as runner


def test_source_plan_selects_only_chosen_stage_paths():
    plan=deepcopy(runner.SOURCE_RUN)
    plan['start_stage']='stay'
    plan['paths']['stay']['local']=['C:/MEDPAR/folder1','C:/MEDPAR/folder2','C:/MEDPAR/file.parquet']
    stage,configured,settings=runner.source_run_configuration(plan)
    assert stage=='stay' and list(configured)==['stay']
    item=configured['stay']['single_files'][0]
    assert item['source']==plan['paths']['stay']['local']
    assert 'pipeline_outputs' not in item and settings=={}


@pytest.mark.parametrize('change,message',[
    ({'source_type':'other'},'source_type'),
    ({'start_stage':'unknown'},'start_stage'),
    ({'run_date':'not-a-date'},'time data'),
    ({'source_type':'s3'},'YOUR-BUCKET'),
    ({'settings':[]},'settings'),
])
def test_invalid_source_plan_is_rejected(change,message):
    plan=deepcopy(runner.SOURCE_RUN);plan.update(change)
    with pytest.raises(ValueError,match=message):runner.source_run_configuration(plan)


def test_source_plan_rejects_wrong_source_type_and_empty_list():
    plan=deepcopy(runner.SOURCE_RUN)
    plan['paths']['final_action']['local']=['s3://real-bucket/input/']
    with pytest.raises(ValueError,match='wrong type'):runner.source_run_configuration(plan)
    plan['paths']['final_action']['local']=[]
    with pytest.raises(ValueError,match='one or more'):runner.source_run_configuration(plan)
