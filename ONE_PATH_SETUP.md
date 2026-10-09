# One input path — automatic stage run

Production-stage validation code is under `src/medpar_qa/stages/`. `tests/` contains only regression tests.

## Configure once
Open `run_commands.py` and change:
```python
INPUT_PATH = "data/user_inputs/final_action/source/my_claims.json"
INPUT_STAGE = "final_action"
INPUT_RUN_DATE = "2024-04-04"
INPUT_MODE = "calculate"
```
You may use a folder as INPUT_PATH to load all JSON/Parquet files in that folder in a single stage run. Use project-relative paths with forward slashes on Windows.

## Run
```bash
python -m pip install -e ".[test]"
python run_commands.py
```
This calls `scripts/run_stage.py` which invokes `medpar_qa.orchestration.pipeline.Pipeline`, which invokes the selected stage processor in `src/medpar_qa/stages/`. The runner generates one timestamped report session, including Final Action exception/statistics artifacts.

`calculate` is a QA validation mode, **not a production claim-extract writer**. To compare against actual output use `INPUT_MODE="reconcile"` and set `ACTUAL_OUTPUT_PATH`. To compare against golden output set `INPUT_MODE="golden"` and both actual and expected paths.

This package excludes private input fixtures and generated reports. Copy the extracted contents over the cloned Git branch, not the parent folder. Check `git status` shows changes, then run tests and commit.

## Known approval blockers
FA-01, FA-05 and FA-08 still need business decisions; production legacy format and netting golden parity are not certified. See independent audit.
