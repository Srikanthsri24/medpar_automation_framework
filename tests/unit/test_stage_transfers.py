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


def test_independent_pass_does_not_claim_movement(tmp_path):
    check = dict(rule_id='INGEST-READ-FILE', status='PASS', actual=dict(role='source', record_count=1, file='a.json'), source_files=['a.json'], record_ids=['1'])
    text = independent_transfers(tmp_path, {'final_action': [dict(stage=dict(rule_results=[check]))]})
    assert 'transfer not verified' in text
    detail = (tmp_path / 'final_action_transfers.html').read_text()
    assert 'Not executed as a connected handoff' in detail
    assert 'File checks passed' in detail
    assert 'final_action_file_' in detail
