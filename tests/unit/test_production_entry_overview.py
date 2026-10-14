"""Entry reviews retain independent source counts and do not fabricate transfers."""
from types import SimpleNamespace
import json
from pathlib import Path
import run_commands as runner


def test_overview_links_separate_entry_reports_and_records_counts(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(runner,'PROJECT_ROOT',tmp_path)
    calls=[]
    def child(args):
        stage=args[1];calls.append(args)
        folder=tmp_path/'reports'/stage/'connected';folder.mkdir(parents=True)
        (folder/'index.html').write_text('entry evidence')
        journey=folder/'batch';journey.mkdir()
        (journey/'journey.json').write_text(json.dumps(dict(source_file_count=3,conclusion='Validation stopped',steps=[dict(stage=stage,status='FAIL',input_files=['a','b','c'],input_records=7,retained=0,dropped=0)])))
        print(f'Connected pipeline report: reports/{stage}/connected/index.html')
        return 1
    monkeypatch.setattr(runner,'main',child)
    assert runner.run_all_source_entries(SimpleNamespace(run_date=None,aws_config=None))==1
    assert [call[1] for call in calls]==list(runner.STAGE_ORDER)
    assert len({call[3] for call in calls})==1
    report=next((tmp_path/'reports').glob('20*/master/entry_reviews.json'))
    data=json.loads(report.read_text())
    assert len(data['entries'])==5 and all(row['input_files']==3 for row in data['entries'])
    page=report.with_name('index.html').read_text()
    assert 'not evidence of a shared transfer' in page
    assert page.count('3 files received, 7 records read, 0 kept, 0 dropped; FAIL')==5
    for row in data['entries']:assert (report.parent/row['report']).resolve().is_file()
