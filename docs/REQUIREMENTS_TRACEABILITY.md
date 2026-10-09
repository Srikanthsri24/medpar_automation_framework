# Requirements Traceability — Starter Matrix

This file is the controlled location for mapping each approved business requirement to automation.

| Requirement ID | Stage | Rule/Field | Validation | Status |
|---|---|---|---|---|
| FA-001 | Final Action | Record type | Derive I for transaction 1/2/3 and S for 0/4 | Started |
| FA-101 | Final Action | Rule 1 | Single-record QC decision | Implemented; QC2 remains configurable |
| FA-102 | Final Action | Rule 2 | Newest-first 5-0-3 or 5-0-1; keep QC5 | Implemented |
| FA-103 | Final Action | Rule 3 | Same QC; newest record per unique ICN | Implemented |
| FA-105 | Final Action | Rule 5 | ICN comparison and QC0 handling | Pending approved prerequisites |
| FA-106 | Final Action | Rule 6 | ICN + action-code decision matrix | BLOCKED: exact matrix required |
| FA-107 | Final Action | Rule 7 | No QC5; QC0 >= QC1+QC3 | Pending |
| FA-108 | Final Action | Rule 8 | No QC5; newest QC0 | Pending |
| FA-109 | Final Action | Rule 9 | No QC5; newest non-QC0 | Pending |
| FA-110A | Final Action | Rule 10A | QC5 exists; QC0 dominance | Pending |
| FA-110B | Final Action | Rule 10B | Fallback first non-QC0 | Pending conflict resolution |
| SP-001 | Split | Four-year window | Configurable eligibility window | Foundation implemented |
| SP-002 | Split | Split indicator | Yx0109 / Yx1012 / Y99999 | Implemented |
| ST-CC-001 | Stay | Condition Codes | Duplicate code takes latest claim value | Implemented helper/tests |
| ST-OC-001 | Stay | Occurrence Codes | Duplicate code takes latest claim value | Implemented helper/tests |
| ST-0400 | Stay | MEDPAR-TOT-CHRG-0400 | Decimal, 3-digit calculation precision | Foundation implemented |
| ST-0380 | Stay | MEDPAR-DRG-PRICE-0380 | Decimal, 3-digit calculation precision | Foundation implemented |
| ST-1130 | Stay | MEDPAR-SQSTRTN-RDCTN-AMT-1130 | Decimal, 3-digit calculation precision | Foundation implemented |
| ST-0220 | Stay | MEDPAR-DTE-CR-ENDED-0220 | Date source/precedence/format | BLOCKED: mapping required |
| INT-0410 | Intermediate | MEDPAR-COV-CHRG-0410 | Decimal precision | Implemented validator/tests |
| INT-0470 | Intermediate | MEDPAR-SERVICE-CHARGES-0470 | Decimal precision | Implemented validator/tests |
| INT-0440 | Intermediate | MEDPAR-TOT-DPT-CHRG-0440 | Decimal precision | Implemented validator/tests |
| INT-PROC | Intermediate | Procedure fields 0500/0511/0512/0513/0514 | Counts, versions, dates, alignment | Implemented validator/tests |
| INT-DIAG | Intermediate | Diagnosis/POA fields | Counts and positional alignment | Implemented validator/tests |
| INT-WIN | Intermediate | Five-year January window | Jan 1 of run_year-4 through run date | Implemented utility/tests |
| FM-3000 | Final MEDPAR | 3000-byte output | Real encoded byte length | Implemented validator; field layout pending |

## Required evidence for each regression failure

- Run ID
- Stage
- Rule ID
- Field name
- Group key or record ID
- Source file and source row
- Expected value
- Actual value
- Reason
- PASS/FAIL/BLOCKED status
