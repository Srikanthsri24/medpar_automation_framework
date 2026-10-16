"""Ticket acceptance scenarios; external production/UAT acceptance is separate."""
from copy import deepcopy
from datetime import date
import pytest
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.death_policy import effective_death, cutoff_options, warning08_death_bit
from medpar_qa.stages.output_contracts import (forbidden_result, remove_fields, intermediary_id,
    intermediary_type, carry_forward_contracts, parquet_contracts)
from medpar_qa.stages.intermediate.business_rules import validate_business_rules, death_after_admission
from medpar_qa.stages.intermediate.structural import validate_death_after_admission, validate_warning_summary
from medpar_qa.stages.final_medpar.archive_audit import payload_fingerprint


@pytest.mark.parametrize('payload,failed', [
    ({'medparSsaNo0021':'123456789'}, False),
    ({'cacheDataInternal':None}, True),
    ({'nested':[{'CACHE_DATA_INTERNAL':{}}]}, True),
    ({'cachedatainternal':{'deathDate':None}}, True),
])
def test_reg01_forbidden_nested_and_case(payload, failed, make_record):
    result=forbidden_result(make_record(payload))
    assert (result.status == ValidationStatus.FAIL) is failed
    if failed:
        assert result.actual
        assert result.source_files == ['fixture.json']


def test_reg01_only_approved_fields_removed_and_source_unchanged():
    source={'cacheDataInternal':{'deathDate':'20200101'},'medparSplitYearIndicator':'Y0',
            'medparIntmdNum0580':'01234','nested':{'amount':-20},'medparDeathAfterAdm0611':-1776}
    before=deepcopy(source)
    final=remove_fields(source,('cacheDataInternal','medparSplitYearIndicator'))
    assert source==before
    assert payload_fingerprint(source)==payload_fingerprint(final)
    final['nested']['amount']=0
    assert payload_fingerprint(source)!=payload_fingerprint(final)


@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('good', [False, True])
def test_reg01_reg02_parquet_schema_even_empty(tmp_path, empty, good):
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema=pa.schema([pa.field('medparIntmdNum0580',pa.string() if good else pa.struct([('id',pa.string())])),
                      pa.field('medparDeathAfterAdm0611',pa.int32())]+([] if good else [pa.field('outer',pa.struct([('CACHE_DATA_INTERNAL',pa.string())]))]))
    rows=[] if empty else [{'medparIntmdNum0580':'01234' if good else {'id':'01234'},'medparDeathAfterAdm0611':-1776}]
    path=tmp_path/'output.parquet';pq.write_table(pa.Table.from_pylist(rows,schema=schema),path)
    results=parquet_contracts(path,Stage.FINAL_MEDPAR)
    assert {r.rule_id for r in results} == {'FM-NO-INTERNAL-FIELDS','FM-TYPE-0580','FM-TYPE-0611'}
    assert all(r.status==ValidationStatus.PASS for r in results) is good
    if not good:
        assert 'outer.CACHE_DATA_INTERNAL' in str(results[0].actual)


@pytest.mark.parametrize('value', ['13201','01234'])
def test_reg02_string_value_and_leading_zero(value, make_record, resolver):
    source=make_record({'fiscalIntermediary':{'id':value,'approvedDate':20200101}})
    output=make_record({'medparIntmdNum0580':value}, stage=Stage.INTERMEDIATE)
    result=next(r for r in validate_business_rules(source,output,resolver) if r.field_name=='medpar_intmd_num_0580')
    assert result.status==ValidationStatus.PASS
    assert intermediary_type(output,resolver,Stage.INTERMEDIATE).status==ValidationStatus.PASS
    output.data['medparIntmdNum0580']={'id':value}
    assert intermediary_type(output,resolver,Stage.INTERMEDIATE).status==ValidationStatus.FAIL
    assert intermediary_id(source.data['fiscalIntermediary']) == value


@pytest.mark.parametrize('actual,passed', [('01234',True),('1234',False),({'id':'01234'},False)])
def test_reg02_final_carry_preserves_value_and_type(actual,passed,make_record,resolver):
    results=carry_forward_contracts(make_record({'medparIntmdNum0580':'01234'}),make_record({'medparIntmdNum0580':actual}),resolver)
    assert (results[0].status==ValidationStatus.PASS) is passed


def bic_payload(death='20240305',status='1',match=True):
    return dict(admissionDate='20240301',stayThruDate='20240309',dischargeStatus=status,
        warningIndicator08='0', cacheDataInternal=dict(deathDate=death,isDeathDateVerified='V',bic_api_match_found=match))


@pytest.mark.parametrize('raw,status,match,expected,verify',[
    ('20240305','1',True,date(2024,3,5),'V'),
    ('20240310','1',True,date(2024,3,10),'V'),
    ('20240311','1',True,None,None),
    ('20240311','20',True,date(2024,3,9),'B'),
    (None,'20',False,date(2024,3,9),'B'),
    (None,'1',False,None,None),
    ('20240305','1',False,None,None),
])
def test_reg03_before_equal_after_no_match_fallback(raw,status,match,expected,verify,resolver):
    source=bic_payload(raw,status,match);before=deepcopy(source)
    evidence=effective_death(source,resolver,dod_data_cutoff_date='2024-03-10')
    assert evidence.death==expected
    assert evidence.verification==verify
    assert evidence.raw_date==raw
    assert source==before


def test_reg03_cutoff_not_inferred_and_equality_configurable(resolver):
    with pytest.raises(LookupError,match='dod_data_cutoff_date'):
        effective_death(bic_payload(),resolver)
    assert effective_death(bic_payload('20240310'),resolver,dod_data_cutoff_date='2024-03-10',dod_cutoff_inclusive=False).death is None
    with pytest.raises(ValueError):cutoff_options({'dod_data_cutoff_date':'yesterday'})
    with pytest.raises(ValueError):cutoff_options({'dod_cutoff_inclusive':'false'})


@pytest.mark.parametrize('raw,status,expected_days,expected_dod,expected_verify,wi08',[
    ('20190209','1',-1776,'2019040','V','2'),
    ('20231221','1',1,'2023355','V','0'),
    ('20231231','1',10,'2023365','V','0'),
    ('20250101','1','', '', '', '0'),
    ('20250101','20',8,'2023363','B','0'),
])
def test_reg03_reg04_independent_calculations_and_final_sign(raw,status,expected_days,expected_dod,expected_verify,wi08,make_record,resolver):
    data=bic_payload(raw,status)
    data.update(admissionDate='20231221',stayThruDate='20231229')
    source=make_record(data);sink={}
    validate_business_rules(source,make_record({}),resolver,dod_data_cutoff_date='2023-12-31',
        calculation_sink=lambda field,value,error:sink.update({field:value}) if not error else None)
    assert sink['medpar_death_after_adm_0611'] == (None if expected_days=='' else expected_days)
    assert sink['medpar_himaster_dod_0230'] == (None if expected_dod=='' else expected_dod)
    assert sink['medpar_dod_ind_0240'] == (None if expected_verify=='' else expected_verify)
    assert sink['warning_indicator_08']==wi08
    output=make_record({'medparDeathAfterAdm0611':sink['medpar_death_after_adm_0611']})
    assert all(r.status==ValidationStatus.PASS for r in carry_forward_contracts(output,deepcopy(output),resolver))


@pytest.mark.parametrize('death,actual,status', [('20190209',-1776,ValidationStatus.PASS),('20190209',0,ValidationStatus.FAIL),('20231221',1,ValidationStatus.PASS),(None,0,ValidationStatus.NOT_APPLICABLE)])
def test_reg04_signed_structural_check(death,actual,status,make_record,resolver):
    record=make_record({'admissionDate':'20231221','dateOfDeath':death,'medparDeathAfterAdm0611':actual})
    assert validate_death_after_admission(record,resolver).status==status


def test_reg04_warning_summary_and_negative_consistency(make_record,resolver):
    data={f'warning_indicator_{n:02}':'0' for n in range(1,18)}
    data.update(medparDeathAfterAdm0611=-1776,warning_indicator_08='2',medparWarningInd0640='00000002000000000')
    record=make_record(data)
    assert all(r.status==ValidationStatus.PASS for r in validate_warning_summary(record,resolver))
    data['warning_indicator_08']='0'
    assert all(r.status==ValidationStatus.FAIL for r in validate_warning_summary(record,resolver))
    assert warning08_death_bit('3',None,date(2024,1,1))=='1'


def test_reg02_first_bill_object_retained_but_0580_is_flat(resolver,make_record):
    from medpar_qa.processing import writers
    from medpar_qa.stages.stay.processor import StayProcessor
    from medpar_qa.stages.intermediate.processor import IntermediateProcessor
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
    from test_source_writers import bill
    first=bill(fiscalIntermediary={'id':'01234','approvedDate':20260101})
    second={**bill(fiscalIntermediary={'id':'99999','approvedDate':20260102}),'processingDate':'20260106','stayFromDate':'20260102','stayThruDate':'20260105'}
    stays,_=writers.stay([make_record(first,row=1),make_record(second,row=2)],StayProcessor(resolver))
    assert len(stays)==1
    assert resolver.get(stays[0],'fiscal_intermediary')['id']=='01234'
    intermediate,_=writers.intermediate([make_record(stays[0])],IntermediateProcessor(resolver,date(2026,4,20)))
    assert resolver.get(intermediate[0],'medpar_intmd_num_0580')=='01234'
    final,_,_=writers.final_medpar([make_record(intermediate[0])],FinalMedparProcessor(resolver))
    assert len(final)==1
    assert resolver.get(final[0],'medpar_intmd_num_0580')=='01234'


def test_reg01_final_writer_removes_internal_preserves_intermediate(resolver,make_record):
    from medpar_qa.processing.writers import final_medpar
    from medpar_qa.stages.final_medpar.processor import FinalMedparProcessor
    data=dict(providerId='990999',cacheDataInternal={'deathDate':'20190209'},
              nested={'CACHE_DATA_INTERNAL':None,'other':123}, medparIntmdNum0580='01234',
              medparDeathAfterAdm0611=-1776)
    source=make_record(data);before=deepcopy(data)
    final,_,dropped=final_medpar([source],FinalMedparProcessor(resolver))
    assert len(final)==1 and not dropped
    assert source.data==before
    assert final[0]['nested']=={'other':123}
    assert 'cacheDataInternal' not in final[0]
    assert final[0]['medparDeathAfterAdm0611']==-1776


def test_reg03_no_dod_allows_zero_days_but_missing_cutoff_blocks(make_record,resolver):
    source=make_record(bic_payload('20250101'))
    actual=make_record({'medparDeathAfterAdm0611':0,'medparHimasterDod0230':0,'medparDodInd0240':''})
    checks=validate_business_rules(source,actual,resolver,dod_data_cutoff_date='2024-12-31')
    assert all(r.status==ValidationStatus.PASS for r in checks if r.rule_id in ('INT-DEATH-DAYS-CALCULATION','INT-DOD-CALCULATION','INT-DOD-VERIFY'))
    checks=validate_business_rules(source,make_record({}),resolver)
    assert all(r.status==ValidationStatus.BLOCKED for r in checks if r.rule_id in ('INT-DEATH-DAYS-CALCULATION','INT-DOD-CALCULATION','INT-DOD-VERIFY'))


def test_reg01_empty_delivered_parquet_schema_reaches_pipeline(tmp_path,resolver):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from medpar_qa.enums import FileRole
    from medpar_qa.models import RunManifest, ManifestFile
    from medpar_qa.orchestration.pipeline import Pipeline
    path=tmp_path/'final.parquet'
    pq.write_table(pa.Table.from_pylist([],schema=pa.schema([('cacheDataInternal',pa.string()),('medparIntmdNum0580',pa.struct([('id',pa.string())]))])),path)
    manifest=RunManifest(run_id='schema-only',run_date=date(2026,4,20),base_directory=tmp_path,
        files=[ManifestFile(path='final.parquet',stage=Stage.FINAL_MEDPAR,role=FileRole.ACTUAL_OUTPUT)])
    _,diagnostics=Pipeline(manifest,resolver).load_with_diagnostics()
    checks=diagnostics[Stage.FINAL_MEDPAR].rule_results
    assert any(r.rule_id=='FM-NO-INTERNAL-FIELDS' and r.status==ValidationStatus.FAIL for r in checks)
    assert any(r.rule_id=='FM-TYPE-0580' and r.status==ValidationStatus.FAIL for r in checks)
    read=next(r for r in checks if r.rule_id=='INGEST-READ-FILE')
    assert read.actual['record_count']==0  # Empty input remains rejected separately.
    assert 'error_type' not in read.actual
