"""Regression tests and local fixtures for detailed reporting. Tests describe controlled examples;
passing them does not certify all production files.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import ManifestFile, RuleResult, RunManifest, StageResult
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline
from medpar_qa.reporting.report_bundle import write_report_bundle


@pytest.mark.unit
def test_report_bundle_contains_complete_validation_evidence(tmp_path: Path):
    """Verify report bundle contains complete validation evidence. The assertions below state
    exactly what this test proves for its fixtures.
    """
    stage_result = StageResult(
        stage=Stage.STAY,
        rule_results=[
            RuleResult(
                stage=Stage.STAY,
                rule_id="ST-TOTAL-CHARGE",
                status=ValidationStatus.FAIL,
                message="MEDPAR-TOT-CHRG-0400 mismatch",
                expected="10.125",
                actual="10.124",
                field_name="MEDPAR-TOT-CHRG-0400",
                source_files=["stay_source.json", "stay_actual.json"],
                record_ids=["source-1", "actual-1"],
                evidence={"decimal_scale": "0.001"},
            )
        ],
    )
    manifest = RunManifest(
        run_id="report_test",
        run_date=date(2026, 7, 19),
        files=[ManifestFile("stay_source.json", Stage.STAY, FileRole.SOURCE)],
    )

    bundle = write_report_bundle(
        run_id=manifest.run_id,
        results=[stage_result],
        output_directory=tmp_path,
        manifest=manifest,
    )

    assert bundle.html.exists()
    assert bundle.json.exists()
    assert bundle.text.exists()
    html = bundle.html.read_text(encoding="utf-8")
    assert "ST-TOTAL-CHARGE" in html
    assert "MEDPAR-TOT-CHRG-0400" in html
    assert "Why this is wrong" in html
    assert "10.125" in html
    assert "10.124" in html
    assert "validator_function" in html


@pytest.mark.unit
def test_missing_input_file_is_reported_as_failure_instead_of_false_pass(tmp_path: Path):
    """Verify missing input file is reported as failure instead of false pass. The assertions below
    state exactly what this test proves for its fixtures.
    """
    manifest = RunManifest(
        run_id="missing_file",
        run_date=date(2026, 7, 19),
        files=[
            ManifestFile(
                "does/not/exist/*.json",
                Stage.FINAL_ACTION,
                FileRole.SOURCE,
            )
        ],
        base_directory=tmp_path,
    )
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")

    results = Pipeline(manifest, resolver).run()

    assert len(results) == 1
    assert not results[0].passed
    discovery = next(
        item for item in results[0].rule_results if item.rule_id == "INGEST-DISCOVERY"
    )
    assert discovery.status is ValidationStatus.FAIL
    assert "No files matched" in discovery.message


@pytest.mark.unit
def test_stage_status_counts_are_available_for_html_summary():
    """Verify stage status counts are available for html summary. The assertions below state
    exactly what this test proves for its fixtures.
    """
    result = StageResult(
        stage=Stage.INTERMEDIATE,
        rule_results=[
            RuleResult(Stage.INTERMEDIATE, "A", ValidationStatus.PASS, "correct"),
            RuleResult(Stage.INTERMEDIATE, "B", ValidationStatus.FAIL, "wrong"),
            RuleResult(
                Stage.INTERMEDIATE,
                "C",
                ValidationStatus.NOT_APPLICABLE,
                "not applicable",
            ),
        ],
    )
    assert result.status_counts == {
        "PASS": 1,
        "FAIL": 1,
        "NOT_APPLICABLE": 1,
        "BLOCKED": 0,
        "KNOWN_DIFFERENCE": 0,
    }

@pytest.mark.unit
def test_team_report_explains_requirement_expected_actual_and_conclusion(tmp_path: Path):
    """Verify team report explains requirement expected actual and conclusion. The assertions below
    state exactly what this test proves for its fixtures.
    """
    stage_result = StageResult(
        stage=Stage.SPLIT,
        rule_results=[
            RuleResult(
                stage=Stage.SPLIT,
                rule_id="SP-RULE-INDICATOR",
                status=ValidationStatus.FAIL,
                message="Split indicator mismatch",
                expected="Y10109",
                actual="Y30109",
                field_name="split_year_indicator",
                source_files=["data/user_inputs/split/source/sample.json"],
            )
        ],
    )
    bundle = write_report_bundle(
        run_id="team_report",
        results=[stage_result],
        output_directory=tmp_path,
    )
    page = bundle.html.read_text(encoding="utf-8")
    assert "Business requirement" in page
    assert "What was validated" in page
    assert "Expected result" in page
    assert "Observed result" in page
    assert "Why this is wrong" in page
    assert "Recommended action" in page
    assert "data/user_inputs/split/source/sample.json" in page


@pytest.mark.unit
def test_timestamped_session_writes_stage_and_master_indexes(tmp_path: Path):
    """Verify timestamped session writes stage and master indexes. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.reporting.run_layout import ReportSession
    from medpar_qa.reporting.session_index import refresh_session_indexes

    session = ReportSession.create(
        tmp_path,
        session_path=tmp_path / "20260719_150000",
        project_root=tmp_path,
    )
    command_dir = session.command_directory("stay", "one_file")
    stage_result = StageResult(
        stage=Stage.STAY,
        rule_results=[
            RuleResult(Stage.STAY, "ST-TOTAL-CHARGE", ValidationStatus.PASS, "matched", "1.000", "1.000")
        ],
    )
    write_report_bundle(run_id="one_file", results=[stage_result], output_directory=command_dir)
    master = refresh_session_indexes(session.root)

    assert (session.root / "stay" / "index.html").exists()
    assert master == session.root / "master" / "index.html"
    assert master.exists()
    assert "Files and records by stage" in master.read_text(encoding="utf-8")
    assert "ST-TOTAL-CHARGE" in (master.parent / "details.html").read_text(encoding="utf-8")

@pytest.mark.unit
def test_file_review_preserves_shared_checks_and_unattributed_failures():
    """Verify file review preserves shared checks and unattributed failures. The assertions below
    state exactly what this test proves for its fixtures.
    """
    from medpar_qa.reporting.file_review import file_review, readable_time
    checks = [
        {'rule_id': 'INGEST-READ-FILE', 'status': 'PASS', 'message': 'Read 2 records', 'source_files': ['a.json'], 'actual': {'role': 'source'}},
        {'rule_id': 'ST-TOTAL-CHARGE', 'status': 'FAIL', 'message': 'Expected 10, observed 9', 'source_files': ['a.json', 'b.json'], 'evidence': {}},
        {'rule_id': 'STAGE-FINAL-SUMMARY', 'status': 'BLOCKED', 'message': 'Reference missing', 'source_files': []},
    ]
    rendered = file_review('stay', checks, 'stay-1')
    assert '2 unique evidence files; 1 successfully read' in rendered
    assert rendered.count("href='#stay-1-2'") == 2
    assert rendered.count('Final conclusion for this file:') == 2
    assert 'Stage-wide checks without an individual file attribution (1)' in rendered
    assert 'No file-level result recorded' in rendered
    assert '11 October 2026 at 02:01:38 AM (UTC+05:30)' == readable_time('2026-10-11T02:01:38+05:30')

@pytest.mark.unit
def test_master_report_defines_metrics_and_file_navigation(tmp_path):
    """Verify master report defines metrics and file navigation. The assertions below state exactly
    what this test proves for its fixtures.
    """
    import json
    from medpar_qa.reporting.session_index import write_master_index
    folder = tmp_path / 'stay' / 'run'
    folder.mkdir(parents=True)
    (folder / 'report.json').write_text(json.dumps({'stages': [{'stage': 'stay', 'passed': False, 'rule_results': [{'rule_id': 'INGEST-READ-FILE', 'status': 'PASS', 'message': 'Read file', 'source_files': ['example.json']}, {'rule_id': 'ST-TOTAL-CHARGE', 'status': 'FAIL', 'message': 'Mismatch', 'source_files': ['example.json']}]}]}))
    page = write_master_index(tmp_path).read_text()
    assert 'Files and records by stage' in page
    assert 'stay_pass_files.html' in page
    assert 'stay_fail_files.html' in page
    selected = (tmp_path / 'master' / 'stay_fail_files.html').read_text()
    assert 'example.json' in selected
    assert 'Mismatch' in selected
    assert 'Read file' not in selected
    assert (tmp_path / 'master' / 'overview.html').exists()
    page = (tmp_path / 'master' / 'details.html').read_text()
    assert 'How to read file, record and validation counts' in page
    assert 'Validations = Pass + Fail + Blocked + N/A' in page
    assert "id='stay-1-2'" in page
    assert "href='#stay-1-2'" in page
    assert 'example.json' in page
    assert 'Final conclusion for this file' in page

@pytest.mark.unit
def test_stage_conclusions_count_unique_files_and_keep_global_blocks():
    """Verify stage conclusions count unique files and keep global blocks. The assertions below
    state exactly what this test proves for its fixtures.
    """
    from medpar_qa.reporting.file_review import stage_conclusion, file_review
    checks = [
        {'rule_id': 'INGEST-READ-FILE', 'status': 'PASS', 'message': 'Read', 'source_files': ['a.json'], 'actual': {'role': 'source'}},
        {'rule_id': 'ST-TOTAL-CHARGE', 'status': 'FAIL', 'message': 'Expected 10, observed 9', 'source_files': ['a.json', 'b.json']},
        {'rule_id': 'INGEST-SNAPSHOT-MATCH', 'status': 'BLOCKED', 'message': 'Different snapshots', 'source_files': []},
    ]
    conclusion = stage_conclusion('stay', checks)
    assert '2 unique evidence files; 1 successfully read; 3 checks' in conclusion
    assert 'Stay: FAIL' in conclusion
    assert 'Files linked to failed checks: 2' in conclusion
    assert 'Different snapshots' in conclusion
    assert 'Required action' in conclusion
    assert 'Stay: BLOCKED' in stage_conclusion('stay', checks[2:])
    assert 'Stay: PASS' in stage_conclusion('stay', checks[:1])
    assert 'Stay: NOT ESTABLISHED' in stage_conclusion('stay', [])
    inventory = file_review('stay', checks, 'stay-1')
    assert 'file-search' in inventory and 'file-select' in inventory
    assert "data-file='a.json'" in inventory
    assert "value='b.json'" in inventory
