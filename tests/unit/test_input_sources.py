import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from medpar_qa.ingestion.input_sources import InputSources, InputSourceError, s3_location, aws_client


class FakeS3:
    def __init__(self, objects):
        self.objects=objects
        self.downloads=[]
        self.listings=[]

    def head_object(self, Bucket, Key):
        return {'ContentLength':len(self.objects[(Bucket,Key)]),'ETag':'fake-etag'}

    def get_paginator(self, operation):
        assert operation=='list_objects_v2'
        return self

    def paginate(self, Bucket, Prefix):
        self.listings.append((Bucket,Prefix))
        keys=sorted(k for b,k in self.objects if b==Bucket and k.startswith(Prefix))
        # One object per page exercises complete pagination instead of one-page discovery.
        for key in keys:yield {'Contents':[{'Key':key,'Size':len(self.objects[(Bucket,key)]),'ETag':'fake-etag'}]}

    def download_file(self, bucket, key, filename):
        self.downloads.append((bucket,key))
        Path(filename).write_bytes(self.objects[(bucket,key)])


@pytest.mark.parametrize('url,expected',[
    ('s3://medpar-demo-bucket/folder/file.json',('medpar-demo-bucket','folder/file.json')),
    ('https://medpar-demo-bucket.s3.ap-south-1.amazonaws.com/folder/a%20b.parquet',('medpar-demo-bucket','folder/a b.parquet')),
    ('https://s3.amazonaws.com/medpar-demo-bucket/folder/',('medpar-demo-bucket','folder/')),
    ('https://s3.console.aws.amazon.com/s3/buckets/medpar-demo-bucket?prefix=folder%2F',('medpar-demo-bucket','folder/')),
    ('https://ap-south-1.console.aws.amazon.com/s3/object/medpar-demo-bucket?prefix=folder%2Ffile.json',('medpar-demo-bucket','folder/file.json')),
])
def test_s3_link_formats(url,expected):
    assert s3_location(url)==expected


def test_local_multiple_folders_and_external_absolute_files(tmp_path):
    root=tmp_path/'project';root.mkdir()
    for directory in ('inputs/one','inputs/two'):
        p=root/directory;p.mkdir(parents=True);(p/'claim.json').write_text('{}')
    (root/'inputs/one'/'ignored.txt').write_text('ignore')
    external=tmp_path/'external'/'year=2025';external.mkdir(parents=True)
    source=external/'extra.parquet';source.write_bytes(b'parquet-fixture')
    resolver=InputSources(root,root/'reports/run')
    values=resolver.resolve(['inputs/one','inputs/two',str(source)])
    assert len(values)==3 and len(set(values))==3
    assert all((root/p).exists() for p in values)
    assert 'year=2025' in values[2]
    assert resolver.files[values[2]]['origin']==str(source)
    assert resolver.files[values[2]]['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()


def test_s3_pages_folders_files_wildcards_and_overlap(tmp_path):
    bucket='medpar-demo-bucket'
    objects={(bucket,k):b'{}' for k in ('folder/year=2025/a.json','folder/year=2026/a.parquet','folder-two/b.json','folder-other/not-in-folder.json','folder/readme.txt')}
    fake=FakeS3(objects);resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    paths=resolver.resolve([f's3://{bucket}/folder/',f's3://{bucket}/folder',f's3://{bucket}/folder/year=2025/a.json',f's3://{bucket}/folder-two/',f's3://{bucket}/folder/*.parquet'])
    assert len(paths)==3 and len(fake.downloads)==3
    assert any('year=2025' in path for path in paths)
    assert fake.listings[0]==(bucket,'folder/')
    assert all('readme.txt' not in r['origin'] and 'folder-other' not in r['origin'] for r in resolver.files.values())
    resolver.write_inventory()
    inventory=json.loads((tmp_path/'reports/run/input_sources.json').read_text())
    assert inventory['resolved_files']==3 and all(r['sha256'] for r in inventory['files'])


def test_mixed_roles_and_downstream_sources_share_one_download(tmp_path):
    bucket='medpar-demo-bucket';fake=FakeS3({(bucket,'file.json'):b'{}'})
    (tmp_path/'local.json').write_text('{}')
    config={'final_action':{'single_files':[dict(source=['local.json',f's3://{bucket}/file.json'],actual=[f's3://{bucket}/file.json'],pipeline_outputs={'stay':[f's3://{bucket}/file.json']})]},'stay':{'folder_paths':[dict(enabled=False,source=['s3://never-contact-this-bucket/no/'])]}}
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    result=resolver.prepare(config,connected=True)
    item=result['final_action']['single_files'][0]
    assert len(item['source'])==2 and item['source'][1]==item['actual'][0]==item['pipeline_outputs']['stay'][0]
    assert fake.downloads==[(bucket,'file.json')]
    assert config['final_action']['single_files'][0]['source'][1].startswith('s3://')


def test_empty_s3_folder_stops_and_writes_evidence(tmp_path):
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=FakeS3({}))
    with pytest.raises(InputSourceError,match='No JSON or Parquet'):
        resolver.prepare({'final_action':{'folder_paths':[dict(source=['s3://medpar-demo-bucket/empty/'])]}})
    evidence=json.loads((tmp_path/'reports/run/input_sources.json').read_text())
    assert evidence['resolved_files']==0 and evidence['errors']


def test_failed_download_never_leaves_partial_input(tmp_path):
    fake=FakeS3({('medpar-demo-bucket','a.json'):b'{}'})
    def broken(bucket,key,filename):
        Path(filename).write_bytes(b'partial')
        raise RuntimeError('a secret that must never appear in evidence')
    fake.download_file=broken
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    with pytest.raises(InputSourceError):
        resolver.prepare({'final_action':{'folder_paths':[dict(source=['s3://medpar-demo-bucket/a.json'])]}})
    assert not list(resolver.cache.rglob('*.download'))
    assert not resolver.files
    assert 'a secret' not in (tmp_path/'reports/run/input_sources.json').read_text()


def test_unsafe_s3_key_cannot_escape_cache(tmp_path):
    fake=FakeS3({('medpar-demo-bucket','../a.json'):b'{}'})
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    with pytest.raises(InputSourceError,match='safely staged'):
        resolver.resolve('s3://medpar-demo-bucket/../a.json')
    assert not fake.downloads and not (tmp_path/'a.json').exists()


def test_placeholder_settings_use_standard_credential_chain(tmp_path,monkeypatch):
    import sys
    supplied=[]
    class Session:
        def __init__(self,**kwargs):supplied.append(kwargs)
        def client(self,service):return 'mock-client'
    monkeypatch.setitem(sys.modules,'boto3',SimpleNamespace(Session=Session))
    path=tmp_path/'credentials.json'
    path.write_text(json.dumps(dict(region_name='ap-south-1',aws_access_key_id='YOUR_AWS_ACCESS_KEY_ID',aws_secret_access_key='YOUR_AWS_SECRET_ACCESS_KEY',aws_session_token='YOUR_AWS_SESSION_TOKEN')))
    assert aws_client(path)=='mock-client'
    assert supplied==[{'region_name':'ap-south-1'}]


def test_partial_credentials_rejected_without_exposing_value(tmp_path):
    path=tmp_path/'settings.json';path.write_text('{"aws_access_key_id":"private-test-value"}')
    with pytest.raises(InputSourceError) as error:aws_client(path)
    assert 'private-test-value' not in str(error.value)


def test_signed_links_rejected_without_echoing_signature():
    with pytest.raises(InputSourceError) as error:
        s3_location('https://medpar-demo-bucket.s3.amazonaws.com/a.json?X-Amz-Signature=private-test-value')
    assert 'private-test-value' not in str(error.value)


def test_existing_local_files_never_initialize_aws(tmp_path,monkeypatch):
    import medpar_qa.ingestion.input_sources as module
    def unexpected(*args):raise AssertionError('Local runs must not contact AWS')
    monkeypatch.setattr(module,'aws_client',unexpected)
    (tmp_path/'claim.json').write_text('{}')
    resolver=InputSources(tmp_path,tmp_path/'reports/run')
    assert resolver.resolve(['claim.json'])==['claim.json']


def test_download_size_mismatch_is_not_used_as_input(tmp_path):
    fake=FakeS3({('medpar-demo-bucket','a.json'):b'{}'})
    fake.head_object=lambda **kwargs:{'ContentLength':100,'ETag':'fake'}
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    with pytest.raises(InputSourceError,match='size differs'):
        resolver.resolve('s3://medpar-demo-bucket/a.json')
    assert not resolver.files and not list(resolver.cache.rglob('*.download'))


def test_windows_bom_credentials_trim_values_and_ignore_placeholders(tmp_path,monkeypatch):
    import sys
    supplied=[]
    class Session:
        def __init__(self,**kwargs):supplied.append(kwargs)
        def client(self,service):return 'mock'
    monkeypatch.setitem(sys.modules,'boto3',SimpleNamespace(Session=Session))
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'region_name':' ap-south-1 ','aws_access_key_id':' YOUR_AWS_ACCESS_KEY_ID ','aws_secret_access_key':' YOUR_AWS_SECRET_ACCESS_KEY '}),encoding='utf-8-sig')
    assert aws_client(path)=='mock' and supplied==[{'region_name':'ap-south-1'}]


def test_expired_aws_token_has_actionable_redacted_evidence(tmp_path):
    class Expired(Exception):response={'Error':{'Code':'ExpiredToken','Message':'private-value'}}
    fake=FakeS3({})
    def failed(**kwargs):raise Expired('private-value')
    fake.head_object=failed
    resolver=InputSources(tmp_path,tmp_path/'reports/run',client=fake)
    with pytest.raises(InputSourceError,match='refresh access key'):
        resolver.prepare({'final_action':{'single_files':[{'source':['s3://medpar-demo-bucket/a.json']}]}})
    text=(tmp_path/'reports/run/input_sources.json').read_text()
    assert 'ExpiredToken' in text and 'private-value' not in text


def test_real_boto3_download_and_pagination_with_stubbed_aws_responses(tmp_path):
    from botocore.stub import Stubber
    from botocore.response import StreamingBody
    from io import BytesIO
    settings=tmp_path/'aws.json'
    settings.write_text(json.dumps({'region_name':'us-east-1','aws_access_key_id':'test-key','aws_secret_access_key':'test-secret'}))
    client=aws_client(settings)
    content=b'{"demo": true}'
    with Stubber(client) as stub:
        stub.add_response('list_objects_v2',{'IsTruncated':True,'NextContinuationToken':'next-page','Contents':[{'Key':'seed/readme.txt','Size':5}]},{'Bucket':'medpar-demo-bucket','Prefix':'seed/'})
        stub.add_response('list_objects_v2',{'IsTruncated':False,'Contents':[{'Key':'seed/year=2026/claim.json','Size':len(content)}]},{'Bucket':'medpar-demo-bucket','Prefix':'seed/','ContinuationToken':'next-page'})
        stub.add_response('head_object',{'ContentLength':len(content)})
        stub.add_response('get_object',{'ContentLength':len(content),'Body':StreamingBody(BytesIO(content),len(content))})
        resolver=InputSources(tmp_path,tmp_path/'reports/run',client=client)
        paths=resolver.resolve('s3://medpar-demo-bucket/seed/')
        assert len(paths)==1 and (tmp_path/paths[0]).read_bytes()==content
        assert resolver.files[paths[0]]['origin']=='s3://medpar-demo-bucket/seed/year=2026/claim.json'
        stub.assert_no_pending_responses()
