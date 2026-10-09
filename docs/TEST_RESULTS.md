# Verification results — v0.5.0

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
