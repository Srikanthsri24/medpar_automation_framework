# MEDPAR V3 implementation status — not production certified

## Implemented and regression tested in this revision
- WP-04: canonical and alias field matching ignores case and nonalphanumeric separators; ambiguity returns missing rather than guessing.
- WP-07: YYYYDDD and YYDDD Julian input dates, with year rollover rejection.
- WP-13: three V3 spelling aliases.
- WP-05: Parquet list/struct conversion code and fixture test; test requires optional pyarrow dependency and is skipped when absent.
- Prior approved FA-01, FA-05, FA-08 and STAGE_RUNS-only runner changes retained.

## Unresolved — do not represent as completed
- WP-01 end-to-end stage chaining: existing processors validate and compare records; they do not all generate the next stage's production records.
- WP-02 fixed-width layout: MPRRECL and UTLIPSNL copybooks are not provided. Byte offsets, 32,004/32,007/32,010/3,050/3,000 contracts cannot be certified from field names alone.
- WP-03 full 200-field derivation and golden coverage: requires authoritative per-field mapping, not merely adding strings to selected_fields.
- WP-06 external DOD/HISKEW, SSI, 3M DRG, outlier and IDR feeds: source formats and reference values absent.
- WP-08 exhaustive FA decision-tree pattern matrix: incomplete.
- WP-09 realistic 600–700M-claim load/performance run: not performed.
- WP-10 stage-by-stage balancing and per-file counts: not complete.
- WP-11 rule6 manifests were previously set true; full manifest inventory and regression still required.
- WP-12 LD-3137 intentional differences: requires owner-signed reference golden files.
- WP-14 outpatient rules 12–16 excluded by V3.

## Conflicts requiring decisions or authoritative COBOL
- CF-01 and CF-02: resolved by business responses (FA-05 and FA-01).
- CF-03: warning 0640 approved deletion per V3; do not reintroduce.
- CF-04 stay key LD-3137 vs notes: business confirmation needed.
- CF-05 diagnosis/procedure last bill vs combined: business confirmation needed.
- CF-06 3 vs 6 header bytes: copybook/owner decision needed.
- CF-07 special unit/outlier LD-394: COBOL needed.
- CF-08 warning 10 duplicate code descriptions: business clarification needed.
- CF-09 value-code amounts missing derivations: COBOL/mapping needed.
- CF-10 revenue totals 0890–1120 missing 40+ derivations: COBOL needed.

## Scope of remaining functional work
SRT-01..06, FA-02..10, SPL-01..09, STY-01..11, INT-01..28, FIN-01..07, BAY-01..02 require individual verification against the gap register. No blanket completion assertion is supported by current tests. Existing validation test pass rate is not proof of production output parity.
