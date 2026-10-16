"""Stream top-level claim rows, keeping source row numbers and optional related context."""
from medpar_qa.progress import emit, Progress
from pathlib import Path
from collections import Counter
from medpar_qa.models import SourceRecord,SourceLocation
from medpar_qa.ingestion.readers import _record_id,InputReadError


def iter_records(path,stage,role,root):
    """Yield one top-level record at a time; preserve physical file row numbers."""
    path=Path(path);display=path.resolve().relative_to(Path(root).resolve()).as_posix()
    if path.suffix.lower()=='.parquet':
        import pyarrow.parquet as pq
        from urllib.parse import unquote
        partitions={unquote(k):unquote(v) for part in path.parent.parts if '=' in part for k,v in [part.split('=',1)] if v!='__HIVE_DEFAULT_PARTITION__'}
        def rows():
            for batch in pq.ParquetFile(path).iter_batches(batch_size=1024):
                for row in batch.to_pylist():
                    for key,value in partitions.items():
                        names=[name for name in row if ''.join(c.lower() for c in name if c.isalnum())==''.join(c.lower() for c in key if c.isalnum())]
                        name=names[0] if names else key
                        if row.get(name) is not None and str(row[name]).strip()!=value.strip():raise InputReadError(f'Parquet partition {key} conflicts with row value in {display}')
                        if row.get(name) is None:row[name]=value
                    yield row
        values=rows();fmt='parquet'
    elif path.suffix.lower()=='.json':
        try:from ijson.backends import python as ijson
        except ImportError as exc:raise InputReadError('Streaming JSON dependency is missing. Run: python -m pip install -e ".[test]" (or python -m pip install -r requirements.txt)') from exc
        def rows():
            with path.open('rb') as handle:
                offset=3 if handle.read(3)==b'\xef\xbb\xbf' else 0
                handle.seek(offset);first=b''
                while not first:
                    chunk=handle.read(1)
                    if not chunk:raise InputReadError(f'Empty JSON input: {display}')
                    first=chunk.strip()
                prefix='item' if first==b'[' else ''
                if first==b'{':
                    handle.seek(offset)
                    for event_path,event,value in ijson.parse(handle,use_float=True):
                        if event_path.split('.')[-1] in ('records','claims','data','items') and 'item' not in event_path.split('.') and event=='start_array':
                            prefix=event_path+'.item';break
                handle.seek(offset)
                for row in ijson.items(handle,prefix,use_float=True):yield row
        values=rows();fmt='json'
    else:raise InputReadError(f'Unsupported input format: {display}')
    from .schema_metadata import parquet_schema
    metadata={'parquet_schema':parquet_schema(path)} if fmt=='parquet' else {}
    for number,row in enumerate(values,1):
        if not isinstance(row,dict):raise InputReadError(f'Input row {number} must be an object in {display}')
        yield SourceRecord(dict(row),SourceLocation(display,number,fmt,stage,role),_record_id(path,number,row),metadata=metadata)


def options(value):
    """Validate row-selection choices without treating booleans as numeric limits."""
    value={'mode':'all'} if value is None else value
    if not isinstance(value,dict) or value.get('mode') not in ('all','first_n_per_file','first_n_total'):raise ValueError('row_selection.mode must be all, first_n_per_file or first_n_total')
    if value['mode']!='all' and (type(value.get('limit')) is not int or value['limit']<1):raise ValueError('row_selection.limit must be a positive integer')
    if type(value.get('include_related_records',True)) is not bool:raise ValueError('include_related_records must be true or false')
    return value


def select(files,stage,role,root,selection,token_function):
    """Count every supplied row and select targets plus transitive related context."""
    selection=options(selection);selected=[];inventory=[]
    file_progress=Progress('Source files read',len(files),'files')
    for file_number,name in enumerate(files,1):
        emit(f'Reading source file {file_number}/{len(files)}: {name}; selection {selection}')
        row_progress=Progress('Source rows scanned: '+str(name),unit='rows')
        total=0;chosen=[]
        from .s3_sampling import sample_metadata
        remote=sample_metadata(Path(root)/name)
        for row in iter_records(Path(root)/name,stage,role,root):
            total+=1
            if total%1000==0:row_progress.update(total)
            if selection['mode']=='all' or (len(chosen) if selection['mode']=='first_n_per_file' else len(selected)+len(chosen))<selection['limit']:chosen.append(row)
        row_progress.update(total,force=True)
        if remote:total=remote['source_total_rows']
        emit(f'Source file read: {name}; {total:,} original rows; {len(chosen):,} selected rows')
        file_progress.update(file_number,force=True)
        selected.extend(chosen)
        inventory.append(dict(file=name,total_rows=total,selected_rows=len(chosen),context_rows=0))
    target_ids={r.record_id for r in selected};known=set(target_ids);context=[]
    if selection['mode']!='all' and selection.get('include_related_records',True):
        tokens={key for row in selected for key in token_function(row)}
        while True:
            added=0
            for name in files:
                for row in iter_records(Path(root)/name,stage,role,root):
                    if row.record_id in known:continue
                    keys=token_function(row)
                    if tokens.intersection(keys):
                        context.append(row);known.add(row.record_id);tokens.update(keys);added+=1
            if not added:break
    counts=Counter(row.source.file_path for row in context)
    for item in inventory:item['context_rows']=counts[item['file']]
    return selected+context,dict(selection=selection,files=inventory,target_record_ids=sorted(target_ids),target_rows=len(selected),context_rows=len(context),processed_rows=len(selected)+len(context),full_dataset=all(i['total_rows']==i['selected_rows'] for i in inventory),scope='Nested diagnosis/procedure/revenue arrays belong to their parent claim; they are not additional input rows.')
