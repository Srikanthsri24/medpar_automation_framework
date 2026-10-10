# Production archive validation review — 11 October 2026

The exact enabled STAGE_RUNS entries in run_commands.py were executed against the local q61 archive. Final MEDPAR is disabled because no identifiable Final MEDPAR dataset is available. These are calculation/structural runs: actual and expected lists are empty. They do not certify source-to-output equivalence.

After correcting runner settings and identity adapters, the run completed with failures. Reports are local, ignored by Git, and may contain sensitive record-level evidence.

| Stage | PASS checks | FAIL checks | BLOCKED checks | NOT_APPLICABLE checks |
| --- | ---: | ---: | ---: | ---: |
| Final Action | 34 | 1,249 | 130 | 1 |
| Split | 5,888 | 360 | 0 | 264 |
| Stay | 1,415 | 0 | 0 | 9,877 |
| Intermediate | 334 | 2 | 0 | 0 |
| Final MEDPAR | Not run | Not run | Not run | Not run |

Counts are validation checks, not distinct records. Each failing stage includes one final-summary FAIL.

## Findings

- Final Action: 1,248 schema failures consist of 624 unsupported transaction-code checks and 624 unsupported query-code checks. An additional 130 ordering groups are blocked. Codes outside the approved rules remain exceptions; the allowlists have not been widened to make the archive pass.
- Split: 359 records have unsupported transaction codes (C:150, H:31, 6:108, 5:70).
- Stay: the selected JSON folder contains merged Stay outputs, not the preceding bill inputs. A structural pass plus 9,877 N/A checks does not validate the join, field selection or accumulation rules.
- Intermediate: the selected folder contains outputs. Its 166 files form 83 pairs with identical payloads apart from filename metadata. Duplicate identity validation fails, so that input-only run does not evaluate the output calculations.
- No CMS golden outputs or Final MEDPAR records were present in the configured runs.

## Additional source-to-output investigation

Compared all 83 Stay JSON records with one representative from each identical Intermediate output pair. Original files were neither edited nor deleted. The duplicate issue remains separately reported. Filename lineage, account+EQ-BIC, CCN and admission match all 166 original Intermediate files to their Stay source.

This comparison produced 15,205 PASS, 3,062 FAIL, 332 BLOCKED and 1,245 NOT_APPLICABLE checks, including one final-summary failure. It is a diagnostic result, not an accepted production baseline. Failures require adapter/rule/data triage before attributing them to upstream processing: for example service charges arrive as an array while one existing scalar precision check expects a number, and zero date sentinels encounter strict date parsing. Other checks report source-to-target, span, age, monetary and indicator mismatches. Missing DOD/SSI references and an unapproved no-organ default block calculations. No golden expectations were fabricated.

## Framework corrections verified

- Stage runner retains SNF records and uses Final classifications S/L/N consistently with the documented contracts.
- A short claimCanNchEquatable EQ-BIC is joined to the nine-character claim account instead of collapsing beneficiaries sharing the same BIC. A short EQ-BIC without the required account does not become a complete identifier.
- Intermediate identity uses the six-character MEDPAR provider 0130 before the extended provider 1660 field.
- Synthetic fixture identity updated to a full identifier; regression tests cover identity collisions, explicit HICN precedence and provider precedence.

Full automated suite: **230 passed**. This is synthetic framework regression evidence, separate from the failing production diagnostics.

## Local evidence

- Configured run: reports/20261011_012408/master/index.html
- Full tests: reports/20261011_012448/pytest/pytest_complete_suite/report.html
- Additional Intermediate comparison: reports/production_reconciliation_review/summary.json and intermediate.json

## Remaining submission work

1. Triage production schema/order exceptions and Intermediate adapter/calculation mismatches; reconcile each stage against correctly paired inputs and outputs, including retained/dropped control totals.
2. Obtain complete approved copybooks/layouts, DRG/revenue/reference mappings and CMS golden outputs; verify byte reconstruction and external reference calculations.
3. Resolve open warning/default/routing/HICN merge requirements documented in MEDPAR_GAP_SUBMISSION.md.
4. Validate Final MEDPAR with actual files and establish production-scale performance evidence. Confirm BayState scope before claiming its completion.

The existing Excel review records 25 implemented, 7 existing, 24 partial, 14 needs-input and 4 not-required functionality items. Production validation above adds acceptance work; it does not convert partial or blocked items into completed work.
