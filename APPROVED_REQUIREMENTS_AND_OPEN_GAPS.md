# MEDPAR V3 approved decisions and open implementation gaps

Reviewed: V3 36-page functionality document, user-supplied V3-vs-repo workbook, and 2026-10-09 business clarifications.

## Approved Final Action rules
- FA-01: covered days > length of stay -> bypass, warning 04=2. Default configured as `covered_gt_los`.
- FA-05: May 21 2026 tree supersedes conflicting V3 page 20. All ICNs same -> DROP all. Otherwise newest non-QC0 with ICN different from QC0 -> KEEP.
- FA-08: Rules 7–9/10A keep all non-QC0 with unique ICNs, not newest per ICN.
- STAGE_RUNS: sole stage input configuration; redundant INPUT_* block removed.

## Not certified
The workbook also documents gaps in Sort/Feeds, Split, Stay, Intermediate, Final MEDPAR, BayState and integration. These are not resolved by the above configuration changes. V3 pp10–14 and 23–35 require full trailer field mappings, DRG/DOD/SSI feeds, fixed-width record specifications, calculations and golden expected outputs. Existing code is a QA validation framework; it does not yet replace all COBOL production output-generation processes. Do not claim complete V3 parity or merge as production certified.
