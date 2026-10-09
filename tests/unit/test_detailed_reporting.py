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
    }

@pytest.mark.unit
def test_team_report_explains_requirement_expected_actual_and_conclusion(tmp_path: Path):
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
    assert "ST-TOTAL-CHARGE" in master.read_text(encoding="utf-8")
