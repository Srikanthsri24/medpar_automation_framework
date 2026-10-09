# MEDPAR V3 all-stage status — not production certified

This package is a **partial gap-remediation build**, not an assertion that all 74 V3 functionality gaps have been implemented.

## New changes in this build
- SPL-03: Split transaction codes outside 0–4 produce explicit FAIL instead of being processed as ordinary claims.
- SPL-04/05: Split stay-group bill count is checked using HICN + provider + admission date; groups above 75 produce FAIL. Exact legacy grouping and overflow-file behavior still need golden evidence.
- Previous Final Action and one-path runner changes are preserved.

## Open by stage
- Sort/feed (SRT-01 to SRT-06): legacy DOD preparation, EQ-BIC, historical merge, date edits, warning header not implemented in full.
- Final Action (FA-01 to FA-11): FA-01, FA-05, FA-08 require business decisions; other legacy output parity and financial balancing remain unverified.
- Split (SPL-01 to SPL-09): SPL-03/05 validation added, but routing/output-file creation, balancing, sampling, audit trail, and legacy bypass parity remain open.
- Stay (STY-01 to STY-11): trailer groups, warning flags, revenue overflow, complete 54-field accumulation, 5 output files, header layout and golden parity remain open.
- Intermediate (INT-01 to INT-28): many derivations and edit tables remain missing; full 3050-byte layout and financial formulas require official specifications/lookup tables.
- Final MEDPAR (FIN-01 to FIN-07): output routing, 3050->3000 transform, multi-input merge, inclusion rules, BayState feed remain open.
- BayState (BAY-01 to BAY-02): DB2 SSI recalculation and output fields remain unimplemented.

**Do not merge or deploy as complete V3.** Missing source algorithms, file layouts, DB2 tables, golden records and approved business decisions cannot safely be inferred. A passing pytest suite is not sufficient to close these gaps.
