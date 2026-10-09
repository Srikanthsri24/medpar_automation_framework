# Running Real Input Files

This project has two different execution paths:

1. **Pytest** validates the automation framework and approved data fixtures.
2. **Stage/manifest execution** validates real JSON or Parquet business files and writes a detailed report.

Do not confuse a pytest result with the result of a business input file. A negative fixture may correctly produce a business-rule failure while its pytest test passes because the test expected that failure.

## Data folders

```text
data/user_inputs/
├── final_action/source/
├── split/source/
└── reference/
```

Create these folders when output files become available:

```text
data/user_inputs/<stage>/actual_output/
data/user_inputs/<stage>/expected_output/
```

Use these stage names:

```text
final_action
split
stay
intermediate
final_medpar
```

## Execution modes

### Calculate mode

Uses source files and calculates/checks whatever can be determined from the source. Inline output fields are compared when present.

```bash
python scripts/run_stage.py --stage split --run-date 2024-04-04 \
  --source "data/user_inputs/split/source/Split01_claim.r1.a_20210103.json"
```

### Reconcile mode

Compares calculated expectations with actual application output.

```bash
python scripts/run_stage.py --stage stay --run-date 2024-04-04 \
  --mode reconcile \
  --source "data/user_inputs/stay/source/*.json" \
  --actual "data/user_inputs/stay/actual_output/*.json"
```

### Golden mode

Compares source, actual output and approved expected output.

```bash
python scripts/run_stage.py --stage intermediate --run-date 2024-04-04 \
  --mode golden \
  --source "data/user_inputs/intermediate/source/*.parquet" \
  --actual "data/user_inputs/intermediate/actual_output/*.parquet" \
  --expected "data/user_inputs/intermediate/expected_output/*.parquet"
```

## Run one file

Final Action:

```bash
python scripts/run_stage.py --stage final_action --run-date 2024-04-04 \
  --source "data/user_inputs/final_action/source/claim.r2.a (1).json" \
  --show-pass
```

Split:

```bash
python scripts/run_stage.py --stage split --run-date 2024-04-04 \
  --source "data/user_inputs/split/source/Split03_claim.r1.b_20220103.json" \
  --show-pass
```

A failed business validation exits with code 1 and still creates a JSON report.

## Run multiple files in one stage

Use a glob:

```bash
python scripts/run_stage.py --stage final_action --run-date 2024-04-04 \
  --source "data/user_inputs/final_action/source/*.json"
```

Or repeat `--source`:

```bash
python scripts/run_stage.py --stage split --run-date 2024-04-04 \
  --source "data/user_inputs/split/source/Split01_claim.r1.a_20210103.json" \
  --source "data/user_inputs/split/source/Split02_claim.r1.a_20230103.json"
```

For Final Action, all source files are loaded before claim grouping. Rule 2 requires three top-level records or three separate files with the same Rec-Type, HICN, provider, stay-from date and stay-thru date.

## Run a saved manifest

One Final Action file:

```bash
python -m medpar_qa.cli --manifest config/runs/final_action/claim_r2_a_1.yaml
```

All uploaded Final Action files:

```bash
python -m medpar_qa.cli --manifest config/runs/final_action/all_uploaded.yaml
```

One Split file:

```bash
python -m medpar_qa.cli --manifest config/runs/split/split01_claim_r1_a_20210103.yaml
```

All uploaded Split files:

```bash
python -m medpar_qa.cli --manifest config/runs/split/all_uploaded.yaml
```

Known positive uploaded suite:

```bash
python -m medpar_qa.cli --manifest config/runs/positive_uploaded_suite.yaml
```

Known negative Split fixtures:

```bash
python -m medpar_qa.cli --manifest config/runs/negative_uploaded_split_suite.yaml
```

The negative suite is expected to return exit code 1 because it contains intentional indicator mismatches.

## Run pytest

All framework and uploaded-data tests:

```bash
pytest -v
```

Only uploaded input-data tests:

```bash
pytest -m input_data -v
```

Only Final Action uploaded files:

```bash
pytest -m "input_data and final_action" -v
```

Only Split uploaded files:

```bash
pytest -m "input_data and split" -v
```

All stage code tests:

```bash
pytest -m final_action -v
pytest -m split -v
pytest -m stay -v
pytest -m intermediate -v
pytest -m final_medpar -v
```

Regression and byte-by-byte groups:

```bash
pytest -m regression -v
pytest -m byte_by_byte -v
```

Generate HTML and JUnit reports:

```bash
pytest -v \
  --html=reports/pytest-report.html --self-contained-html \
  --junitxml=reports/pytest-junit.xml
```

## Run all five stages

An all-stage manifest runs each configured stage in one command:

```bash
python -m medpar_qa.cli \
  --manifest config/run_manifest.all_stages.example.yaml
```

For real files, create entries for all five stages with the correct roles:

```yaml
files:
  - {path: data/final_action/source/*.json, stage: final_action, role: source}
  - {path: data/final_action/actual_output/*.json, stage: final_action, role: actual_output}

  - {path: data/split/source/*.json, stage: split, role: source}
  - {path: data/split/actual_output/*.json, stage: split, role: actual_output}

  - {path: data/stay/source/*.parquet, stage: stay, role: source}
  - {path: data/stay/actual_output/*.parquet, stage: stay, role: actual_output}
  - {path: data/stay/expected_output/*.parquet, stage: stay, role: expected_output}

  - {path: data/intermediate/source/*.parquet, stage: intermediate, role: source}
  - {path: data/intermediate/actual_output/*.parquet, stage: intermediate, role: actual_output}
  - {path: data/intermediate/expected_output/*.parquet, stage: intermediate, role: expected_output}

  - {path: data/final_medpar/source/*.json, stage: final_medpar, role: source}
  - {path: data/final_medpar/actual_output/*.json, stage: final_medpar, role: actual_output}
  - {path: data/final_medpar/expected_output/*.json, stage: final_medpar, role: expected_output}
```

The present pipeline is a QA validation pipeline. It executes all configured stage validators together, but it does not replace the production application or transform Final Action source records into Stay and Final MEDPAR output automatically.

## Uploaded file classification

### Final Action source fixtures

```text
claim.r2.a (1).json
FA_T.CVM.CWFCB.D240404.T1438012-000000004.json
FileRule1Rule2.json
```

Each currently has one top-level claim and therefore runs Final Action Rule 1 independently. `FileRule1Rule2.json` does not currently contain a three-record top-level Rule 2 group.

### Split source fixtures

Using run date `2024-04-04`:

| File | Calculated | File value | Business result |
|---|---:|---:|---|
| Split01_claim.r1.a_20210103.json | Y99999 | Y99999 | PASS |
| Split02_claim.r1.a_20230103.json | Y20109 | Y20109 | PASS |
| Split03_claim.r1.b_20220103.json | Y10109 | Y30109 | FAIL |
| Split04_claim.r1.b_20200104.json | Y99999 | Y99999 | PASS |
| Split drop_T.CVM.CWFCB.D240404.T1438012-000000001.json | Y40109 | Y00109 | FAIL |

### Reference file

`schema.json` is reference metadata. It is not a complete claim record and must not be placed in a stage `source` folder.

## Important run-date rule

The Split and Intermediate date calculations depend on `run_date`. Always use the actual business processing date. Changing the run date can change the expected date window and Split indicator.

## Reports

Business validation reports are written to:

```text
reports/<run_id>_validation_report.json
```

The report shows:

- Stage status
- Rule ID
- PASS/FAIL/BLOCKED status
- Expected value
- Actual value
- Source filename
- Record IDs
- Final Action KEEP/DROP decisions
