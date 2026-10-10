"""Aggregate-only Intermediate investigation; never changes production inputs.

Default validation includes every output. --distinct-payloads is an explicit
investigation of identical file copies, not acceptance of the duplicate archive.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
from medpar_qa.enums import FileRole, Stage
from medpar_qa.models import ManifestFile, RunManifest
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.orchestration.pipeline import Pipeline
from medpar_qa.reporting.path_utils import ensure_relative_user_path


def distinct_payload_paths(paths: list[Path]) -> tuple[list[Path], int]:
    """Ignore only filename metadata; differences in any data field remain."""
    unique: dict[str, Path] = {}
    for path in sorted(paths):
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Distinct-payload diagnostic requires one JSON object per file')
        payload = json.dumps({key: value for key, value in data.items() if key != 'filename'}, sort_keys=True)
        unique.setdefault(payload, path)
    return list(unique.values()), len(paths) - len(unique)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='data/production/q61')
    parser.add_argument('--output', default='reports/production_intermediate_review/summary.json')
    parser.add_argument('--run-date', default='2026-05-14')
    parser.add_argument('--distinct-payloads', action='store_true')
    args = parser.parse_args()
    ensure_relative_user_path(args.root, 'root')
    ensure_relative_user_path(args.output, 'output')
    root = PROJECT_ROOT / args.root
    sources = sorted((root / '4-stay-processing').rglob('*.json'))
    originals = sorted((root / '5-intermediate-processing').rglob('*.json'))
    if not sources or not originals:
        parser.error('Both Stay source and Intermediate output folders must contain JSON files')
    representatives, copies = distinct_payload_paths(originals)
    actuals = representatives if args.distinct_payloads else originals
    files = [ManifestFile(path=path.relative_to(PROJECT_ROOT).as_posix(), stage=Stage.INTERMEDIATE, role=role)
             for paths, role in ((sources, FileRole.SOURCE), (actuals, FileRole.ACTUAL_OUTPUT)) for path in paths]
    manifest = RunManifest(run_id='production_intermediate_review', run_date=date.fromisoformat(args.run_date),
                           files=files, settings={'intermediate': {'require_actual_output': True}}, base_directory=PROJECT_ROOT)
    results = Pipeline(manifest, FieldResolver.from_yaml(PROJECT_ROOT / 'config/field_aliases.yaml')).run()
    summary = {'source_files': len(sources), 'original_actual_files': len(originals),
               'identical_payload_copies_excluding_filename': copies,
               'actual_files_validated': len(actuals), 'distinct_payload_diagnostic': args.distinct_payloads,
               'golden_outputs_supplied': False, 'production_certified': False,
               'passed': all(result.passed for result in results), 'stages': []}
    for result in results:
        checks = result.rule_results
        summary['stages'].append({'stage': result.stage.value, 'counts': result.status_counts,
            'fail_rules': dict(Counter(check.rule_id for check in checks if check.status.value == 'FAIL')),
            'blocked_rules': dict(Counter(check.rule_id for check in checks if check.status.value == 'BLOCKED'))})
    output = PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
