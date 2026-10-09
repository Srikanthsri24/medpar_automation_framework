# Stay Process Workflow

The default Stay group key is HICN, provider and admission date. It is configurable.

## Implemented known validations

- Latest-record precedence for duplicate Condition Codes
- Latest-record precedence for duplicate Occurrence Codes
- Preservation of unique older codes
- Condition Code 04 to `MEDPAR-INFOR-ENCTR-IND-SW-0800`
- Condition Code 69 to `MEDPAR-MA-TEACH-IND-SW-0810`
- Value Code 73 total to `MEDPAR-SQSTRTN-RDCTN-AMT-1130`
- Three-decimal Decimal precision
- Total charge reconciliation when source charge values are supplied
- Selected-field expected-versus-actual regression comparison
- Missing, duplicate and unexpected Stay output detection

## Selected regression fields

- MEDPAR-DTE-CR-ENDED-0220
- MEDPAR-TOT-CHRG-0400
- MEDPAR-DRG-PRICE-0380
- MEDPAR-SQSTRTN-RDCTN-AMT-1130
- MEDPAR-INFOR-ENCTR-IND-SW-0800
- MEDPAR-MA-TEACH-IND-SW-0810
- MEDPAR-SNF-QUAL-FROM-DATE-0180

The full Stay 01–23 catalogue is recorded in `config/rules/stay.yaml`. Exact derivations not present in the supplied requirements use approved expected-output comparison instead of guessed logic.
