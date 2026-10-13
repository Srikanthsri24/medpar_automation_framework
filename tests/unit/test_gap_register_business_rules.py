"""Regression tests and local fixtures for gap register business rules. Tests describe controlled
examples; passing them does not certify all production files.
"""
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
    """Verify whole dollars ties away from zero. The assertions below state exactly what this test
    proves for its fixtures.
    """
    assert whole_dollars(raw)==Decimal(expected)


def test_money_positive_overflow_uses_approved_nine_digit_cap():
    """Verify money positive overflow uses approved nine digit cap. The assertions below state
    exactly what this test proves for its fixtures.
    """
    assert whole_dollars('1000000000.500') == Decimal('999999999')


@pytest.mark.parametrize('input_field,output_field', DIRECT_MOVES.items())
def test_recovered_document_direct_moves_detect_wrong_output(resolver, make_record, input_field, output_field):
    """Verify recovered document direct moves detect wrong output. The assertions below state
    exactly what this test proves for its fixtures.
    """
    source=make_record({input_field:'APPROVED'},stage=Stage.INTERMEDIATE)
    target=make_record({output_field:'WRONG'},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver)
              if r.rule_id=='INT-DOCUMENTED-DIRECT-MOVE' and r.field_name==output_field)
    assert rule.status==ValidationStatus.FAIL and rule.expected=='APPROVED'


def test_recovered_aco_position_and_mrn_fallback(resolver,make_record):
    """Verify recovered aco position and mrn fallback. The assertions below state exactly what this
    test proves for its fixtures.
    """
    source=make_record({'ngAcoIndicatorCodes':['A','1','2','3','4'],'medicalRecord':' ','patientControl':'PC'},stage=Stage.INTERMEDIATE)
    target=make_record({'medparNgAcoInd1Cd1330':'A','medparNgAcoInd5Cd1370':'4','medparMrn0670':'PC'},stage=Stage.INTERMEDIATE,row=2)
    rules=[r for r in validate_business_rules(source,target,resolver) if r.rule_id in {'INT-DOCUMENTED-ACO-MOVE','INT-MRN-FALLBACK'}]
    assert sum(r.status==ValidationStatus.PASS for r in rules)==3


@pytest.mark.parametrize('can,expected',[('000000005','1'),('000000006','0')])
def test_recovered_five_percent_sample_uses_positions_eight_nine(resolver,make_record,can,expected):
    """Verify recovered five percent sample uses positions eight nine. The assertions below state
    exactly what this test proves for its fixtures.
    """
    source=make_record({'claimCan':can},stage=Stage.INTERMEDIATE)
    target=make_record({'meparSample050680':expected},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-FIVE-PERCENT-SAMPLE')
    assert rule.status==ValidationStatus.PASS


@pytest.mark.parametrize('rate,days,expected', [('1.5',2,4),('1.499',2,2),('999999999',2,999999999)])
def test_source_perdiem_rounds_rate_before_days(resolver, make_record, rate, days, expected):
    """Verify source perdiem rounds rate before days. The assertions below state exactly what this
    test proves for its fixtures.
    """
    source=make_record({'passThruPerDiem':rate,'utilizationDays':days},stage=Stage.INTERMEDIATE)
    target=make_record({'medparBillTotPerdiem0381':expected},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-SOURCE-PERDIEM-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_stay_first_nonblank_skips_spaces_and_preserves_zero(resolver,make_record):
    """Verify stay first nonblank skips spaces and preserves zero. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.stay.merge_rules import validate_merge_rules
    records=[make_record({'stayFromDate':'2026-01-01','stayThruDate':'2026-01-02','uniqueTrackingNumber':'  ','priorAuthorizationIndicator':0},stage=Stage.STAY),
             make_record({'stayFromDate':'2026-01-03','stayThruDate':'2026-01-04','uniqueTrackingNumber':'TRACK','priorAuthorizationIndicator':1},stage=Stage.STAY,row=2)]
    target=make_record({'uniqueTrackingNumber':'TRACK','priorAuthorizationIndicator':0},stage=Stage.STAY,row=3)
    rules=[r for r in validate_merge_rules(records,target,resolver,Decimal('0.001')) if r.rule_id=='ST-FIRST-NONBLANK']
    assert len(rules)==2 and all(r.status==ValidationStatus.PASS for r in rules)


@pytest.mark.parametrize("start,end,status,expected",[("2026-01-01","2026-01-01",20,1),("2026-01-01","2026-01-03",30,3),("2026-01-01","2026-01-03",1,2)])
def test_los_discharge_and_same_day(start,end,status,expected):
    """Verify los discharge and same day. The assertions below state exactly what this test proves
    for its fixtures.
    """
    assert length_of_stay(date.fromisoformat(start),date.fromisoformat(end),status)==expected


def test_los_rejects_inverted_dates():
    """Verify los rejects inverted dates. The assertions below state exactly what this test proves
    for its fixtures.
    """
    with pytest.raises(ValueError):
        length_of_stay(date(2026,1,3),date(2026,1,1),1)


def test_death_day_count_and_blank():
    """Verify death day count and blank. The assertions below state exactly what this test proves
    for its fixtures.
    """
    assert death_after_admission(date(2026,1,1),date(2026,1,1))==1
    assert death_after_admission(date(2026,1,1),date(2026,1,4))==3
    assert death_after_admission(date(2026,1,1),None) is None


def test_age_birthday_and_medicare_adjustment():
    """Verify age birthday and medicare adjustment. The assertions below state exactly what this
    test proves for its fixtures.
    """
    assert age_at_admission(date(1961,7,20),date(2026,7,19),"10")==65
    assert age_at_admission(date(1961,7,20),date(2026,7,19),"20")==64
    assert age_at_admission(date(1961,7,20),date(2026,7,20),"20")==65


def test_source_operands_not_replaced_with_target(resolver,make_record):
    """Verify source operands not replaced with target. The assertions below state exactly what
    this test proves for its fixtures.
    """
    source=make_record({},stage=Stage.INTERMEDIATE)
    target=make_record({"medparDrgPrice0380":100},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-DRG-PRICE-CALCULATION")
    assert rule.status==ValidationStatus.BLOCKED


@pytest.mark.parametrize("rev,expected",[("0810","K1"),("0815","H1"),("0819","01")])
def test_organ_highest_valid_type(resolver,make_record,rev,expected):
    """Verify organ highest valid type. The assertions below state exactly what this test proves
    for its fixtures.
    """
    source=make_record({"revenueLines":[{"code":"0818"},{"code":rev}]},stage=Stage.INTERMEDIATE)
    target=make_record({"medparOrganInd0487":expected},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-ORGAN-TYPE-CALCULATION")
    assert r.status==ValidationStatus.PASS


def test_organ_yn_is_wrong(resolver,make_record):
    """Verify organ yn is wrong. The assertions below state exactly what this test proves for its
    fixtures.
    """
    source=make_record({"revenueLines":[{"code":"0819"}]},stage=Stage.INTERMEDIATE)
    target=make_record({"medparOrganInd0487":"Y"},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-ORGAN-TYPE-CALCULATION")
    assert r.status==ValidationStatus.FAIL


def test_value_credits_summed_before_whole_dollar_rounding(resolver,make_record):
    """Verify value credits summed before whole dollar rounding. The assertions below state exactly
    what this test proves for its fixtures.
    """
    source=make_record({"valueLines":[{"code":"Q1","amount":"-1.25"},{"code":"Q1","amount":"-1.25"}]},stage=Stage.INTERMEDIATE)
    target=make_record({"MEDPAR-VALQ1-PMT-RDCTN-AM-1470":-3},stage=Stage.INTERMEDIATE,row=2)
    r=next(r for r in validate_business_rules(source,target,resolver) if r.field_name=="medpar_val_q1_pmt_rdctn_amt_1470")
    assert r.status==ValidationStatus.PASS
    target.data["MEDPAR-VALQ1-PMT-RDCTN-AM-1470"]=-2.5
    r=next(r for r in validate_business_rules(source,target,resolver) if r.field_name=="medpar_val_q1_pmt_rdctn_amt_1470")
    assert r.status==ValidationStatus.FAIL


def split_bill(make_record,code,row,thru="20260102",admit="20251230"):
    """Test helper for split bill. It constructs or summarizes controlled fixture data for the
    assertions in this file.
    """
    return make_record({"claimCan":f"C{row}","hicn":"H","providerId":"P","admissionDate":admit,
        "stayFromDate":admit,"stayThruDate":thru,"transactionCode":code},row=row,stage=Stage.SPLIT)


def test_split_inpatient_last_thru_and_snf_admission(resolver,make_record):
    """Verify split inpatient last thru and snf admission. The assertions below state exactly what
    this test proves for its fixtures.
    """
    p=SplitProcessor(resolver,date(2026,10,11))
    for code,expected in [(1,"Y00109"),(0,"Y11012"),(4,"Y11012")]:
        r=split_bill(make_record,code,1)
        assert p.calculate_indicator(r)==expected
        result=p.validate([r])
        assert result.decisions[0].decision==RecordDecision.KEEP


def test_split_same_stay_all_bills_use_last_thru(resolver,make_record):
    """Verify split same stay all bills use last thru. The assertions below state exactly what this
    test proves for its fixtures.
    """
    bills=[split_bill(make_record,1,1,thru="20251231"),split_bill(make_record,1,2)]
    result=SplitProcessor(resolver,date(2026,10,11)).validate(bills)
    assert [r.expected for r in result.rule_results if r.rule_id=="SP-RULE-INDICATOR"]==["Y00109","Y00109"]


def test_split_full_year_and_drop_balance(resolver,make_record):
    """Verify split full year and drop balance. The assertions below state exactly what this test
    proves for its fixtures.
    """
    p=SplitProcessor(resolver,date(2026,7,1))
    assert p.calculate_indicator(split_bill(make_record,1,1,thru="20261231"))=="Y01012"
    result=p.validate([split_bill(make_record,1,1,thru="20220101",admit="20220101"),split_bill(make_record,6,2)])
    balance=next(r for r in result.rule_results if r.rule_id=="SP-RECORD-BALANCE")
    assert balance.actual=={"retained":0,"dropped":1,"exceptions":1}


def test_split_76_bills_retained_and_audited(resolver,make_record):
    """Verify split 76 bills retained and audited. The assertions below state exactly what this
    test proves for its fixtures.
    """
    result=SplitProcessor(resolver,date(2026,10,11)).validate([split_bill(make_record,1,i) for i in range(76)])
    assert len(result.decisions)==76
    assert next(r for r in result.rule_results if r.rule_id=="SP-STAY-BILL-LIMIT").status==ValidationStatus.PASS


def test_stay_different_admissions_never_merge(resolver,make_record):
    """Verify stay different admissions never merge. The assertions below state exactly what this
    test proves for its fixtures.
    """
    p=StayProcessor(resolver)
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2,admit="20260101")]
    assert len(p._group_sources(bills))==2


def test_span_same_code_different_dates_retained(resolver,make_record):
    """Verify span same code different dates retained. The assertions below state exactly what this
    test proves for its fixtures.
    """
    records=[make_record({"processingDate":"20260102","occurrenceSpanLines":[{"code":"70","fromDate":"20260101","toDate":"20260102"},{"code":"70","fromDate":"20260103","toDate":"20260104"}]})]
    assert len(latest_values_by_code(records,collection_path="occurrence_span_lines",date_paths=("processing_date",),resolver=resolver))==2


def test_stay_value_code_amounts_sum(resolver,make_record):
    """Verify stay value code amounts sum. The assertions below state exactly what this test proves
    for its fixtures.
    """
    records=[make_record({"processingDate":"20260102","valueLines":[{"code":"73","amount":"1.5"}]},row=1),make_record({"processingDate":"20260103","valueLines":[{"code":"73","amount":"-0.5"}]},row=2)]
    items=strip_lineage(latest_values_by_code(records,collection_path="value_lines",date_paths=("processing_date",),resolver=resolver))
    assert Decimal(items[0]["amount"])==1


def test_final_bypass_and_trailer_prefix(resolver,make_record):
    """Verify final bypass and trailer prefix. The assertions below state exactly what this test
    proves for its fixtures.
    """
    source=make_record({"utilizationDays":4,"MEDPAR-LGTH-STAY-0260":3,"fixedWidthRecord":"A"*3000+"T"*50},stage=Stage.FINAL_MEDPAR)
    target=make_record({"fixedWidthRecord":"A"*3000},stage=Stage.FINAL_MEDPAR,row=2)
    assert bypass_required(source,resolver) is True
    assert validate_trailer_removal(source,target,resolver,"ascii").status==ValidationStatus.PASS
    target.data["fixedWidthRecord"]="B"+"A"*2999
    assert validate_trailer_removal(source,target,resolver,"ascii").status==ValidationStatus.FAIL


def test_exact_bytes_find_same_length_mismatch(resolver,make_record):
    """Verify exact bytes find same length mismatch. The assertions below state exactly what this
    test proves for its fixtures.
    """
    expected=make_record({"fixedWidthRecord":"A"*3000},stage=Stage.FINAL_MEDPAR)
    actual=make_record({"fixedWidthRecord":"A"*2999+"B"},stage=Stage.FINAL_MEDPAR,row=2)
    r=compare_final_bytes(expected,actual,resolver,"ascii")
    assert r.status==ValidationStatus.FAIL
    assert r.actual["first_mismatch_positions"]==[3000]


@pytest.mark.parametrize("provider,expected",[("12M123","121123"),("12W123","122123"),("12TA34","122034"),("12SD34","123034"),("12TK34","124434")])
def test_base_ccn_position_mapping(provider,expected):
    """Verify base ccn position mapping. The assertions below state exactly what this test proves
    for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import base_facility_ccn
    assert base_facility_ccn(provider)==expected


def test_accommodation_categories_include_rug_boundaries():
    """Verify accommodation categories include rug boundaries. The assertions below state exactly
    what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import accommodation_totals
    lines=[{"code":code,"units":1,"charges":"1.500"} for code in ("0110","0120","0150","0200","0210","9018","9019","9032","9033","9044")]
    days,charges=accommodation_totals(lines)
    assert days==[3,3,2,1,1]
    assert charges==[Decimal(5),Decimal(5),Decimal(3),Decimal(2),Decimal(2)]
    with pytest.raises(LookupError):
        accommodation_totals([{"code":"0110","units":1}])


def test_ssi_counts_month_boundaries_and_excludes_discharge():
    """Verify ssi counts month boundaries and excludes discharge. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.reference_data import ssi_days
    assert ssi_days(date(2024,1,31),date(2024,3,1),{"2024-02":1})==29
    assert ssi_days(date(2024,1,31),date(2024,3,1),{"2024-01":2,"2024-02":0})==1
    assert ssi_days(date(2024,1,31),date(2024,1,31),{"2024-01":1})==0


def test_reference_duplicate_ssi_flags_and_dod_cutoff(tmp_path,resolver):
    """Verify reference duplicate ssi flags and dod cutoff. The assertions below state exactly what
    this test proves for its fixtures.
    """
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
    """Verify missing ssi feed never passes populated output. The assertions below state exactly
    what this test proves for its fixtures.
    """
    source=make_record({},stage=Stage.INTERMEDIATE)
    target=make_record({"MEDPAR-SSI-DATA-0251":10},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=="INT-SSI-DAYS")
    assert rule.status==ValidationStatus.BLOCKED


def test_registry_compares_previously_uncovered_field(resolver,make_record):
    """Verify registry compares previously uncovered field. The assertions below state exactly what
    this test proves for its fixtures.
    """
    from medpar_qa.stages.v3_fields import compare_v3_fields, field_contract
    assert len(field_contract())==200
    expected=make_record({"MEDPAR-BASE-OPRTG-DRG-AMT-0870":20},stage=Stage.INTERMEDIATE)
    actual=make_record({"MEDPAR-BASE-OPRTG-DRG-AMT-0870":21},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in compare_v3_fields(expected,actual,resolver) if r.evidence["register_field_id"]==2)
    assert rule.status==ValidationStatus.FAIL


def test_registry_missing_both_sides_does_not_claim_coverage(resolver,make_record):
    """Verify registry missing both sides does not claim coverage. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.v3_fields import compare_v3_fields
    source=make_record({},stage=Stage.INTERMEDIATE)
    result=compare_v3_fields(source,source,resolver)
    assert next(r for r in result if r.evidence["register_field_id"]==2).status==ValidationStatus.NOT_APPLICABLE


def test_identity_julian_matches_gregorian_and_composite_hicn(resolver,make_record):
    """Verify identity julian matches gregorian and composite hicn. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.common import record_identity
    left=make_record({"MEDPAR-SSA-NO-0021":"001234567","MEDPAR-BIC-CODE-0022":"A","MEDPAR-ADM-DATE-0200":"2026064"})
    right=make_record({"hicn":"001234567A","admissionDate":"20260305"},row=2)
    assert record_identity(left,resolver,("hicn","admission_date"))==record_identity(right,resolver,("hicn","admission_date"))


def test_final_default_uses_one_byte_classification(resolver,make_record):
    """Verify final default uses one byte classification. The assertions below state exactly what
    this test proves for its fixtures.
    """
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
    p=FinalMedparProcessor(resolver)
    record=make_record({"MEDPAR-SS-LS-SNF-IND-0140":"S"},stage=Stage.FINAL_MEDPAR)
    assert next(r for r in p._validate_record(record) if r.rule_id=="FM-CLASSIFICATION").status==ValidationStatus.PASS
    record.data["MEDPAR-SS-LS-SNF-IND-0140"]="SS"
    assert next(r for r in p._validate_record(record) if r.rule_id=="FM-CLASSIFICATION").status==ValidationStatus.FAIL


def test_physical_stage_record_lengths(resolver,make_record):
    """Verify physical stage record lengths. The assertions below state exactly what this test
    proves for its fixtures.
    """
    from medpar_qa.stages.record_contracts import validate_record_contracts
    from medpar_qa.enums import FileRole
    source=make_record({"fixedWidthRecord":"A"*32010},stage=Stage.INTERMEDIATE)
    output=make_record({"fixedWidthRecord":"A"*3050},stage=Stage.INTERMEDIATE,row=2,role=FileRole.ACTUAL_OUTPUT)
    assert all(r.status==ValidationStatus.PASS for r in validate_record_contracts([source,output],resolver))
    output.data["fixedWidthRecord"]="A"*3000
    assert validate_record_contracts([output],resolver)[0].status==ValidationStatus.FAIL


def test_specific_new_rule10a_precedes_general_fallback(resolver,make_record):
    """Verify specific new rule10a precedes general fallback. The assertions below state exactly
    what this test proves for its fixtures.
    """
    from medpar_qa.stages.final_action.processor import FinalActionProcessor
    base={"hicn":"H","providerId":"P","stayFromDate":"20260101","stayThruDate":"20260102","transactionCode":1}
    qcs=[5,0,0,3]
    records=[make_record({**base,"queryCode":qc,"internalControlNumber":f"I{i}","processingDate":f"202601{20-i:02d}"},row=i+1) for i,qc in enumerate(qcs)]
    from medpar_qa.stages.final_action.settings import FinalActionSettings
    result=FinalActionProcessor(resolver,FinalActionSettings(rule10a_requires_latest_qc0=False)).validate_group(records)
    decision=next(r for r in result.rule_results if r.rule_id=="FA-RULE-10A")
    assert decision.evidence["requirement"]=="MM-FINAC-16C/D/E"
    assert sum(d.decision==RecordDecision.KEEP for d in result.decisions)==2


def test_split_missing_bill_in_supplied_output_fails(resolver,make_record):
    """Verify split missing bill in supplied output fails. The assertions below state exactly what
    this test proves for its fixtures.
    """
    from medpar_qa.enums import FileRole
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2)]
    output=make_record({**bills[0].data,"splitYearIndicator":"Y00109"},row=3,stage=Stage.SPLIT,role=FileRole.ACTUAL_OUTPUT)
    result=SplitProcessor(resolver,date(2026,10,11)).validate([*bills,output])
    assert any(r.rule_id=="SP-RULE-INDICATOR" and r.status==ValidationStatus.FAIL for r in result.rule_results)


def test_split_charge_accounting_preserves_negative_credits(resolver,make_record):
    """Verify split charge accounting preserves negative credits. The assertions below state
    exactly what this test proves for its fixtures.
    """
    bills=[split_bill(make_record,1,1),split_bill(make_record,1,2,thru="20220101",admit="20220101"),split_bill(make_record,6,3)]
    for bill,amount in zip(bills,["100.125","-20.125","3.5"]):bill.data['totalCharges']=amount
    result=SplitProcessor(resolver,date(2026,10,11)).validate(bills)
    balance=next(r for r in result.rule_results if r.rule_id=="SP-CHARGE-BALANCE")
    assert balance.status==ValidationStatus.PASS
    assert Decimal(balance.actual['input'])==Decimal('83.500')
    assert balance.actual['dropped']=='-20.125'


def test_final_bypass_exports_even_when_route_is_valid(tmp_path,resolver,make_record):
    """Verify final bypass exports even when route is valid. The assertions below state exactly
    what this test proves for its fixtures.
    """
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
    """Verify nonfinite amounts rejected. The assertions below state exactly what this test proves
    for its fixtures.
    """
    with pytest.raises(ValueError):whole_dollars(amount)


@pytest.mark.parametrize('code,field',[('18','MEDPAR-DISPROPORTIONATE-0360'),('19','MEDPAR-IME-AMOUNT-0370'),('77','MEDPAR-NEW-TECH-ADD-O-AMT-0860'),('73','MEDPAR-SQSTRTN-RDCTN-AMT-1130'),('Q7','MEDPAR-ISLET-ADDON-PMTAMT-1450'),('Q1','MEDPAR-VALQ1-PMT-RDCTN-AM-1470'),('QB','MEDPAR-VALQB-PMT-ADJ-AMT-1500')])
def test_documented_value_code_fields(resolver,make_record,code,field):
    """Verify documented value code fields. The assertions below state exactly what this test
    proves for its fixtures.
    """
    source=make_record({'valueLines':[{'code':code,'amount':'2.5'}]},stage=Stage.INTERMEDIATE)
    actual=make_record({field:3},stage=Stage.INTERMEDIATE,row=2)
    checks=validate_business_rules(source,actual,resolver)
    matched=[r for r in checks if r.rule_id=='INT-VALUE-CODE-AMOUNT' and r.actual==3]
    assert len(matched)==1
    assert matched[0].status==ValidationStatus.PASS


def test_drg_price_all_six_terms(resolver,make_record):
    """Verify drg price all six terms. The assertions below state exactly what this test proves for
    its fixtures.
    """
    source=make_record({'claimPaymentAmount':100,'primaryPayerClaimPaidAmount':20,'beneficiaryCoinsuranceAmount':3,'inpatientDeductibleAmount':4,'bloodDeductibleAmount':5,'outlierApprovedPaymentAmount':10},stage=Stage.INTERMEDIATE)
    actual=make_record({'MEDPAR-DRG-PRICE-0380':122},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,actual,resolver) if r.rule_id=='INT-DRG-PRICE-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_dead_status_fallback_and_verify_b(resolver,make_record):
    """Verify dead status fallback and verify b. The assertions below state exactly what this test
    proves for its fixtures.
    """
    source=make_record({'admissionDate':'20260301','stayThruDate':'20260305','patientStatus':20},stage=Stage.INTERMEDIATE)
    actual=make_record({'MEDPAR-HIMASTER-DOD-0230':'2026064','MEDPAR-HIMASTER-DOD-IND-0240':'B','MEDPAR-DEATH-AFTER-ADM-0611':4},stage=Stage.INTERMEDIATE,row=2)
    checks=validate_business_rules(source,actual,resolver)
    assert all(r.status==ValidationStatus.PASS for r in checks if r.rule_id in {'INT-DOD-CALCULATION','INT-DOD-VERIFY','INT-DEATH-DAYS-CALCULATION'})


def test_cms_no_organ_default_is_blank_and_rejects_zero_code(resolver,make_record):
    """Verify cms no organ default is blank and rejects zero code. The assertions below state
    exactly what this test proves for its fixtures.
    """
    source=make_record({'revenueLines':[{'code':'0818'}]},stage=Stage.INTERMEDIATE)
    actual=make_record({'medparOrganInd0487':'00'},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,actual,resolver) if r.rule_id=='INT-ORGAN-TYPE-CALCULATION')
    assert rule.status==ValidationStatus.FAIL
    actual.data['medparOrganInd0487']=' '
    rule=next(r for r in validate_business_rules(source,actual,resolver) if r.rule_id=='INT-ORGAN-TYPE-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_nested_production_code_groups_and_accommodation_amounts():
    """Verify nested production code groups and accommodation amounts. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import accommodation_totals, codes
    lines=[{'revenueCenter': {'revenueCenterId':'0200'}, 'units':2, 'totalAmount':'12.500'},
           {'revenueCenter': {'revenueCenterId':'0300'}, 'units':1, 'totalAmount':'999'}]
    days, amounts=accommodation_totals(lines)
    assert days==[0,0,0,2,0] and amounts==[Decimal(0),Decimal(0),Decimal(0),Decimal(13),Decimal(0)]
    assert codes([{'conditionCodeId':'71'}], 'conditionCode')==['71']
    assert codes([{'occurrenceSpanCode':{'occurrenceSpanCodeId':'70'}}], 'occurrenceSpanCode')==['70']


def test_zero_birth_date_blocks_age_instead_of_inventing_birth(resolver,make_record):
    """Verify zero birth date blocks age instead of inventing birth. The assertions below state
    exactly what this test proves for its fixtures.
    """
    source=make_record({'beneficiaryDateOfBirth':0,'admissionDate':'20260101'},stage=Stage.INTERMEDIATE)
    target=make_record({'medparAge0030':-1},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-AGE-CALCULATION')
    assert rule.status==ValidationStatus.BLOCKED


def test_repeated_service_charges_validate_each_entry(resolver,make_record):
    """Verify repeated service charges validate each entry. The assertions below state exactly what
    this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.settings import IntermediateSettings
    from medpar_qa.stages.intermediate.structural import validate_decimal_values
    settings=IntermediateSettings()
    for values,expected in [([0,'12.500'],ValidationStatus.PASS),([0,'invalid'],ValidationStatus.FAIL)]:
        record=make_record({'medparServiceCharges0470':values},stage=Stage.INTERMEDIATE)
        rules=validate_decimal_values(record,resolver,settings.decimal_fields,settings.repeated_decimal_fields,settings.decimal_scale)
        assert len(rules)==1 and rules[0].status==expected


def test_indicator_derivations_use_source_arrays_not_output(resolver,make_record):
    """Verify indicator derivations use source arrays not output. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.legacy_discrepancies import validate_condition_switches, validate_revenue_indicator
    source=make_record({'conditionCodes':[{'conditionCodeId':'04'}], 'revenueLines':[{'revenueCenter':{'revenueCenterId':'0200'},'totalAmount':100}]},stage=Stage.INTERMEDIATE)
    target=make_record({'medparInforEnctrIndSw0800':'Y', 'medparIntensiveCareInd0481':'0'},stage=Stage.INTERMEDIATE,row=2)
    rules=validate_condition_switches(target,resolver,{'medpar_infor_enctr_ind_sw_0800':('04',)},source=source)
    assert rules[0].status==ValidationStatus.PASS
    rule=validate_revenue_indicator(target,resolver,field_name='medpar_intensive_care_ind_0481',rule_id='TEST',search_codes=['0200'],source=source)
    assert rule.status==ValidationStatus.PASS
    missing=make_record({},stage=Stage.INTERMEDIATE,row=3)
    assert validate_condition_switches(target,resolver,{'medpar_infor_enctr_ind_sw_0800':('04',)},source=missing)[0].status==ValidationStatus.BLOCKED
    assert validate_revenue_indicator(target,resolver,field_name='medpar_intensive_care_ind_0481',rule_id='TEST',search_codes=['0200'],source=missing).status==ValidationStatus.BLOCKED


def test_ndc_arrays_validate_entries_without_concatenation(resolver,make_record):
    """Verify ndc arrays validate entries without concatenation. The assertions below state exactly
    what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.structural import validate_age_and_ndc
    for values,expected in [(['01234567890','12345678901'],ValidationStatus.PASS),(['01234567890','1234567890X'],ValidationStatus.FAIL)]:
        target=make_record({'medparAge0030':65,'medparRevCntrNdcNum1550':values},stage=Stage.INTERMEDIATE)
        rule=next(r for r in validate_age_and_ndc(target,resolver,11) if r.rule_id=='INT-NDC')
        assert rule.status==expected


def test_missing_intermediate_output_never_validates_source_as_output(resolver,make_record,monkeypatch):
    """Verify missing intermediate output never validates source as output. The assertions below
    state exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.processor import IntermediateProcessor
    from medpar_qa.stages.intermediate.settings import IntermediateSettings
    processor=IntermediateProcessor(resolver,date(2026,5,14),IntermediateSettings(require_actual_output=True))
    source=make_record({'hicn':'H001','providerId':'123456','admissionDate':'20260101','splitYearIndicator':'Y0'},stage=Stage.INTERMEDIATE)
    def unexpected(*args,**kwargs):
        """Test helper for unexpected. It constructs or summarizes controlled fixture data for the
        assertions in this file.
        """
        raise AssertionError('Missing output must not fall back to source structural validation')
    monkeypatch.setattr(processor,'_validate_actual_structure',unexpected)
    result=processor.validate([source])
    assert any(r.rule_id=='INT-MISSING-ACTUAL-OUTPUT' and r.status==ValidationStatus.FAIL for r in result.rule_results)
    assert not any(r.rule_id=='INT-PROC-CODE-COUNT' for r in result.rule_results)


def test_duplicate_archive_diagnostic_preserves_real_data_differences(tmp_path):
    """Verify duplicate archive diagnostic preserves real data differences. The assertions below
    state exactly what this test proves for its fixtures.
    """
    import json, runpy
    select=runpy.run_path('scripts/review_production_intermediate.py',run_name='review_test')['distinct_payload_paths']
    paths=[]
    for index,payload in enumerate([{'filename':'one','amount':1},{'filename':'two','amount':1},{'filename':'three','amount':2}]):
        path=tmp_path/f'{index}.json';path.write_text(json.dumps(payload));paths.append(path)
    selected,copies=select(paths)
    assert len(selected)==2 and copies==1
    assert len(paths)==3 and all(path.exists() for path in paths)


def test_age_operands_and_mrn_are_not_raw_intermediate_direct_moves(resolver,make_record):
    """Verify age operands and mrn are not raw intermediate direct moves. The assertions below
    state exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.settings import IntermediateSettings
    from medpar_qa.stages.intermediate.legacy_discrepancies import validate_source_to_actual_direct_moves
    settings=IntermediateSettings()
    source=make_record({'beneficiaryDateOfBirth':0,'medicareStatus':'10','medicalRecord':'MRN'},stage=Stage.INTERMEDIATE)
    target=make_record({'medparAge0030':-1,'medparMrn0670':'WRONG'},stage=Stage.INTERMEDIATE,row=2)
    direct=validate_source_to_actual_direct_moves(source,target,resolver,settings.source_to_target_fields,decimal_fields=set(settings.decimal_fields),scale=settings.decimal_scale)
    assert not direct
    derived=validate_business_rules(source,target,resolver)
    assert next(r for r in derived if r.rule_id=='INT-AGE-CALCULATION').status==ValidationStatus.BLOCKED
    assert next(r for r in derived if r.rule_id=='INT-MRN-FALLBACK').status==ValidationStatus.FAIL


@pytest.mark.parametrize('revenue,expected',[([], '0'),(['0500'],'1'),(['0499'],'2'),(['0490','0509'],'3')])
def test_cms_outpatient_service_code_table(revenue,expected):
    """Verify cms outpatient service code table. The assertions below state exactly what this test
    proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import outpatient_services_indicator
    assert outpatient_services_indicator(revenue)==expected


def test_cms_care_unit_uses_accumulated_charges_and_blocks_unresolved_tie():
    """Verify cms care unit uses accumulated charges and blocks unresolved tie. The assertions
    below state exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import care_unit_indicator
    lines=[{'code':'0200','charges':60},{'code':'0200','charges':60},{'code':'0201','charges':100}]
    assert care_unit_indicator(lines,'020')=='0'
    lines.append({'code':'0201','charges':20})
    with pytest.raises(LookupError,match='tie'):
        care_unit_indicator(lines,'020')
    assert care_unit_indicator([{'code':'0300','charges':500}],'020')==''
    assert care_unit_indicator([{'code':'0214','charges':50}],'021')=='4'
    with pytest.raises(LookupError,match='total charge'):
        care_unit_indicator([{'code':'0200'}],'020')


def test_cms_surgical_switch_is_binary_and_rejects_yn(resolver,make_record):
    """Verify cms surgical switch is binary and rejects yn. The assertions below state exactly what
    this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.structural import validate_procedure_structure
    for value,status in [('1',ValidationStatus.PASS),('Y',ValidationStatus.FAIL),('0',ValidationStatus.FAIL)]:
        target=make_record({'medparSurgCode0513':['0ABC'],'medparSurgInd0500':value},stage=Stage.INTERMEDIATE)
        rule=next(r for r in validate_procedure_structure(target,resolver,date(2022,1,1),date(2026,5,14)) if r.rule_id=='INT-PROC-SURGICAL-INDICATOR')
        assert rule.status==status


def test_missing_dod_feed_is_not_a_confirmed_no_match(resolver,make_record):
    """Verify missing dod feed is not a confirmed no match. The assertions below state exactly what
    this test proves for its fixtures.
    """
    source=make_record({'admissionDate':'20260101','stayThruDate':'20260103','patientStatus':1,'dateOfDeath':0},stage=Stage.INTERMEDIATE)
    target=make_record({'medparHimasterDod0230':0,'medparDeathAfterAdm0611':0},stage=Stage.INTERMEDIATE,row=2)
    rules=validate_business_rules(source,target,resolver)
    assert all(r.status==ValidationStatus.BLOCKED for r in rules if r.rule_id in {'INT-DOD-CALCULATION','INT-DEATH-DAYS-CALCULATION'})
    source.data['dod_reference_available']=True
    source.data['dod_reference_matched']=False
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-DOD-CALCULATION')
    assert rule.status==ValidationStatus.PASS


def test_optional_span_zero_date_is_absent_not_wrong_calendar_date(resolver,make_record):
    """Verify optional span zero date is absent not wrong calendar date. The assertions below state
    exactly what this test proves for its fixtures.
    """
    source=make_record({'occurrenceSpanLines':[]},stage=Stage.INTERMEDIATE)
    target=make_record({'medparHospHomeFromDt1630':0,'medparHospHomeThruDt1640':0},stage=Stage.INTERMEDIATE,row=2)
    rules=[r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-SPAN-DATE-DERIVATION' and r.field_name in {'medpar_hosp_home_from_dt_1630','medpar_hosp_home_thru_dt_1640'}]
    assert len(rules)==2 and all(r.status==ValidationStatus.PASS for r in rules)
    target.data['medparHospHomeFromDt1630']=2026001
    assert next(r for r in validate_business_rules(source,target,resolver) if r.field_name=='medpar_hosp_home_from_dt_1630').status==ValidationStatus.FAIL


def test_mismatched_snapshot_blocks_before_record_comparison(resolver,make_record,monkeypatch):
    """Verify mismatched snapshot blocks before record comparison. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.models import RunManifest,ManifestFile
    from medpar_qa.enums import FileRole
    from medpar_qa.orchestration.pipeline import Pipeline
    source=make_record({'hicn':'H001'},stage=Stage.STAY)
    actual=make_record({'hicn':'H001'},stage=Stage.STAY,row=2,role=FileRole.ACTUAL_OUTPUT)
    from dataclasses import replace
    source.source=replace(source.source,file_path='bills/yearQuarter=2025Q3/rundate=20260320/source.json')
    actual.source=replace(actual.source,file_path='stay/yearQuarter=2026Q2/rundate=20260514/actual.json')
    manifest=RunManifest(run_id='snapshots',run_date=date(2026,5,14),files=[ManifestFile(path='ignored.json',stage=Stage.STAY,role=FileRole.SOURCE)],settings={'stay':{'require_matching_snapshot':True}})
    pipeline=Pipeline(manifest,resolver)
    monkeypatch.setattr(pipeline,'load_with_diagnostics',lambda:({Stage.STAY:[source,actual]},{}))
    class UnexpectedProcessor:
        """Implement this stage through the BaseStageProcessor validation interface and hold its
        resolver/settings.
        """
        def validate(self,records):
            """Run this test-local validation adapter with its deliberately controlled fixture
            behavior.
            """
            raise AssertionError('Cross-snapshot records must not be compared')
    monkeypatch.setattr(pipeline,'_processors',lambda:{Stage.STAY:UnexpectedProcessor()})
    results=pipeline.run()
    check=next(r for r in results[0].rule_results if r.rule_id=='INGEST-SNAPSHOT-MATCH')
    assert check.status==ValidationStatus.BLOCKED
    actual.source=replace(actual.source,file_path='stay/yearQuarter=2025Q3/rundate=20260320/actual.json')
    assert pipeline._snapshot_check(Stage.STAY,[source,actual]).status==ValidationStatus.PASS


def test_cms_ndc_width_occurrences_and_order(resolver,make_record):
    """Verify cms ndc width occurrences and order. The assertions below state exactly what this
    test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.business_rules import ndc_values_from_revenue
    from medpar_qa.stages.intermediate.structural import validate_age_and_ndc
    from medpar_qa.stages.intermediate.settings import IntermediateSettings
    values=[f'{index:011}' for index in range(12)]
    lines=[{'investigationalDeviceExemption':value} for value in values]
    assert ndc_values_from_revenue(lines)==values[:10]
    source=make_record({'revenueLines':lines},stage=Stage.INTERMEDIATE)
    target=make_record({'medparRevCntrNdcNum1550':values[:10],'medparAge0030':65},stage=Stage.INTERMEDIATE,row=2)
    rule=next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-NDC-SOURCE-DERIVATION')
    assert rule.status==ValidationStatus.PASS
    target.data['medparRevCntrNdcNum1550']=list(reversed(values[:10]))
    assert next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-NDC-SOURCE-DERIVATION').status==ValidationStatus.FAIL
    for output in [values[:11],['1234567890']]:
        target.data['medparRevCntrNdcNum1550']=output
        assert next(r for r in validate_age_and_ndc(target,resolver,IntermediateSettings().ndc_length) if r.rule_id=='INT-NDC').status==ValidationStatus.FAIL


def test_ndc_copy_match_does_not_hide_non_numeric_source_codes(resolver,make_record):
    """Verify ndc copy match does not hide non numeric source codes. The assertions below state
    exactly what this test proves for its fixtures.
    """
    from medpar_qa.stages.intermediate.structural import validate_age_and_ndc
    source=make_record({'revenueLines':[{'investigationalDeviceExemption':'NDC12345678'}]},stage=Stage.INTERMEDIATE)
    target=make_record({'medparRevCntrNdcNum1550':['NDC12345678'],'medparAge0030':65},stage=Stage.INTERMEDIATE,row=2)
    assert next(r for r in validate_business_rules(source,target,resolver) if r.rule_id=='INT-NDC-SOURCE-DERIVATION').status==ValidationStatus.PASS
    assert next(r for r in validate_age_and_ndc(target,resolver,11) if r.rule_id=='INT-NDC').status==ValidationStatus.FAIL
