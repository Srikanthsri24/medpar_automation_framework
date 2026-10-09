# Final Action V3 gap cross-verification — 2026-10-09

Scope: V3 pp. 8, 15–21, revised 2026-05-21 decision tree, and user-supplied FA-01 through FA-11 register.

**Important:** This is a validation framework. It does not itself produce production-netted claim files. Its KEEP/DROP decisions must be reconciled against authoritative golden outputs before certification.

| Gap | Status after this update | Evidence / limitation |
|---|---|---|
| FA-01 | PARTIAL — policy blocked | Configurable covered-days vs LOS bypass with warning 04=2 and separate JSON bypass artifact; default OFF because pp15/35 conflict. Requires approved direction and LOS basis. |
| FA-02 | IMPLEMENTED for QA | `final_action_error_file.json` exports FAIL/BLOCKED validations. This is an exception audit, not the COBOL production error-file format. |
| FA-03 | IMPLEMENTED with assumption | Detects multiple service years per physical input file, using stay-through year. Confirm scope of 'input data' and service-year definition. |
| FA-04 | PARTIAL | Enforces >900 continuation and >875 hold when input records carry `record_table_type`. Raw COBOL continuation/hold table parsing not available. |
| FA-05 | BLOCKED BUSINESS CONFLICT | Current code follows revised diagram (all ICNs same drop; else newest non-QC0 with ICN different from QC0). V3 p20 says opposite; require signed golden cases. |
| FA-06 | IMPLEMENTED / NEED GOLDEN | Rule6 enabled by default and in runner/manifests; uses QC0 action code 4/6 only, missing matching-ICN action blocks. |
| FA-07 | IMPLEMENTED | Default accepts only QC0/1/3/5; unsupported QC2 fails. |
| FA-08 | PARTIAL | Rules 7/8/9 use `keep_unique_non_qc0_icns`; whether all unique or newest-per-ICN needs approved expected output. |
| FA-09 | PARTIAL | IP/SNF group key partitions claims; stage emits separate IP/SNF statistics. No separate IP/SNF edit/production netting modules. |
| FA-10 | IMPLEMENTED for QA | `FA-NETTING-STATISTICS` plus JSON artifact; financial totals and external golden stats not yet reconciled. |
| FA-11 | OUT OF SCOPE | Outpatient Rules 12–16 intentionally omitted. |

Additional discovered issues:
- `run_stage.py` had `rule6_enabled=False` even after earlier changes; fixed.
- YAML still incorrectly documented QC2, transaction/action fallback, and unsafe default KEEP; corrected.
- A passing pytest suite does **not** prove all decision-tree branches and V3 legacy interfaces are complete.
- Reconciliation, error handling and table limits require real production fixtures to establish complete coverage.
- **FA-01/05/08 remain business-signoff dependencies. Do not deploy to production as fully certified.**

Outputs on `python run_commands.py`: under `reports/<timestamp>/final_action/<command>/`:
- `report.html` and other existing detailed reports
- `final_action_error_file.json`
- `final_action_bypass_file.json`
- `final_action_statistics.json`

Suggested next evidence: MPRNETVL and MPRSEQVL source, 3-record Rule5 golden cases, 7–10A ICN comparison examples, covered-days bypass approved direction, continuation/hold field layout, service-year file definition, production error-file layout.
