# Field Coverage Matrix — August 2026

## Calculated and directly validated

| Field | Stage | Coverage |
|---|---|---|
| MEDPAR-TOT-ACC-CHRG-0430 | Intermediate | Each charge rounded before sum; exact Decimal comparison |
| MEDPAR-BILL-TOT-PERDIEM-0381 | Intermediate | Per-diem rounded before multiplication |
| MEDPAR-INTENSIVE-CARE-IND-0481 | Intermediate | Revenue-code derivation includes 0200 and 0201 |
| medparAdmDay0090 | Intermediate | Admission-date day code |
| MEDPAR-ORGAN-IND-0487 | Intermediate | Configurable revenue-code derivation; code list requires sign-off |
| Condition-code switches 0800/0810/0820/0830/1560/1570/1580 | Intermediate | Configured Y/N derivation |
| MEDPAR procedure groups | Intermediate | Counts/alignment/window; maximum 25 |
| Span Code/date groups | Stay | Latest duplicate wins, unique values retained, maximum 10 |
| MEDPAR-TOT-CHRG-0400 | Stay/Intermediate/Final | Decimal/source-to-target/golden comparison |
| MEDPAR-DRG-PRICE-0380 | Stay/Intermediate/Final | Latest/direct-move/golden comparison |
| MEDPAR-SQSTRTN-RDCTN-AMT-1130 | Stay/Intermediate/Final | Value Code 73 and golden comparison |
| MEDPAR-DTE-CR-ENDED-0220 | Stay/Intermediate/Final | Date/latest-record/golden comparison |
| DRG code | Intermediate/Final | Format/direct-move/golden comparison; proprietary calculation formula not supplied |

## Registered aliases and available for schema/golden comparison

- Numbered Final MEDPAR BIC, Q1 reduction, SSI, DOD/DOD indicator, provider and warning fields.
- Hospital-at-Home dates, two-midnight indicator, E-diagnosis/version/POA fields.
- CMS payment-policy fields: HAC, HRR, VBP, bundled M1, care model, low-volume, IDE and cancellation.
- Beneficiary demographic and administrative fields.
- Revenue-center code, NDC/UPC, units, total/noncovered charges, patient add-on, RP indicator and model reimbursement.
- CLM diagnosis/POA/value/occurrence group containers.
- Lower-confidence legacy names such as uniqueTrackingNumber and internalControlNumberOrigin.

A registered alias means the framework can find and compare the field. It does not claim that a proprietary derivation was implemented unless the field is listed in the calculated section.

## Open specification items

- Exact 3050-to-3000 conversion offsets.
- HICN merge precedence.
- Exact Legacy organ-acquisition code list.
- Emergency-use switch source code.
- Rule 6 Action Code versus transactionCode precedence sign-off.
