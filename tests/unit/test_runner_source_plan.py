"""One editable path list selects the entry stage; downstream inputs are generated."""
from copy import deepcopy
import pytest
import run_commands as runner


def test_source_plan_uses_one_list_for_multiple_files_and_folders():
    plan=deepcopy(runner.SOURCE_RUN)
    plan.update(start_stage='stay',source_paths=['C:/MEDPAR/folder1','C:/MEDPAR/folder2','C:/MEDPAR/file.parquet'])
    stage,configured,settings=runner.source_run_configuration(plan)
    assert stage=='stay' and list(configured)==['stay']
    item=configured['stay']['single_files'][0]
    assert item['source']==plan['source_paths']
    assert 'pipeline_outputs' not in item and settings=={}


@pytest.mark.parametrize('change,message',[
    ({'start_stage':'unknown'},'start_stage'),
    ({'run_date':'not-a-date'},'time data'),
    ({'source_paths':['s3://YOUR-BUCKET/input/']},'YOUR-BUCKET'),
    ({'source_paths':[]},'one or more'),
    ({'settings':[]},'settings'),
])
def test_invalid_source_plan_is_rejected(change,message):
    plan=deepcopy(runner.SOURCE_RUN);plan['start_stage']='final_action';plan.update(change)
    with pytest.raises(ValueError,match=message):runner.source_run_configuration(plan)


def test_same_list_accepts_local_and_s3_paths():
    plan=deepcopy(runner.SOURCE_RUN)
    plan['start_stage']='final_action'
    plan['source_paths']=['/tmp/claims','s3://medpar-demo-bucket/input/']
    _,configured,_=runner.source_run_configuration(plan)
    assert configured['final_action']['single_files'][0]['source']==plan['source_paths']


def test_stage_map_selects_only_the_requested_entry():
    plan=deepcopy(runner.SOURCE_RUN)
    stage,configured,_=runner.source_run_configuration(plan,start_stage='final_medpar')
    assert configured[stage]['single_files'][0]['source']==['data/production/r65/5-intermediate-processing']
    stage,configured,_=runner.source_run_configuration(plan,start_stage='stay')
    assert configured[stage]['single_files'][0]['source']==['data/production/q61/3-4yr-window-parquet']


def test_none_business_date_uses_current_local_date():
    from datetime import datetime
    plan=deepcopy(runner.SOURCE_RUN)
    plan['source_paths']=['input'];plan['run_date']=None
    _,configured,_=runner.source_run_configuration(plan,start_stage='final_action')
    assert configured['final_action']['run_date']==datetime.now().date().isoformat()
