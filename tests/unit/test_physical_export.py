"""Physical encoding refuses incomplete or lossy layout definitions."""
import pytest
from medpar_qa.processing.physical_export import encode_record


def test_complete_layout_encodes_exact_bytes(resolver):
    layout=[dict(name='code',start=1,length=2),dict(name='amount',start=3,length=4,type='integer'),dict(start=7,length=2994,type='filler')]
    raw=encode_record({'code':'A','amount':12},resolver,layout)
    assert len(raw.encode('ascii'))==3000
    assert raw[:6]=='A 0012' and raw[6:]==' '*2994


@pytest.mark.parametrize('layout,data,reason',[
    ([dict(name='a',start=1,length=2)],{'a':'A'},'Incomplete'),
    ([dict(name='a',start=1,length=2),dict(start=2,length=2999,type='filler')],{'a':'A'},'overlapping'),
    ([dict(name='a',start=1,length=3000)],{},'missing required'),
    ([dict(name='a',start=1,length=3000,type='integer')],{'a':'1.5'},'whole integer'),
    ([dict(name='a',start=1,length=3000,type='integer')],{'a':'-1'},'signed numeric'),
    ([dict(name='a',start=1,length=2),dict(start=3,length=2998,type='filler')],{'a':'ABC'},'exceeds'),
])
def test_invalid_layout_stops_export(resolver,layout,data,reason):
    with pytest.raises(ValueError,match=reason):encode_record(data,resolver,layout)
