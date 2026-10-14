"""File disposition comes from the gated output, not isolated validation passes."""
from pathlib import Path
from medpar_qa.reporting.stage_volume import connected_dispositions,summarize_stage_volume,volume_strip


def item(tmp_path,status,decisions=()):
    checks=[{'rule_id':'INGEST-READ-FILE','status':'PASS','source_files':[p],'record_ids':[p+'1',p+'2'],'actual':{'role':'source','record_count':2}} for p in ('a.json','b.json')]
    stage={'rule_results':checks,'decisions':list(decisions)}
    entry={'path':tmp_path/'report.json','payload':{'context':{'handoff':{'status':status,'reason':'Stage gate evidence'}}}}
    return {'entry':entry,'stage':stage},summarize_stage_volume(checks)


def test_global_failure_stops_even_files_with_passing_checks(tmp_path):
    data,volume=item(tmp_path,'FAIL')
    volume=connected_dispositions([data],volume)
    assert (volume['files_in'],volume['files_kept'],volume['files_dropped'],volume['files_stopped'])==(2,0,0,2)
    header=volume_strip(volume)
    assert 'Files passed' not in header and 'Records in' not in header and '—' not in header


def test_mixed_record_file_is_kept_and_all_drop_file_is_dropped(tmp_path):
    decisions=[{'record_id':'a.json1','decision':'KEEP'},{'record_id':'a.json2','decision':'DROP'},{'record_id':'b.json1','decision':'DROP'},{'record_id':'b.json2','decision':'DROP'}]
    data,volume=item(tmp_path,'KEEP',decisions)
    volume=connected_dispositions([data],volume)
    assert (volume['files_kept'],volume['files_dropped'],volume['files_stopped'])==(1,1,0)
    assert volume['file_sets']['kept']=={'a.json'}
    assert volume['file_sets']['dropped']=={'b.json'}


def test_all_drop_files_are_business_drops_without_required_decisions(tmp_path):
    data,volume=item(tmp_path,'DROP')
    volume=connected_dispositions([data],volume)
    assert volume['files_dropped']==2 and volume['files_stopped']==0
