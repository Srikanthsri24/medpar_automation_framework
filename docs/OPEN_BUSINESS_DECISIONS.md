# Open business decisions — 11 October 2026

Current authority: `MEDPAR_GAP_SUBMISSION.md` and `medpar_gap_completion.json`. The historical v0.5.0 notes below are superseded where they conflict with the latest supplied requirements.

Resolved: admission exclusion applies to FA only; Stay retains admission; QC2 is unsupported; Rule6 uses action code; bypass belongs to Final for covered days > LOS; organ0818 is excluded; emergency condition91 is supported; Final preserves the first3000bytes of3050; LD-1410 specifies integer-rate rounding before days and a positive999999999cap.

Still open: complete approved copybooks/current MPRPARL, EQ-BIC/cache/IDR contracts, DRG/outlier and revenue mappings, CY/FY routing, HICN merge policy, warning03/06/07/08/10, SSI0253, HAH limits, conflicting sum/date rules, optional samples, undischarged-stay policy, BayState scope/layout, CMS golden fixtures and production-scale performance acceptance.

## Historical v0.5.0 decisions (superseded where noted above)

The August 2026 update implements the rules that are explicitly supported by the supplied discrepancy report and user-story text. The framework still refuses to invent proprietary behavior that was not supplied.

## Resolved in v0.5.0

- Final Action Rule 1 accepts QC1, QC2, QC3, and QC5; QC0 is dropped.
- Final Action Rule 6 now implements the supplied QC0/QC5 rule. A matching control number plus a QC0 Action/Transaction code of 4 or 6 drops both; otherwise QC5 is kept and QC0 is dropped.
- LD-3137 is enforced for Final Action, Split, Stay, and Final MEDPAR: `admissionDate` is excluded from configured sort/group keys.
- Accommodation total rounds each charge before summation.
- Bill total per-diem rounds the per-diem before multiplying by utilization days.
- Intensive-care revenue-code search includes 0200 and 0201.

## Still requiring business-owner confirmation

1. **Rule 6 field name conflict.** The latest story says `transactionCode`; earlier flow material says Action Code. v0.5.0 checks an explicit Action Code 4/6 first, then transactionCode, and reports which field caused the decision. Confirm this precedence.
2. **Organ acquisition revenue-code list.** The validator is complete and configurable, but the exact Legacy search-code list was not supplied. Default configuration uses 0810–0819 and must be approved or replaced.
3. **Emergency-use indicator.** `medparEmerUseSw1590` is registered, but the source condition/revenue code needed to derive it was not supplied.
4. **Admission-day numbering.** The implemented mapping is Sunday=1 through Saturday=7. Confirm this matches Legacy.
5. **Final Action tie-breaker.** Exact tie-breaking remains unknown when processing date, accrete date, and source sequence are identical. Such groups remain BLOCKED.
6. **Final MEDPAR 3050-to-3000 transformation.** The official deletion/offset map was not supplied. The framework validates a real 3000-byte output and configurable byte fields, but does not invent the 3050 conversion.
7. **HICN merge precedence.** The discrepancy report identifies a Legacy merge-by-HICN test, but no approved field-level merge precedence was supplied. Current behavior detects duplicate identities rather than guessing a merge.
8. **Historical field derivations.** All listed missing fields are now registered, and fields with supplied logic are validated. Registry coverage alone does not prove a derivation for fields whose business formula was not supplied; those require golden expected data or a signed-off rule.
9. **NDC source quality.** CMS CR18 specifies 11-character entries, up to ten occurrences. Defaults now match this contract and do not add zeros. Supplied values contain alphabetic characters; obtain valid NDC values or an approved shared IDE/NDC/UPC classification rule.
10. **Rounding mode.** The supplied requirement confirms three decimal places. v0.5.0 uses `ROUND_HALF_UP`; confirm if Legacy uses a different tie-breaking mode.
