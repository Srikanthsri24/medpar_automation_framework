"""Repeatable synthetic S3 preparation benchmark; does not establish a live AWS SLA.

Run: python scripts/benchmark_s3_preparation.py --output /tmp/benchmark.json
Measures serial cold, parallel cold, and verified warm-cache access to identical
complete JSON objects. Simulated request latency is explicitly reported.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, sleep

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from medpar_qa.ingestion.input_sources import InputSources
from medpar_qa.normalization import fields


class SyntheticS3:
    def __init__(self,count,rows,latency):
        self.latency=latency;self.downloads=0
        self.objects={f'input/{i:04}.json':json.dumps([{'id':f'{i}-{r}','value':r} for r in range(rows)]).encode() for i in range(count)}
    def get_paginator(self,name):return self
    def paginate(self,**kwargs):
        yield {'Contents':[{'Key':key,'Size':len(value),'ETag':hashlib.md5(value).hexdigest()} for key,value in self.objects.items()]}
    def download_file(self,bucket,key,filename,**kwargs):
        sleep(self.latency)
        self.downloads+=1;Path(filename).write_bytes(self.objects[key])
        if 'Callback' in kwargs:kwargs['Callback'](len(self.objects[key]))


def benchmark(count=100,rows=1000,latency_ms=20,workers=8):
    client=SyntheticS3(count,rows,latency_ms/1000)
    results={}
    with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
        root=Path(directory)
        def run(label,location,workers):
            before=client.downloads;start=perf_counter()
            sources=InputSources(location,location/f'reports/{label}',client=client,s3_workers=workers)
            paths=sources.resolve('s3://medpar-benchmark-bucket/input/')
            elapsed=perf_counter()-start
            hashes=[sources.files[path]['sha256'] for path in paths]
            assert len(paths)==count
            results[label]={'seconds':round(elapsed,4),'downloads':client.downloads-before,'files':len(paths)}
            return hashes
        serial=run('serial_cold',root/'serial',1)
        parallel=run('parallel_cold',root/'parallel',workers)
        warm=run('parallel_verified_cache',root/'parallel',workers)
        assert serial==parallel==warm
        resolver=fields.FieldResolver({'sample':['nested.externalValue']})
        payload={f'unrelatedField{i}':i for i in range(100)}
        payload['Nested']={'External_Value':123}
        indexed_get=fields.nested_get
        def previous_get(data,path,default=None):
            current=data
            for part in path.split('.'):
                if not isinstance(current,dict):return default
                if part in current:current=current[part];continue
                matches=[key for key in current if fields._key_form(key)==fields._key_form(part)]
                if len(matches)!=1:return default
                current=current[matches[0]]
            return current
        timings={}
        try:
            for label,function in [('previous_normalized_key_scan',previous_get),('indexed_key_shapes',indexed_get)]:
                fields.nested_get=function;start=perf_counter()
                for _ in range(5000):assert resolver.get(payload,'sample')==123
                timings[label]=round(perf_counter()-start,4)
        finally:fields.nested_get=indexed_get
    return {'scope':'Synthetic complete-object preparation and field-resolution benchmark; no live AWS calls or business-rule runtime SLA',
        'objects':count,'rows_per_object':rows,'total_rows':count*rows,'simulated_request_latency_ms':latency_ms,'workers':workers,
        'object_preparation':results,'identical_ordered_sha256':True,'field_resolution_5000_lookups_seconds':timings,
        'cold_preparation_speedup':round(results['serial_cold']['seconds']/results['parallel_cold']['seconds'],2),
        'note':'Five-minute end-to-end acceptance requires a representative team S3 run; object sizes, network, full reference scans and reports affect runtime.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--objects',type=int,default=100)
    parser.add_argument('--rows',type=int,default=1000)
    parser.add_argument('--latency-ms',type=float,default=20)
    options=parser.parse_args()
    result=benchmark(options.objects,options.rows,options.latency_ms)
    text=json.dumps(result,indent=2)
    if options.output:
        options.output.parent.mkdir(parents=True,exist_ok=True);options.output.write_text(text+'\n')
    print(text)
