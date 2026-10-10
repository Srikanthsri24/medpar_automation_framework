# MedPAR team demonstration

The framework fixes are verified by 254 passing tests and a passing five-stage synthetic example. Production reconciliation is failing on the supplied archive. Demonstrate both results; do not describe the Excel register as fully closed.

## Demonstration

1. Run `.venv/bin/python -m pytest -q`. Explain that these regressions test documented logic and reject wrong outputs.
2. Run `PYTHONPATH=src .venv/bin/python -m medpar_qa.cli --manifest config/run_manifest.all_stages.example.yaml --command-id team-demo --failures-only`. Open the generated master report. This demonstrates all five stages, including Final MEDPAR, using explicitly synthetic fixtures.
3. Run `.venv/bin/python run_commands.py`. It now supplies actual outputs for the first four stage comparisons. A nonzero exit is expected until archive exceptions/coverage are resolved. Detailed reports can contain sensitive production data; share only through approved team channels.
4. Run `.venv/bin/python scripts/review_production_intermediate.py --distinct-payloads`. Show the aggregate summary, the 166 original files/83 identical copies and the explicit diagnostic selection. No source data is rewritten and no golden certification is claimed.
5. Review `PRODUCTION_VALIDATION_REVIEW.md`, `MEDPAR_GAP_SUBMISSION.md` and the Excel review together. Separate implemented validation from upstream data correction and missing requirements.

## Team decisions and material required

- Supply Split/bill inputs corresponding to the May 14 Stay output snapshot. The March Split snapshot does not match those Stay identities.
- Resolve unsupported transaction/query codes and the policy for replayed identical Final Action rows. Supply unique Intermediate output extracts or approve how duplicate deliveries are handled.
- Supply complete approved copybooks/current MPRPARL. CMS indicator types and 11-character NDC width are now implemented. Complete current byte offsets, missing-date defaults and equal-charge ICU/CCU tie policy still require approval.
- Supply DOB/DOD/SSI/reference fixtures, DRG/revenue mappings and CMS golden outputs/control totals. Resolve warning/default/routing/HICN merge requirements identified in the gap review.
- Supply actual Final MEDPAR files and a performance environment. Confirm BayState scope.

These are acceptance dependencies, not permissions to replace production values with expected values. The Excel review remains 24 partial and 14 needs-input functionality items until their listed dependencies and acceptance checks are satisfied.
