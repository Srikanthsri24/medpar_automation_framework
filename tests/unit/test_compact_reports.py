import base64,gzip,json,re
from medpar_qa.reporting.compact import compact_reports


def unpack(path):
    content=path.read_text()
    encoded=re.search(r'type="application/octet-stream">([^<]+)</script>',content).group(1)
    data=json.loads(gzip.decompress(base64.b64decode(encoded)))
    data['screens']={}
    for encoded in re.findall(r'id="block-\d+" type="application/octet-stream">([^<]+)</script>',content):data['screens'].update(json.loads(gzip.decompress(base64.b64decode(encoded))))
    return data


def test_compact_keeps_screens_counts_and_evidence_with_six_html_files(tmp_path):
    master=tmp_path/'master';master.mkdir()
    (master/'index.html').write_text('<html><body><a href="final_action_file_1.html">5 kept</a></body></html>')
    detail='<html><body><details><summary>PASS</summary>Proof '+('evidence '*1000)+'</details></body></html>'
    (master/'final_action_file_1.html').write_text(detail)
    stage=tmp_path/'final_action';stage.mkdir()
    (stage/'index.html').write_text('<html>Stage</html>')
    evidence=stage/'report.json';evidence.write_text('{"passed":5}')
    compact_reports(tmp_path)
    assert len(list(tmp_path.rglob('*.html')))==6
    data=unpack(stage/'index.html')
    assert data['screens']['master/final_action_file_1.html']==detail
    assert data['routes']['master/final_action_file_1.html']=='final_action'
    assert '5 kept' in unpack(master/'index.html')['screens']['master/index.html']
    assert evidence.read_text()=='{"passed":5}'
    stats=json.loads((tmp_path/'compact_report.json').read_text())
    assert stats['html_files_before']==3 and stats['html_files_after']==6
    assert compact_reports(tmp_path)==master/'index.html'


def test_downstream_report_is_packaged_in_its_own_stage(tmp_path):
    report=tmp_path/'entries/final_action/connected/group/stay/report.html'
    report.parent.mkdir(parents=True);report.write_text('<html>Stay evidence</html>')
    compact_reports(tmp_path)
    data=unpack(tmp_path/'stay/index.html')
    key='entries/final_action/connected/group/stay/report.html'
    assert data['routes'][key]=='stay'
    assert data['screens'][key]=='<html>Stay evidence</html>'
    assert 'No stage inputs' in unpack(tmp_path/'split/index.html')['screens']['split/index.html']


def test_windows_legacy_html_is_decoded_without_losing_punctuation(tmp_path):
    master=tmp_path/'master';master.mkdir()
    text='<html><meta charset="utf-8"><body>PASS · “Evidence” — 5 files</body></html>'
    (master/'index.html').write_bytes(text.encode('cp1252'))
    assert b'\xb7' in (master/'index.html').read_bytes()
    compact_reports(tmp_path)
    assert unpack(master/'index.html')['screens']['master/index.html']==text
    stats=json.loads((tmp_path/'compact_report.json').read_text())
    assert stats['legacy_html_encodings']==[{'file':'master/index.html','encoding':'cp1252'}]


def test_utf16_bom_report_is_preserved(tmp_path):
    master=tmp_path/'master';master.mkdir()
    text='<html>Evidence · 你好</html>'
    (master/'index.html').write_bytes(text.encode('utf-16'))
    compact_reports(tmp_path)
    assert unpack(master/'index.html')['screens']['master/index.html']==text
