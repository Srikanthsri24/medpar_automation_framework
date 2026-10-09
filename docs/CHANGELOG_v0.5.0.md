# Changelog v0.5.0

## Business logic

- Implemented accommodation-charge round-before-sum logic.
- Implemented per-diem round-before-multiply logic.
- Added intensive-care codes 0200 and 0201.
- Added configurable organ-acquisition indicator derivation.
- Added admission-day derivation.
- Implemented the supplied Final Action Rule 6 logic.
- Updated Final Action Rule 1 to accept QC2.
- Added LD-3137 sort and grouping evidence for four stages.
- Added procedure maximum 25 and Stay Span Code maximum 10.
- Expanded direct-move and final selected-field checks.

## Field coverage

- Expanded `config/field_aliases.yaml` from generic buckets to include the missing numbered, policy, demographic, warning, diagnosis and revenue-line names identified in the discrepancy report.
- Added known typo aliases for 043/0430, 113/1130 and INTERSIVE/INTENSIVE.

## Reporting

- Added high-detail metadata for every new rule.
- Golden comparisons where expected and actual are both blank now return `NOT_APPLICABLE`, preventing false PASS results.
- LD-3137 reports show configured identity fields, group counts and groups containing more than one admission date.

## Tests

- Added 19 discrepancy/LD-3137 regression tests.
- Final verification: 104 passed, 0 failed.
