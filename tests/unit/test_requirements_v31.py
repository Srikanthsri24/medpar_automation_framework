from decimal import Decimal
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.stay.requirements_v31 import validate_stay_calculations
from medpar_qa.stages.intermediate.revenue_totals import revenue_total
from medpar_qa.stages.intermediate.business_rules import whole_dollars
from medpar_qa.stages.split.settings import SplitSettings
from medpar_qa.reporting.status_navigation import number_file_tables


def test_stay_formula_and_highest_span_use_all_bills(resolver,make_record):
    bills=[]
    for row,end in enumerate(('20260120','20260110'),1):
        bills.append(make_record(dict(transactionCode=4,claimPaymentAmount='10.24975',primary_payment_amount='1',coinsuranceAmount='2',inPatientDeduction='3',bloodDeductable='4',outlierAmount='5',occurrenceSpanLines=[dict(spanCode='22',thruDate=end)]),row=row,stage=Stage.STAY))
    output=make_record({'MEDPAR-DRG-PRICE-0380':'31','MEDPAR-DTE-CR-ENDED-0220':'2026020','billCount':2},stage=Stage.STAY)
    checks=validate_stay_calculations(bills,output,resolver)
    for rule in ('ST-DRG-PRICE-CALCULATION','ST-COVERED-CARE-END','ST-MERGED-BILL-COUNT'):
        assert next(c for c in checks if c.rule_id==rule).status==ValidationStatus.PASS
    output.data['billCount']=1
    assert next(c for c in validate_stay_calculations(bills,output,resolver) if c.rule_id=='ST-MERGED-BILL-COUNT').status==ValidationStatus.FAIL


def test_missing_price_operands_blocks_populated_output(resolver,make_record):
    output=make_record({'MEDPAR-DRG-PRICE-0380':1},stage=Stage.STAY)
    c=next(c for c in validate_stay_calculations([make_record({})],output,resolver) if c.rule_id=='ST-DRG-PRICE-CALCULATION')
    assert c.status==ValidationStatus.BLOCKED


def test_revenue_accumulation_rounds_after_sum():
    assert revenue_total([dict(revenueCode='0270',totalCharge='0.24975'),dict(revenueCode='0270',totalCharge='0.24975'),dict(revenueCode='0280',totalCharge='100')],270,270)==1
    assert whole_dollars('-0.4995')==Decimal('-1')


def test_split_identity_keeps_distinct_icns():
    assert 'icn' in SplitSettings().identity_fields and 'query_code' in SplitSettings().identity_fields


def test_serial_numbers_restart_per_table():
    text=number_file_tables('<table><tr><th>File</th></tr><tr data-file="a"><td>a</td></tr><tr data-file="b"><td>b</td></tr></table>')
    assert '<th>No.</th>' in text and '<td>1</td>' in text and '<td>2</td>' in text


def test_original_fields_detect_missing_and_changed_values(resolver,make_record):
    from medpar_qa.stages.preservation import unchanged_fields
    source=make_record({'transactionCode':1,'provider':{'providerId':'100001'},'totalCharges':'12'})
    target=make_record({'transactionCode':1,'providerId':'100001','totalCharges':'13'})
    c=unchanged_fields(Stage.SPLIT,source,target,resolver,'TEST')
    assert c.status==ValidationStatus.FAIL
    assert c.evidence['differences']=={'totalCharges':{'expected':'12','observed':'13'}}


def test_revenue_merge_keeps_dates_separate_and_sums_occurrences():
    from medpar_qa.stages.stay.revenue_merge import aggregate_revenue
    rows=[dict(code='0270',serviceDate='20260101',units=1,charges='2'),dict(code='0270',serviceDate='20260101',units=2,charges='3'),dict(code='0270',serviceDate='20260102',units=1,charges='4')]
    result=aggregate_revenue(rows)
    assert len(result)==2 and Decimal(result[0]['charges'])==5 and Decimal(result[0]['units'])==3


def test_revised_tree_rule2_needs_sequence_not_latest_accretion(resolver,make_record):
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    records=[make_record(dict(hicn='H',providerId='100001',stayFromDate='20260101',stayThruDate='20260102',queryCode=qc,transactionCode=1,internalControlNumber=str(i),processingDate=f'202601{20-i:02}',accreteDate=f'202601{10+i:02}'),row=i+1) for i,qc in enumerate((5,0,3))]
    c=FinalActionProcessor(resolver).validate_group(records)
    assert c.passed and {d.rule_id for d in c.decisions}=={'FA-RULE-02'}


def test_final_action_year_minus_five_window(resolver,make_record):
    from datetime import date
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    def record(day):return make_record(dict(hicn='H',providerId='100001',stayFromDate=day,stayThruDate=day,queryCode=1,transactionCode=1,internalControlNumber='A',processingDate='20260120'))
    processor=FinalActionProcessor(resolver,run_date=date(2026,3,20))
    assert processor.validate_group([record('20210101')]).passed
    assert any(c.rule_id=='FA-INPUT-WINDOW' and c.status==ValidationStatus.FAIL for c in processor.validate_group([record('20201231')]).rule_results)


def test_processing_quarter_y0_and_explicit_override(resolver):
    from datetime import date
    from medpar_qa.stages.split.processor import SplitProcessor
    assert SplitProcessor(resolver,date(2026,3,20),settings=SplitSettings(processing_quarter='2026Q1')).reference_year()==2025
    assert SplitProcessor(resolver,date(2026,3,20),settings=SplitSettings(processing_quarter='2026Q2')).reference_year()==2026
    assert SplitProcessor(resolver,date(2026,3,20),settings=SplitSettings(processing_quarter='2026Q1',current_year=2024)).reference_year()==2024


def test_unique_non_cancelled_icn_keeps_newest_per_distinct_icn(resolver,make_record):
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    from medpar_qa.enums import RecordDecision
    records=[make_record(dict(hicn='H',providerId='100001',stayFromDate='20260101',stayThruDate='20260102',queryCode=qc,transactionCode=1,internalControlNumber=icn,processingDate=f'202601{20-i:02}'),row=i+1) for i,(qc,icn) in enumerate(((1,'A'),(1,'A'),(3,'B'),(0,'C')))]
    result=FinalActionProcessor(resolver).validate_group(records)
    kept={d.record_id for d in result.decisions if d.decision==RecordDecision.KEEP}
    assert kept=={'record-1','record-3'}


def test_output_segments_are_validated_not_arbitrarily_deduplicated(resolver,make_record):
    from medpar_qa.stages.stay.revenue_merge import coalesce_segments
    first=make_record(dict(hicn='H',providerId='100001',admissionDate='20260101',revenueLines=[dict(code='0270',charges=1)]*45),row=1,stage=Stage.STAY)
    last=make_record(dict(hicn='H',providerId='100001',admissionDate='20260101',revenueLines=[dict(code='0271',charges=2)]),row=2,stage=Stage.STAY)
    records,checks=coalesce_segments([first,last],resolver,('hicn','provider_id','admission_date'))
    assert len(records)==1 and len(records[0].data['revenueLines'])==46 and checks[0].status==ValidationStatus.PASS
    last.data['providerId']='OTHER'
    records,checks=coalesce_segments([first,last],resolver,('hicn','provider_id','admission_date'))
    assert len(records)==2 and not checks


def test_missing_final_action_output_is_attributed_to_source(resolver,make_record):
    from medpar_qa.stages.final_action.reconciler import reconcile_actual_output
    from medpar_qa.stages.final_action.settings import FinalActionSettings
    from medpar_qa.models import ClaimDecision
    from medpar_qa.enums import RecordDecision
    source=make_record(dict(claimCan='CAN',internalControlNumber='A',queryCode=1,processingDate='20260101',accreteDate='20260102'),file_name='input.json')
    c=reconcile_actual_output([source],[],[ClaimDecision(source.record_id,RecordDecision.KEEP,'R','keep')],resolver,FinalActionSettings())
    assert c.status==ValidationStatus.FAIL and 'input.json' in c.source_files


def test_unreadable_source_is_counted_as_one_failed_input():
    from medpar_qa.reporting.stage_volume import summarize_stage_volume
    checks=[dict(rule_id='INGEST-DISCOVERY',status='PASS',evidence={'role':'source'},actual=['broken.json'],source_files=['broken.json']),dict(rule_id='INGEST-READ-FILE',status='FAIL',evidence={'role':'source'},actual={'file':'broken.json','error':'Invalid JSON'},source_files=['broken.json'])]
    result=summarize_stage_volume(checks)
    assert (result['files_in'],result['files_passed'],result['files_failed'])==(1,0,1)


def test_stay_warning08_prefers_matched_edb_dod(resolver,make_record):
    from medpar_qa.stages.stay.warnings import warning08
    r=make_record(dict(hicn='H',providerId='100001',admissionDate='20260102',stayFromDate='20260102',stayThruDate='20260105',processingDate='20260110',queryCode=1,dateOfDeath='20260201',dod_reference_available=True,matched_date_of_death='20260101'))
    assert warning08([r],resolver)=='2'


def test_dropped_net_indicator_has_real_episode_proof(resolver,make_record):
    from medpar_qa.stages.final_action.dropped_output import validate_dropped_output
    from medpar_qa.stages.final_action.settings import FinalActionSettings
    from medpar_qa.enums import RecordDecision
    from medpar_qa.models import ClaimDecision
    common=dict(hicn='H',claimCan='C',providerId='100001',stayFromDate='20260101',stayThruDate='20260102',internalControlNumber='A',processingDate='20260110',transactionCode=1)
    sources=[make_record({**common,'queryCode':qc},row=i+1) for i,qc in enumerate((0,5))]
    actuals=[make_record({**r.data,'netIndicator':3},row=i+3) for i,r in enumerate(sources)]
    decisions=[ClaimDecision(r.record_id,RecordDecision.DROP,'R','drop') for r in sources]
    checks=validate_dropped_output(sources,actuals,decisions,resolver,FinalActionSettings())
    assert all(c.status==ValidationStatus.PASS for c in checks)
    net=next(c for c in checks if c.rule_id=='FA-DROPPED-NET-INDICATOR')
    assert net.expected==3 and net.evidence['episode_query_codes']==['0','5']


def test_ssi_export_merges_duplicates_and_checks_recreate_order():
    from medpar_qa.infrastructure_validation import validate_ssi_export
    source=[dict(ssn='DEMO',flags=[0]*41+[2]),dict(ssn='DEMO',flags=[1]+[0]*41)]
    actual=dict(table='mpr-ssi-demo',rows=[dict(ssn='DEMO',flags=[1]+[0]*40+[1])],events=[dict(operation=op,table='mpr-ssi-demo',year=2026) for op in ('DELETE_TABLE','CREATE_TABLE')])
    assert all(c['status']=='PASS' for c in validate_ssi_export(source,actual,dict(table='mpr-ssi-demo',year=2026)))
    actual['rows'][0]['flags'][-1]=0
    assert validate_ssi_export(source,actual,dict(table='mpr-ssi-demo',year=2026))[0]['status']=='FAIL'


def test_ingestion_partition_uses_thru_date_not_run_date():
    from medpar_qa.infrastructure_validation import validate_daily_ingestion
    rows=[dict(claim_id='DEMO',stay_thru_date='20251231',claim_sequence_last_digit=7,cwf_host='A')]
    actual=dict(schedule_cron='approved',objects=[dict(claim_id='DEMO',partition_path='7A/year=2025/month=12/day=31/',bucket='approved')])
    policy=dict(schedule_cron='approved',bucket='approved')
    assert all(c['status']=='PASS' for c in validate_daily_ingestion(rows,actual,policy))
    actual['objects'][0]['partition_path']='7A/year=2026/month=01/day=01/'
    assert validate_daily_ingestion(rows,actual,policy)[0]['status']=='FAIL'


def test_missing_external_exports_are_blocked():
    from medpar_qa.infrastructure_validation import validate_ssi_export,validate_daily_ingestion,validate_historical_transfer,validate_logging
    for function in (validate_ssi_export,validate_daily_ingestion,validate_historical_transfer,validate_logging):assert function()[0]['status']=='BLOCKED'


def test_logging_checks_payload_not_claimed_redaction_flag():
    from medpar_qa.infrastructure_validation import validate_logging
    policy=dict(correlation_ids=['demo'],sinks=['CloudWatch','Splunk'],sensitive_tokens=['DEMO-SENSITIVE'],retention_days=30,alarms=['failed-run'])
    row=dict(timestamp='2026-10-14T00:00:00+05:30',level='ERROR',correlation_id='demo',message='[REDACTED]')
    actual=dict(sink_events={sink:[dict(row)] for sink in policy['sinks']},retention_days=30,alarms=['failed-run'])
    assert all(c['status']=='PASS' for c in validate_logging(policy,actual))
    actual['sink_events']['Splunk'][0]['message']='DEMO-SENSITIVE';actual['pii_redacted']=True
    assert validate_logging(policy,actual)[1]['status']=='FAIL'


def test_ambiguous_or_range_needs_mapping_and_rounds_after_all_ranges(resolver,make_record):
    from medpar_qa.stages.intermediate.business_rules import validate_business_rules
    source=make_record({'revenueLines':[dict(code='0360',charges='0.24975'),dict(code='0710',charges='0.24975')]},stage=Stage.INTERMEDIATE)
    target=make_record({'MEDPAR-OPRTG-ROOM-AMT-1100':'1'},stage=Stage.INTERMEDIATE)
    checks=validate_business_rules(source,target,resolver)
    assert next(c for c in checks if c.field_name=='medpar_oprtg_room_amt_1100').status==ValidationStatus.BLOCKED
    checks=validate_business_rules(source,target,resolver,revenue_category_ranges={'medpar_oprtg_room_amt_1100':[(360,369),(710,719)]})
    assert next(c for c in checks if c.field_name=='medpar_oprtg_room_amt_1100').status==ValidationStatus.PASS


def test_fa_grouping_uses_exact_ric_even_when_transaction_is_deferred(resolver,make_record):
    from medpar_qa.stages.final_action.grouping import build_group_key
    base=dict(hicn='H',providerId='100001',stayFromDate='20260101',stayThruDate='20260102',transactionCode='C')
    a=make_record({**base,'nchNearLineRIC':{'code':'1'}})
    b=make_record({**base,'nchNearLineRIC':{'code':'2'}})
    assert build_group_key(a,resolver,validate_transaction_codes=False)!=build_group_key(b,resolver,validate_transaction_codes=False)


def test_split_balance_lists_year_quarter_and_outside_categories(resolver,make_record):
    from datetime import date
    from medpar_qa.stages.split.processor import SplitProcessor
    records=[make_record(dict(claimCan=str(i),hicn='H',providerId='100001',internalControlNumber=str(i),queryCode=1,transactionCode=1,stayFromDate=day,stayThruDate=day,totalCharges=amount),row=i+1,stage=Stage.SPLIT) for i,(day,amount) in enumerate((('20260101','10'),('20251001','20'),('20200101','30')))]
    result=SplitProcessor(resolver,date(2026,4,20)).validate(records)
    check=next(c for c in result.rule_results if c.rule_id=='SP-INDICATOR-BALANCE')
    assert check.status==ValidationStatus.PASS
    assert check.actual['categories']=={'Y00109':{'records':1,'charges':'10'},'Y11012':{'records':1,'charges':'20'},'Y99999':{'records':1,'charges':'30'}}
    assert check.expected['source_charges']=='60' and check.actual['accounted_records']==3


def test_simultaneous_run_sessions_do_not_merge_reports(tmp_path):
    from datetime import datetime
    from medpar_qa.reporting.run_layout import ReportSession
    moment=datetime(2026,10,14,1,0,0)
    first=ReportSession.create(project_root=tmp_path,moment=moment)
    second=ReportSession.create(project_root=tmp_path,moment=moment)
    assert first.root != second.root
    assert second.timestamp=='20261014_010000_02'
    shared=ReportSession.create(session_path=first.root.relative_to(tmp_path),project_root=tmp_path,moment=moment)
    assert shared.root==first.root


import pytest


@pytest.mark.parametrize('pairs,rule_id',[
    ([(0,'C'),(0,'D'),(0,'E'),(1,'A'),(1,'A'),(3,'B')],'FA-RULE-07'),
    ([(0,'C'),(1,'A'),(1,'A'),(3,'B')],'FA-RULE-08'),
    ([(1,'A'),(1,'A'),(3,'B')],'FA-RULE-09'),
    ([(0,'C'),(0,'D'),(5,'A'),(1,'A'),(3,'B')],'FA-RULE-10A'),
])
def test_each_distinct_icn_route_keeps_newest_a_and_b(resolver,make_record,pairs,rule_id):
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    from medpar_qa.enums import RecordDecision
    records=[make_record(dict(hicn='H',providerId='100001',stayFromDate='20260101',stayThruDate='20260102',queryCode=qc,transactionCode=1,internalControlNumber=icn,processingDate=f'202601{25-i:02}'),row=i+1) for i,(qc,icn) in enumerate(pairs)]
    result=FinalActionProcessor(resolver).validate_group(records)
    assert result.passed and {d.rule_id for d in result.decisions}=={rule_id}
    kept={d.record_id for d in result.decisions if d.decision==RecordDecision.KEEP}
    assert kept=={next(r.record_id for r in records if r.data['internalControlNumber']=='A'),next(r.record_id for r in records if r.data['internalControlNumber']=='B')}
