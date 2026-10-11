"""R65 import preserves archive bytes and refuses unsafe paths or overwrites."""
import zipfile
import pytest
from scripts.extract_r65 import extract_archive


def test_import_preserves_bytes_and_is_repeatable(tmp_path):
    archive = tmp_path / 'R65.txt'
    payload = b'{"medparSSLSSNFIND0140":"S"}'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('home/cloudshell-user/my_bucket3/6-final-processing/SS/file.json', payload)
    destination = tmp_path / 'data'
    first = extract_archive(archive, destination)
    assert extract_archive(archive, destination) == first
    assert (destination / first[0]['path']).read_bytes() == payload
    assert (destination / 'archive_inventory.json').exists()
    (destination / first[0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='refusing overwrite'):
        extract_archive(archive, destination)


def test_import_rejects_traversal(tmp_path):
    archive = tmp_path / 'bad.txt'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('my_bucket3/../escape.json', '{}')
    with pytest.raises(ValueError, match='Unexpected archive path'):
        extract_archive(archive, tmp_path / 'data')


def test_final_files_checked_independently_without_cross_file_dedup(tmp_path, monkeypatch):
    import json
    import shutil
    import sys
    from pathlib import Path
    from scripts import run_stage
    root = Path(__file__).resolve().parents[2]
    (tmp_path / 'config').mkdir()
    shutil.copyfile(root / 'config/field_aliases.yaml', tmp_path / 'config/field_aliases.yaml')
    for name in ('first.json', 'second.json'):
        shutil.copyfile(root / 'data/demo_connected/final_medpar_candidate.json', tmp_path / name)
    monkeypatch.setattr(run_stage, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['run_stage.py', '--stage', 'final_medpar', '--run-date', '2026-05-14',
        '--source', 'first.json', '--source', 'second.json', '--per-file', '--report-session', 'reports/check'])
    assert run_stage.main() == 0
    payload = json.loads(next((tmp_path / 'reports/check').glob('final_medpar/*/report.json')).read_text())
    checks = [check for stage in payload['stages'] for check in stage['rule_results']]
    indicators = [check for check in checks if check['rule_id'] == 'FM-SPLIT-YEAR-INDICATOR']
    assert len(indicators) == 2
    assert all(check['status'] == 'PASS' for check in indicators)
    assert not any(check['status'] == 'FAIL' for check in checks)
