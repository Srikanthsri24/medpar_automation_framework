"""Load manifest files with ingestion diagnostics, optionally enrich Intermediate source
references, run requested processors and add each stage completion result.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.ingestion.discovery import discover_files
from medpar_qa.ingestion.readers import read_records
from medpar_qa.models import RuleResult, RunManifest, SourceRecord, StageResult
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.reporting.path_utils import relative_display
from medpar_qa.stages.final_action.processor import FinalActionProcessor
from medpar_qa.stages.final_action.settings import FinalActionSettings
from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
from medpar_qa.stages.final_medpar.settings import FinalMedparSettings
from medpar_qa.stages.intermediate.processor import IntermediateProcessor
from medpar_qa.stages.intermediate.settings import IntermediateSettings
from medpar_qa.stages.split.processor import SplitProcessor
from medpar_qa.stages.split.settings import SplitSettings
from medpar_qa.stages.stay.processor import StayProcessor
from medpar_qa.stages.stay.settings import StaySettings


class Pipeline:
    """Represent pipeline with the fields and methods declared below. This class groups the related
    operations below.
    """
    def __init__(self, manifest: RunManifest, field_resolver: FieldResolver) -> None:
        """Initialize this Pipeline with the supplied dependencies/configuration and the
        assignments in its constructor.
        """
        self.manifest = manifest
        self.field_resolver = field_resolver

    def _snapshot_check(self, stage: Stage, records: list[SourceRecord]) -> RuleResult:
        """Compare available source/output rundate and yearQuarter folder metadata; BLOCKED means a
        compatible comparison cycle is not established.
        """
        from medpar_qa.enums import FileRole
        axes = ("rundate", "yearQuarter")
        snapshots = {role: {axis: set() for axis in axes}
                     for role in (FileRole.SOURCE, FileRole.ACTUAL_OUTPUT)}
        for record in records:
            if record.source.role not in snapshots:
                continue
            for part in Path(record.source.file_path).parts:
                for axis in axes:
                    if part.startswith(axis + "="):
                        snapshots[record.source.role][axis].add(part.split("=", 1)[1])
        common = [axis for axis in axes if all(snapshots[role][axis] for role in snapshots)]
        mismatched = [axis for axis in common
                      if snapshots[FileRole.SOURCE][axis] != snapshots[FileRole.ACTUAL_OUTPUT][axis]]
        valid = bool(common) and not mismatched
        return RuleResult(stage=stage, rule_id="INGEST-SNAPSHOT-MATCH",
                          status=ValidationStatus.PASS if valid else ValidationStatus.BLOCKED,
                          message="Source/output snapshot metadata matches" if valid else
                          "Source/output snapshots differ or cannot be established; supply matching extraction before reconciliation",
                          expected="Matching source/output snapshot metadata",
                          actual={role.value: {axis: sorted(values) for axis, values in data.items()}
                                  for role, data in snapshots.items()},
                          evidence={"compared_axes": common, "mismatched_axes": mismatched})

    def load_with_diagnostics(
        self,
    ) -> tuple[dict[Stage, list[SourceRecord]], dict[Stage, StageResult]]:
        """Load all manifest files while creating reportable PASS/FAIL checks.

        A missing, unreadable, or malformed file is converted to a RuleResult instead
        of terminating before an HTML report can be created.
        """
        grouped: dict[Stage, list[SourceRecord]] = defaultdict(list)
        diagnostics: dict[Stage, StageResult] = {}

        for entry in self.manifest.files:
            stage_result = diagnostics.setdefault(entry.stage, StageResult(stage=entry.stage))
            try:
                paths = discover_files(entry.path, self.manifest.base_directory)
            except Exception as exc:  # defensive: path/glob implementation errors
                stage_result.rule_results.append(
                    RuleResult(
                        stage=entry.stage,
                        rule_id="INGEST-DISCOVERY",
                        status=ValidationStatus.FAIL,
                        message=f"File discovery failed: {exc}",
                        expected="At least one readable file matching the configured path",
                        actual=entry.path,
                        source_files=[entry.path],
                        evidence={"role": entry.role.value, "format": entry.format or "auto"},
                    )
                )
                continue

            if not paths:
                stage_result.rule_results.append(
                    RuleResult(
                        stage=entry.stage,
                        rule_id="INGEST-DISCOVERY",
                        status=ValidationStatus.FAIL,
                        message="No files matched the configured path or glob",
                        expected="At least one matching file",
                        actual=entry.path,
                        source_files=[entry.path],
                        evidence={"role": entry.role.value, "format": entry.format or "auto"},
                    )
                )
                continue

            stage_result.rule_results.append(
                RuleResult(
                    stage=entry.stage,
                    rule_id="INGEST-DISCOVERY",
                    status=ValidationStatus.PASS,
                    message=f"Discovered {len(paths)} file(s) for {entry.role.value}",
                    expected="One or more matching files",
                    actual=[relative_display(path, project_root=self.manifest.base_directory) for path in paths],
                    source_files=[relative_display(path, project_root=self.manifest.base_directory) for path in paths],
                    evidence={
                        "configured_path": entry.path,
                        "role": entry.role.value,
                        "format": entry.format or "auto",
                    },
                )
            )

            for path in paths:
                try:
                    records = read_records(
                        path,
                        entry.stage,
                        entry.role,
                        entry.format,
                        display_base=self.manifest.base_directory,
                    )
                except Exception as exc:
                    stage_result.rule_results.append(
                        RuleResult(
                            stage=entry.stage,
                            rule_id="INGEST-READ-FILE",
                            status=ValidationStatus.FAIL,
                            message=f"Could not read or parse input file: {exc}",
                            expected="Valid JSON or Parquet content",
                            actual={
                                "file": relative_display(path, project_root=self.manifest.base_directory),
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                            source_files=[relative_display(path, project_root=self.manifest.base_directory)],
                            evidence={"role": entry.role.value, "format": entry.format or path.suffix.lstrip(".")},
                        )
                    )
                    continue

                grouped[entry.stage].extend(records)
                stage_result.rule_results.append(
                    RuleResult(
                        stage=entry.stage,
                        rule_id="INGEST-READ-FILE",
                        status=ValidationStatus.PASS,
                        message=f"File was read successfully and produced {len(records)} record(s)",
                        expected="Readable file containing at least one record",
                        actual={
                            "file": relative_display(path, project_root=self.manifest.base_directory),
                            "record_count": len(records),
                            "role": entry.role.value,
                        },
                        source_files=[relative_display(path, project_root=self.manifest.base_directory)],
                        record_ids=[record.record_id for record in records],
                        evidence={"file_size_bytes": Path(path).stat().st_size},
                    )
                )

        return dict(grouped), diagnostics

    def load(self) -> dict[Stage, list[SourceRecord]]:
        """Backward-compatible record loading API.

        Unlike the previous implementation, missing files do not throw here. Use
        ``run()`` to receive the corresponding failed ingestion validation.
        """
        records, _ = self.load_with_diagnostics()
        return records

    def _processors(self):
        """Instantiate each concrete stage processor with its typed settings and run date where
        required.
        """
        return {
            Stage.FINAL_ACTION: FinalActionProcessor(
                self.field_resolver,
                FinalActionSettings.from_mapping(
                    self.manifest.settings.get("final_action")
                ),
            ),
            Stage.SPLIT: SplitProcessor(
                self.field_resolver,
                self.manifest.run_date,
                settings=SplitSettings.from_mapping(
                    self.manifest.settings.get("split")
                    or {
                        "window_years": self.manifest.settings.get(
                            "split_window_years", 4
                        )
                    }
                ),
            ),
            Stage.STAY: StayProcessor(
                self.field_resolver,
                StaySettings.from_mapping(self.manifest.settings.get("stay")),
            ),
            Stage.INTERMEDIATE: IntermediateProcessor(
                self.field_resolver,
                self.manifest.run_date,
                IntermediateSettings.from_mapping(
                    self.manifest.settings.get("intermediate")
                    or {
                        "window_years": self.manifest.settings.get(
                            "intermediate_window_years", 5
                        )
                    }
                ),
            ),
            Stage.FINAL_MEDPAR: FinalMedparProcessor(
                self.field_resolver,
                FinalMedparSettings.from_mapping(
                    self.manifest.settings.get("final_medpar")
                    or {
                        "expected_bytes": self.manifest.settings.get(
                            "final_medpar_bytes", 3000
                        )
                    }
                ),
            ),
        }

    def run(self) -> list[StageResult]:
        """Load evidence, apply optional references and record contracts, execute requested stages
        and add the final stage summary.
        """
        records_by_stage, diagnostics = self.load_with_diagnostics()
        reference_config = self.manifest.settings.get("reference_feeds")
        if reference_config:
            from medpar_qa.reference_data import ReferenceData
            try:
                references = ReferenceData(reference_config, self.manifest.base_directory)
                for record in records_by_stage.get(Stage.INTERMEDIATE, []):
                    if record.source.role == FileRole.SOURCE:
                        record.data = references.enrich(record.data, self.field_resolver)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                diagnostics.setdefault(Stage.INTERMEDIATE, StageResult(stage=Stage.INTERMEDIATE)).rule_results.append(
                    RuleResult(stage=Stage.INTERMEDIATE,rule_id="INT-REFERENCE-FEED",status=ValidationStatus.BLOCKED,
                        message=f"Configured reference feed is unavailable or invalid ({type(exc).__name__})",
                        expected="Readable, valid DOD/SSI reference feed"))
        processors = self._processors()
        results: list[StageResult] = []

        requested_stages = {entry.stage for entry in self.manifest.files}
        for stage in Stage:
            if stage not in requested_stages:
                continue

            preliminary = diagnostics.get(stage, StageResult(stage=stage))
            records = records_by_stage.get(stage, [])
            snapshot_blocked = False
            if self.manifest.settings.get(stage.value, {}).get("require_matching_snapshot"):
                snapshot = self._snapshot_check(stage, records)
                preliminary.rule_results.append(snapshot)
                snapshot_blocked = snapshot.status == ValidationStatus.BLOCKED
            from medpar_qa.stages.record_contracts import validate_record_contracts
            preliminary.rule_results.extend(validate_record_contracts(records,self.field_resolver))
            if records and not snapshot_blocked:
                processed = processors[stage].validate(records)
                processed.rule_results = [
                    *preliminary.rule_results,
                    *processed.rule_results,
                ]
            else:
                processed = preliminary
                if not processed.rule_results:
                    processed.rule_results.append(
                        RuleResult(
                            stage=stage,
                            rule_id="INGEST-NO-RECORDS",
                            status=ValidationStatus.FAIL,
                            message="No records were available for stage validation",
                            expected="One or more valid records",
                            actual=0,
                        )
                    )

            pre_summary_passed = processed.passed
            counts = processed.status_counts
            processed.rule_results.append(
                RuleResult(
                    stage=stage,
                    rule_id="STAGE-FINAL-SUMMARY",
                    status=(
                        ValidationStatus.PASS
                        if pre_summary_passed
                        else ValidationStatus.FAIL
                    ),
                    message=(
                        "Stage completed with no failed or blocked validations"
                        if pre_summary_passed
                        else "Stage completed with failed or blocked validations"
                    ),
                    expected={"FAIL": 0, "BLOCKED": 0},
                    actual=counts,
                    evidence={
                        "source_record_count": len(records),
                        "decision_count": len(processed.decisions),
                    },
                )
            )
            results.append(processed)
        return results
