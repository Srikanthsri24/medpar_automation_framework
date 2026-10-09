# August 2026 Discrepancy, Missing-Field, and LD-3137 Update

## Scope reviewed

This update was based on the supplied Old-vs-New discrepancy report and the supplied Final Action/Stay/Intermediate/Final MEDPAR requirement notes. It separates three levels of coverage:

- **Implemented derivation:** the source rule was supplied and is calculated by Python.
- **Registered and compared:** aliases/schema/golden comparison exist, but a proprietary formula was not supplied.
- **Open/blocked:** implementing behavior would require guessing.

## Implemented code corrections

| Area | Rule implemented | Validation ID |
|---|---|---|
| Intermediate | Round every accommodation charge to 3 decimals before summing MEDPAR-TOT-ACC-CHRG-0430 | `INT-ACCOMMODATION-TOTAL` |
| Intermediate | Round passThruPerDiem before multiplying by utilizationDays for MEDPAR-BILL-TOT-PERDIEM-0381 | `INT-BILL-TOT-PERDIEM-ROUNDING` |
| Intermediate | Include revenue codes 0200 and 0201 in intensive-care search | `INT-INTENSIVE-CARE-IND-0481` |
| Intermediate | Validate organ-acquisition indicator against configurable Legacy code list | `INT-ORGAN-IND-0487` |
| Intermediate | Calculate medparAdmDay0090 from admissionDate | `INT-ADMISSION-DAY-0090` |
| Intermediate | Verify DRG code and selected fields move from source/Stay to actual Intermediate | `INT-SOURCE-TO-TARGET` |
| Intermediate | Validate revenue-center line subfields individually | `INT-REVENUE-LINE-ITEMS` |
| Intermediate | Enforce maximum 25 procedure code/version/date groups | `INT-PROC-MAX-25` |
| Stay | Consolidate unique Span Code/date groups from all claims, maximum 10 | `ST-SPAN-CODE-LIMIT` |
| Final Action | Implement current Rule 6 QC0/QC5 decision | `FA-RULE-06` |
| Final Action | Accept QC2 in Rule 1 under current non-zero approved list | `FA-RULE-01` |
| Four affected stages | Exclude admissionDate from sort/group configuration | `FA/SP/ST/FM-SORT-ORDER-LD3137` |
| Final MEDPAR | Include newly requested Intermediate/final fields in selected-field golden comparison | `FM-REGRESSION-*` |

## LD-3137 behavior

`admissionDate` is not part of the configured sort order for Final Action, Split, Stay, or Final MEDPAR. Stay and Final MEDPAR identities use HICN, provider, and split-year indicator, so differing admission dates do not create separate records solely for that reason. The Split process may still use admissionDate as the reference date for deriving the split-year indicator; LD-3137 only requested its removal from sorting/grouping.

## Missing-field registry coverage

`config/field_aliases.yaml` now contains the numbered Final MEDPAR fields, HAH/2-midnight fields, E-diagnosis fields, CMS payment-policy fields, beneficiary/administrative fields, warning indicators, revenue-center subfields, and lower-confidence legacy names identified by the report.

Aliases were also added for source spelling differences and known ticket typos, including:

- `MEDPAR-TOT-ACC-CHRG-043` and `...-0430`;
- `MEDPAR-SQSTRTN-RDCTN-AMT-113` and `...-1130`;
- `MEDPAR-INTERSIVE-CARE-IND-0481` and `MEDPAR-INTENSIVE-CARE-IND-0481`.

## Reporting behavior

A golden comparison where both expected and actual values are absent is now `NOT_APPLICABLE`, not `PASS`. The report says that the field was not tested because no approved expected value was supplied. This prevents registry-only fields from appearing falsely validated.

## Items intentionally not guessed

The official 3050-to-3000 byte conversion map, HICN merge precedence, exact organ revenue-code list, emergency-use source mapping, and several proprietary historical derivations remain listed in `OPEN_BUSINESS_DECISIONS.md`.
