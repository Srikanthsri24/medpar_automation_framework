# Final MEDPAR Workflow

- Match source, actual and expected records by the configured identity.
- Validate split-year indicator format.
- Validate SS/LS/SNF classification.
- Compare selected output fields with approved golden output.
- Detect missing, duplicate and unexpected records.
- Validate the actual encoded fixed-width string, when supplied, is exactly 3000 bytes.

Full byte-position validation remains BLOCKED until the approved 3050-to-3000 field-offset specification is available. The framework does not simulate byte conversion by changing a numeric length variable.
