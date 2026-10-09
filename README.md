# MEDPAR QA Automation v0.5.0 — Discrepancy and LD-3137 Update

The project now includes the supplied 2026 byte-by-byte corrections, missing-field registry expansion, Final Action Rule 6 implementation, and admissionDate sort-order removal for Final Action, Split, Stay, and Final MEDPAR. See `docs/AUGUST_2026_DISCREPANCY_AND_LD3137_UPDATE.md` and `docs/OPEN_BUSINESS_DECISIONS.md`.

Verified: **104 tests passed, 0 failed**, the working all-five-stage manifest passed, and the default seven-command reporting session completed without unexpected results.

Key update documents:

- `docs/AUGUST_2026_DISCREPANCY_AND_LD3137_UPDATE.md`
- `docs/FIELD_COVERAGE_MATRIX.md`
- `docs/OPEN_BUSINESS_DECISIONS.md`
- `docs/CHANGELOG_v0.5.0.md`
- `config/requirements_2026.yaml`

## Team-ready timestamped reports

The reporting workflow now creates one timestamped folder per execution session:

```text
reports/<timestamp>/master/index.html
reports/<timestamp>/<stage>/index.html
reports/<timestamp>/<stage>/<command>/report.html
```

Open `master/index.html` first. It contains all stage validations, rule explanations, expected/observed values, business status, command status, and relative links.

Configure stage-wise single files and folder wildcards in `run_commands.py`, then run:

```cmd
python run_commands.py
```

All configured paths must be relative to the project folder. See `docs/TEAM_REPORTING_WORKFLOW.md`.

## Detailed HTML reporting

Every single-file run, stage run, manifest run, pytest run, and `run_commands.py` execution now creates shareable HTML evidence. Reports include every rule, field, validator function, expected value, actual value, source file, record ID, reason for PASS/FAIL/BLOCKED/N/A, and Final Action KEEP/DROP decisions.

```cmd
python scripts\run_stage.py --stage final_action --run-date 2024-04-04 --source "data\user_inputs\final_action\source\claim.r2.a (1).json" --show-pass
```

Open the printed `Detailed HTML` path under `reports/`. See `docs/DETAILED_HTML_REPORTS.md` for report types and commands.

A missing input file or malformed JSON now produces a failed ingestion validation and an HTML report; it cannot silently produce a passing test.

This is the replacement project for validating all five MEDPAR processing stages:

1. Final Action
2. Four-Year Split
3. Stay
4. Intermediate
5. Final MEDPAR

It supports JSON and Parquet, one or many files, stage-only execution, source-versus-actual reconciliation, approved golden comparisons, PASS/FAIL/BLOCKED evidence, JSON reports, HTML/JUnit pytest reports, and a complete five-stage manifest.

## Python requirement

Use **Python 3.11 or newer**. Python 3.8 does not support the language features used by the project.

Check installed versions on Windows:

```cmd
py -0p
```

Create and activate the environment:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[test]"
```

Verify:

```cmd
python --version
python -m pytest --collect-only
python -m pytest -v
```

## Run commands from one file

Edit:

```text
run_commands.py
```

Change file paths, stages, dates and modes. Set `enabled=True` only for commands you want. Then run:

```cmd
python run_commands.py
```

The file already includes commands for all five stages, all-stage execution, uploaded-data tests, regression tests and HTML/JUnit reports.

## Run one stage directly

Final Action:

```cmd
python scripts\run_stage.py --stage final_action --run-date 2024-04-04 --source "data/user_inputs/final_action/source/claim.r2.a (1).json" --show-pass
```

Split:

```cmd
python scripts\run_stage.py --stage split --run-date 2024-04-04 --source "data/user_inputs/split/source/Split01_claim.r1.a_20210103.json" --show-pass
```

Stay golden regression:

```cmd
python scripts\run_stage.py --stage stay --run-date 2026-07-19 --mode golden --source "data/user_inputs/stay/source/*" --actual "data/user_inputs/stay/actual_output/*" --expected "data/user_inputs/stay/expected_output/*" --show-pass
```

Intermediate golden regression:

```cmd
python scripts\run_stage.py --stage intermediate --run-date 2026-07-19 --mode golden --source "data/user_inputs/intermediate/source/*" --actual "data/user_inputs/intermediate/actual_output/*" --expected "data/user_inputs/intermediate/expected_output/*" --show-pass
```

Final MEDPAR golden regression:

```cmd
python scripts\run_stage.py --stage final_medpar --run-date 2026-07-19 --mode golden --source "data/user_inputs/final_medpar/source/*" --actual "data/user_inputs/final_medpar/actual_output/*" --expected "data/user_inputs/final_medpar/expected_output/*" --show-pass
```

## Run all five stages

Complete working example:

```cmd
python -m medpar_qa.cli --manifest config/run_manifest.all_stages.example.yaml
```

Template for your own files:

```cmd
python -m medpar_qa.cli --manifest config/runs/all_5_stages_user_template.yaml
```

Remove or comment a manifest entry when that file folder is empty.

## Run pytest by stage

```cmd
python -m pytest -m final_action -v
python -m pytest -m split -v
python -m pytest -m stay -v
python -m pytest -m intermediate -v
python -m pytest -m final_medpar -v
python -m pytest -m input_data -v
python -m pytest -m regression -v
python -m pytest -m byte_by_byte -v
```

HTML and JUnit reports:

```cmd
python -m pytest -v --html=reports/pytest-report.html --self-contained-html --junitxml=reports/pytest-junit.xml
```

## Input roles

- `source`: input consumed by the stage.
- `actual_output`: output produced by the application under test.
- `expected_output`: approved golden output.

Modes:

- `calculate`: run known calculations and structural checks.
- `reconcile`: compare source and actual output.
- `golden`: compare source, actual output and approved expected output.

## Validation coverage

Read:

- `docs/COMPLETE_VALIDATION_SCOPE.md`
- `docs/RUN_COMMANDS_GUIDE.md`
- `docs/OPEN_BUSINESS_DECISIONS.md`
- `docs/RUNNING_YOUR_INPUT_FILES.md`

The project implements all rules and selected-field requirements available in the supplied material. It does not invent the unresolved Final Action Rule 6 matrix or proprietary Final MEDPAR byte offsets; those remain explicit blocked/configurable items.