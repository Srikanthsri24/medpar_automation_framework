# Split Process Workflow

- Source records are matched by claim/HICN/provider/from/thru identity.
- Transaction codes 0 and 4 bypass slicing by default and are configurable.
- The configured window begins January 1 of `run_year - (window_years - 1)` and ends on the run date.
- Outside-window claims receive `Y99999`.
- January through September receive `Y{year-last-digit}0109`.
- October through December receive `Y{year-last-digit}1012`.
- Actual output is checked for missing, duplicate and unexpected identities.
