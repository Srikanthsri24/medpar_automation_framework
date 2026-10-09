# MEDPAR V3 — Demo package (document-backed)

## Run on Windows PowerShell

```powershell
cd medpar_automation_framework
python -m pip install -e .
python -m pytest -q
python -m medpar_qa.demo_pipeline --input data/demo_v3/demo_claims.json --output reports/demo_v3 --year 2024
start reports/demo_v3/index.html
```

The ZIP already contains a successful example at `reports/demo_v3/`.

## Show the audience

1. `reports/demo_v3/index.html` — five-stage counts and evidence links.
2. `reports/demo_v3/final_action/audit.json` — approved rule-router decisions and exceptions.
3. `reports/demo_v3/split/output.json` — four-year routing and sample flag.
4. `reports/demo_v3/stay/output.json` — multi-bill H2 stay (two bills become one; last-bill diagnosis).
5. `reports/demo_v3/intermediate/output.json` — demonstrable LOS and Julian date conversion.
6. `reports/demo_v3/final_medpar/output.json` — inpatient discharge filter and SNF retention.
7. `tests/integration/test_demo_pipeline.py` — five integration tests, including boundary cases.

## Important distinctions

- The existing `run_commands.py` retains `STAGE_RUNS` as the stage-wise configuration; this demo uses a **separate, explicit** integration command and does not change existing STAGE_RUNS behavior.
- This is a **real five-stage JSON processing chain**, but **not** a full legacy MEDPAR production engine.
- The 36-page V3 document refers to unavailable COBOL for the 54 Stay fields and 400-line mapping; exact fixed-width copybooks, SSI, DRG and payment formulas are not supplied. We do not invent these values.
- `covered_days` and `total_charges` summation in this demo is illustrative only; production mapping must be approved field-by-field.
- This sample uses fabricated identifiers; no real patient data.
- `run_commands.py` is the existing stage QA runner, not a substitute for this executable chain.

## Documentation mapping

- V3 p20–21: Final Action rules 1–10B, with approved later clarifications applied by existing processor.
- V3 p22: Split uses SNF admission date, inpatient last-bill through date, 4-year window and 75-bill check.
- V3 p11 and p23: Stay combines by HICN/provider/admission; last-bill diagnoses and procedures; first-to-last unique trailers.
- V3 p12–14: Intermediate LOS and YYYYDDD conversion demonstrated; missing external derivations explicitly marked.
- V3 p16 and p26+: Final MEDPAR inpatient discharge eligibility; SNF without discharge accepted.
