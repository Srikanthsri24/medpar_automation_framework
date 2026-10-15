import json
from pathlib import Path
from medpar_qa.ingestion.row_selection import select
from medpar_qa.enums import Stage,FileRole


def test_json_wrapper_nested_lines_are_not_input_rows(tmp_path):
    rows=[{'id':i,'diagnoses':[{'code':'A'}]*100} for i in range(20)]
    (tmp_path/'claims.json').write_text(json.dumps({'response':{'records':rows}}))
    chosen,audit=select(['claims.json'],Stage.FINAL_ACTION,FileRole.SOURCE,tmp_path,{'mode':'first_n_per_file','limit':5,'include_related_records':False},lambda r:[])
    assert len(chosen)==5 and audit['files'][0]['total_rows']==20
    assert [r.source.row_number for r in chosen]==[1,2,3,4,5]
    assert audit['target_rows']==5 and not audit['full_dataset']


def test_related_cross_file_claims_are_context_without_using_up_target_limit(tmp_path):
    (tmp_path/'a.json').write_text(json.dumps([{'key':'A'},{'key':'B'}]))
    (tmp_path/'b.json').write_text(json.dumps([{'key':'C'},{'key':'A'}]))
    records,audit=select(['a.json','b.json'],Stage.FINAL_ACTION,FileRole.SOURCE,tmp_path,{'mode':'first_n_per_file','limit':1},lambda r:[r.data['key']])
    assert audit['target_rows']==2 and audit['context_rows']==1
    assert len(records)==3
    assert {(r.source.file_path,r.source.row_number) for r in records}=={('a.json',1),('b.json',1),('b.json',2)}


def test_parquet_top_level_rows_and_all_mode(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.table({'id':list(range(1000)),'lines':[[{'code':'A'}]]*1000}),tmp_path/'claims.parquet')
    records,audit=select(['claims.parquet'],Stage.SPLIT,FileRole.SOURCE,tmp_path,{'mode':'first_n_per_file','limit':5,'include_related_records':False},lambda r:[])
    assert len(records)==5 and audit['files'][0]['total_rows']==1000
    records,audit=select(['claims.parquet'],Stage.SPLIT,FileRole.SOURCE,tmp_path,{'mode':'all'},lambda r:[])
    assert len(records)==1000 and audit['full_dataset']


def test_large_json_counts_all_rows_but_keeps_only_five(tmp_path):
    source=tmp_path/'large.json'
    with source.open('w') as out:
        out.write('[')
        for i in range(100000):
            if i:out.write(',')
            out.write(json.dumps({'id':i,'lines':[{'code':'A'},{'code':'B'}]}))
        out.write(']')
    rows,audit=select(['large.json'],Stage.FINAL_ACTION,FileRole.SOURCE,tmp_path,{'mode':'first_n_per_file','limit':5,'include_related_records':False},lambda r:[])
    assert audit['files'][0]['total_rows']==100000 and len(rows)==5
    assert [r.data['id'] for r in rows]==[0,1,2,3,4]


def test_total_limit_is_shared_across_files(tmp_path):
    for name in ('a.json','b.json'):(tmp_path/name).write_text(json.dumps([{'id':i} for i in range(10)]))
    rows,audit=select(['a.json','b.json'],Stage.SPLIT,FileRole.SOURCE,tmp_path,{'mode':'first_n_total','limit':5,'include_related_records':False},lambda r:[])
    assert len(rows)==5 and audit['target_rows']==5
    assert [f['selected_rows'] for f in audit['files']]==[5,0]
    assert [f['total_rows'] for f in audit['files']]==[10,10]
