"""Offline acceptance checks for independently supplied infrastructure exports.

These checks compare supplied evidence; they do not claim to operate or inspect AWS.
Source policies/golden outputs must be supplied separately from actual exports.
"""
import json
from datetime import datetime
from decimal import Decimal
from medpar_qa.normalization.dates import parse_date


def result(rule, expected, valid, actual):
    return dict(rule_id=rule,status='PASS' if valid else 'FAIL',expected=expected,actual=actual)


def unavailable(rule, requirement):
    return dict(rule_id=rule,status='BLOCKED',expected=requirement,actual='Required independent reference or actual export not supplied')


def validate_ssi_export(source_rows=None, actual=None, policy=None):
    if source_rows is None or actual is None or policy is None:
        return [unavailable('SSI-LOAD','SSA source rows, actual DynamoDB export, approved table/year policy and recreate audit')]
    expected={}
    for row in source_rows:
        ssn=str(row['ssn']); flags=row['flags']
        if len(flags)!=42:raise ValueError('SSI source rows must contain 42 monthly flags')
        values=[int(Decimal(str(v))>0) for v in flags]
        prior=expected.setdefault(ssn,[0]*42)
        expected[ssn]=[max(a,b) for a,b in zip(prior,values)]
    rows=actual['rows'];observed={str(r['ssn']):r['flags'] for r in rows}
    valid=len(observed)==len(rows) and observed==expected and all(len(r['flags'])==42 and all(type(v) is int and v in (0,1) for v in r['flags']) for r in rows)
    events=[e['operation'] for e in actual.get('events',[]) if e.get('year')==policy['year'] and e.get('table')==policy['table']]
    return [result('SSI-CONSOLIDATION','One row per SSN; 42 flags; any positive source flag becomes 1',valid,{'source_rows':len(source_rows),'expected_rows':len(expected),'actual_rows':len(rows)}),
            result('SSI-TABLE-POLICY','Approved annual table and ordered delete/create evidence',actual.get('table')==policy['table'] and 'DELETE_TABLE' in events and 'CREATE_TABLE' in events and events.index('DELETE_TABLE')<events.index('CREATE_TABLE'),{'matching_event_count':len(events)})]


def validate_daily_ingestion(source_rows=None, actual=None, policy=None):
    if source_rows is None or actual is None or policy is None:
        return [unavailable('DAILY-INGESTION','Source claim metadata, actual object/schedule export and approved bucket/cron policy')]
    expected={}
    for row in source_rows:
        day=parse_date(row['stay_thru_date'])
        digit=str(row['claim_sequence_last_digit']);host=str(row['cwf_host'])
        if len(digit)!=1 or not digit.isdigit() or not host:raise ValueError('Missing partition operands')
        expected[str(row['claim_id'])]=f'{digit}{host}/year={day.year:04}/month={day.month:02}/day={day.day:02}/'
    objects=actual['objects'];matched=[]
    for index,obj in enumerate(objects):
        path=expected.get(str(obj['claim_id']))
        if path is None or obj['partition_path']!=path or obj['bucket']!=policy['bucket']:matched.append(index+1)
    valid=not matched and {str(o['claim_id']) for o in objects}==set(expected) and len(objects)==len(expected)
    return [result('INGESTION-PARTITIONS','Exactly one object per source claim, approved bucket, and stay-through-date partition',valid,{'expected_objects':len(expected),'actual_objects':len(objects),'mismatched_row_numbers':matched}),
            result('INGESTION-SCHEDULE','Approved nightly cron specification in actual schedule export',actual.get('schedule_cron')==policy['schedule_cron'],{'schedule_matches':actual.get('schedule_cron')==policy['schedule_cron']})]


def validate_historical_transfer(golden=None, actual=None, policy=None):
    if golden is None or actual is None or policy is None:
        return [unavailable('HISTORICAL-TRANSFER','Approved 14-file mainframe byte/JSON golden bundle, JSON schema and actual conversion/promotion export')]
    expected=golden['files'];observed=actual['files']
    parity=set(expected)==set(observed) and len(expected)==len(observed)==14 and all(expected[name]['bytes']==observed[name]['bytes'] and expected[name]['json']==observed[name]['json'] for name in expected)
    types={'string':str,'integer':int,'number':(int,float),'array':list,'object':dict,'boolean':bool}
    invalid=[]
    for name,file in observed.items():
        row=file['json']
        if not isinstance(row,dict) or any(field not in row or not isinstance(row[field],types[kind]) or kind=='integer' and isinstance(row[field],bool) for field,kind in policy['required_schema'].items()):invalid.append(name)
    promotion=actual.get('promotion',{})
    return [result('HISTORICAL-BUNDLE-PARITY','All 14 files match independent mainframe byte and logical JSON goldens',parity,{'golden_files':len(expected),'actual_files':len(observed)}),
            result('HISTORICAL-JSON-SCHEMA','Required field/type contract supplied in approved schema',not invalid,{'invalid_file_count':len(invalid)}),
            result('HISTORICAL-PROMOTION','IMPL to PROD with independently approved source bundle digest',promotion.get('from')=='IMPL' and promotion.get('to')=='PROD' and promotion.get('source_sha256')==policy['bundle_sha256'],{'promotion_matches':promotion.get('source_sha256')==policy['bundle_sha256']})]


def validate_logging(source_policy=None, actual=None):
    if source_policy is None or actual is None:
        return [unavailable('ERROR-LOGGING','Approved source correlation IDs, sensitive tokens, sink/retention/alarm policy and actual sink event exports')]
    expected_ids=set(source_policy['correlation_ids']);invalid=[];leaks=[];counts={}
    for sink in source_policy['sinks']:
        rows=actual.get('sink_events',{}).get(sink,[]);counts[sink]=len(rows)
        observed=set()
        for index,row in enumerate(rows):
            try:
                if not isinstance(row,dict) or not all(row.get(k) for k in ('timestamp','level','correlation_id','message')):raise ValueError('Missing JSON log field')
                datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
                observed.add(row['correlation_id'])
            except (TypeError,ValueError):invalid.append((sink,index+1))
            raw=json.dumps(row)
            if any(token and token in raw for token in source_policy['sensitive_tokens']):leaks.append((sink,index+1))
        if observed!=expected_ids:invalid.append((sink,'correlation coverage'))
    return [result('LOG-JSON-CORRELATION','Structured events and all expected correlation IDs delivered to each required sink',not invalid,{'sink_event_counts':counts,'invalid_event_locations':invalid}),
            result('LOG-PII-REDACTION','Independent sensitive source tokens absent from exported event payloads',not leaks,{'unredacted_event_locations':leaks}),
            result('LOG-RETENTION-ALARMS','Approved retention and required alarm policies',actual.get('retention_days')==source_policy['retention_days'] and set(source_policy['alarms']).issubset(actual.get('alarms',[])),{'retention_matches':actual.get('retention_days')==source_policy['retention_days']})]
