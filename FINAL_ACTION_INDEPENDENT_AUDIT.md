# Final Action V3 — Independent cross-verification

Date: 2026-10-09
Sources: *Medpar functionality notes V3* pp. 8, 15–21; revised decision-tree image dated 05/21/2026; supplied FA-01–FA-11 gap register; inspected Python code, YAML, CLI/runner and tests.

## Release verdict: NOT APPROVED for full V3 compliance

119 automated tests pass locally. This establishes only the current suite's behavior; it does **not** establish production parity with MPRNETVL/MPRSEQVL or approved KEEP/DROP outputs. No production COBOL, golden claims, reference statistics, or signed decisions for FA-01/05/08 were supplied.

## Gap-by-gap status

| ID | Status | Evidence / release action |
|---|---|---|
| FA-01 | BLOCKED | Bypass code is configurable but disabled by default; source p15 says LOS > covered, p8/35 say covered > LOS. Also clarify whether LOS is inclusive, admission/discharge treatment, and whether warning indicator must be set in original claim output. |
| FA-02 | PARTIAL | JSON error audit is emitted for FAIL/BLOCKED, but not a validated legacy-format error file; verify record payload, group key, severity, retention and data privacy. |
| FA-03 | PARTIAL | Multiple service years checked per source file using stay-through year. V3 does not define file scope or service-year basis precisely; obtain golden example. |
| FA-04 | PARTIAL | 900/875 limits checked only when records carry `record_table_type`. Actual continuation/hold COBOL table mapping unverified. |
| FA-05 | BLOCKED | Revised tree follows all-same ICNs DROP; otherwise keep latest non-QC0 not matching QC0 ICN. Contradicts V3 p20; no production signoff. |
| FA-06 | PARTIAL | Enabled in defaults and checked runner manifests; matching-ICN QC0 action 4/6 drops both, missing action blocks. Needs input alias audit and actual golden pairs. |
| FA-07 | IMPLEMENTED (code) | Default QC set is 0/1/3/5; explicit manifests reviewed for Rule 6. User-story QC2 conflict requires governance confirmation if still active. |
| FA-08 | BLOCKED | Current helper keeps non-QC0 only if its ICN occurs exactly once across entire group. 'Newest per distinct ICN' alternative remains undecided; impacts 7/8/9/10A. |
| FA-09 | PARTIAL | Claim-type derived from transaction code and used in grouping and summary; distinct IP/SNF source validation/netting and expected output reconciliation unproven. |
| FA-10 | PARTIAL | Decision counts by type generated; financial/amount totals and reconciled input=keep+drop+exception golden stats not established. |
| FA-11 | EXCLUDED CORRECTLY | Outpatient rules 12–16 are out of scope. |

## Additional issues discovered in this independent pass

1. **Rule 2 unsafe fallthrough — FIXED in this audit:** If group pattern is 5-0-3/5-0-1 but accretion date is missing or QC5 is not latest by accretion, previous routing fell through to Rule 10B and could KEEP a claim. It now BLOCKS with `FA-RULE-02-PRECONDITION`. Added two regression tests.
2. **Stale reporting rule catalog — FIXED:** `FA-DEFAULT` description previously still said KEEP newest nonzero QC, contradicting actual BLOCKED behavior. Corrected catalog text.
3. **Service-year checking — OPEN:** early return on multiple service years skips other validation and statistics; acceptable fail-fast only if reports explicitly communicate the skipped checks.
4. **Error-file completeness — OPEN:** audit JSON includes rule results rather than full original record images; cannot be called a legacy error-file replacement.
5. **Table-limit inputs — OPEN:** no verified source mapping for continuation/hold record types, so the check may never fire for raw claim feeds.
6. **Record ordering — OPEN:** ties are blocked when enabled, but source sequence, process date and accretion-date normalization need golden validation; Rule 2 requires verified ordering.
7. **Scope of claim grouping — OPEN:** Python groups by type + HICN + provider + from/thru; verify against COBOL SAME BENE, PROVDR, FROM/THRU and sort/merge behavior, especially across source files.
8. **Reporting vs business processing — OPEN:** framework validates claims and compares actual outputs when provided; it is not a certified production netting/patch replacement.
9. **Stage reconciliation semantics — OPEN:** blocked/failed records are counted as accounted for in the stage reconciliation rule, which may PASS even when overall stage fails. Require distinct decided/blocked/failed counts and fail release on any unresolved high-severity outcome.
10. **Test evidence — OPEN:** suite is not a complete decision-tree truth table with golden expected ICNs. Build table covering QC patterns, all group sizes, permutations, equal/unequal ICNs, ties, missing dates/actions, and both claim types.

## Mandatory release gate

- Obtain approved written responses to FA-01, FA-05, FA-08 and update policy/expected outcomes.
- Obtain representative deidentified golden inputs and MPRNETVL/MPRSEQVL outputs, including error/bypass cases.
- Verify every decision-tree branch and negative path with explicit expected retained record IDs.
- Verify source schema, aliases, file grouping, record ordering and claim-type boundaries.
- Verify error/bypass file formats, all reconciliation counts and charge/amount balancing.
- Require zero unexplained FAIL/BLOCKED decisions on production-like acceptance fixtures.
- Execute full `python run_commands.py`, archive reports and compare to signed golden results.

## Test result

`python -m pytest -q`: **119 passed** (2026-10-09). No claim of complete V3 compliance.
