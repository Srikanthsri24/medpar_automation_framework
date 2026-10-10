from datetime import date
from decimal import Decimal
import pytest
from medpar_qa.enums import Stage, ValidationStatus, RecordDecision
from medpar_qa.stages.intermediate.business_rules import (
    whole_dollars, length_of_stay, death_after_admission, age_at_admission, validate_business_rules, DIRECT_MOVES)
from medpar_qa.stages.split.processor import SplitProcessor
from medpar_qa.stages.stay.code_precedence import latest_values_by_code, strip_lineage
from medpar_qa.stages.stay.processor import StayProcessor
from medpar_qa.stages.final_medpar.business_rules import compare_final_bytes, validate_trailer_removal, bypass_required


@pytest.mark.parametrize("raw,expected",[("1.499",1),("1.500",2),("-1.500",-2),("-1.499",-1),("0.500",1)])
def test_whole_dollars_ties_away_from_zero(raw,expected):
    assert whole_dollars(raw)==Decimal(expected)


def test_money_positive_overflow_uses_approved_nine_digit_cap():
    assert whole_dollars('1000000000.500') == Decimal('999999999')


@pytest.mark.parametrize('input_field,output_field', DIRECT_MOVES.items())
def test_recovered_document_direct_moves_detect_wrong_output(resolver, make_record, input_field, output_field):
    source=make_record({input_field:'APPROVED'},stage=Stage.INTERMEDIATE)
    target=make_record({output_field:'WRONG'},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver)
              if r.rule_id=='INT-DOCUMENTED-DIRECT-MOVE' and r.field_name==output_field)
    assert rule.status==ValidationStatus.FAIL and rule.expected=='APPROVED'


def test_recovered_aco_position_and_mrn_fallback(resolver,make_record):
    source=make_record({'ngAcoIndicatorCodes':['A','1','2','3','4'],'medicalRecord':' ','patientControl':'PC'},stage=Stage.INTERMEDIATE)
    target=make_record({'medparNgAcoInd1Cd1330':'A','medparNgAcoInd5Cd1370':'4','medparMrn0670':'PC'},stage=Stage.INTERMEDIATE,row=2)
    rules=[r for r in validate_business_rules(source,target,resolver) if r.rule_id in {'INT-DOCUMENTED-ACO-MOVE','INT-MRN-FALLBACK'}]
    assert sum(r.status==ValidationStatus.PASS for r in rules)==3


@pytest.mark.parametrize('can,expected',[('000000005','1'),('000000006','0')])
def test_recovered_five_percent_sample_uses_positions_eight_nine(resolver,make_record,can,expected):
    source=make_record({'claimCan':can},stage=Stage.INTERMEDIATE)
    target=make_record({'meparSample050680':expected},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-FIVE-PERCENT-SAMPLE')
    assert rule.status==ValidationStatus.PASS


@pytest.mark.parametrize('rate,days,expected', [('1.5',2,4),('1.499',2,2),('999999999',2,999999999)])
def test_source_perdiem_rounds_rate_before_days(resolver, make_record, rate, days, expected):
    source=make_record({'passThruPerDiem':rate,'utilizationDays':days},stage=Stage.INTERMEDIATE)
    target=make_record({'medparBillTotPerdiem0381':expected},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-SOURCE-PERDIEM-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_stay_first_nonblank_skips_spaces_and_preserves_zero(resolver,make_record):
    from medpar_qa.stages.stay.merge_rules import validate_merge_rules
    records=[make_record({'stayFromDate':'2026-01-01','stayThruDate':'2026-01-02','uniqueTrackingNumber':'  ','priorAuthorizationIndicator':0},stage=Stage.STAY),
             make_record({'stayFromDate':'2026-01-03','stayThruDate':'2026-01-04','uniqueTrackingNumber':'TRACK','priorAuthorizationIndicator':1},stage=Stage.STAY,row=2)]
    target=make_record({'uniqueTrackingNumber':'TRACK','priorAuthorizationIndicator':0},stage=Stage.STAY,row=3)
    rules=[r for r in validate_merge_rules(records,target,resolver,Decimal('0.001')) if r.rule_id=='ST-FIRST-NONBLANK']
    assert len(rules)==2 and all(r.status==ValidationStatus.PASS for r in rules)


@pytest.mark.parametrize("start,end,status,expected",[("2026-01-01","2026-01-01",20,1),("2026-01-01","2026-01-03",30,3),("2026-01-01","2026-01-03",1,2)])
def test_los_discharge_and_same_day(start,end,status,expected):
    assert length_of_stay(date.fromisoformat(start),date.fromisoformat(end),status)==expected


def test_los_rejects_inverted_dates():
    with pytest.raises(ValueError):
        length_of_stay(date(2026,1,3),date(2026,1,1),1)


def test_death_day_count_and_blank():
    assert death_after_admission(date(2026,1,1),date(2026,1,1))==1
    assert death_after_admission(date(2026,1,1),date(2026,1,4))==3
    assert death_after_admission(date(2026,1,1),None) is None


def test_age_birthday_and_medicare_adjustment():
    assert age_at_admission(date(1961,7,20),date(2026,7,19),"10")==65
    assert age_at_admission(date(1961,7,20),date(2026,7,19),"20")==64
    assert age_at_admission(date(1961,7,20),date(2026,7,20),"20")==65


def test_source_operands_not_replaced_with_target(resolver,make_record):
    source=make_record({},stage=Stage.INTERMEDIATE)
    target=make_record({"medparDrgPrice0380":100},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-DRG-PRICE-CALCULATION")
    assert rule.status==ValidationStatus.BLOCKED


@pytest.mark.parametrize("rev,expected",[("0810","K1"),("0815","H1"),("0819","01")])
def test_organ_highest_valid_type(resolver,make_record,rev,expected):
    source=make_record({"revenueLines":[{"code":"0818"},{"code":rev}]},stage=Stage.INTERMEDIATE)
    target=make_record({"medparOrganInd0487":expected},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-ORGAN-TYPE-CALCULATION")
    assert r.status==ValidationStatus.PASS


def test_organ_yn_is_wrong(resolver,make_record):
    source=make_record({"revenueLines":[{"code":"0819"}]},stage=Stage.INTERMEDIATE)
    target=make_record({"medparOrganInd0487":"Y"},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-ORGAN-TYPE-CALCULATION")
    assert r.status==ValidationStatus.FAIL


def test_value_credits_summed_before_whole_dollar_rounding(resolver,make_record):
    source=make_record({"valueLines":[{"code":"Q1","amount":"-1.25"},{"code":"Q1","amount":"-1.25"}]},stage=Stage.INTERMEDIATE)
    target=make_record({"MEDPAR-VALQ1-PMT-RDCTN-AM-1470":-3},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.field_name=="medpar_val_q1_pmt_rdctn_amt_1470")
    assert r.status==ValidationStatus.PASS
    target.data["MEDPAR-VALQ1-PMT-RDCTN-AM-1470"]=-2.5
    r=next(r for r in validate_business_rules(source,target,resolver) if r.field_name=="medpar_val_q1_pmt_rdctn_amt_1470")
    assert r.status==ValidationStatus.FAIL


def split_bill(make_record,code,row,thru="20260102",admit="20251230"):
    return make_record({"claimCan":f"C{row}","hicn":"H","providerId":"P","admissionDate":admit,
        "stayFromDate":admit,"stayThruDate":thru,"transactionCode":code},row=row,stage=Stage.SPLIT)


def test_split_inpatient_last_thru_and_snf_admission(resolver,make_record):
    p=SplitProcessor(resolver,date(2026,10,11))
    for code,expected in [(1,"Y00109"),(0,"Y11012"),(4,"Y11012")]:
        r=split_bill(make_record,code,1)
        assert p.calculate_indicator(r)==expected
        result=p.validate([r])
        assert result.decisions[0].decision==RecordDecision.KEEP


def test_split_same_stay_all_bills_use_last_thru(resolver,make_record):
    bills=[split_bill(make_record,1,1,thru="20251231"),split_bill(make_record,1,2)]
    result=SplitProcessor(resolver,date(2026,10,11)).validate(bills)
    assert [r.expected for r in result.rule_results if r.rule_id=="SP-RULE-INDICATOR"]==["Y00109","Y00109"]


def test_split_full_year_and_drop_balance(resolver,make_record):
    p=SplitProcessor(resolver,date(2026,7,1))
    assert p.calculate_indicator(split_bill(make_record,1,1,thru="20261231"))=="Y01012"
    result=p.validate([split_bill(make_record,1,1,thru="20220101",admit="20220101"),split_bill(make_record,6,2)])
    balance=next(r for r in result.rule_results if r.rule_id=="SP-RECORD-BALANCE")
    assert balance.actual=={"retained":0,"dropped":1,"exceptions":1}


def test_split_76_bills_retained_and_audited(resolver,make_record):
    result=SplitProcessor(resolver,date(2026,10,11)).validate([split_bill(make_record,1,i) for i in range(76)])
    assert len(result.decisions)==76
    assert next(r for r in result.rule_results if r.rule_id=="SP-STAY-BILL-LIMIT").status==ValidationStatus.PASS


def test_stay_different_admissions_never_merge(resolver,make_record):
    p=StayProcessor(resolver)
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2,admit="20260101")]
    assert len(p._group_sources(bills))==2


def test_span_same_code_different_dates_retained(resolver,make_record):
    records=[make_record({"processingDate":"20260102","occurrenceSpanLines":[{"code":"70","fromDate":"20260101","toDate":"20260102"},{"code":"70","fromDate":"20260103","toDate":"20260104"}]})]
    assert len(latest_values_by_code(records,collection_path="occurrence_span_lines",date_paths=("processing_date",),resolver=resolver))==2


def test_stay_value_code_amounts_sum(resolver,make_record):
    records=[make_record({"processingDate":"20260102","valueLines":[{"code":"73","amount":"1.5"}]},row=1),make_record({"processingDate":"20260103","valueLines":[{"code":"73","amount":"-0.5"}]},row=2)]
    items=strip_lineage(latest_values_by_code(records,collection_path="value_lines",date_paths=("processing_date",),resolver=resolver))
    assert Decimal(items[0]["amount"])==1


def test_final_bypass_and_trailer_prefix(resolver,make_record):
    source=make_record({"utilizationDays":4,"MEDPAR-LGTH-STAY-0260":3,"fixedWidthRecord":"A"*3000+"T"*50},stage=Stage.FINAL_MEDPAR)
    target=make_record({"fixedWidthRecord":"A"*3000},stage=Stage.FINAL_MEDPAR,row=2)
    assert bypass_required(source,resolver) is True
    assert validate_trailer_removal(source,target,resolver,"ascii").status==ValidationStatus.PASS
    target.data["fixedWidthRecord"]="B"+"A"*2999
    assert validate_trailer_removal(source,target,resolver,"ascii").status==ValidationStatus.FAIL


def test_exact_bytes_find_same_length_mismatch(resolver,make_record):
    expected=make_record({"fixedWidthRecord":"A"*3000},stage=Stage.FINAL_MEDPAR)
    actual=make_record({"fixedWidthRecord":"A"*2999+"B"},stage=Stage.FINAL_MEDPAR,row=2)
    r=compare_final_bytes(expected,actual,resolver,"ascii")
    assert r.status==ValidationStatus.FAIL
    assert r.actual["first_mismatch_positions"]==[3000]


@pytest.mark.parametrize("provider,expected",[("12M123","121123"),("12W123","122123"),("12TA34","122034"),("12SD34","123034"),("12TK34","124434")])
def test_base_ccn_position_mapping(provider,expected):
    from medpar_qa.stages.intermediate.business_rules import base_facility_ccn
    assert base_facility_ccn(provider)==expected


def test_accommodation_categories_include_rug_boundaries():
    from medpar_qa.stages.intermediate.business_rules import accommodation_totals
    lines=[{"code":code,"units":1,"charges":"1.500"} for code in ("0110","0120","0150","0200","0210","9018","9019","9032","9033","9044")]
    days,charges=accommodation_totals(lines)
    assert days==[3,3,2,1,1]
    assert charges==[Decimal(5),Decimal(5),Decimal(3),Decimal(2),Decimal(2)]
    with pytest.raises(LookupError):
        accommodation_totals([{"code":"0110","units":1}])


def test_ssi_counts_month_boundaries_and_excludes_discharge():
    from medpar_qa.reference_data import ssi_days
    assert ssi_days(date(2024,1,31),date(2024,3,1),{"2024-02":1})==29
    assert ssi_days(date(2024,1,31),date(2024,3,1),{"2024-01":2,"2024-02":0})==1
    assert ssi_days(date(2024,1,31),date(2024,1,31),{"2024-01":1})==0


def test_reference_duplicate_ssi_flags_and_dod_cutoff(tmp_path,resolver):
    import json
    from medpar_qa.reference_data import ReferenceData
    (tmp_path/"ssi.json").write_text(json.dumps([{"ssa_no":"001","months":{"2024-02":0}},{"ssa_no":"001","months":{"2024-02":2}}]))
    (tmp_path/"dod.json").write_text(json.dumps([{"hicn":"OLD","date_of_death":"19971231"},{"hicn":"H","date_of_death":"2026064","verify_switch":"A"}]))
    references=ReferenceData({"ssi":"ssi.json","dod":"dod.json"},tmp_path)
    assert "OLD" not in references.dod
    data=references.enrich({"hicn":"H","ssa_no":"001"},resolver)
    assert data["ssi_month_flags"]=={"2024-02":1}
    assert data["matched_date_of_death"]=="2026-03-05"
    assert data["ssi_reference_matched"] is True


def test_missing_ssi_feed_never_passes_populated_output(resolver,make_record):
    source=make_record({},stage=Stage.INTERMEDIATE)
    target=make_record({"MEDPAR-SSI-DATA-0251":10},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-SSI-DAYS")
    assert rule.status==ValidationStatus.BLOCKED


def test_registry_compares_previously_uncovered_field(resolver,make_record):
    from medpar_qa.stages.v3_fields import compare_v3_fields, field_contract
    assert len(field_contract())==200
    expected=make_record({"MEDPAR-BASE-OPRTG-DRG-AMT-0870":20},stage=Stage.INTERMEDIATE)
    actual=make_record({"MEDPAR-BASE-OPRTG-DRG-AMT-0870":21},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in compare_v3_fields(expected,actual,resolver) if r.evidence["register_field_id"]==2)
    assert rule.status==ValidationStatus.FAIL


def test_registry_missing_both_sides_does_not_claim_coverage(resolver,make_record):
    from medpar_qa.stages.v3_fields import compare_v3_fields
    source=make_record({},stage=Stage.INTERMEDIATE)
    result=compare_v3_fields(source,source,resolver)
    assert next(r for r in result if r.evidence["register_field_id"]==2).status==ValidationStatus.NOT_APPLICABLE


def test_identity_julian_matches_gregorian_and_composite_hicn(resolver,make_record):
    from medpar_qa.stages.common import record_identity
    left=make_record({"MEDPAR-SSA-NO-0021":"001234567","MEDPAR-BIC-CODE-0022":"A","MEDPAR-ADM-DATE-0200":"2026064"})
    right=make_record({"hicn":"001234567A","admissionDate":"20260305"},row=2)
    assert record_identity(left,resolver,("hicn","admission_date"))==record_identity(right,resolver,("hicn","admission_date"))


def test_final_default_uses_one_byte_classification(resolver,make_record):
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
    p=FinalMedparProcessor(resolver)
    record=make_record({"MEDPAR-SS-LS-SNF-IND-0140":"S"},stage=Stage.FINAL_MEDPAR)
    assert next(r for r in p._validate_record(record) if r.rule_id=="FM-CLASSIFICATION").status==ValidationStatus.PASS
    record.data["MEDPAR-SS-LS-SNF-IND-0140"]="SS"
    assert next(r for r in p._validate_record(record) if r.rule_id=="FM-CLASSIFICATION").status==ValidationStatus.FAIL


def test_physical_stage_record_lengths(resolver,make_record):
    from medpar_qa.stages.record_contracts import validate_record_contracts
    from medpar_qa.enums import FileRole
    source=make_record({"fixedWidthRecord":"A"*32010},stage=Stage.INTERMEDIATE)
    output=make_record({"fixedWidthRecord":"A"*3050},stage=Stage.INTERMEDIATE,row=2,role=FileRole.ACTUAL_OUTPUT)
    assert all(r.status==ValidationStatus.PASS for r in validate_record_contracts([source,output],resolver))
    output.data["fixedWidthRecord"]="A"*3000
    assert validate_record_contracts([output],resolver)[0].status==ValidationStatus.FAIL


def test_specific_new_rule10a_precedes_general_fallback(resolver,make_record):
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    base={"hicn":"H","providerId":"P","stayFromDate":"20260101","stayThruDate":"20260102","transactionCode":1}
    qcs=[5,0,0,3]
    records=[make_record({**base,"queryCode":qc,"internalControlNumber":f"I{i}","processingDate":f"202601{20-i:02d}"},row=i+1) for i,qc in enumerate(qcs)]
    result=FinalActionProcessor(resolver).validate_group(records)
    decision=next(r for r in result.rule_results if r.rule_id=="FA-RULE-10A")
    assert decision.evidence["requirement"]=="MM-FINAC-16C/D/E"
    assert sum(d.decision==RecordDecision.KEEP for d in result.decisions)==2


def test_split_missing_bill_in_supplied_output_fails(resolver,make_record):
    from medpar_qa.enums import FileRole
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2)]
    output=make_record({**bills[0].data,"splitYearIndicator":"Y00109"},row=3,stage=Stage.SPLIT,role=FileRole.ACTUAL_OUTPUT)
    result=SplitProcessor(resolver,date(2026,10,11)).validate([*bills,output])
    assert any(r.rule_id=="SP-RULE-INDICATOR" and r.status==ValidationStatus.FAIL for r in result.rule_results)


def test_split_charge_accounting_preserves_negative_credits(resolver,make_record):
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2,thru="20220101",admit="20220101"),split_bill(make_record,6,3)]
    for bill,amount in zip(bills,["100.125","-20.125","3.5"]):bill.data['totalCharges']=amount
    result=SplitProcessor(resolver,date(2026,10,11)).validate(bills)
    balance=next(r for r in result.rule_results if r.rule_id=="SP-CHARGE-BALANCE")
    assert balance.status==ValidationStatus.PASS
    assert Decimal(balance.actual['input'])==Decimal('83.500')
    assert balance.actual['dropped']=='-20.125'


def test_final_bypass_exports_even_when_route_is_valid(tmp_path,resolver,make_record):
    from medpar_qa.reporting.stage_audit import write_stage_audit
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
    source=make_record({"hicn":"H","providerId":"P","admissionDate":"20260101","splitYearIndicator":"Y00109","warningIndicator04":2},stage=Stage.FINAL_MEDPAR)
    result=FinalMedparProcessor(resolver).validate([source])
    route=next(r for r in result.rule_results if r.rule_id=='FM-BYPASS-EXCEPTION')
    assert route.status==ValidationStatus.PASS
    paths=write_stage_audit(result,tmp_path)
    assert 'FM-BYPASS-EXCEPTION' in paths['bypass'].read_text()


@pytest.mark.parametrize('amount',['NaN','Infinity','-Infinity'])
def test_nonfinite_amounts_rejected(amount):
    with pytest.raises(ValueError):whole_dollars(amount)


@pytest.mark.parametrize('code,field',[('18','MEDPAR-DISPROPORTIONATE-0360'),('19','MEDPAR-IME-AMOUNT-0370'),('77','MEDPAR-NEW-TECH-ADD-O-AMT-0860'),('73','MEDPAR-SQSTRTN-RDCTN-AMT-1130'),('Q7','MEDPAR-ISLET-ADDON-PMTAMT-1450'),('Q1','MEDPAR-VALQ1-PMT-RDCTN-AM-1470'),('QB','MEDPAR-VALQB-PMT-ADJ-AMT-1500')])
def test_documented_value_code_fields(resolver,make_record,code,field):
    source=make_record({'valueLines':[{'code':code,'amount':'2.5'}]},stage=Stage.INTERMEDIATE)
    actual=make_record({field:3},stage=Stage.INTERMEDIATE,row=2)
    checks=validate_business_rules(source,actual,resolver)
    matched=[r for r in checks if r.rule_id=='INT-VALUE-CODE-AMOUNT' and r.actual==3]
    assert len(matched)==1
    assert matched[0].status==ValidationStatus.PASS


def test_drg_price_all_six_terms(resolver,make_record):
    source=make_record({'claimPaymentAmount':100,'primaryPayerClaimPaidAmount':20,'beneficiaryCoinsuranceAmount':3,'inpatientDeductibleAmount':4,'bloodDeductibleAmount':5,'outlierApprovedPaymentAmount':10},stage=Stage.INTERMEDIATE)
    actual=make_record({'MEDPAR-DRG-PRICE-0380':122},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,actual,resolver) if r.rule_id=='INT-DRG-PRICE-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_dead_status_fallback_and_verify_b(resolver,make_record):
    source=make_record({'admissionDate':'20260301','stayThruDate':'20260305','patientStatus':20},stage=Stage.INTERMEDIATE)
    actual=make_record({'MEDPAR-HIMASTER-DOD-0230':'2026064','MEDPAR-HIMASTER-DOD-IND-0240':'B','MEDPAR-DEATH-AFTER-ADM-0611':4},stage=Stage.INTERMEDIATE,row=2)
    checks=validate_business_rules(source,actual,resolver)
    assert all(r.status==ValidationStatus.PASS for r in checks if r.rule_id in {'INT-DOD-CALCULATION','INT-DOD-VERIFY','INT-DEATH-DAYS-CALCULATION'})


def test_unconfirmed_no_organ_default_is_blocked(resolver,make_record):
    source=make_record({'revenueLines':[{'code':'0818'}]},stage=Stage.INTERMEDIATE)
    actual=make_record({'medparOrganInd0487':'00'},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,actual,resolver) if r.rule_id=='INT-ORGAN-TYPE-CALCULATION')
    assert rule.status==ValidationStatus.BLOCKED
