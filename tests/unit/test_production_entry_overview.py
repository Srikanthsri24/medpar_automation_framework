"""Entry reviews retain independent source counts and do not fabricate transfers."""
from types import SimpleNamespace
import json
from pathlib import Path
import run_commands as runner


def test_overview_links_separate_entry_reports_and_records_counts(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(runner,'PROJECT_ROOT',tmp_path)
    calls=[]
    def child(args, *, report_session=None):
        stage=args[1];calls.append(args)
        folder=report_session.root/'connected';folder.mkdir(parents=True)
        (folder/'index.html').write_text('entry evidence')
        journey=folder/'batch';journey.mkdir()
        (journey/'journey.json').write_text(json.dumps(dict(source_file='source.json',source_files=['a','b','c'],source_file_count=3,conclusion='Validation stopped',steps=[dict(stage=stage,status='FAIL',reason='Validation stopped',input_files=['a','b','c'],input_records=7,retained=0,dropped=0)])))
        print('Connected pipeline report: '+(folder/'index.html').relative_to(tmp_path).as_posix())
        return 1
    monkeypatch.setattr(runner,'main',child)
    assert runner.run_all_source_entries(SimpleNamespace(run_date=None,aws_config=None))==1
    assert [call[1] for call in calls]==list(runner.STAGE_ORDER)
    assert len({call[3] for call in calls})==1
    report=next((tmp_path/'reports').glob('20*/master/entry_reviews.json'))
    data=json.loads(report.read_text())
    assert len(data['entries'])==5 and all(row['input_files']==3 for row in data['entries'])
    import base64,gzip,re
    archive=re.search(r'type="application/octet-stream">([^<]+)</script>',report.with_name('index.html').read_text()).group(1)
    screens={}
    for encoded in re.findall(r'id="block-\d+" type="application/octet-stream">([^<]+)</script>',report.with_name('index.html').read_text()):screens.update(json.loads(gzip.decompress(base64.b64decode(encoded))))
    page=screens['master/entry_overview.html']
    assert 'MEDPAR QA — Master Report' in screens['master/index.html']
    assert 'not evidence of a shared transfer' in page
    assert page.count('3 files received, 7 records read, 0 kept, 0 dropped; FAIL')==5
    assert len(list((tmp_path/'reports').iterdir()))==1
    for row in data['entries']:
        target=(report.parent/row['report']).resolve()
        stage=row['entry_stage']
        encoded=re.search(r'type="application/octet-stream">([^<]+)</script>',(report.parent.parent/stage/'index.html').read_text()).group(1)
        routes=json.loads(gzip.decompress(base64.b64decode(encoded)))['routes']
        assert target.relative_to(report.parent.parent).as_posix() in routes
