import json
from medpar_qa.reporting.session_index import _business_report_entries


def test_direct_connected_runs_discover_executed_stage_reports(tmp_path):
    for stage,status in [('final_action','KEEP'),('split','FAIL'),('stay','NOT_REACHED')]:
        path=tmp_path/'connected/group'/stage/'report.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'context':{'handoff':{'status':status}},'stages':[{'stage':stage}]}))
    entries=_business_report_entries(tmp_path)
    assert {entry['stage_folder'] for entry in entries}=={'final_action','split'}
    assert all(entry['command_folder'].startswith('Source entry') for entry in entries)


def test_refresh_preserves_connected_navigation_page(tmp_path):
    from medpar_qa.reporting.session_index import refresh_session_indexes
    page=tmp_path/'connected/index.html';page.parent.mkdir()
    document='<html><section id="stage-results">Saved connected results</section><section id="stage-transfers">Saved transfer proof</section></html>'
    page.write_text(document)
    refresh_session_indexes(tmp_path)
    assert page.read_text()==document
