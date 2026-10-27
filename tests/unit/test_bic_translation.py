import pytest
from medpar_qa.stages.death_policy import effective_death

@pytest.mark.parametrize('value,expected',[('Y','V'),('N',' '),(' ',' '),('',' '),(None,' ')])
def test_real_bic_codes(value,expected,resolver):
    data={'cacheDataInternal':{'deathDate':'20240305','isDeathDateVerified':value,'bic_api_match_found':True}}
    assert effective_death(data,resolver,dod_data_cutoff_date='2024-03-10').verification == expected

def test_unknown_bic_code_fails(resolver):
    with pytest.raises(ValueError,match='Unmapped BIC'):
        effective_death({'cacheDataInternal':{'deathDate':'20240305','isDeathDateVerified':'X'}},resolver,dod_data_cutoff_date='2024-03-10')
