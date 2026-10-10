# MedPAR gap-register implementation review — 11 October 2026

This submission records changes to the QA automation framework against the supplied V3 gap register, modernization requirements, byte-by-byte notes, October clarifications and question responses. It distinguishes implemented validation from production transformation and CMS certification. Original workbook findings are preserved; added columns provide current evidence and remaining actions.

## Changes delivered

- Final Action: default bypass moved to Final; query-code ordering added; revised Rule10A precedence covers latest non-QC0 with QC0 dominance. Admission is excluded from FA grouping while remaining part of Stay identity.
- Split: SNF retained; Y0–Y3 year-back indicators; whole calendar-year window; invalid-type exception audit; over75-bill audit without rejection; record and signed-charge reconciliation.
- Stay: admission-based identity; first/last, first-nonblank, high/low and non-conflicting sum checks; value-code amount accumulation; span uniqueness by code/date pair; known trailer caps; all revenue lines; warning01/05 calculations.
- Intermediate: independent LOS, age, discharge, death-day, DOD/SSI, CCN/PPS, ESRD condition, emergency, value amounts, accommodation, span, radiology and outpatient checks. Source values never come from output values to manufacture a passing calculation.
- Recovered mail specifications: LD-1410 establishes whole-dollar per-diem rate rounding before multiplication and positive nine-digit monetary cap. LD-1421 separates value derivations from monetary moves. LD-1407/1408 provide direct/ACO field mappings; LD-1406 provides MRN fallback and the5% CAN sample rule. LD-1314 documents first-nonblank Stay fields.
- Final: one-byte S/L/N class contract, covered-days>LOS bypass and exact3050-to3000 prefix/trailer verification.
- Cross-stage: all200 registered fields included in golden comparison; case/separator-insensitive aliases; strict Gregorian/Julian distinction; raw physical length contracts; per-stage error, bypass, decision and statistics audit files.

Missing operands block populated calculation targets. Fields absent from both golden and actual receive NOT_APPLICABLE, which is not counted as calculation coverage. Supplied actual datasets with missing retained records fail instead of being silently replaced by input records.

## Validation and reproduction

Run the full suite from the repository root:

```sh
.venv/bin/python -m pytest -q
```

The accompanying workbook identifies the latest passing suite and HTML report. Tests are synthetic regression evidence. They do not establish a match to unavailable CMS production golden outputs or production-scale performance. User input files remain unchanged; synthetic sample outputs were corrected to the documented rules.

`docs/medpar_gap_completion.json` is the portable row-by-row evidence ledger. The workbook adds current status, implementation evidence, test evidence and remaining input/action across all200 fields,74 functionality items,14 project items and10 conflicts. An “Implemented” functionality status means the specified validation is implemented and tested; field mapping, byte reconstruction and production acceptance may be separate rows.

## External dependencies still open

1. Complete approved MPRRECL/UTLIPSNL and current MPRPARL/related routines: field offsets, accumulator widths, flags, full trailer schemas, special-unit derivation, ICU/CCU tie policy, ESRD setting and40+revenue categories. Raw-length and prefix checks already work, but reconstructing bytes from Parquet cannot be certified without the layouts.
2. CMS golden fixtures and control totals, approved DRG grouper/version/outlier reference tables, EQ-BIC/cache contracts and IDR HICN feed.
3. Approved14-file CY/FY routing architecture and final HICN merge policy. Distinct admissions are preserved until the merge rule is established.
4. Clarification of warning03/06/07/08/10, secondary SSI0253, HAH limits and conflicting first-versus-sum fields. The old LD-1062 research also combines Q1/Q7/QB into one indexed slot; this conflicts with newer separately named payment fields and has not been introduced as an unapproved regression.
5. BayState scope, DB2 source/extract contract, corrected LOS/SSI formulas and3004-byte encoding. The supplied notes do not establish these sufficiently.
6. A production-scale environment and agreed performance limits for600–700million-record history processing.

## Source precedence and email review

The supplied modernization requirements and later October clarifications take precedence over contradictory earlier research/demo wording. Examples: FA uses action code for Rule6; unsupported QC2 remains rejected; FA alone excludes admission; Stay diagnosis/procedures use the last bill; deleted physical fields remain filler while internal warning checks continue.

Read-only Gmail searches found the lead's “Missing fields all through the stages” message dated31July2026 and “Important- verify the Stay process and start on Intermediate process with the documents attached in the mail” dated9January2025. Original supported attachments were read locally for this review. Test-case-name-only documents list scenarios but do not define authoritative expected values. ZIP code attachments were unsupported by the Gmail attachment reader and were not treated as current approved specifications. No email was sent and no external submission was made.

This is a reviewable implementation and dependency handoff. It must not be represented as complete CMS byte-for-byte certification while the dependencies above remain open.
