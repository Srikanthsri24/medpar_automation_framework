# MEDPAR framework — single definitive package

This ZIP is the full repository content (not just tests). Copy the CONTENTS of the `medpar_automation_framework` folder into your existing Git checkout. Do not replace `.git`.

## Production code
- `src/medpar_qa/stages/final_action/`: Final Action schema, grouping, routing, rule implementations, and reconciliation
- `src/medpar_qa/orchestration/`: stage pipeline
- `scripts/run_stage.py`: stage invocation
- `run_commands.py`: ONE-PLACE input configuration and automatic reporting
- `tests/`: verification only, not the production implementation

## One-path run
Open `run_commands.py`, change only the top `INPUT_PATH` and optionally `INPUT_RUN_DATE`:
```python
INPUT_PATH = "data/user_inputs/final_action/source/my_claims.json"
INPUT_STAGE = "final_action"
INPUT_MODE = "calculate"
```
Then run `python run_commands.py`. The path must be project-relative; JSON or Parquet file or directory containing them. Reports appear in `reports/<timestamp>/`.

## Setup and verification (Git Bash, Windows)
```bash
python -m pip install -e .
python -m pytest -q
python run_commands.py
git status
git add -A
git commit -m "Update full MEDPAR framework and Final Action V3 single-path runner"
git push -u origin feature/final-action-v3-comprehensive
```

## Release limits — DO NOT CLAIM FULL V3 CERTIFICATION
- FA-01 bypass direction, FA-05 Rule5, FA-08 Rules7-9 await written business decisions.
- Production net-billed extract writing, legacy error file format, financial balancing and golden parity are not certified.
- The single-path calculate mode is a QA validation run and produces decisions/reports, NOT a production claim extract.
- 123 local tests pass when included sample fixtures are present; the user's separate Git checkout with only 91 tests has not received this package until files are copied.

See `FINAL_ACTION_INDEPENDENT_AUDIT.md` for the detailed open items.
