# Detailed HTML reports

Every execution path now produces a shareable HTML report automatically.

## What the report contains

For every stage and every emitted validation rule, the report shows:

- Stage and overall PASS/FAIL/BLOCKED result
- Rule ID and validated field
- Exact Python validator function and source line
- A plain-language explanation of why the result is correct, wrong, blocked, or not applicable
- Expected value
- Actual value
- Source file paths
- Source record IDs and group key
- Additional technical evidence
- Final Action KEEP/DROP decisions
- Input paths and run settings
- Counts by PASS, FAIL, BLOCKED and NOT_APPLICABLE

The HTML is self-contained. It can be opened locally, emailed, shared through Teams/Drive, printed, or saved as PDF.

## Single stage or single file

```cmd
python scripts\run_stage.py --stage final_action --run-date 2024-04-04 --source "data\user_inputs\final_action\source\claim.r2.a (1).json" --show-pass
```

The command prints every validation in the terminal and creates:

```text
reports/<run-id>_<timestamp>_detailed_report.html
reports/<run-id>_validation_report.json
reports/<run-id>_<timestamp>_detailed_report.txt
```

The report is created for a PASS, FAIL, BLOCKED, missing file, malformed JSON, or invalid field.

## Complete stage folder

```cmd
python scripts\run_stage.py --stage split --run-date 2024-04-04 --source "data\user_inputs\split\source\*.json" --show-pass
```

Each discovered file receives separate file-discovery and file-read checks. All source rows and business-rule validations are then shown.

## All five stages

```cmd
python -m medpar_qa.cli --manifest config\run_manifest.all_stages.example.yaml
```

This creates one HTML report containing separate expandable sections for:

1. Final Action
2. Split
3. Stay
4. Intermediate
5. Final MEDPAR

## Pytest reports

Running pytest now always creates a custom detailed HTML report:

```cmd
python -m pytest -m final_action -v
```

Output:

```text
reports/pytest_detailed_<timestamp>.html
```

The report contains each pytest test result and all `RuleResult`/`ClaimDecision` details emitted by that test. This includes validations from passed tests, which standard pytest reports often hide inside captured output.

To additionally create the normal `pytest-html` report:

```cmd
python -m pytest -v --html=reports\pytest_standard.html --self-contained-html --junitxml=reports\pytest_junit.xml
```

Both reports will be available. The custom MEDPAR report is the more detailed business-rule report.

## Run all enabled commands

Edit `run_commands.py` and set `enabled=True` or `enabled=False` for each command.

```cmd
python run_commands.py
```

Each stage command creates its own detailed HTML report. The runner also creates:

```text
reports/command_suite_<timestamp>.html
```

This master report contains:

- Every executed command
- Command exit code
- Expected exit codes
- Complete terminal output
- Links to reports created by that command
- Overall command-suite result

## Report filters

The stage report supports:

- Search by rule, field, function, message or file
- Filter by stage
- Filter by PASS/FAIL/BLOCKED/NOT_APPLICABLE
- Expand all / collapse all
- Copy one validation's details
- Print or Save as PDF

## Missing-file false-pass issue

A test must never pass because a file was not found. File handling now emits explicit rules:

- `INGEST-DISCOVERY`
- `INGEST-READ-FILE`
- `INGEST-NO-RECORDS`

A missing or malformed file is a failed validation, is visible in the HTML report, and causes business execution to return exit code `1`.
