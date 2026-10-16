"""Actionable, source-backed row explanations without changing validation outcomes."""
from collections import Counter


def diagnose_row(record, checks, resolver, stage, identity_fields=(), identity_locations=None):
    """Keep direct failures distinct from a stop inherited from a related group."""
    issues = []
    seen = set()
    for check in checks:
        if check.get('status') not in ('FAIL', 'BLOCKED'):
            continue
        evidence = check.get('evidence') or {}
        inherited = check.get('rule_id') == 'PIPELINE-GROUP-STOP'
        rule = evidence.get('blocking_rule', check.get('rule_id', 'UNKNOWN')) if inherited else check.get('rule_id', 'UNKNOWN')
        token = (rule, check.get('field_name'), str(check.get('expected')), str(check.get('actual')))
        if token in seen:
            continue
        seen.add(token)
        category = 'Validation discrepancy'
        action = 'Review the supplied source and expected/observed evidence for this rule.'
        facts = {}
        if rule == 'FA-PRE-SCHEMA' and (check.get('field_name') == 'query_code' or 'query code' in check.get('message', '').lower()):
            category = 'Invalid Final Action claim code'
            facts = {'row_query_code': resolver.get(record.data, 'query_code'), 'allowed_query_codes': [0, 1, 3, 5],
                     'row_action_code': resolver.get(record.data, 'action_code')}
            action = 'Confirm the source query-code mapping. Action codes 4/6 are separate fields and do not extend the query-code domain.'
        elif rule == 'SP-INVALID-TRANSACTION-CODE':
            category = 'Split transaction-code exception'
            facts = {'row_transaction_code': resolver.get(record.data, 'transaction_code'), 'allowed_codes': [0, 1, 2, 3, 4]}
            action = 'Supply the documented IP/SNF transaction code or review this row in the exception output. It is not a KEEP/DROP row.'
        elif 'DUPLICATE-IDENTITY' in rule:
            category = 'Repeated claim identity'
            key = tuple(str(resolver.get(record.data, name)).strip() for name in identity_fields)
            locations = (identity_locations or {}).get(key, [])
            facts = {'identity': dict(zip(identity_fields, key)), 'selected_source_occurrences': len(locations), 'source_locations': locations[:10]}
            action = 'Check repeated extraction runs and the approved identity fields. Repeated rows are shown with locations; the framework does not silently delete them.'
        elif rule == 'INT-AGE' or 'AGE-CALCULATION' in rule:
            category = 'Birth date / age input unavailable' if resolver.get(record.data, 'beneficiary_date_of_birth') in (None, '', 0, '0', '00000000') else 'Age derivation discrepancy'
            facts = {'source_birth_date': resolver.get(record.data, 'beneficiary_date_of_birth'),
                     'admission_date': resolver.get(record.data, 'admission_date'), 'delivered_age': resolver.get(record.data, 'medpar_age_0030')}
            action = 'Provide the approved beneficiary birth date and recalculate age. A missing/zero birth date is not replaced with an invented age.'
        elif rule == 'ST-COVERED-CARE-END':
            category = 'Occurrence-span input unavailable'
            facts = {'transaction_code': resolver.get(record.data, 'transaction_code'), 'occurrence_spans': resolver.get(record.data, 'occurrence_span_lines')}
            action = 'Supply the occurrence-span collection needed by the SNF care-end rule. A missing collection is not assumed to be an explicitly empty collection.'
        elif 'WINDOW' in rule:
            category = 'Date outside selected business window'
            facts = {'admission_date': resolver.get(record.data, 'admission_date'), 'discharge_date': resolver.get(record.data, 'discharge_date'),
                     'procedure_dates': resolver.get(record.data, 'medpar_surg_date_0514'), 'configured_window': check.get('expected')}
            action = 'Confirm the intended archive business date or correct the source date. The execution date is not silently changed to make historical data pass.'
        elif rule in ('FM-TYPE-0580', 'INT-TYPE-0580') or 'medpar_intmd_num_0580' in rule or '0580' in rule:
            category = 'Intermediary 0580 format / value discrepancy'
            facts = {'source_0580': resolver.get(record.data, 'medpar_intmd_num_0580'), 'expected': check.get('expected'), 'observed': check.get('actual')}
            action = 'Generated output uses the documented intermediary ID string. Regenerate supplied comparison outputs that still contain the old object/struct; leading zeros must remain intact.'
        elif 'dod_data_cutoff_date' in str(check.get('expected')) or 'dod_data_cutoff_date' in check.get('message', ''):
            category = 'Approved death-date cutoff missing'
            facts = evidence.get('death_policy', {})
            action = 'Set the team-approved claims coverage date in SOURCE_RUN.settings.intermediate.dod_data_cutoff_date; rerun without replacing it with the execution date.'
        elif rule == 'ROW-OUTPUT-MEMBERSHIP':
            category = 'Calculated decision and supplied output membership disagree'
            facts = {'reference_counts': check.get('actual'), 'comparison_identity': evidence.get('comparison_identity'),
                     'locations': {role: evidence.get(role, []) for role in ('keep', 'drop')}}
            action = 'Check that original/keep/drop describe the same extraction. All reference rows were searched; a matching count alone does not prove the decision and values agree.'
        elif rule.startswith('ROW-OUTPUT-'):
            category = 'Supplied output comparison discrepancy'
            facts = {'field': check.get('field_name'), 'expected': check.get('expected'), 'observed': check.get('actual'), 'reference_evidence': evidence}
            action = 'Review the selected reference file/row and differing field values. Supply the missing expected operand or regenerate the incorrect output; do not assume missing values are zero.'
        issues.append({'rule_id': rule, 'status': check['status'], 'category': category,
                       'scope': 'Related group stopped; this is not proof that this row alone violates the rule' if inherited else 'Check linked to this row',
                       'reason': check.get('message', ''), 'expected': check.get('expected'), 'observed': check.get('actual'),
                       'source_file': record.source.file_path, 'source_row': record.source.row_number,
                       'source_facts': facts, 'next_action': action,
                       'validator_evidence': {key: value for key, value in evidence.items() if key in ('validator_function', 'source_line', 'specification', 'death_policy', 'blocking_rule', 'comparison_identity', 'selected_reference')}})
    return issues


def summarize_issues(rows):
    counts = Counter()
    for row in rows:
        counts.update({issue['category'] for issue in row.get('issues', [])})
    return dict(counts)
