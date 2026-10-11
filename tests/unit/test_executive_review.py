from pathlib import Path
from medpar_qa.reporting.executive_review import write_executive_review


def test_shared_evidence_does_not_multiply_global_check_counts(tmp_path):
    checks = [{'rule_id': 'R1', 'status': 'FAIL', 'message': '<unsafe>', 'source_files': ['a', 'b'], 'record_ids': ['1']}, {'rule_id': 'R1', 'status': 'FAIL', 'message': 'second', 'source_files': ['b'], 'record_ids': ['1']}, {'rule_id': 'R2', 'status': 'KNOWN_DIFFERENCE', 'message': 'review'}]
    entry = {'path': tmp_path / 'run' / 'report.json', 'command_folder': 'run', 'payload': {'stages': [{'stage': 'stay', 'rule_results': checks}]}}
    page = write_executive_review([entry], tmp_path / 'index.html').read_text()
    assert '2 recorded checks · 2 linked evidence files · 1 distinct record IDs' in page
    assert '3 recorded checks' in page
    assert '<unsafe>' not in page
    assert '&lt;unsafe&gt;' in page
    assert 'Not run' in page
    assert 'Action required' in page


def test_known_difference_is_not_presented_as_acceptance(tmp_path):
    entry = {'path': tmp_path / 'report.json', 'command_folder': 'run', 'payload': {'stages': [{'stage': 'split', 'rule_results': [{'rule_id': 'R', 'status': 'KNOWN_DIFFERENCE', 'message': 'pending policy'}]}]}}
    page = write_executive_review([entry], tmp_path / 'index.html').read_text()
    assert '<h1>Review required</h1>' in page
    assert 'REVIEW DIFFERENCES' in page
