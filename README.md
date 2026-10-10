# MEDPAR QA Automation

Validate Final Action, Four-Year Split, Stay, Intermediate and Final MEDPAR using JSON or Parquet inputs. The framework compares production outputs with source rules and approved expected outputs, and produces reports explaining every recorded result.

**Current verification:** 257 automated tests passed on 11 October 2026. All five synthetic demo stages pass (`reports/20261011_023400/master/index.html`). Supplied production validation remains failing or blocked; a passing software test suite does not establish production acceptance.

## Setup

Python 3.11 or newer is required. Run commands from this repository's root folder.

macOS / Linux:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

## Demo

Run the complete synthetic five-stage example:

```sh
python -m medpar_qa.cli --manifest config/run_manifest.all_stages.example.yaml
```

Run the configured production stages:

```sh
python run_commands.py
```

Edit `STAGE_RUNS` in `run_commands.py` to select stage dates, individual files and folders. Enable only the required runs. Input paths must be relative to the repository. Production inputs are local under `data/production/q61/` and are excluded from Git. Missing files, mismatched snapshots and business failures remain visible in reports.

The current production demo is `reports/20261011_020107/master/index.html`. Reports are generated locally and are not uploaded to GitHub. To view them in a browser:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/reports/20261011_020107/master/index.html`. Stop the server with Ctrl+C when finished.

## Reading the report

Start with `reports/<session>/master/index.html`:

- **Business runs:** report-producing business validation runs in the session; each can cover many files.
- **Validations:** individual recorded checks, including ingestion and summary checks, rather than files or unique claims.
- **Pass:** a check met its expected condition.
- **Fail:** a check found a discrepancy.
- **Blocked:** a prerequisite, source input or reference needed for a decision was unavailable.
- **N/A:** the check did not apply; this is not a pass.
- **Pytest runs:** software test sessions included in this report, separate from production validation. Zero means no pytest report was included.

Validations equal Pass + Fail + Blocked + N/A. Checks can involve overlapping files and records; these totals are not unique defective-record counts.

Open a stage, then its run. Search part of a file name/path or choose a file from the dropdown. The filter narrows file lists and full rule evidence. Reset restores all files. Stage-wide findings remain visible; filters do not change the full-run totals or conclusions.

Each recorded rule retains its business requirement, evaluation logic, expected and observed values, conclusion, recommended action and source evidence. Every file has a conclusion. Each stage and the overall report summarize acceptance, file counts, finding categories and actions. Unexecuted rules and stages without results are not accepted as passes.

## Run your own files

The manifest roles are `source`, `actual_output` and `expected_output`. Modes are `calculate` (known calculations/structural checks), `reconcile` (source versus actual) and `golden` (approved expected versus actual, with source checks).

Single-stage example:

```sh
python scripts/run_stage.py --stage final_action --run-date 2026-03-20 --mode reconcile --source 'data/user_inputs/final_action/source/*.json' --actual 'data/user_inputs/final_action/actual_output/*.json' --show-pass
```

For all stages, copy and edit `config/runs/all_5_stages_user_template.yaml`. Select a processing date, match source/output snapshots and supply required reference feeds. Empty folders cannot establish acceptance.

To import an extracted q61 directory:

```sh
python scripts/prepare_q61_production.py --source '/path/to/extracted/my-bucket-data'
```

This copies files without changing the source archive and gives verified extensionless Parquet inputs a `.parquet` suffix. Production data must remain excluded from Git.

## Tests

```sh
python -m pytest -q
python -m pytest -m final_action -v
python -m pytest -m split -v
python -m pytest -m stay -v
python -m pytest -m intermediate -v
python -m pytest -m final_medpar -v
```

Tests generate timestamped HTML evidence. The latest full-suite evidence at cleanup is `reports/20261011_023341/pytest/pytest_complete_suite/report.html`.

## Production status

The supplied production archive is not accepted. The current full run has 8,865 checks: 6,773 pass, 1,960 fail, 131 blocked and one N/A across four stages. Final MEDPAR has no identifiable production dataset in this archive.

| Stage | Files reviewed (source / actual) | Outcome and required action |
|---|---|---|
| Final Action | 15 / 65 | Schema/transaction-code failures, reconciliation mismatches and tied source ordering. Correct exports and obtain the approved replay/tie policy. |
| Split | 65 / 12 | Unsupported transaction codes, duplicate identities and indicator mismatches. Obtain CMS/CVM code mappings and correct output. |
| Stay | 12 / 83 | March Split inputs cannot validate May Stay outputs. Supply the matching May source extract. |
| Intermediate | 83 / 166 | Duplicate output identities prevent unique reconciliation. Supply unique exports or an approved replay contract. |
| Final MEDPAR | No production files supplied | Not run; provide production input/output and acceptance references. |

An explicitly selected distinct-payload Intermediate diagnostic reviews 83 source/output pairs. It contains 16,909 pass, 785 fail, 498 blocked and 1,569 N/A checks, including the failed final summary. These are overlapping check counts, not unique issue counts. Required corrections include:

- Recover missing birth dates: supplied DOBs are zero and ages are -1.
- Correct 83 base-facility CCNs exported as zero.
- Resolve alphabetic values in shared IDE/NDC/UPC data. Source copies match, but numeric NDC validity fails; entries are 11 characters, up to ten occurrences, without invented padding.
- Correct date windows, covered-care-end, 29 value-amount mismatches and four death-day disagreements using per-record evidence.
- Supply DOD/EDB, SSI and other authoritative reference feeds. Missing feeds cannot prove a confirmed no-match.
- Supply approved complete current copybooks, revenue/DRG mappings, CMS golden outputs and the production-scale performance environment. BayState scope/layout and unresolved business branches require owner decisions.

Independent field semantics use supplied requirements and supplementary [CMS CR14](https://www.cms.gov/files/document/medpar-cr14-rif-report.pdf) / [CMS CR18](https://www.cms.gov/files/document/medpar-cr18-rif-report.pdf). These do not certify the current complete byte layout.

The detailed gap evidence remains in `docs/medpar_gap_completion.json`, with `productionCertified: false`. The reviewed workbook remains under `outputs/medpar_gap_submission_20261011/`; it is an earlier review snapshot, not proof that all production gaps are closed. Original production data and the current diagnostic reports are preserved.

## Repository layout

| Path | Purpose |
|---|---|
| `README.md` | Single setup, demo, reporting and status guide |
| `run_commands.py` | Stage/run selection and report orchestration |
| `src/medpar_qa/` | Loaders, normalization, validation stages and reporting |
| `config/` | Aliases, schemas, rules, field contracts and manifests |
| `scripts/` | Stage runner, regression runner and production utilities |
| `tests/` | Unit, integration and regression tests |
| `sample_data/` | Synthetic source/actual/expected fixtures |
| `data/` | Demo/user inputs and ignored local production data |
| `docs/medpar_gap_completion.json` | Machine-readable gap evidence ledger |
| `outputs/` | Reviewed submission workbook |
| `reports/` | Ignored, locally generated current demo/test evidence |

Older guides, diagnostic drafts, sample reports and previous report sessions were archived outside this repository during demo cleanup. They remain recoverable; historical tracked files are also available in Git history. This cleanup does not alter business validation outcomes.
