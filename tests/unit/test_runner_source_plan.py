"""The selected backend supports explicit files, folders, or both in one stage entry."""
from copy import deepcopy
from datetime import datetime
import pytest
import run_commands as runner


def plan_for(stage='stay',source_type='local',files=None,folders=None):
    plan=deepcopy(runner.SOURCE_RUN)
    plan.update(start_stage=stage,source_type=source_type)
    plan['source_paths'][stage]={'files':files or [],'folders':folders or []}
    return plan


@pytest.mark.parametrize('source_type',['local','s3'])
@pytest.mark.parametrize('kind',['files','folders','both'])
def test_selected_backend_accepts_files_folders_and_both(source_type,kind):
    file='C:/MEDPAR/file.parquet' if source_type=='local' else 's3://medpar-demo-bucket/file.parquet'
    folder='C:/MEDPAR/folder' if source_type=='local' else 's3://medpar-demo-bucket/input/'
    plan=plan_for(source_type=source_type,files=[file] if kind!='folders' else [],folders=[folder] if kind!='files' else [])
    stage,configured,settings=runner.source_run_configuration(plan)
    assert configured[stage]['single_files'][0]['source']==([file] if kind!='folders' else [])+([folder] if kind!='files' else [])
    assert list(configured)==['stay'] and settings=={}


@pytest.mark.parametrize('source_type,path',[('local','s3://medpar-demo-bucket/input/'),('s3','C:/MEDPAR/input')])
def test_wrong_backend_path_is_rejected(source_type,path):
    with pytest.raises(ValueError,match='does not match selected source_type'):
        runner.source_run_configuration(plan_for(source_type=source_type,folders=[path]))


@pytest.mark.parametrize('change,message',[
    ({'start_stage':'unknown'},'start_stage'),
    ({'source_type':'other'},'source_type'),
    ({'run_date':'not-a-date'},'time data'),
    ({'settings':[]},'settings'),
])
def test_invalid_source_plan_is_rejected(change,message):
    plan=plan_for(folders=['input']);plan.update(change)
    with pytest.raises(ValueError,match=message):runner.source_run_configuration(plan)


def test_empty_lists_and_incorrect_existing_local_type_are_rejected(tmp_path):
    with pytest.raises(ValueError,match='one or more'):runner.source_run_configuration(plan_for())
    with pytest.raises(ValueError,match='not a file'):runner.source_run_configuration(plan_for(files=[str(tmp_path)]))
    file=tmp_path/'input.json';file.write_text('[]')
    with pytest.raises(ValueError,match='not a folder'):runner.source_run_configuration(plan_for(folders=[str(file)]))


def test_s3_object_cannot_be_a_folder_or_dummy_bucket():
    with pytest.raises(ValueError,match='not a folder'):
        runner.source_run_configuration(plan_for(source_type='s3',files=['s3://medpar-demo-bucket/input/']))
    with pytest.raises(ValueError,match='YOUR-BUCKET'):
        runner.source_run_configuration(plan_for(source_type='s3',folders=['s3://YOUR-BUCKET/input/']))


def test_stage_selection_and_automatic_current_date():
    stage,config,_=runner.source_run_configuration(runner.SOURCE_RUN,start_stage='final_medpar')
    assert config[stage]['single_files'][0]['source']==['data/production/r65/5-intermediate-processing']
    assert config[stage]['run_date']==datetime.now().date().isoformat()
