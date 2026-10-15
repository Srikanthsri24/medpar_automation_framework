import hashlib
import io
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from medpar_qa.ingestion.input_sources import InputSources
from medpar_qa.ingestion.s3_sampling import S3RangeReader,sample_metadata
from medpar_qa.ingestion.row_selection import select,iter_records
from medpar_qa.enums import Stage,FileRole


class RangeS3:
    def __init__(self,data):self.data=data;self.ranges=[];self.downloads=[]
    def head_object(self,Bucket,Key):return {'ContentLength':len(self.data),'ETag':'snapshot-v1'}
    def get_object(self,Bucket,Key,Range,IfMatch=None):
        assert IfMatch=='snapshot-v1'
        start,end=map(int,Range.removeprefix('bytes=').split('-'));self.ranges.append((start,end))
        return {'Body':io.BytesIO(self.data[start:end+1])}
    def download_file(self,bucket,key,filename):self.downloads.append(key);Path(filename).write_bytes(self.data)


def parquet_bytes():
    sink=pa.BufferOutputStream()
    pq.write_table(pa.table({'sequence':range(50000),'payload':[hashlib.sha256(str(i).encode()).hexdigest() for i in range(50000)]}),sink,row_group_size=1000)
    return sink.getvalue().to_pybytes()


def test_range_sample_keeps_exact_source_total_and_reference_is_complete(tmp_path):
    client=RangeS3(parquet_bytes())
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=client,s3_read_mode='sample_parquet',row_selection={'mode':'first_n_per_file','limit':5,'include_related_records':False})
    cfg={'final_action':{'single_files':[{'source':['s3://medpar-demo-bucket/year=2026/object'],'actual':['s3://medpar-demo-bucket/year=2026/object']} ]}}
    staged=resolver.prepare(cfg,connected=True)
    item=staged['final_action']['single_files'][0]
    source=tmp_path/item['source'][0];reference=tmp_path/item['actual'][0]
    assert source!=reference
    assert pq.ParquetFile(source).metadata.num_rows==5
    assert pq.ParquetFile(reference).metadata.num_rows==50000
    meta=sample_metadata(source)
    assert meta['source_total_rows']==50000 and meta['cached_rows']==5
    assert meta['bytes_transferred']<len(client.data)//3
    assert meta['complete_source'] is False
    rows,selection=select(item['source'],Stage.FINAL_ACTION,FileRole.SOURCE,tmp_path,{'mode':'first_n_per_file','limit':5,'include_related_records':False},lambda r:())
    assert len(rows)==5 and selection['files'][0]['total_rows']==50000
    assert selection['full_dataset'] is False
    assert [r.source.row_number for r in rows]==[1,2,3,4,5]
    assert rows[0].data['year']=='2026'
    assert len(client.downloads)==1
    assert len(list(iter_records(reference,Stage.FINAL_ACTION,FileRole.SOURCE,tmp_path)))==50000


@pytest.mark.parametrize('selection',[{'mode':'all'},{'mode':'first_n_per_file','limit':5,'include_related_records':True}])
def test_full_or_related_context_selection_does_not_use_partial_sample(tmp_path,selection):
    client=RangeS3(parquet_bytes());resolver=InputSources(tmp_path,tmp_path/'reports/run',client=client,s3_read_mode='sample_parquet',row_selection=selection)
    paths=resolver.resolve(['s3://medpar-demo-bucket/object.parquet'],sample_source=True)
    assert len(client.downloads)==1 and not client.ranges
    assert sample_metadata(tmp_path/paths[0]) is None


def test_json_keeps_full_download_for_exact_counts(tmp_path):
    client=RangeS3(json.dumps([{'n':i} for i in range(100)]).encode())
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=client,s3_read_mode='sample_parquet',row_selection={'mode':'first_n_per_file','limit':5,'include_related_records':False})
    path=tmp_path/resolver.resolve(['s3://medpar-demo-bucket/source.json'],sample_source=True)[0]
    assert len(json.loads(path.read_text()))==100 and len(client.downloads)==1


def test_invalid_byte_range_response_is_not_silently_accepted():
    class Bad:
        def get_object(self,**kw):return {'Body':io.BytesIO(b'incomplete')}
    with S3RangeReader(Bad(),'bucket','key',100,'etag') as stream:
        with pytest.raises(ValueError,match='byte range'):stream.read(20)


def test_dependency_is_declared_in_install_metadata():
    import tomllib
    config=tomllib.loads(Path('pyproject.toml').read_text())
    assert 'ijson>=3.3' in config['project']['dependencies']


def test_missing_json_dependency_stops_before_source_preparation(monkeypatch,capsys):
    import importlib.util
    import run_commands as runner
    from medpar_qa.ingestion import input_sources
    original=importlib.util.find_spec
    monkeypatch.setattr(importlib.util,'find_spec',lambda name:None if name=='ijson' else original(name))
    def fail(*a,**kw):raise AssertionError('Source access started before dependency check')
    monkeypatch.setattr(input_sources,'InputSources',fail)
    assert runner.main(['--start-stage','final_action'])==2
    assert 'No S3 downloads started' in capsys.readouterr().out


def test_changed_remote_snapshot_fails_without_full_download_fallback(tmp_path):
    from botocore.exceptions import ClientError
    from medpar_qa.ingestion.input_sources import InputSourceError
    class Changed(RangeS3):
        def get_object(self,**kwargs):raise ClientError({'Error':{'Code':'PreconditionFailed'}},'GetObject')
    client=Changed(parquet_bytes())
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=client,s3_read_mode='sample_parquet',row_selection={'mode':'first_n_per_file','limit':5,'include_related_records':False})
    with pytest.raises(InputSourceError,match='stable extraction snapshot'):
        resolver.resolve(['s3://medpar-demo-bucket/source.parquet'],sample_source=True)
    assert not client.downloads
