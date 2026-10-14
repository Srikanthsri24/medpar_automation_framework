"""Literal business examples for source-driven output calculations and exclusions."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from medpar_qa.enums import Stage
from medpar_qa.processing import writers
from medpar_qa.stages.stay.processor import StayProcessor
from medpar_qa.stages.intermediate.processor import IntermediateProcessor
from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor


def bill(**extra):
    return dict(hicn='DEMO',providerId='990999',admissionDate='20260101',stayFromDate='20260101',stayThruDate='20260103',processingDate='20260105',queryCode=1,internalControlNumber='A',transactionCode=1,patientStatus='01',claimPaymentAmount='10',primary_payment_amount='2',coinsuranceAmount='1',inPatientDeduction='3',bloodDeductable='4',outlierAmount='5',totalCharges='20',utilization_days=2,conditionCodes=[],occurrenceCodes=[],occurrenceSpanLines=[],valueLines=[],revenueLines=[dict(code='0270',charges='10',nonCoveredCharge='2')],**extra)


def test_stay_sums_bills_and_revenue_with_literal_expected_values(resolver,make_record):
    first=make_record(bill(),row=1,stage=Stage.STAY)
    second=make_record({**bill(),'internalControlNumber':'B','processingDate':'20260106','totalCharges':'30'},row=2,stage=Stage.STAY)
    payload,notes=writers.stay([first,second],StayProcessor(resolver))
    assert len(payload)==1
    row=payload[0]
    assert resolver.get(row,'bill_count')==2
    assert Decimal(resolver.get(row,'totalCharges'))==50
    assert Decimal(resolver.get(row,'medpar_drg_price_0380'))==30
    assert Decimal(resolver.get(row,'revenue_lines')[0]['charges'])==20
    assert Decimal(resolver.get(row,'revenue_lines')[0]['nonCoveredCharge'])==4


def test_intermediate_clinical_arrays_and_revenue_total_are_derived(resolver,make_record):
    source=make_record(bill(procedureLines=[dict(code='0ABC',version='0',procedureDate='20260102')],diagnosisLines=[dict(code='I10',version='0',poa='Y')]),stage=Stage.INTERMEDIATE)
    processor=IntermediateProcessor(resolver,date(2026,4,20))
    rows,notes=writers.intermediate([source],processor)
    row=rows[0]
    assert row['medpar_no_surg_codes_0511']==1 and row['medpar_surg_date_0514']==['2026002']
    assert row['medpar_no_diag_codes_0491']==1 and row['medpar_poa_dgns_ind_cd']==['Y']
    assert Decimal(row['medpar_cov_chrg_0410'])==8
    assert Decimal(row['medpar_tot_dpt_chrg_0440'])==10
    assert Decimal(row['medpar_mdcl_srg_gen_amt_0890'])==10


def test_missing_clinical_version_is_blocked_not_invented(resolver,make_record):
    source=make_record(bill(procedureLines=[dict(code='0ABC',procedureDate='20260102')]),stage=Stage.INTERMEDIATE)
    with pytest.raises(writers.GenerationBlocked,match='source version'):
        writers.intermediate([source],IntermediateProcessor(resolver,date(2026,4,20)))


def test_final_removes_exact_trailer_and_drops_bypass(resolver,make_record):
    source=make_record(dict(providerId='990999',fixed_width_record='A'*3000+'T'*50,utilization_days=2,medpar_lgth_stay_0260=2),stage=Stage.FINAL_MEDPAR)
    bypass=make_record(dict(providerId='990999',utilization_days=3,medpar_lgth_stay_0260=2),row=2,stage=Stage.FINAL_MEDPAR)
    rows,notes,dropped=writers.final_medpar([source,bypass],FinalMedparProcessor(resolver))
    assert len(rows)==1 and rows[0]['fixed_width_record']=='A'*3000
    assert rows[0]['medpar_ss_ls_snf_ind_0140']=='S'
    assert len(dropped)==1 and dropped[0]['source_record_id']==bypass.record_id


def test_accommodation_total_caps_at_documented_maximum(resolver,make_record):
    from medpar_qa.stages.intermediate.structural import validate_accommodation_totals
    from medpar_qa.enums import ValidationStatus
    record=make_record({'medpar_accommodation_chrg_0460':['600000000','600000000'],'medpar_tot_acc_chrg_0430':'999999999'},stage=Stage.INTERMEDIATE)
    assert validate_accommodation_totals(record,resolver,Decimal('0.001')).status==ValidationStatus.PASS


def test_alias_updates_keep_uppercase_source_amount_in_sync(resolver):
    data={'TOTALCHARGES':'10'}
    writers.put(data,'totalCharges',Decimal(30),resolver)
    assert data['TOTALCHARGES']=='30' and data['totalCharges']=='30'


def test_explicit_empty_codes_do_not_reuse_stale_derived_counts(resolver,make_record):
    source=make_record(bill(diagnosisCodes=[],medpar_diag_code_0492=['I10'],medpar_dgns_vrsn_cd=['0'],medpar_poa_dgns_ind_cd=['Y'],medpar_no_diag_codes_0491=1),stage=Stage.INTERMEDIATE)
    with pytest.raises(writers.GenerationBlocked):writers.intermediate([source],IntermediateProcessor(resolver,date(2026,4,20)))


def test_source_demo_calculates_financial_fields_without_expected_files(resolver,make_record):
    import json
    from pathlib import Path
    source=make_record(json.loads(Path('data/demo_source_only/claims.json').read_text())[0],stage=Stage.STAY)
    stays,_=writers.stay([source],StayProcessor(resolver))
    assert Decimal(stays[0]['medpar_drg_price_0380'])==134
    intermediate_source=make_record(stays[0],stage=Stage.INTERMEDIATE)
    rows,notes=writers.intermediate([intermediate_source],IntermediateProcessor(resolver,date(2026,4,20)))
    assert Decimal(rows[0]['medpar_tot_chrg_0400'])==150
    assert Decimal(rows[0]['medpar_cov_chrg_0410'])==140
    assert Decimal(rows[0]['medpar_tot_acc_chrg_0430'])==100
    assert Decimal(rows[0]['medpar_ssi_data_0251'])==4
    assert rows[0]['medpar_no_diag_codes_0491']==1
