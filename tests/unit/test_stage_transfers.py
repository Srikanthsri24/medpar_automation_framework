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
