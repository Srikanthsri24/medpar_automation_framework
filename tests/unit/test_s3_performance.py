"""Concurrent complete-object input handling retains deterministic evidence."""
import json
from pathlib import Path
from threading import Lock
import time
import pytest
from test_input_sources import FakeS3
from medpar_qa.ingestion.input_sources import InputSources, InputSourceError


class ConcurrentS3(FakeS3):
    def __init__(self, objects):
        super().__init__(objects)
        self.lock=Lock();self.active=0;self.peak=0;self.version='v1'

    def paginate(self, **kwargs):
        for page in super().paginate(**kwargs):
            for obj in page['Contents']:obj['ETag']=self.version
            yield page

    def download_file(self,bucket,key,filename,**kwargs):
        with self.lock:
            self.active+=1;self.peak=max(self.peak,self.active)
        try:
            time.sleep(0.01)
            super().download_file(bucket,key,filename)
            if 'Callback' in kwargs:kwargs['Callback'](Path(filename).stat().st_size)
        finally:
            with self.lock:self.active-=1


def objects():
    return {('medpar-demo-bucket',f'input/{i:03}.json'):json.dumps([{'id':i,'rows':[1,2,3]}]).encode() for i in range(24)}


def prepare(tmp_path,client,name,workers=8):
    source=InputSources(tmp_path,tmp_path/f'reports/{name}',client=client,s3_workers=workers)
    paths=source.resolve('s3://medpar-demo-bucket/input/')
    return source,paths


def test_parallel_downloads_order_content_and_cache_reuse(tmp_path):
    client=ConcurrentS3(objects())
    source,paths=prepare(tmp_path,client,'first')
    assert 1<client.peak<=8
    assert len(paths)==24
    assert [json.loads((tmp_path/p).read_text())[0]['id'] for p in paths]==list(range(24))
    before=len(client.downloads)
    second,paths2=prepare(tmp_path,client,'second')
    assert len(client.downloads)==before
    assert [source.files[p]['sha256'] for p in paths]==[second.files[p]['sha256'] for p in paths2]
    assert all(item.get('access_mode')!='s3_parquet_sample' for item in second.files.values())


def test_corrupt_cache_downloaded_again_and_version_change_invalidates(tmp_path):
    client=ConcurrentS3(objects())
    prepare(tmp_path,client,'first')
    cached=next((tmp_path/'data/.input_cache/shared').glob('*/object.bin'))
    cached.write_bytes(b'bad')
    before=len(client.downloads)
    prepare(tmp_path,client,'second')
    assert len(client.downloads)==before+1
    client.version='v2'
    prepare(tmp_path,client,'third')
    assert len(client.downloads)==before+25


def test_worker_failure_never_returns_partial_folder(tmp_path):
    class Broken(ConcurrentS3):
        def download_file(self,bucket,key,filename,**kwargs):
            if key=='input/004.json':raise RuntimeError('simulated failure')
            return super().download_file(bucket,key,filename,**kwargs)
    with pytest.raises(InputSourceError):prepare(tmp_path,Broken(objects()),'failure')
    assert not list((tmp_path/'data/.input_cache/failure').rglob('*.download'))


@pytest.mark.parametrize('workers',[0,33,True,'8'])
def test_concurrency_limit_validated(tmp_path,workers):
    with pytest.raises(InputSourceError,match='s3_workers'):
        InputSources(tmp_path,tmp_path/'reports/run',s3_workers=workers)
