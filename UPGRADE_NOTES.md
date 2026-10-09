# MEDPAR QA upgraded reporting build

Run `python run_commands.py` from the project folder. Each execution now writes `reports/<timestamp>/quality_summary.html` and `quality_summary.json` in addition to the existing stage and master reports.

## What changed
- Added one-page per-command execution dashboard with stage, exit code, result, and links to generated reports.
- Differentiated successful validation, expected validation failure, unexpected validation failure, and runtime error.
- Added structured machine-readable JSON with command and log tail.
- Preserved existing rule implementations and configuration, rather than silently choosing between conflicting V3 specifications.

## Not yet fixed / business signoff required
- Revised Final Action tree and conflicting Rule 5 documentation; action-code field precedence.
- Split inpatient last-through-date vs SNF admission-date routing; LD-3137 grouping interpretation.
- Stay field-by-field COBOL mapping and trailer accumulation.
- Intermediate DOD/SSI/DRG external lookup and field derivation completeness.
- Final MEDPAR approved 3050-to-3000-byte layout and output reconciliation.
- Live S3 JSON reads (bucket, prefixes, IAM, and file selection not supplied).

Do not treat this build as V3-compliant until approved source-to-output fixtures and specifications are supplied and all rule paths pass.
