# MEDPAR QA Automation — Complete Five-Stage Validation Scope

This project validates JSON and Parquet files for all five MEDPAR stages. It supports one file, many files, stage-only runs, source-versus-actual reconciliation, approved golden comparisons, and a complete five-stage manifest.

## Validation statuses

- `PASS`: the applicable requirement matched.
- `FAIL`: the actual data violated an applicable requirement.
- `NOT_APPLICABLE`: the optional field or comparison was not supplied.
- `BLOCKED`: the rule is known but an approved business decision is still unavailable.

A stage fails when any check is `FAIL` or `BLOCKED`.

## 1. Final Action

Implemented validations:

- JSON/Parquet loading and source lineage.
- Required identity, provider, stay dates, transaction code, QC, ICN, and processing date.
- Rec-Type derivation from transaction code.
- Grouping by Rec-Type, HICN, provider, stay-from and stay-thru dates.
- Newest-first ordering using weekly-processing date, accrete date, and source sequence.
- Ambiguous ordering is blocked rather than guessed.
- All-QC0 handling.
- Rules 1, 2, 3, 5, 7, 8, 9, 10A, 10B, and Default Rule.
- Rule-level KEEP/DROP evidence.
- One decision per source record.
- Source count = KEEP + DROP reconciliation.
- Expected KEEP set versus actual Final Action output.
- Missing, unexpected, and duplicate actual-output records.

Known blocked item:

- Rule 6 is detected, but the approved ICN/Action-Code decision matrix is not available. The framework returns `BLOCKED` instead of guessing.

## 2. Four-Year Split

Implemented validations:

- Required claim CAN, HICN, provider, stay dates, and transaction code.
- Date parsing and `stayFromDate <= stayThruDate`.
- Configurable bypass for transaction codes 0 and 4.
- January-aligned four-year processing window.
- Admission-date fallback to stay-from date.
- January–September indicator `Y#0109`.
- October–December indicator `Y#1012`.
- Outside-window indicator `Y99999`.
- Inline or separate actual-output comparison.
- Duplicate, missing, and unexpected output identities.

## 3. Stay

Implemented validations:

- Required HICN, provider, stay-from and stay-thru identity/date fields.
- Admission-date format and stay-date order.
- Grouping by configured Stay identity.
- Condition, occurrence, span, value, and revenue collection structure.
- Latest-record precedence for duplicate Condition Codes.
- Latest-record precedence for duplicate Occurrence Codes.
- Latest-record precedence for duplicate Span Codes.
- Latest-record precedence for duplicate Value Codes.
- Unique older codes retained; duplicate selected objects retain source lineage.
- Condition Code 04 → `MEDPAR-INFOR-ENCTR-IND-SW-0800`.
- Condition Code 69 → `MEDPAR-MA-TEACH-IND-SW-0810`.
- Value Code 73 → `MEDPAR-SQSTRTN-RDCTN-AMT-1130`.
- Decimal conversion through `Decimal(str(value))`.
- Explicit three-decimal precision for selected Stay amount fields.
- Total charge reconciliation from eligible source fields.
- Latest-record checks for `MEDPAR-DRG-PRICE-0380` and `MEDPAR-DTE-CR-ENDED-0220` when derivable from supplied source records.
- Date format for `MEDPAR-DTE-CR-ENDED-0220`.
- SNF qualification from/thru date format and relationship.
- Bill-count numeric validation.
- Selected-field golden comparison.
- Missing, unexpected, and duplicate Stay output groups.

Selected Stay regression fields:

- `MEDPAR-DTE-CR-ENDED-0220`
- `MEDPAR-TOT-CHRG-0400`
- `MEDPAR-DRG-PRICE-0380`
- `MEDPAR-SQSTRTN-RDCTN-AMT-1130`
- `MEDPAR-INFOR-ENCTR-IND-SW-0800`
- `MEDPAR-MA-TEACH-IND-SW-0810`
- `MEDPAR-SNF-QUAL-FROM-DATE-0180`
- `MEDPAR-SNF-QUAL-THRU-DATE-0190`

For Stay catalogue fields whose proprietary formula was not supplied, exact validation is performed through approved expected-output/golden files rather than invented logic.

## 4. Intermediate

Implemented validations:

- Unique source, actual, and expected identities.
- January-aligned five-year window: January 1 of run year minus four years through run date.
- Three-decimal `Decimal` precision for positive and negative values.
- `MEDPAR-COV-CHRG-0410`.
- `MEDPAR-SERVICE-CHARGES-0470`.
- `MEDPAR-TOT-DPT-CHRG-0440`.
- `MEDPAR-TOT-ACC-CHRG-0430`.
- `MEDPAR-DRG-PRICE-0380`.
- Repeated `MEDPAR-ACCOMMODATION-CHRG-0460` precision.
- Repeated `MEDPAR-ACCOMMODATION-DAYS-0450` non-negative integers.
- Accommodation charge/day array alignment.
- Total accommodation charge reconciliation.
- Procedure code/date/version arrays and counts.
- Procedure code/date positional alignment.
- Surgical indicator derivation.
- Procedure-date five-year window.
- Diagnosis/version array alignment.
- Diagnosis count.
- POA count and diagnosis/POA positional alignment.
- `medparDeathAfterAdm0611` derivation.
- Age integer range 0–120.
- NDC numeric normalization to configured length.
- Direct-field format checks for admission diagnosis, diagnosis version, MBI, provider full number, and primary payer.
- SNF qualification thru-date format/window.
- Calendar-window checks for all configured Intermediate date fields.
- Exact selected-field expected-versus-actual regression comparison.
- Missing, unexpected, and duplicate Intermediate outputs.

## 5. Final MEDPAR

Implemented validations:

- Unique source, actual, and expected identities.
- Split-year indicator format.
- SS/LS/SNF classification.
- Selected final field comparison: BIC, provider, DOD, SSI, Q1 reduction, SSA/HICN, bill count, split indicator, and classification.
- Actual encoded fixed-width length, not a simulated length variable.
- ASCII/selected encoding validation.
- Required fixed-width data through configuration.
- Configurable one-based byte field offsets, lengths, required status, and expected values.
- Missing, unexpected, and duplicate Final MEDPAR outputs.
- Approved golden output comparison.

Known open item:

- The proprietary 3050-to-3000 byte field layout/offset map is not supplied. The framework supports it through `field_layout`, but does not invent offsets.

## Test coverage

The included automated suite covers:

- Unit validation functions.
- All Final Action routes except the blocked Rule 6 matrix.
- Multi-file JSON inputs.
- Uploaded Final Action and Split business fixtures.
- Positive and known-negative Split fixtures.
- Stay latest-code precedence and selected fields.
- Intermediate Decimal, negative rounding, procedure, diagnosis, POA, dates, age, NDC, and accommodation checks.
- Final MEDPAR byte length, encoding, and configurable offset checks.
- Complete five-stage example manifest.

## August 2026 discrepancy and LD-3137 additions

The following validations are part of the regression scope from v0.5.0 onward:

- `INT-ACCOMMODATION-TOTAL`: round every accommodation charge before summing.
- `INT-BILL-TOT-PERDIEM-ROUNDING`: round per diem before multiplication.
- `INT-INTENSIVE-CARE-IND-0481`: include 0200 and 0201.
- `INT-ORGAN-IND-0487`: configurable Legacy revenue-code derivation.
- `INT-ADMISSION-DAY-0090`: admission day calculation.
- `INT-SOURCE-TO-TARGET`: selected Stay-to-Intermediate direct moves.
- `INT-REVENUE-LINE-ITEMS`: field-level revenue-line validation.
- `INT-PROC-MAX-25`: maximum procedure groups.
- `ST-SPAN-CODE-LIMIT`: maximum unique Span Code/date groups.
- `FA-RULE-06`: current QC0/QC5 keep/drop behavior.
- `FA/SP/ST/FM-SORT-ORDER-LD3137`: sort configuration evidence.
- `FA/SP/ST/FM-GROUP-CONTIGUITY-LD3137`: grouping evidence.

Use the `required_selected_fields` setting in Intermediate or Final MEDPAR manifests when a field must be present for every record in that run. Without this explicit applicability setting, an absent field is reported as `NOT_APPLICABLE`, never as a false PASS.
