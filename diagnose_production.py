#!/usr/bin/env python3
"""Read-only production code/identity audit; no business rules are changed."""
import argparse, collections, csv, json
from pathlib import Path

STAGES = {
 'final_action': '1-quarterly-claims-parquet',
 'split': '2-final-action-rules-parquet',
 'intermediate': '5-intermediate-processing',
}
FIELDS = {
 'transaction': ['transactionCode','transaction_code','transactionCd','trans_cd','TRANSACTION_CODE'],
 'hicn': ['hicn','HICN','bene_id','beneficiary_id'],
 'provider': ['provider_id','providerId','provider','medpar_prvdr_full_num_1660'],
 'admission': ['admission_date','admissionDate','medpar_admsn_date'],
 'indicator': ['split_year_indicator','splitYearIndicator','splitYearInd'],
}
def find_value(row, names):
 for name in names:
  if name in row: return row[name]
 return None

def iter_rows(path):
 if path.suffix.lower()=='.parquet':
  import pyarrow.parquet as pq
  for batch in pq.ParquetFile(path).iter_batches(batch_size=1000):
   yield from batch.to_pylist()
 elif path.suffix.lower()=='.json':
  data=json.loads(path.read_text())
  if isinstance(data,list): yield from data
  elif isinstance(data,dict):
   for key in ('records','data','items','claims'):
    if isinstance(data.get(key),list): yield from data[key]; return
   yield data

def main():
 p=argparse.ArgumentParser(); p.add_argument('--root',required=True);p.add_argument('--out',default='reports/production_diagnosis');a=p.parse_args()
 root=Path(a.root);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 findings=[]; summary={}
 for stage,folder in STAGES.items():
  directory=root/folder
  counts=collections.Counter(); missing=collections.Counter(); ids=collections.Counter(); examples={}; total=0; errors=[]
  files=sorted(x for x in directory.rglob('*') if x.is_file() and x.suffix.lower() in ('.json','.parquet')) if directory.exists() else []
  for path in files:
   try:
    for row in iter_rows(path):
     if not isinstance(row,dict):continue
     total+=1
     if stage!='intermediate':
      code=find_value(row,FIELDS['transaction']); counts[str(code)]+=1
      if str(code) not in examples: examples[str(code)]={'file':str(path.relative_to(root)),'keys':sorted(row.keys())[:35]}
     else:
      identity=tuple(str(find_value(row,FIELDS[f])) for f in ('hicn','provider','admission','indicator'))
      ids[identity]+=1
      for field in ('hicn','provider','admission','indicator'):
       if find_value(row,FIELDS[field]) in (None,''): missing[field]+=1
   except Exception as exc: errors.append({'file':str(path),'error':str(exc)})
  duplicates=[{'identity':list(k),'count':v} for k,v in ids.items() if v>1]
  summary[stage]={'files':len(files),'records':total,'transaction_codes':dict(counts),'missing_identity_fields':dict(missing),'duplicate_identity_groups':len(duplicates),'duplicate_samples':duplicates[:15],'examples':examples,'read_errors':errors[:20]}
 (out/'production_diagnosis.json').write_text(json.dumps(summary,indent=2,default=str))
 print(json.dumps({k:{kk:v for kk,v in val.items() if kk not in ('examples','duplicate_samples')} for k,val in summary.items()},indent=2))
 print('Saved:',out/'production_diagnosis.json')
if __name__=='__main__':main()
