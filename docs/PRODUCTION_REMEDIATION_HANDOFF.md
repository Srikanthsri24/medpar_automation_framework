# Production remediation handoff

Production acceptance is not closed. The QA framework validates supplied outputs; it does not generate or repair the upstream production extracts. Latest evidence: 254 passing regression tests and five passing synthetic stages; production checks remain failing or blocked.

| Required correction/input | Evidence and acceptance condition |
|---|---|
| Matching May Stay inputs | Split inputs are March 20; Stay outputs are May 14. Supply the matching May Split/bill extract before validating Stay derivations. |
| Unique exports and approved replay policy | Intermediate has 166 files / 83 distinct payloads; full acceptance requires unique records or an approved replay contract. Final Action has tied source orders affecting 130 groups. |
| Transaction-code decisions | Split source includes 359 unsupported values: C 150, H 31, 6 108, 5 70. Supplied clarification asks CMS/CVM for their mapping. |
| Correct birth dates and age | All 83 diagnostic sources have DOB zero; output ages are -1. Recover DOB from the authoritative feed and regenerate ages. |
| Correct base-facility CCN | All 83 diagnostic outputs contain CCN 0 despite six-character source CCNs. Regenerate using the documented source mapping. |
| Valid NDC/classification | All source/output NDC lists copy correctly, but supplied 11-character values contain letters. Obtain valid numeric NDCs or approve how shared IDE/NDC/UPC values are classified. No automatic padding or invented replacement is used. |
| Date and financial corrections | Diagnostic has 83 procedure-window, 83 SNF qualification, 253 calendar-window, 83 covered-care-end, 29 value-amount and four death-day failures. Use the per-record report to correct upstream values or supply an approved overriding rule. |
| Authoritative reference feeds | DOD/EDB, SSI and age operands are missing; 498 Intermediate checks remain blocked. A missing feed cannot establish a confirmed no-match. |
| Final-stage acceptance assets | Supply Final MEDPAR production records, CMS golden outputs and current complete copybooks/revenue/DRG mappings. Current byte reconstruction and external derivations cannot be certified from the supplied archive. |

Local per-record diagnostic: `reports/production_intermediate_review/`. Full archive report: `reports/20261011_014942/master/index.html`. Check counts overlap records and are not unique issue counts. Synthetic example: `reports/20261011_015646/master/index.html`.

The original Excel register remains preserved; its earlier status snapshot does not imply production closure. Current evidence is recorded in `medpar_gap_completion.json` and `PRODUCTION_VALIDATION_REVIEW.md`.
