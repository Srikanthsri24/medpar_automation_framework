# Intermediate Process Workflow

## Implemented selected-field validations

- Charge fields use Decimal with explicit three-decimal precision.
- Negative values retain their sign and use the configured rounding mode.
- Repeated accommodation values preserve duplicates and order.
- Total accommodation charge reconciles to repeated charge values.
- Procedure code/date/version arrays and counts align.
- Procedure dates use the January-aligned five-year window.
- Diagnosis/version/POA arrays and counts align.
- `medparDeathAfterAdm0611` is checked against admission and death dates.
- MEDPAR-AGE-0030 is validated as 0 through 120.
- MEDPAR-REV-CNTR-NDC-NUM-1550 is normalized to configured numeric length.
- Approved expected and actual files are compared for all selected regression fields.

The complete selected field inventory is in `config/rules/intermediate.yaml`.
