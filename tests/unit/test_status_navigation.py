from medpar_qa.reporting.status_navigation import write_status_navigation


def test_pass_navigation_does_not_hide_complete_file_failure(tmp_path):
    checks = [dict(rule_id='A',status='PASS',message='matched',source_files=['a.json','b.json']), dict(rule_id='B',status='FAIL',message='mismatch',source_files=['a.json'])]
    render = lambda check, stage, number, prefix: '<p>'+check['rule_id']+' '+check['status']+'</p>'
    write_status_navigation(tmp_path,'stay',checks,render)
    navigation=(tmp_path/'stay_pass_files.html').read_text()
    assert '1 matching checks · 2 linked evidence files' in navigation
    file_pages=list(tmp_path.glob('stay_file_*.html'))
    a=next(p.read_text() for p in file_pages if 'a.json' in p.read_text())
    assert 'File conclusion: FAIL' in a
    assert 'A PASS' in a and 'B FAIL' in a
