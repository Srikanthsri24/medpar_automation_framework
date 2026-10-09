# Final Action Automation Workflow

## Objective

The Final Action stage calculates the expected KEEP/DROP decision for every source claim and, when an `actual_output` file is supplied, compares those expected KEEP records with the application output.

## Input lifecycle

1. Discover every Final Action source JSON/Parquet file.
2. Load all records before business grouping.
3. Preserve file, row, format, role, and record ID lineage.
4. Resolve field aliases into canonical fields.
5. Validate mandatory fields and date formats.
6. Derive record type from transaction code.
7. Group claims by record type, HICN, provider, from date, and thru date.
8. Sort each group newest first by processing date, accrete date, and approved source sequence.
9. Block groups whose newest record cannot be determined.
10. Select exactly one Final Action rule.
11. Assign exactly one KEEP/DROP decision to every record.
12. Reconcile group and stage counts.
13. Compare expected KEEP records with `actual_output`, when provided.

## Canonical group key

```text
record_type
HICN
provider_id
stay_from_date
stay_thru_date
```

## Rule precedence

```text
Rule 1
Rule 2
Rule 6
Rule 5
All-QC0
Rule 3
Rule 10A
Rule 10B
Rule 7
Rule 8
Rule 9
Default
```

The order is intentional. For example, a three-record group with one QC0 and no QC5 is Rule 5 before the generic no-QC5 rules.

## Implemented rules

- Rule 1: one record; QC1/QC3/QC5 KEEP and QC0 DROP.
- Rule 2: newest-first 5-0-3 or 5-0-1; KEEP QC5.
- All-QC0: DROP the complete multi-record group.
- Rule 3: same QC; KEEP newest record for each unique ICN.
- Rule 5: three records, no QC5, exactly one QC0; all same ICN means DROP all, otherwise KEEP newest non-QC0.
- Rule 7: no QC5 and QC0 count is greater than or equal to QC1+QC3; KEEP non-QC0 records with non-matching ICNs.
- Rule 8: no QC5, more than three records, newest is QC0, and QC0 count is less than QC1+QC3; apply ICN comparison.
- Rule 9: no QC5, newest is non-QC0, and QC0 count is less than QC1+QC3; apply ICN comparison.
- Rule 10A: QC5 exists, newest is QC0, and QC0 count is greater than QC5 count; apply ICN comparison.
- Rule 10B: QC5 fallback; KEEP newest non-QC0 without ICN comparison.
- Default: KEEP newest non-zero QC when no numbered route applies.

## Blocked business requirement

Rule 6 is detected for a two-record QC0/QC5 group. It returns `BLOCKED` until the approved ICN and Action Code decision matrix is supplied. It never silently falls into Rule 10B or the default rule.

## PASS/FAIL behavior

A group passes only when one rule is selected and every source record receives exactly one decision. A complete stage passes only when there are no FAIL/BLOCKED results and actual output, when supplied, exactly equals expected KEEP records.

## Run commands

```bash
pytest -m final_action
python -m medpar_qa.cli --manifest config/run_manifest.example.yaml
```
