"""Read sampled Parquet over conditional S3 byte ranges, preserving full row totals."""
from medpar_qa.progress import emit, Progress
import io
import json
from pathlib import Path


def sample_metadata(path):
    marker=Path(str(path)+'.source_sample.json')
    return json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else None


class S3RangeReader(io.RawIOBase):
    """Seekable read-only object adapter. ETag conditions reject changing extracts."""
    def __init__(self,client,bucket,key,size,etag=None):
        self.client=client;self.bucket=bucket;self.key=key;self.size=size;self.etag=etag
        self.position=0;self.bytes_read=0;self.requests=0;self.cached=None
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=io.SEEK_SET):
        position=offset if whence==io.SEEK_SET else self.position+offset if whence==io.SEEK_CUR else self.size+offset if whence==io.SEEK_END else None
        if position is None or position<0:raise ValueError('Invalid S3 seek')
        self.position=position;return position
    def read(self,size=-1):
        if self.closed:raise ValueError('Read on closed S3 object')
        count=max(0,self.size-self.position) if size is None or size<0 else min(size,max(0,self.size-self.position))
        if not count:return b''
        start=self.position
        if self.cached is not None:
            cached_start,data=self.cached
            offset=start-cached_start
            if offset>=0 and offset+count<=len(data):
                self.position+=count;return data[offset:offset+count]
        kwargs=dict(Bucket=self.bucket,Key=self.key,Range=f'bytes={start}-{start+count-1}')
        if self.etag:kwargs['IfMatch']=self.etag
        emit(f'S3 range read: s3://{self.bucket}/{self.key}; bytes {start:,}-{start+count-1:,}; object size {self.size:,}; previously transferred {self.bytes_read:,} bytes')
        response=self.client.get_object(**kwargs);body=response['Body']
        try:data=body.read()
        finally:body.close()
        if len(data)!=count:raise ValueError('S3 returned an incomplete or ignored byte range; sample was not accepted')
        self.cached=(start,data) if len(data)<=8*1024*1024 else None
        self.position+=len(data);self.bytes_read+=len(data);self.requests+=1
        return data
    def readinto(self,buffer):
        data=self.read(len(buffer));buffer[:len(data)]=data;return len(data)


def stage_parquet_sample(client,bucket,key,size,etag,destination,limit):
    """Persist only the first N rows; row totals come from the Parquet footer."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    with S3RangeReader(client,bucket,key,size,etag) as stream:
        stream.seek(0);magic=stream.read(4)
        if magic!=b'PAR1':return None
        parquet=pq.ParquetFile(stream,pre_buffer=False,buffer_size=0)
        emit(f'Parquet footer read: {parquet.metadata.num_rows:,} source rows; selecting up to {limit:,}')
        sample_progress=Progress('Parquet source rows selected',min(limit,parquet.metadata.num_rows),'rows')
        batches=[];remaining=limit
        for batch in parquet.iter_batches(batch_size=limit):
            take=min(batch.num_rows,remaining)
            if take:batches.append(batch.slice(0,take));remaining-=take
            sample_progress.update(limit-remaining,force=True)
            if remaining==0:break
        table=pa.Table.from_batches(batches,schema=parquet.schema_arrow)
        total=parquet.metadata.num_rows
        metadata=dict(access_mode='s3_parquet_sample',source_total_rows=total,cached_rows=table.num_rows,complete_source=table.num_rows==total,source_bytes=size,bytes_transferred=stream.bytes_read,range_requests=stream.requests,source_etag=etag,hash_scope='Cached selected-row Parquet, not the full remote object',population_scope='Full source identity population is not scanned for a partial source cache. Reference outputs remain complete.')
        destination=Path(destination)
        pq.write_table(table,destination)
        Path(str(destination)+'.source_sample.json').write_text(json.dumps(metadata),encoding='utf-8')
        return metadata
