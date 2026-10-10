# Verification results — 11 October 2026

Latest full suite: **227 passed, 0 failed**, in 12.03 seconds.

Report: `reports/20261011_010812/pytest/pytest_complete_suite/report.html`.

All-five-stage example manifest: **PASS**, report `reports/20261011_010607/master/index.html`.

`git diff --check` passed. The updated workbook preserves original cell values and equivalent styles; status formulas reconcile all 74 functionality rows and respond to a temporary status change. Native filters include the added evidence columns.

These checks establish synthetic QA regression behaviour. CMS golden equivalence, complete fixed-width reconstruction, external DRG/reference systems and production-scale performance remain unverified. See `MEDPAR_GAP_SUBMISSION.md` and `medpar_gap_completion.json` for each dependency.

## Historical v0.5.0 results

Validated after implementing the July/August 2026 discrepancy and LD-3137 updates.

```text
104 pytest tests passed
0 pytest tests failed
```

The working five-stage example manifest was executed successfully:

```text
Final Action: PASS
Split: PASS
Stay: PASS
Intermediate: PASS
Final MEDPAR: PASS
```

The default enabled `run_commands.py` session was also executed:

```text
7 commands completed as expected
0 unexpected command results
```

The test suite includes explicit regression cases for:

- rounding each accommodation charge before total summation;
- rounding pass-through per diem before multiplication;
- intensive-care revenue codes 0200 and 0201;
- configurable organ-acquisition indicator derivation;
- admission-day calculation;
- Final Action Rule 6 branches;
- LD-3137 sort/group configuration;
- procedure maximum of 25;
- Span Code maximum of 10;
- registry coverage for the missing-field report; and
- prevention of false PASS when expected and actual values are both absent.
