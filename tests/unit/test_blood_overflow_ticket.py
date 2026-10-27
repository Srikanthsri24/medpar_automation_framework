import pytest
from medpar_qa.processing.physical_export import encode_record
from medpar_qa.stages.final_medpar.overflow import validate_blood_overflow
from medpar_qa.models import ValidationStatus

@pytest.mark.parametrize('value,expected',[(62,'062'),(999,'999'),(1000,'999'),(1062,'999'),(1200,'999')])
def test_cap_and_validation(value,expected,resolver,make_record):
    data={'medpar_blood_pints_0520':value}
    layout=[dict(name='medpar_blood_pints_0520',start=1,length=3,type='integer',max_value=999,on_overflow='cap')]
    log=[]
    result=encode_record(data,resolver,layout,expected_bytes=3,record_id='claim-1',cap_log=log)
    assert result==expected and data['medpar_blood_pints_0520']==value
    assert len(log)==int(value>999)
    assert validate_blood_overflow(make_record(data),resolver,layout,result).status==ValidationStatus.PASS
    if value>999: assert log[0]['record_id']=='claim-1' and log[0]['original_value']==value

def test_cap_default_off_and_truncation_fails(resolver,make_record):
    layout=[dict(name='medpar_blood_pints_0520',start=1,length=3,type='integer')]
    data={'medpar_blood_pints_0520':1062}
    with pytest.raises(ValueError): encode_record(data,resolver,layout,expected_bytes=3)
    assert validate_blood_overflow(make_record(data),resolver,layout,'062').status==ValidationStatus.FAIL
    assert validate_blood_overflow(make_record(data),resolver,[],None).status==ValidationStatus.BLOCKED
