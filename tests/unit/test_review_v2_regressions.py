"""Reproduce review defects and prove source-driven checks without changing input data."""
from datetime import date
import json
from pathlib import Path
import pytest
from medpar_qa.enums import Stage, RecordDecision, ValidationStatus
from medpar_qa.stages.final_action.processor import FinalActionProcessor
from medpar_qa.stages.split.processor import SplitProcessor
from medpar_qa.stages.split.settings import SplitSettings
from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
from medpar_qa.stages.final_medpar.settings import FinalMedparSettings
from medpar_qa.stages.stay.warnings import warning06, warning08
from medpar_qa.stages.stay.code_precedence import latest_values_by_code
from medpar_qa.stages.final_medpar.archive_audit import audit_archive
from test_final_action import base_claim


@pytest.mark.parametrize('qc0_first', [False, True])
@pytest.mark.parametrize('ricid', [None, 1])
def test_rule6_mixed_valid_invalid_transaction_cancels_pair(resolver, make_record, qc0_first, ricid):
    data = [base_claim(queryCode=5, transactionCode=1, internalControlNumber='SAME'),
            base_claim(queryCode=0, transactionCode='C', internalControlNumber='SAME', actionCode=4,
                       nchWeeklyProcessingDate='20260112' if qc0_first else '20260109')]
    if ricid is not None:
        for claim in data: claim['ricid'] = ricid
    records = [make_record(claim, row=i+1) for i,claim in enumerate(data)]
    result = FinalActionProcessor(resolver).validate(records)
    assert len(result.decisions) == 2
    assert all(d.rule_id == 'FA-RULE-06' and d.decision == RecordDecision.DROP for d in result.decisions)


@pytest.mark.parametrize('action', [1, 2, ' 4 ', 6])
def test_rule6_same_icn_action_branches(resolver, make_record, action):
    records = [make_record(base_claim(queryCode=5, internalControlNumber='SAME')),
               make_record(base_claim(queryCode=0, internalControlNumber='SAME', actionCode=action),row=2)]
    result = FinalActionProcessor(resolver).validate(records)
    assert {d.rule_id for d in result.decisions} == {'FA-RULE-06'}
    assert sum(d.decision == RecordDecision.KEEP for d in result.decisions) == (0 if str(action).strip() in ('4', '6') else 1)


def test_deferred_validation_is_disclosed_known_difference(resolver, make_record):
    result = FinalActionProcessor(resolver).validate([make_record(base_claim())])
    waiver = next(r for r in result.rule_results if r.rule_id == 'FA-TRANSACTION-CHECK-DISABLED')
    assert waiver.status == ValidationStatus.KNOWN_DIFFERENCE
    assert waiver.evidence['cms_approval'] == 'Not supplied'


def test_explicit_split_y0_last_complete_year(resolver, make_record):
    processor = SplitProcessor(resolver, date(2026, 3, 20), settings=SplitSettings(current_year=2025))
    assert processor.calculate_indicator(make_record(base_claim(stayFromDate='20250101', stayThruDate='20250105'))) == 'Y00109'
    assert processor.calculate_indicator(make_record(base_claim())) == 'Y99999'


@pytest.mark.parametrize('reason,expected', [('C','3'),('P','4'),('S','5'),('D','6'),('H','7'),('L','8')])
def test_warning06_cancel_reason_overrides_action(resolver, make_record, reason, expected):
    assert warning06([make_record(base_claim(actionCode=4, cancelReasonCode=reason))], resolver) == expected


@pytest.mark.parametrize('duplicates,death,expected', [(False,None,'0'), (True,None,'1'), (False,'20251231','2'),(True,'20251231','3')])
def test_warning08_all_documented_branches(resolver, make_record, duplicates, death, expected):
    data = base_claim(admissionDate='20260101')
    if death: data['dateOfDeath'] = death
    records = [make_record(data)]
    if duplicates: records.append(make_record(dict(data)))
    assert warning08(records, resolver) == expected


def test_latest_duplicate_code_uses_query_then_icn(resolver, make_record):
    older = make_record(base_claim(queryCode=1, conditionCodes=[{'code':'04','value':'old'}]))
    newer = make_record(base_claim(queryCode=5, conditionCodes=[{'code':'04','value':'new'}]))
    assert latest_values_by_code([older,newer],collection_path='condition_codes',date_paths=('processing_date','accrete_date'),resolver=resolver)[0]['value'] == 'new'


def test_final_delivered_extract_omits_indicator(resolver, make_record):
    data = base_claim(admissionDate='20260101', medparSSLSSNFIND0140='S')
    processor = FinalMedparProcessor(resolver, settings=FinalMedparSettings(split_indicator_in_output=False))
    check = next(r for r in processor._validate_record(make_record(data, stage=Stage.FINAL_MEDPAR)) if r.rule_id == "FM-SPLIT-YEAR-INDICATOR")
    assert check.status == ValidationStatus.PASS
    data['medparSplitYearIndicator']='Y00109'
    assert next(r for r in processor._validate_record(make_record(data,stage=Stage.FINAL_MEDPAR)) if r.rule_id == "FM-SPLIT-YEAR-INDICATOR").status == ValidationStatus.FAIL


def test_archive_exact_lineage_and_route_defect_detection(tmp_path,resolver):
    intermediate={'medparSSANo0021':'DEMO','medparBicCode0022':'A','medparProvider0130':'999999',
                  'medparAdmDate0200':'20240101','medparSplitYearIndicator':'Y00109','medparSSLSSNFIND0140':'S',
                  'medparCovDays0280':1,'medparLgthStay0260':1,'medparSSIData0251':0,'medparSSIData0252':'N','medparPrvdrBaseFacCcn1650':'999999'}
    source=tmp_path/'5-intermediate-processing/input.json';source.parent.mkdir();source.write_text(json.dumps(intermediate))
    final={k:v for k,v in intermediate.items() if k!='medparSplitYearIndicator'}
    for period in ('CY','FY'):
        path=tmp_path/f'6-final-processing/MEDPAR_FINAL_SS_FILES/{period}/2024/record.json'
        path.parent.mkdir(parents=True);path.write_text(json.dumps(final))
    result=audit_archive(tmp_path,current_year=2024,resolver=resolver)
    assert not any(r.status==ValidationStatus.FAIL for r in result.rule_results)
    path.write_text(json.dumps(dict(final,medparProvider0130='888888')))
    result=audit_archive(tmp_path,current_year=2024,resolver=resolver)
    assert any(r.rule_id=='FM-ARCHIVE-EXACT-LINEAGE' and r.status==ValidationStatus.FAIL for r in result.rule_results)
    assert any(r.rule_id=='FM-ARCHIVE-ROUTE-COMPLETENESS' and r.status==ValidationStatus.FAIL for r in result.rule_results)


def test_ld3188_scope_accepts_only_rule10b_qc5_tie(resolver, make_record):
    records = [make_record(base_claim(queryCode=5,internalControlNumber=icn)) for icn in ('A','B')]
    records.append(make_record(base_claim(queryCode=1,internalControlNumber='C',nchWeeklyProcessingDate='20260101')))
    result = FinalActionProcessor(resolver).validate(records)
    assert not any(r.rule_id == 'FA-PRE-ORDERING' for r in result.rule_results)
    assert {d.rule_id for d in result.decisions} == {'FA-RULE-10B'}
    other = [make_record(base_claim(queryCode=1,internalControlNumber=icn),row=i+1) for i,icn in enumerate(('A','B'))]
    result = FinalActionProcessor(resolver).validate(other)
    assert result.passed
    assert result.decisions


@pytest.mark.parametrize('payment,charge,primary,days,expected', [(10,20,0,1,'0'),(-10,-20,0,1,'1'),(-10,20,0,1,'2'),(10,-20,0,1,'3'),(0,0,0,0,'4')])
def test_warning03_documented_branches(resolver,make_record,payment,charge,primary,days,expected):
    from medpar_qa.stages.intermediate.business_rules import validate_business_rules
    source=make_record(base_claim(admissionDate='20260101',medicarePaymentAmount=payment,
        medpar_tot_chrg_0400=charge,primary_payment_amount=primary,utilization_days=days),stage=Stage.INTERMEDIATE)
    target=make_record(base_claim(warning_indicator_03=expected),stage=Stage.INTERMEDIATE)
    checks=validate_business_rules(source,target,resolver)
    check=next(r for r in checks if r.rule_id=='INT-WARNING-03-CALCULATION')
    assert check.status==ValidationStatus.PASS
    target.data['warning_indicator_03']='9'
    check=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-WARNING-03-CALCULATION')
    assert check.status==ValidationStatus.FAIL


@pytest.mark.parametrize('state,county,expected',[(True,True,'0'),(False,False,'1'),(False,True,'2'),(True,False,'3')])
def test_warning07_approved_range_results(resolver,make_record,state,county,expected):
    from medpar_qa.stages.intermediate.business_rules import validate_business_rules
    source=make_record(base_claim(state_code_valid=state,county_code_valid=county),stage=Stage.INTERMEDIATE)
    target=make_record(base_claim(warning_indicator_07=expected),stage=Stage.INTERMEDIATE)
    check=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-WARNING-07-CALCULATION')
    assert check.status==ValidationStatus.PASS
    source.data.pop('state_code_valid')
    check=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-WARNING-07-CALCULATION')
    assert check.status==ValidationStatus.BLOCKED


@pytest.mark.parametrize('flag,expected',[(True,'1'),(False,'0')])
def test_warning02_explicit_edit_table_mapping(resolver,make_record,flag,expected):
    from medpar_qa.stages.intermediate.business_rules import validate_business_rules
    source=make_record(base_claim(edit_error_present=flag),stage=Stage.INTERMEDIATE)
    target=make_record(base_claim(warning_indicator_02=expected),stage=Stage.INTERMEDIATE)
    check=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-WARNING-02-CALCULATION')
    assert check.status==ValidationStatus.PASS


def test_tree_rule10a_policy_is_explicit(resolver,make_record):
    from medpar_qa.stages.final_action.settings import FinalActionSettings
    records=[make_record(base_claim(queryCode=5, internalControlNumber='DEBIT'))]
    records += [make_record(base_claim(queryCode=0, internalControlNumber=str(i),nchWeeklyProcessingDate=f'2026010{9-i}'),row=i+2) for i in range(2)]
    requirements=FinalActionProcessor(resolver,FinalActionSettings(rule10a_requires_latest_qc0=False)).validate(records)
    tree=FinalActionProcessor(resolver,FinalActionSettings(rule10a_requires_latest_qc0=True)).validate(records)
    assert {d.rule_id for d in requirements.decisions} == {'FA-RULE-10A'}
    assert {d.rule_id for d in tree.decisions} == {'FA-RULE-10B'}


def test_export_dedup_preserves_differing_business_data(make_record):
    from medpar_qa.stages.intermediate.export_duplicates import deduplicate_exports
    first=make_record({'filename':'job1','amount':5},file_name='job1/a.json')
    second=make_record({'filename':'job2','amount':5},file_name='job2/a.json',row=2)
    records,proof=deduplicate_exports([second,first])
    assert records == [first]
    assert proof.actual['duplicate_export_copies'] == 1
    second.data['amount']=6
    records,proof=deduplicate_exports([first,second])
    assert len(records)==2 and proof is None
    second.data['amount']=5
    second=make_record(second.data,file_name=first.source.file_path,row=2)
    records,proof=deduplicate_exports([first,second])
    assert len(records)==2 and proof is None


def test_hicn_from_final_account_and_bic(resolver):
    assert resolver.get({'medparSSANo0021':'DEMO00001','medparBicCode0022':'A'},'hicn') == 'DEMO00001A'


def test_final_action_missing_stay_through_date_is_reported_without_crash(resolver, make_record):
    from medpar_qa.stages.final_action.settings import FinalActionSettings
    claim = base_claim(stayThruDate=None)
    result = FinalActionProcessor(resolver, FinalActionSettings(enforce_single_service_year=True)).validate([make_record(claim)])
    assert not result.passed
    assert any(check.status == ValidationStatus.FAIL for check in result.rule_results)


def test_archive_field_defect_links_only_exact_matching_final_files(tmp_path,resolver):
    intermediate={'medparSSANo0021':'DEMO','medparBicCode0022':'A','medparProvider0130':'999999','medparAdmDate0200':'20240101','medparSplitYearIndicator':'Y00109','medparSSLSSNFIND0140':'S','medparCovDays0280':1,'medparLgthStay0260':1,'medparSSIData0251':'','medparSSIData0252':'N','medparPrvdrBaseFacCcn1650':'999999'}
    source=tmp_path/'5-intermediate-processing/input.json';source.parent.mkdir();source.write_text(json.dumps(intermediate))
    final=tmp_path/'6-final-processing/MEDPAR_FINAL_SS_FILES/CY/2024/record.json';final.parent.mkdir(parents=True);final.write_text(json.dumps({k:v for k,v in intermediate.items() if k!='medparSplitYearIndicator'}))
    result=audit_archive(tmp_path,current_year=2024,resolver=resolver)
    check=next(check for check in result.rule_results if check.rule_id=='FM-ARCHIVE-SSI-DAYS-DOMAIN')
    assert check.status==ValidationStatus.FAIL
    assert set(check.source_files)=={str(source),str(final)}
