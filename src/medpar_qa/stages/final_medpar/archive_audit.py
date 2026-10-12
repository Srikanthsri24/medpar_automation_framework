"""Verify delivered JSON routing and exact Intermediate-to-Final lineage for an archive.

The business-year anchor and partial-FY policy are explicit inputs. No missing
routing indicator is invented in a Final record. Physical byte certification is
separate from JSON field preservation.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, StageResult
from medpar_qa.normalization.fields import _key_form, FieldResolver
from medpar_qa.normalization.decimal_values import to_decimal


def payload_fingerprint(data):
    """Hash unchanged fields after deleting only the Intermediate split indicator."""
    payload = {key: value for key, value in data.items() if _key_form(key) != 'medparsplityearindicator'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def audit_archive(root, *, current_year, resolver):
    """Return source-linked proof for M1–M7 without granting acceptance to partial FYs."""
    root = Path(root)
    result = StageResult(Stage.FINAL_MEDPAR)
    source_index = defaultdict(list)
    for path in sorted((root / '5-intermediate-processing').rglob('*.json')):
        data = json.loads(path.read_text())
        source_index[payload_fingerprint(data)].append((path, data))
    finals = sorted((root / '6-final-processing').rglob('*.json'))
    delivered_by_source = defaultdict(list)
    routes = Counter()
    matched_routes = Counter()

    def check(rule, valid, expected, actual, paths, message, *, status=None):
        if rule in {'FM-ARCHIVE-SSI-DAYS-DOMAIN', 'FM-ARCHIVE-SSI-INDICATOR-DOMAIN', 'FM-ARCHIVE-BASE-FACILITY-CCN'}:
            # Exact lineage proves these values are carried unchanged into Final.
            # Attribute field findings to those delivered files as well as the source.
            paths = list(dict.fromkeys([*paths, *[final for source in paths for final in delivered_by_source[source]]]))
        result.rule_results.append(RuleResult(stage=Stage.FINAL_MEDPAR, rule_id=rule,
            status=status or (ValidationStatus.PASS if valid else ValidationStatus.FAIL),
            message=message, expected=expected, actual=actual,
            source_files=[path.relative_to(Path(__file__).resolve().parents[4]).as_posix() if path.is_relative_to(Path(__file__).resolve().parents[4]) else str(path) for path in paths],
            evidence={'current_year': current_year, 'audit': 'JSON fields and archive routing; not physical bytes'}))

    for path in finals:
        data = json.loads(path.read_text())
        parts = path.relative_to(root / '6-final-processing').parts
        folder, period, year = parts[:3]
        classification = str(resolver.get(data, 'medpar_ss_ls_snf_ind_0140')).strip()
        expected_folder = 'MEDPAR_FINAL_SNF_FILES' if classification == 'N' else 'MEDPAR_FINAL_SS_FILES' if classification in ('S', 'L') else None
        check('FM-ARCHIVE-CLASSIFICATION-ROUTE', folder == expected_folder, expected_folder, folder, [path], 'S/L route to SS; N routes to SNF')
        routes[(folder, period, int(year))] += 1
        digest = payload_fingerprint(data)
        matches = source_index[digest]
        check('FM-ARCHIVE-EXACT-LINEAGE', len(matches) == 1, 'Exactly one Intermediate record identical except removed Split-Year Indicator',
              {'matching_sources': len(matches), 'sha256': digest}, [path, *[p for p, _ in matches]], 'Exact JSON field preservation against Intermediate')
        if len(matches) != 1:
            continue
        source_path, source = matches[0]
        delivered_by_source[source_path].append(path)
        indicator = resolver.get(source, 'split_year_indicator')
        match = re.fullmatch(r'Y([0-3])(0109|1012)', str(indicator))
        if not match:
            check('FM-ARCHIVE-PERIOD-ROUTE', False, 'Y[0-3]0109 or Y[0-3]1012 on matched Intermediate', indicator, [source_path, path], 'Routing operands missing or invalid')
            continue
        offset, suffix = int(match[1]), match[2]
        cy = current_year - offset
        fy = cy + (suffix == '1012')
        expected_year = cy if period == 'CY' else fy
        valid = period in ('CY', 'FY') and int(year) == expected_year and not (period == 'FY' and indicator == 'Y30109')
        check('FM-ARCHIVE-PERIOD-ROUTE', valid, {'period': period, 'year': expected_year, 'source_indicator': indicator},
              {'period': period, 'year': int(year)}, [source_path, path], 'CY/FY folder year derives from matched source indicator; oldest Jan–Sep subset excluded from FY')
        matched_routes[(source_path, period)] += 1
        if period == 'FY' and int(year) > current_year:
            check('FM-ARCHIVE-PARTIAL-FY', True, 'PO approval required for newest partial FY', {'folder_year': int(year), 'source_indicator': indicator},
                  [source_path, path], 'Partial newest fiscal year is present in DEV output; acceptance policy remains unconfirmed', status=ValidationStatus.KNOWN_DIFFERENCE)
    for matches in source_index.values():
        for path, data in matches:
            indicator = resolver.get(data, 'split_year_indicator')
            for period in ('CY', 'FY'):
                expected = 0 if period == 'FY' and indicator == 'Y30109' else 1
                check('FM-ARCHIVE-ROUTE-COMPLETENESS', matched_routes[(path, period)] == expected,
                      expected, matched_routes[(path, period)], [path], f'Expected {period} delivered copies for this Intermediate record')
    for folder, expected_bypass in (('5-intermediate-processing', False), ('5-intermediate-processing-drops', True)):
        for path in sorted((root / folder).rglob('*.json')):
            data = json.loads(path.read_text())
            if folder == '5-intermediate-processing':
                days = resolver.get(data, 'medpar_ssi_data_0251')
                try:
                    number = to_decimal(days)
                    valid_days = number == int(number) and number >= 0
                except (ValueError, TypeError):
                    valid_days = False
                check('FM-ARCHIVE-SSI-DAYS-DOMAIN', valid_days, 'Nonnegative integer day count in 0251', days, [path],
                      'Byte-by-byte p5 identifies 0251 as SSI days; invalid/blank day counts require source correction',
                      status=ValidationStatus.BLOCKED if days is None else None)
                indicator = resolver.get(data, 'medpar_ssi_data_0252')
                check('FM-ARCHIVE-SSI-INDICATOR-DOMAIN', str(indicator).strip() in ('0', '1', 'Y', 'N'),
                      'Found/not-found indicator (0/1 or Y/N) in 0252', indicator, [path],
                      '0252 is an indicator, not a day count; exact reference derivation still needs SSI feed',
                      status=ValidationStatus.BLOCKED if indicator is None else None)
                from medpar_qa.stages.intermediate.business_rules import base_facility_ccn
                ccn = resolver.get(data, 'medpar_prvdr_base_fac_ccn_1650')
                try:
                    expected_ccn = base_facility_ccn(resolver.get(data, 'provider_id'))
                    check('FM-ARCHIVE-BASE-FACILITY-CCN', ccn == expected_ccn, expected_ccn, ccn, [path],
                          'Compare base facility CCN with existing provider-position derivation')
                except (ValueError, TypeError) as exc:
                    check('FM-ARCHIVE-BASE-FACILITY-CCN', False, 'Valid provider mapping operands', str(exc), [path],
                          'Cannot derive base facility CCN', status=ValidationStatus.BLOCKED)
            covered, los = resolver.get(data, 'utilization_days'), resolver.get(data, 'medpar_lgth_stay_0260')
            if covered is None or los is None:
                check('FM-ARCHIVE-BYPASS-LOCATION', False, 'Covered days and LOS operands', 'Not supplied', [path], 'Cannot establish bypass disposition', status=ValidationStatus.BLOCKED)
            else:
                check('FM-ARCHIVE-BYPASS-LOCATION', (to_decimal(covered) > to_decimal(los)) == expected_bypass,
                      {'covered_gt_los': expected_bypass}, {'covered_gt_los': to_decimal(covered) > to_decimal(los)}, [path], 'Check retained and Intermediate dropped sets for covered-days/LOS bypass; stage ownership requires PO confirmation')
    for report_path in sorted((root / '7-reconciliation-report').glob('*.csv')):
        section = ''
        stats = defaultdict(dict)
        for row in csv.reader(report_path.read_text().splitlines()):
            cells = [cell.strip() for cell in row if cell.strip()]
            if len(cells) == 1:
                section = cells[0]
            elif len(cells) >= 2 and cells[-1].isdigit():
                stats[section][cells[0]] = int(cells[-1])
                match = re.fullmatch(r'(In Patient|SNF) (CY|FY) (\d{4})', cells[0])
                if match:
                    folder = 'MEDPAR_FINAL_SS_FILES' if match[1] == 'In Patient' else 'MEDPAR_FINAL_SNF_FILES'
                    observed = routes[(folder, match[2], int(match[3]))]
                    check('FM-ARCHIVE-REPORT-FILE-COUNT', observed == int(cells[-1]), int(cells[-1]), observed, [report_path], cells[0] + ': reconciliation count versus actual extracted files')
        for name, labels in [('Split', ('Claims In', 'Claims Out', 'Dropped Claims')),
                             ('Intermediate', ('Records In', 'Records Out', 'Records Dropped')),
                             ('Final Action', ('Total input claims', 'Total output "Netted" claims', 'Dropped Claims'))]:
            values = stats[name]
            if all(label in values for label in labels):
                incoming, outgoing, dropped = [values[label] for label in labels]
                check('FM-ARCHIVE-RECONCILIATION-BALANCE', incoming == outgoing + dropped,
                      incoming, {'out': outgoing, 'dropped': dropped, 'unaccounted': incoming-outgoing-dropped}, [report_path], f'{name}: input = output + dropped; errors must explain any remaining difference')
    check('FM-ARCHIVE-CERTIFICATION', True, 'Approved golden bytes / copybook needed for production acceptance', 'Not supplied', [],
          'JSON preservation and routing checks do not certify full physical records or externally derived SSI/CCN fields', status=ValidationStatus.BLOCKED)
    return result
