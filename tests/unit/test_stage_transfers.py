from pathlib import Path
from medpar_qa.reporting.transfers import connected_transfers, independent_transfers


def test_transfer_is_proven_even_when_next_stage_fails(tmp_path):
    steps = [dict(stage='final_action', status='KEEP', output='retained.json', input='source.json', retained=2, reason='Kept'), dict(stage='split', status='FAIL', input='retained.json', output=None, reason='Mismatch')]
    text = connected_transfers([(dict(source_file='claim.json', steps=steps), tmp_path / 'file')], tmp_path / 'index.html')
    assert 'Moved to next stage' in text
    assert 'Next stage proof' in text
    assert '2 retained record(s)' in text
    assert 'Stopped — not moved' in text


def test_output_must_match_next_input(tmp_path):
    steps = [dict(stage='final_action', status='KEEP', output='a.json', reason='Kept'), dict(stage='split', status='KEEP', input='b.json', reason='Kept')]
    text = connected_transfers([(dict(source_file='claim.json', steps=steps), tmp_path / 'file')], tmp_path / 'index.html')
    assert 'Moved to next stage</summary>' not in text
    assert 'Completed final stage' in text


def test_boundary_requires_successful_next_stage_read(tmp_path):
    source = tmp_path / 'retained.json'
    source.write_text('[{"id": 1}]')
    check = dict(rule_id='INGEST-READ-FILE', status='PASS', actual=dict(role='source', record_count=1), source_files=[str(source)])
    def item(context, checks):
        return dict(entry=dict(payload=dict(context=context)), stage=dict(rule_results=checks))
    stages = {'final_action': [item(dict(actual_paths=[str(source)]), [])], 'split': [item(dict(source_paths=[str(source)]), [check])]}
    text = independent_transfers(tmp_path, stages)
    assert '1 / 1 output files — next-stage input verified' in text
    detail = (tmp_path / 'final_action_transfers.html').read_text()
    assert 'PASS — output used as next-stage input' in detail
    assert 'SHA-256 fingerprint' in detail
    stages['split'][0]['stage']['rule_results'][0]['status'] = 'FAIL'
    text = independent_transfers(tmp_path, stages)
    assert '0 / 1 output files — transfer discrepancies found' in text


def test_validation_pass_alone_cannot_establish_transfer(tmp_path):
    item = dict(entry=dict(payload=dict(context={})), stage=dict(rule_results=[]))
    text = independent_transfers(tmp_path, {'final_action': [item]})
    assert 'No retained-output handoff recorded' in text


def test_transfer_uses_original_s3_origin_instead_of_generated_batch_label(tmp_path):
    import json
    root=tmp_path/'entry';directory=root/'connected'/'batch';directory.mkdir(parents=True)
    (root/'input_sources.json').write_text(json.dumps({'files':[{'local_path':'cache.json','origin':'s3://demo-bucket/claims/original.parquet'}]}))
    (root/'input_sources.html').write_text('source fingerprint proof')
    step=dict(stage='final_action',status='FAIL',input='source_batch.json',input_files=['cache.json'],input_records=1,retained=0,dropped=0,reason='Schema failed')
    journey=dict(source_file='source_batch.json',source_files=['cache.json'],start_stage='final_action',steps=[step])
    text=connected_transfers([(journey,directory)],tmp_path/'master/index.html')
    assert 's3://demo-bucket/claims/original.parquet' in text
    assert 'source_batch.json' not in text and 'cache.json' not in text
    assert 'SHA-256 evidence' in text and 'Started here' in text and 'Files moved' in text


def test_each_configured_entry_counts_as_started_at_its_own_stage(tmp_path):
    import json
    from html.parser import HTMLParser
    class Summary(HTMLParser):
        def __init__(self):super().__init__();self.row=[];self.rows=[];self.cell=False
        def handle_starttag(self,t,a):
            if t=='tr':self.row=[]
            if t=='td':self.cell=True;self.row.append('')
        def handle_endtag(self,t):
            if t=='td':self.cell=False
            if t=='tr' and self.row:self.rows.append(self.row)
        def handle_data(self,d):
            if self.cell:self.row[-1]+=d
    counts={'final_action':15,'split':65,'stay':12,'intermediate':83,'final_medpar':552}
    journeys=[]
    for stage,count in counts.items():
        directory=tmp_path/stage;directory.mkdir()
        files=[f'{stage}-{i}.parquet' for i in range(count)]
        step=dict(stage=stage,status='FAIL',input_files=files,input_records=count,retained=0,dropped=0,reason='Stopped')
        journeys.append((dict(source_file='batch.json',source_files=files,start_stage=stage,steps=[step]),directory))
    parser=Summary();parser.feed(connected_transfers(journeys,tmp_path/'index.html'))
    assert [int(row[2]) for row in parser.rows[:5]]==list(counts.values())  # stage,to,started
    assert all(int(row[3])==0 for row in parser.rows[:5])


def test_started_number_links_to_exact_original_file_list(tmp_path):
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,t,a):
            if t=='a':self.paths.extend(v for k,v in a if k=='href' and 'split_movement_started' in v)
    files=['one.parquet','two.parquet']
    journey=dict(source_file='batch.json',source_files=files,start_stage='split',steps=[dict(stage='split',status='FAIL',input_files=files,input_records=2,reason='Rejected',retained=0,dropped=0)])
    text=connected_transfers([(journey,tmp_path/'batch')],tmp_path/'index.html')
    parser=Links();parser.feed(text)
    assert parser.paths
    for href in parser.paths:
        proof=(tmp_path/href).read_text()
        assert '2 physical file event(s)' in proof and 'one.parquet' in proof and 'two.parquet' in proof
    assert (tmp_path/'split_movement_moved.html').is_file()
    assert 'No files match this count' in (tmp_path/'split_movement_moved.html').read_text()


def test_one_input_producing_multiple_groups_counts_input_once(tmp_path,monkeypatch):
    import json,re
    import medpar_qa.reporting.stage_volume as volume
    def dispositions(items,counts):
        files=set(items[0]['entry']['payload']['context']['source_paths'])
        return dict(files_kept=len(files),files_dropped=0,files_stopped=0,file_sets={'kept':files})
    monkeypatch.setattr(volume,'connected_dispositions',dispositions)
    journeys=[]
    for i in range(3):
        directory=tmp_path/f'group{i}'
        (directory/'final_action').mkdir(parents=True)
        (directory/'final_action/report.json').write_text(json.dumps({'context':{'source_paths':['one.parquet']},'stages':[{'rule_results':[]}]}))
        output=f'output{i}.json'
        steps=[dict(stage='final_action',status='KEEP',input_files=['one.parquet'],input_records=1,output=output,retained=1,dropped=0),dict(stage='split',status='FAIL',input=output,input_files=[output],input_records=1,retained=0,dropped=0)]
        journeys.append((dict(source_file='one.parquet',source_files=['one.parquet'],steps=steps),directory))
    html=connected_transfers(journeys,tmp_path/'index.html')
    first=re.search(r'<tr><td>Final Action</td>(.*?)</tr>',html).group(1)
    numbers=re.findall(r'>(\d+)</a>',first)
    assert numbers==['1','0','1','1','0','0','1']
    assert 'Generated outputs transferred' in html
    assert '1 physical file event(s)' in (tmp_path/'final_action_movement_moved.html').read_text()
    second=re.search(r'<tr><td>Split</td>(.*?)</tr>',html).group(1)
    assert re.findall(r'>(\d+)</a>',second)==['0','1','1','0','0','1','0']


def test_nested_connected_row_review_link_targets_session_master(tmp_path):
    folder=tmp_path/'entries/split/connected';folder.mkdir(parents=True)
    step=dict(stage='split',status='FAIL',input_records=1,retained=0,dropped=0,reason='Invalid source code')
    text=connected_transfers([(dict(source_file='input.json',source_files=['input.json'],start_stage='split',steps=[step]),folder/'group')],folder/'index.html')
    assert 'href="../../../master/index.html#record-validation"' in text
