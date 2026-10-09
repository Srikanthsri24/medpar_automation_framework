# MEDPAR Team Reporting Workflow

## Objective

Every execution creates one timestamped report session. Reports are separated by stage, while the `master` folder contains the consolidated view for sharing with the team.

```text
reports/
└── 20260719_153000/
    ├── master/
    │   └── index.html
    ├── final_action/
    │   ├── index.html
    │   ├── final_action_claim_single_file/
    │   │   ├── report.html
    │   │   ├── report.json
    │   │   ├── report.txt
    │   │   ├── console.log
    │   │   └── execution.json
    │   └── final_action_all_json_files/
    │       └── ...
    ├── split/
    │   ├── index.html
    │   └── split01_single_file/
    │       └── ...
    ├── stay/
    ├── intermediate/
    ├── final_medpar/
    └── pytest/
```

Open files in this order:

1. `reports/<timestamp>/master/index.html`
2. Select a stage.
3. Open the stage `index.html`.
4. Open the required single-file, folder, reconciliation, or golden report.

## What the master report contains

The master report is not only a command log. It includes:

- Command execution status.
- Separate business validation status.
- All stage sections.
- Every emitted rule and validation.
- Business requirement.
- What was checked.
- Evaluation logic.
- Expected result.
- Observed result.
- PASS, FAIL, BLOCKED, or NOT_APPLICABLE conclusion.
- Recommended action for failures.
- Relative source-file paths.
- Record IDs and group keys.
- Validator function and technical evidence.
- Links to standalone stage reports.
- Pytest report links.

Command execution status and business status are deliberately separate. For example, a known negative fixture may have:

```text
Execution status: COMPLETED AS EXPECTED
Business status: BUSINESS FAIL / BLOCKED
```

That means the automation correctly detected the expected business defect. It does not mean the business data passed.

## What each rule card explains

Every rule card is presented in this order:

1. **Business requirement** — why the rule exists.
2. **What was validated** — exact field/group/function checked.
3. **How the result was evaluated** — business comparison logic.
4. **Expected result** — value or condition required.
5. **Observed result** — value found in the input/application output.
6. **Why this is correct/wrong/blocked** — plain-language conclusion.
7. **Source evidence** — relative files, rows, record IDs, group keys, and code function.

## Complete stage rule catalogue

Each stage report also contains a complete rule catalogue:

- `EXECUTED`: the rule emitted a result for this input.
- `NOT TRIGGERED BY THIS DATA`: the rule's prerequisites did not occur.

Not triggered is not treated as a hidden PASS.

## Relative paths only

All user-configured paths must be relative to the project directory.

Correct:

```python
"data/user_inputs/stay/source/*.json"
```

Incorrect:

```python
r"C:\Users\name\Desktop\project\data\stay\*.json"
```

The framework rejects absolute paths passed to `run_stage.py`, `medpar_qa.cli`, and `run_commands.py`.

## Stage-wise command configuration

Edit only `run_commands.py`.

Each stage has:

```python
"single_files": []
"folder_paths": []
```

A single-file entry:

```python
{
    "name": "Stay - one source file",
    "enabled": True,
    "mode": "calculate",
    "source": ["data/user_inputs/stay/source/stay_01.json"],
    "actual": [],
    "expected": [],
    "expected_exit_codes": (0,),
}
```

A complete-folder golden regression entry:

```python
{
    "name": "Stay - complete folder golden regression",
    "enabled": True,
    "mode": "golden",
    "source": ["data/user_inputs/stay/source/*.json"],
    "actual": ["data/user_inputs/stay/actual_output/*.json"],
    "expected": ["data/user_inputs/stay/expected_output/*.json"],
    "expected_exit_codes": (0,),
}
```

Disable a run using:

```python
"enabled": False
```

## Run all enabled commands

```cmd
python run_commands.py
```

At completion the terminal prints only relative report paths and identifies:

- Timestamped report folder.
- Master HTML report.
- Unexpected command results.

## Run one stage directly

```cmd
python scripts\run_stage.py --stage final_action --run-date 2024-04-04 --source "data/user_inputs/final_action/source/claim.r2.a (1).json" --show-pass
```

A timestamped session is created automatically.

## Run all five stages from a manifest

```cmd
python -m medpar_qa.cli --manifest config\run_manifest.all_stages.example.yaml
```

The run creates:

- One report under each requested stage folder.
- One all-stage report under `master/<run-id>/report.html`.
- Consolidated `master/index.html`.

## Run pytest stage-wise

```cmd
python -m pytest -m final_action -v
python -m pytest -m split -v
python -m pytest -m stay -v
python -m pytest -m intermediate -v
python -m pytest -m final_medpar -v
```

Pytest creates a timestamped folder automatically. The custom pytest report shows structured RuleResult evidence, not only raw print output.
