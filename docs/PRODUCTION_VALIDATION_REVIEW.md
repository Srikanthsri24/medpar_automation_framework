# Production archive validation review — 11 October 2026

## Latest verified release — 11 October 2026

254 tests pass; all five synthetic stages pass (`reports/20261011_015646/master/index.html`). Production acceptance remains open.

Fixed incorrect raw DOB/Medicare-status/MRN comparisons; ICU/CCU types derived from accumulated charges; outpatient types 0–3; surgical types 0/1; blank no-organ default; optional date sentinel comparisons; absent-reference DOD handling; 11-character NDC width and first-ten source-order checks. Snapshot validation now blocks comparisons between March Split inputs and May Stay outputs. No supplied production file was changed.

Supplementary primary definitions: [CMS CR14](https://www.cms.gov/files/document/medpar-cr14-rif-report.pdf) and [CMS CR18](https://www.cms.gov/files/document/medpar-cr18-rif-report.pdf). These establish the field semantics above, not certification of the current full byte layout.

Latest Intermediate distinct-payload diagnostic: **16,909 PASS, 785 FAIL, 498 BLOCKED, 1,569 N/A** checks across 83 source/output pairs. These are check counts, including one failed final summary, not unique defective-record counts. Original archive still contains 166 output files with 83 repeated payloads. All copied NDC lists agree with source; the supplied 11-character values contain alphabetic characters and still fail numeric validity. Missing source DOBs remain zero while output ages are -1; 83 base-facility CCNs are 0. Date-window, covered-care-end, 29 value-amount and four death-day disagreements remain.

Full archive report: `reports/20261011_014942/master/index.html`. Final Action has 1,250 failed and 130 blocked checks; Split has 624 failed checks; Stay has one snapshot block and a failed summary; Intermediate has 85 failed checks because duplicate outputs prevent unique reconciliation. Final MEDPAR has no identifiable production files. See `PRODUCTION_REMEDIATION_HANDOFF.md` for exact required corrections and inputs.


## Earlier follow-up validation

Additional framework defects have been fixed: nested revenue/condition/span identifier objects; production `totalAmount` charges; repeated service charges and NDC values; blank/zero optional date sentinels while required zero dates still fail; zero birth dates block age calculation; source-based revenue/condition derivations; verified gender/state/county aliases. Missing required outputs no longer trigger structural checks against source records. Original production inputs remain unchanged.

`run_commands.py` now pairs preceding-stage sources with actual outputs. Full suite: **242 passed**. The five-stage synthetic demonstration passes. Production acceptance remains open.

Latest paired run: `reports/20261011_013602/master/index.html`.

| Stage | PASS checks | FAIL checks | BLOCKED checks | N/A checks |
| --- | ---: | ---: | ---: | ---: |
| Final Action | 164 | 1,250 | 130 | 0 |
| Split | 5,913 | 624 | 0 | 1 |
| Stay | 10,015 | 198 | 0 | 16,836 |
| Intermediate | 503 | 85 | 0 | 0 |
| Final MEDPAR | Not run | Not run | Not run | Not run |

Stay source and output are different snapshots: Split `yearQuarter=2025Q3/rundate=20260320`, Stay `yearQuarter=2026Q2/rundate=20260514`. There are 196 distinct source Stay identities and 83 output identities with zero full-identity overlap; 41 beneficiary/provider pairs overlap. This is a cross-snapshot diagnostic, not a valid merge acceptance baseline. Matching May Split inputs are missing.

Final Action has 265 tied ordering buckets whose complete input payloads are identical copies, affecting 130 blocked claim groups. The framework reports the ambiguity; an approved replay/deduplication policy or a clean source extraction is needed before changing decision counts. Split additionally reports duplicate actual identities and 263 year-back indicator mismatches.

Intermediate full-archive validation reports duplicate actual identities and 83 unavailable unique matches. A separate, explicitly selected distinct-payload diagnostic compares all 83 Stay sources to 83 representative outputs. It reports **16,245 PASS, 1,694 FAIL, 415 BLOCKED and 1,490 N/A** checks, versus the initial 3,062 failures. Remaining findings include missing DOB/invalid age, date windows, indicator/CCN/span/value mismatches and output mappings. Templates currently configure NDC width 10 while this archive carries repeated 11-character entries; approved MPRPARL/layout evidence is needed to settle width rather than infer it from observed output. Missing DOD/SSI/reference operands and the no-organ default still block checks.

Reproduce the aggregate-only diagnostic with:

```sh
.venv/bin/python scripts/review_production_intermediate.py --distinct-payloads
```

The flag explicitly selects one copy per identical payload excluding filename metadata, and preserves every original file. Omitting the flag validates the full duplicate archive. `reports/production_intermediate_review/summary.json` contains only aggregate evidence; no golden files were supplied.

See `TEAM_DEMO_GUIDE.md` for the demonstration and team handoff. The following section preserves the initial review for comparison.

## Initial validation (historical)

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
