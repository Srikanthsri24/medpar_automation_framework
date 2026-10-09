# Final Action V3 — Implementation and approval register

Source of truth reviewed: *Medpar functionality notes V3*, pages 15–21; *Final Action Decision Tree Revised*, 05/21/2026. The diagram is the preferred authority for KEEP/DROP when its branches differ from the older slide text. This is a targeted QA-framework upgrade, **not a certification of complete business-rule coverage**.

## Implemented in this delivery

- Retains `run_commands.py` as the execution entry point and existing HTML/JSON reporting.
- Rejects unsupported query code 2 and transaction code 6 according to V3 QC/transaction-code definitions.
- All-QC0 groups are dropped; single-claim 0/1/3/5 routing remains covered.
- Rule 2 matches 5-0-3 and 5-0-1 newest-first sequences only when QC5 has the greatest accretion date.
- Rule 3 keeps the newest record for each distinct ICN in same-QC groups.
- Rule 5 uses the revised diagram: all ICNs same => DROP all; otherwise select newest non-QC0 whose ICN differs from QC0. Unresolvable cases are BLOCKED.
- Rule 6 compares QC0 **action code** (4/6) when ICNs match; transaction code is never substituted. Missing QC0 action code => BLOCKED.
- Rules 7–9, 10A/10B retain existing comparison algorithms and have existing regression tests. They are **not yet certified against a COBOL reference/golden file**.
- Removed unsafe FA-DEFAULT KEEP behavior. Any unhandled pattern now returns BLOCKED with no invented KEEP/DROP decisions.
- Added focused V3 tests for Rule 5, Rule 6, Rule 2 and code validation.

## Gaps requiring authoritative business clarification or external assets

1. **Rule 5 contradiction:** V3 page 20 text reverses the revised decision tree (and V3 page 21) in one case. Implemented revised diagram; obtain written business-owner signoff.
2. **Rules 7/8/9 and 10A matching:** “non-matching ICNs” is implemented as ICNs occurring exactly once in the whole group. The document does not definitively establish whether it means unmatched against QC0 only, or unmatched across all claims. Validate with COBOL and golden scenarios before production.
3. **Rule 2:** The diagram specifies newest-first sequence; V3 adds greatest accretion date. Missing/ambiguous accretion semantics require confirmation.
4. **Final Action upstream/downstream workflow:** Historical database + quarterly TAP merge, separate IP/SNF netting, questionable-group exception file, multiple service-year exception, >900 continuation and >875 hold errors, financial balancing and full audit stats are not implemented as complete new production processes in this patch.
5. **Covered-days versus length-of-stay bypass:** V3 pages 15 and 8/35 disagree on direction and stage. Not silently added.
6. **Date edits and input sort:** MPRDATEL annual routine is unspecified; legacy RIC S/D checks are described as unnecessary. Not invented.
7. **Rule 6 action-code source:** Confirm alias mapping and RIF definitions against real input payloads; action code is distinct from transaction code.
8. **Reference validation:** No production golden outputs or original MPRSEQVL/MPRNETVL COBOL were supplied. Passing unit tests is not equivalent to business signoff.

## How to run

```bash
python run_commands.py
python -m pytest tests/unit/test_final_action.py tests/unit/test_final_action_v3_decision_tree.py -q
```

Inspect the run-specific `reports/` directory for the execution summary, stage HTML and JSON details. BLOCKED is an intentional fail-safe status and must be investigated, not treated as KEEP.

## Release gate

Do not mark the entire Final Action process as gap-free until the eight items above are resolved, independently verified with production-like test fixtures, and approved by the business owner.
