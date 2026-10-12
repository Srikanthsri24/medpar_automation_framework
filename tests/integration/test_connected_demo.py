"""Real processor evidence for the labelled synthetic demo; no processor mocks."""
import json
import shutil
from pathlib import Path

from medpar_qa.reporting.run_layout import ReportSession
from scripts.run_connected_demo import run_demo


def fixture_root(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'data/demo_connected'
    shutil.copytree(source, tmp_path / 'data/demo_connected')
    (tmp_path / 'config').mkdir()
    shutil.copyfile(source.parents[1] / 'config/field_aliases.yaml', tmp_path / 'config/field_aliases.yaml')
    return tmp_path


def test_real_five_stage_demo_completes_with_visible_coverage(tmp_path):
    """Valid synthetic input completes all five real validators without a failure or blocker."""
    root = fixture_root(tmp_path)
    journeys, index = run_demo(root, ReportSession.create(project_root=root))
    journey, directory = journeys[0]
    assert journey['completed']
    assert [step['status'] for step in journey['steps']] == ['KEEP'] * 5
    for position, step in enumerate(journey['steps']):
        if position:
            assert step['input'] == journey['steps'][position - 1]['output']
        report = json.loads((directory / step['stage'] / 'report.json').read_text())
        checks = report['stages'][0]['rule_results']
        assert any(check['status'] == 'PASS' for check in checks)
        assert not any(check['status'] in ('FAIL', 'BLOCKED') for check in checks)
    assert 'Synthetic demonstration' in index.read_text()
    assert 'not certified' in index.read_text()
    assert 'data/demo_connected/claims.json' in index.read_text()
    assert 'Executed checks and proof (43)' in index.read_text()
    assert 'Not assessed / not applicable' in index.read_text()
    assert 'Source proof' in index.read_text()


def test_wrong_stay_warning_fails_and_stops_downstream(tmp_path):
    """Intentional invalid input: warning 01=2 must fail at Stay and prevent later stages from running."""
    root = fixture_root(tmp_path)
    path = root / 'data/demo_connected/stay_candidate.json'
    data = json.loads(path.read_text())
    data[0]['warning_indicator_01'] = '2'
    path.write_text(json.dumps(data))
    journeys, index = run_demo(root, ReportSession.create(project_root=root))
    journey, directory = journeys[0]
    assert not journey['completed']
    assert [step['status'] for step in journey['steps']] == ['KEEP', 'KEEP', 'FAIL', 'NOT_REACHED', 'NOT_REACHED']
    report = json.loads((directory / 'stay/report.json').read_text())
    failure = next(check for check in report['stages'][0]['rule_results'] if check['status'] == 'FAIL')
    assert failure['rule_id'] == 'ST-WARNING-01'
    assert failure['expected'] == '0'
    assert failure['actual'] == '2'
    assert 'Intermediate — Not run' in index.read_text()
    assert 'Final Medpar — Not run' in index.read_text()
    assert 'Files and records by stage' in index.read_text()
    assert 'PIPELINE-NOT-REACHED' not in index.read_text()  # Skipped rules are not reported as extra blocks.
