# MEDPAR QA Automation v0.5.0 — Project Architecture and Execution Guide

This guide explains the folder structure, the responsibility of each important file, and the complete execution path from a command to the final HTML report.

## 1. What this project is

The project is a **validation and regression framework** for five MEDPAR stages:

1. Final Action
2. Four-Year Split
3. Stay
4. Intermediate
5. Final MEDPAR

It reads JSON or Parquet records, normalizes field names, runs stage-specific validations, compares source/actual/expected outputs when supplied, and writes detailed reports.

It is **not the production MEDPAR transformation application**. An all-stage run validates files supplied for all stages; it does not automatically transform Final Action output into Split output, then into Stay, and so on.

---

## 2. Top-level folder structure

```text
medpar_qa_automation_ld3137_fields_update/
├── config/                 Business configuration, field aliases, schemas, manifests
├── data/                   User-provided business input/output files
├── docs/                   Functional and technical documentation
├── reports/                Generated timestamped reports
├── sample_data/            Small controlled examples for tests and demonstrations
├── sample_reports/         Example HTML report session
├── scripts/                Direct command-line runners
├── src/medpar_qa/          Framework source code
├── tests/                  Pytest unit, data, and integration tests
├── run_commands.py         Stage-wise master command runner
├── pyproject.toml          Package/build/test dependencies and plugin registration
├── pytest.ini              Pytest markers and discovery configuration
├── requirements.txt        Direct dependency list
├── setup.py                Editable-install compatibility entry point
├── sitecustomize.py        Adds src/ to Python path for local execution
├── README.md               Setup and usage overview
└── .gitignore              Files excluded from version control
```

---

## 3. Root files

### `run_commands.py`

The main team runner. It contains three editable configuration sections:

- `STAGE_RUNS`: single-file and complete-folder runs, organized by stage.
- `ALL_STAGE_RUNS`: YAML-manifest-based runs covering multiple stages.
- `PYTEST_RUNS`: stage-specific or complete pytest selections.

Execution responsibilities:

1. Creates `reports/<timestamp>/`.
2. Converts enabled configuration entries into subprocess commands.
3. Runs `scripts/run_stage.py`, `medpar_qa.cli`, or pytest.
4. Captures console output.
5. Saves `console.log` and `execution.json` for every command.
6. Refreshes stage indexes and `master/index.html`.

### `pyproject.toml`

Defines the Python package, dependencies, optional test dependencies, and pytest plugin registration. `pip install -e ".[test]"` uses this file.

### `pytest.ini`

Defines test folders and markers such as `final_action`, `split`, `stay`, `intermediate`, `final_medpar`, `input_data`, `regression`, and `byte_by_byte`.

### `requirements.txt`

Contains packages such as pytest, pytest-html, PyYAML, pandas, and pyarrow.

### `setup.py`

Compatibility wrapper for editable installation, especially on older pip/setuptools combinations.

### `sitecustomize.py`

Ensures the local `src/` folder is importable when the project is run without a full package installation.

---

## 4. `config/`

### `config/field_aliases.yaml`

The central field registry. Each canonical framework name maps to one or more possible JSON/Parquet names.

Example concept:

```yaml
provider_id:
  - provider.providerId
  - provider.providerid
  - MEDPAR-PRVDR-FULL-NUM-1660
```

All processors ask the `FieldResolver` for canonical names instead of hard-coding one spelling.

### `config/requirements_2026.yaml`

Machine-readable record of the new discrepancy tickets and LD-3137 requirements. It documents rounding changes, new fields, sort-order changes, and open decisions.

### `config/stages.yaml`

High-level stage order and stage metadata.

### `config/rules/*.yaml`

Human/config representation of each stage's rules:

- `final_action.yaml`
- `split.yaml`
- `stay.yaml`
- `intermediate.yaml`
- `final_medpar.yaml`

The Python processors remain the executable source of logic; these YAML files document/configure business scope.

### `config/schemas/*.yaml`

Expected field structures and required fields per stage. They support requirement traceability and future schema-driven validation.

### `config/run_manifest.example.yaml`

Small single-stage example manifest.

### `config/run_manifest.all_stages.example.yaml`

Working sample that supplies files and settings for all five stages.

### `config/runs/`

Reusable run definitions:

- Stage-specific uploaded-file runs.
- Positive uploaded suite.
- Known-negative Split suite.
- Stay/Intermediate/Final MEDPAR user templates.
- Five-stage user template.

A manifest entry has:

```yaml
- path: relative/path/*.json
  stage: stay
  role: source
  format: json
```

Roles are `source`, `actual_output`, and `expected_output`.

---

## 5. `data/`

### `data/user_inputs/final_action/source/`

User Final Action source claims.

### `data/user_inputs/split/source/`

User Split claims containing or expecting Split indicators.

### `data/user_inputs/stay/`

- `source/`: claims entering Stay.
- `actual_output/`: output produced by the MEDPAR application.
- `expected_output/`: approved legacy/golden output.

### `data/user_inputs/intermediate/`

The same `source`, `actual_output`, and `expected_output` role folders for Intermediate.

### `data/user_inputs/final_medpar/`

The same three role folders for Final MEDPAR.

### `data/user_inputs/reference/schema.json`

Reference metadata only. It is not treated as a full claim input.

---

## 6. `sample_data/`

Small deterministic fixtures used by unit tests, integration tests, all-stage examples, and sample report generation.

- `input/<stage>/...`: source examples.
- `actual/<stage>/...`: simulated application output.
- `expected/<stage>/...`: approved expected output.

These samples are for framework verification, not production evidence.

---

## 7. `scripts/`

### `scripts/run_stage.py`

Runs one stage directly.

It:

1. Parses `--stage`, `--run-date`, `--source`, `--actual`, `--expected`, and `--mode`.
2. Rejects absolute user paths.
3. Converts command arguments into an in-memory `RunManifest`.
4. Loads field aliases.
5. calls `Pipeline.run()`.
6. Writes HTML, JSON, and text reports.
7. Refreshes master/stage indexes.
8. Returns exit code 0 for business pass and 1 for business fail/block.

Modes:

- `calculate`: source only; derive/check what can be checked.
- `reconcile`: source + actual output.
- `golden`: source + actual output + approved expected output.

### `scripts/run_regression.py`

Thin convenience wrapper around the package CLI for regression execution.

---

## 8. `src/medpar_qa/` core package

### `__init__.py`

Marks the package and contains package metadata.

### `enums.py`

Defines shared controlled values:

- `Stage`
- `FileRole`
- `ValidationStatus`
- `RecordDecision`

### `exceptions.py`

Framework-specific exceptions for manifest, input, and configuration errors.

### `models.py`

The central data contracts:

- `SourceLocation`: file, row, format, stage, role.
- `SourceRecord`: record data plus lineage and record ID.
- `RuleResult`: one validation's stage, rule ID, status, expected, actual, field, evidence, and source trace.
- `ClaimDecision`: Final Action KEEP/DROP decision.
- `StageResult`: all rule results and decisions for one stage.
- `ManifestFile`: one configured file path/stage/role.
- `RunManifest`: run ID, business date, files, settings, base directory.

Creating a `RuleResult` also records a reporting event and captures the validator function/call chain.

### `manifest.py`

Loads YAML manifests, validates their shape, converts stage/role strings into enums, resolves the project root, and returns `RunManifest`.

### `cli.py`

Entry point for manifest-based execution:

```text
python -m medpar_qa.cli --manifest config/...
```

It runs the pipeline, creates one report bundle per stage, creates an overall report, refreshes the master index, and returns a meaningful exit code.

---

## 9. `src/medpar_qa/ingestion/`

### `discovery.py`

Expands one relative file or wildcard into actual file paths.

### `readers.py`

Reads JSON and Parquet. It:

- Supports one object, a list of objects, and common wrapper collections.
- Adds source file, source row, role, stage, and format.
- Creates stable record IDs.
- Raises readable errors for malformed content.

---

## 10. `src/medpar_qa/normalization/`

### `fields.py`

Contains `FieldResolver` and nested-path access. It resolves canonical field names using `field_aliases.yaml`.

### `dates.py`

Parses supported date formats and implements January-aligned four/five-year windows.

### `decimal_values.py`

Converts values directly to `Decimal`, applies explicit quantization, and sums without binary floating-point error.

---

## 11. `src/medpar_qa/orchestration/`

### `pipeline.py`

The central coordinator.

`load_with_diagnostics()`:

1. Loops through manifest file entries.
2. Discovers matching files.
3. Emits `INGEST-DISCOVERY` PASS/FAIL results.
4. Reads every file.
5. Emits `INGEST-READ-FILE` PASS/FAIL results.
6. Groups loaded `SourceRecord` objects by stage.

`_processors()` constructs all five stage processors with manifest settings.

`run()`:

1. Determines requested stages.
2. Calls each selected stage processor.
3. Prepends ingestion results.
4. Adds `STAGE-FINAL-SUMMARY`.
5. Returns `list[StageResult]`.

Important: stages are validated in enum order, but the current pipeline does not transform one stage's output into the next stage's input.

---

## 12. `src/medpar_qa/stages/` shared files

### `base.py`

Abstract interface requiring every processor to implement `validate(records)`.

### `common.py`

Shared role splitting, identity construction, duplicate checks, collection normalization, presence checks, and LD-3137 sort/group validations.

### `field_checks.py`

Reusable validators for required fields, dates, allowed values, decimal fields, collections, and regex patterns.

### `comparison.py`

Expected-versus-actual comparison helpers, including protection against false `None == None` passes.

---

## 13. Final Action folder

```text
stages/final_action/
├── context.py
├── grouping.py
├── ordering.py
├── processor.py
├── reconciler.py
├── router.py
├── schema.py
├── settings.py
└── rules/
```

### `settings.py`

Final Action approved query codes, Rule 1 retention codes, transaction codes, Rule 6 configuration, identity fields, and LD-3137 sort fields.

### `schema.py`

Required field/type/date validation for each source claim.

### `grouping.py`

Derives record type and creates the Final Action group key.

### `ordering.py`

Sorts newest first by processing date, accrete date, and source sequence; identifies ambiguous ties.

### `context.py`

Builds one normalized group context containing ordered records, QCs, ICNs, action codes, transaction codes, and group key.

### `router.py`

Chooses exactly one applicable rule.

### `rules/base.py`

Common rule interface and standardized `RuleEvaluation` creation.

### `rules/all_qc0.py`

Drops an all-QC0 group.

### `rules/rule_01.py`

Single-record rule.

### `rules/rule_02.py`

Three-record 5-0-3 / 5-0-1 sequence.

### `rules/rule_03.py`

Same-QC logic and newest record per unique control number.

### `rules/rule_05.py`

Three records, one QC0, no QC5.

### `rules/rule_06.py`

Two records, QC0/QC5, with matching-control-number and 4/6 cancellation logic.

### `rules/rule_07.py`, `rule_08.py`, `rule_09.py`

No-QC5 routes based on QC counts and newest QC.

### `rules/rule_10a.py`, `rule_10b.py`

QC5 fallback routes.

### `rules/default_rule.py`

Safe fallback when no numbered rule applies.

### `rules/helpers.py`

Shared KEEP/DROP construction helpers.

### `reconciler.py`

Validates one decision per record and compares expected KEEP records with actual Final Action output.

### `processor.py`

Coordinates schema validation, grouping, ordering, rule routing, decisions, stage reconciliation, LD-3137 evidence, and actual-output reconciliation.

---

## 14. Split folder

### `settings.py`

Four-year window, bypass transaction codes, identity fields, sort fields, and outside-window indicator.

### `processor.py`

Validates required fields/date order, applies transaction bypass, derives `Y#0109`, `Y#1012`, or `Y99999`, compares populated/actual indicator, checks duplicates, performs output reconciliation, and emits LD-3137 validations.

---

## 15. Stay folder

### `settings.py`

Stay identity/grouping fields, sort fields, Decimal scale, selected fields, condition-code mappings, and Value Code 73.

### `code_precedence.py`

Selects the latest complete code object for duplicate condition, occurrence, span, and value codes while retaining unique codes.

### `derivations.py`

Reusable condition switch, value-code amount, and sum derivations.

### `structural.py`

Source/output structure checks, date checks, required Stay fields, latest nonblank value selection, and selected-value validation.

### `selected_fields.py`

Three-decimal validation for selected Stay monetary fields.

### `processor.py`

Groups source claims, indexes actual/expected records, validates latest-code precedence, enforces maximum ten span groups, derives selected Stay fields, validates total charges/DRG/SNF dates, compares actual and golden records, and reports LD-3137 grouping/sort evidence.

---

## 16. Intermediate folder

### `settings.py`

Five-year window, Decimal scale, selected fields, direct-move fields, repeated arrays, NDC length, procedure limit, revenue search codes, organ codes, and condition switch mappings.

### `structural.py`

Validates Decimal amount fields, procedure structure, diagnosis/POA alignment, death-after-admission, age/NDC, and accommodation totals.

### `selected_fields.py`

Validates selected monetary fields, procedures, diagnoses, counts, versions, dates, and POA values.

### `direct_fields.py`

Validates direct source-to-target fields and repeated-array alignment.

### `legacy_discrepancies.py`

Implements newly identified legacy discrepancies:

- Round each accommodation charge before summation.
- Round per-diem before multiplying by utilization days.
- Revenue-code indicator validation including 0200/0201.
- Admission day 0090.
- Organ acquisition indicator.
- Condition switches.
- Revenue-center line-item checks.
- Source-to-actual direct movement checks.

### `processor.py`

Coordinates all structural, selected-field, legacy-discrepancy, actual-output, golden, duplicate, and date-window validations.

---

## 17. Final MEDPAR folder

### `settings.py`

Expected byte length, encoding, classification values, identity/sort fields, required selected fields, and optional byte field layout.

### `byte_layout.py`

Validates encoded length and configured one-based field offsets/widths.

### `processor.py`

Validates Split indicator, SS/LS/SNF classification, fixed-width record, selected field presence, duplicate identities, source/actual/expected availability, golden comparisons, and LD-3137 grouping/sort evidence.

The official 3050-to-3000 transformation itself remains unimplemented until the authoritative offset/deletion map is supplied.

---

## 18. Reporting folder

### `event_recorder.py`

Captures structured validation and decision events during pytest/business execution.

### `console_reporter.py`

Turns `RuleResult` objects into readable terminal text with requirement, expected, actual, and conclusion.

### `html_reporter.py`

Creates detailed rule cards and stage sections in HTML.

### `json_reporter.py`

Writes machine-readable evidence.

### `report_bundle.py`

Creates the `.html`, `.json`, and `.txt` bundle for one command/stage.

### `rule_catalog.py`

Provides business descriptions and recommendations for known rule IDs.

### `path_utils.py`

Enforces relative paths, creates safe folder names, and calculates relative links.

### `run_layout.py`

Creates the timestamped report-session directory and stage/command folders.

### `session_index.py`

Builds stage `index.html` pages and `master/index.html` from generated report/execution files.

### `pytest_plugin.py`

Captures pytest evidence and writes custom detailed pytest reports into the same timestamped session.

---

## 19. `tests/`

### `tests/conftest.py`

Shared resolver, record factory, and validation-event capture fixture.

### `tests/unit/`

Tests individual calculations and processors:

- Final Action rules and reconciliation.
- Split indicators and required fields.
- Stay latest-code precedence and selected fields.
- Intermediate procedure, diagnosis, rounding, NDC, death, accommodation, and discrepancy fixes.
- Final MEDPAR byte length/layout.
- Detailed report generation.
- Command configuration and relative paths.
- 2026 discrepancy and LD-3137 changes.

### `tests/data/`

Runs the user-uploaded Final Action and Split fixtures, including known negative data.

### `tests/integration/`

Loads YAML manifests and runs one-stage/all-stage pipeline scenarios.

---

## 20. End-to-end command communication

### A. `python run_commands.py`

```text
run_commands.py
  -> reads enabled STAGE_RUNS / ALL_STAGE_RUNS / PYTEST_RUNS
  -> creates reports/<timestamp>/
  -> starts subprocess for each command
       -> scripts/run_stage.py OR medpar_qa.cli OR pytest
  -> captures console output and exit code
  -> writes console.log + execution.json
  -> refreshes stage indexes and master/index.html
```

### B. Direct stage command

```text
scripts/run_stage.py
  -> validates relative arguments
  -> creates RunManifest in memory
  -> loads field_aliases.yaml into FieldResolver
  -> Pipeline.run()
      -> discover_files()
      -> read_records()
      -> SourceRecord + lineage
      -> stage processor.validate()
      -> RuleResult / ClaimDecision
      -> StageResult
  -> write_report_bundle()
      -> report.html
      -> report.json
      -> report.txt
  -> refresh_session_indexes()
  -> exit 0 or 1
```

### C. Manifest command

```text
python -m medpar_qa.cli --manifest ...
  -> load_manifest()
  -> Pipeline.run()
  -> one report bundle per requested stage
  -> overall report bundle
  -> master/stage indexes
```

---

## 21. How source, actual, and expected communicate

The relationship is identity-based, not filename-based.

```text
SOURCE
  Used to calculate business expectations and identify records/groups.

ACTUAL_OUTPUT
  Output produced by the current MEDPAR application.

EXPECTED_OUTPUT
  Approved legacy or golden output.
```

The processor creates an identity tuple from configured canonical fields and matches records across roles.

- Calculate mode: validate/derive using source or supplied target record.
- Reconcile mode: compare source-derived expectation with actual output.
- Golden mode: compare actual output with approved expected output, while also validating source-based rules.

---

## 22. Report flow

```text
RuleResult created
  -> event_recorder captures it
  -> StageResult collects it
  -> console_reporter prints it
  -> report_bundle writes HTML/JSON/TXT
  -> session_index discovers report files
  -> stage index created
  -> master index created
```

A report card contains:

- Stage
- Rule ID
- Status
- Business requirement
- What was checked
- Expected value
- Actual value
- Why it passed/failed/blocked/N/A
- Field
- Record IDs
- Relative source files
- Group key
- Validator function and call chain
- Technical evidence

---

## 23. Important current consistency issues to correct

### 1. Direct stage defaults are stale

`FinalActionSettings` defaults now allow QC2 and enable Rule 6, but `scripts/run_stage.py::_stage_settings()` still supplies the older values:

```text
rule1_keep_qcs: 1,3,5
allowed_query_codes: 0,1,3,5
rule6_enabled: false
```

Therefore direct `scripts/run_stage.py` Final Action runs can behave differently from the new all-stage example manifest and unit tests.

### 2. The user all-stage template is stale

`config/runs/all_5_stages_user_template.yaml` also contains the older QC/Rule 6 settings. It should be aligned with `config/run_manifest.all_stages.example.yaml`.

### 3. Final Action group validation is called twice

`FinalActionProcessor.validate()` contains two consecutive calls to `self.validate_group(group)`, with the first result immediately overwritten. This does not duplicate the final result, but it executes the group logic twice and should be reduced to one call.

### 4. Five-stage execution is validation, not transformation

The pipeline does not feed generated Final Action decisions into Split, or generated Split results into Stay. To perform true end-to-end application validation, the production application must generate each stage's actual output, and the manifest must point to those files.

---

## 24. Recommended files to edit most often

For normal test execution:

1. `run_commands.py`
2. `data/user_inputs/<stage>/...`
3. `config/runs/all_5_stages_user_template.yaml`

For business settings:

1. `config/field_aliases.yaml`
2. `src/medpar_qa/stages/<stage>/settings.py`
3. Stage processor/rule file
4. Corresponding tests

For reporting:

1. `reporting/rule_catalog.py`
2. `reporting/console_reporter.py`
3. `reporting/html_reporter.py`
4. `reporting/session_index.py`

