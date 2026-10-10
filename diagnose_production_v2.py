#!/usr/bin/env python3
"""Read-only, PHI-minimizing MEDPAR production field audit."""
import argparse, collections, json, re
from pathlib import Path

FOLDERS={'final_action':'1-quarterly-claims-parquet','split':'2-final-action-rules-parquet','intermediate':'5-intermediate-processing'}
ALIASES={
 'transaction_code':['transactioncode','transactionCode','transaction_code','CLM-TRANS-CD'],
 'hicn':['claimcannchequatable','claimCanNchEquatable','hicn','HICN','beneficiaryId'],
 'provider_id':['medparProvider0130','medparPrvdrFullNum1660','providerid','providerId','provider_id'],
 'admission_date':['admissiondate','admissionDate','medparAdmissionDate','admission_date'],
 'split_year_indicator':['medparSplitYearIndicator','splitYearIndicator','split_year_indicator'],
}
def norm(x): return re.sub('[^a-z0-9]','',str(x).lower())
def lookup(row, field):
 indexed={norm(k):v for k,v in row.items()}
 for name in ALIASES[field]:
  val=indexed.get(norm(name))
  if val is not None and str(val).strip()!='': return val
 return None
def rows(path):
 if path.suffix.lower()=='.parquet':
  import pyarrow.parquet as pq
  for batch in pq.ParquetFile(path).iter_batches(batch_size=2000): yield from batch.to_pylist()
 else:
  data=json.loads(path.read_text(encoding='utf-8'))
  if isinstance(data,list): yield from data
  elif isinstance(data,dict):
   for key in ('records','data','items','claims'):
    if isinstance(data.get(key),list): yield from data[key]; return
   yield data

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',default='reports/production_diagnosis_v2');a=p.parse_args()
 root=Path(a.root); out=Path(a.out);out.mkdir(parents=True,exist_ok=True); summary={}
 for stage,folder in FOLDERS.items():
  directory=root/folder; files=sorted(f for f in directory.rglob('*') if f.is_file() and f.suffix.lower() in ('.json','.parquet')) if directory.exists() else []
  codes=collections.Counter(); missing=collections.Counter(); identities=collections.Counter(); errors=[]; count=0; examples={}
  for file in files:
   try:
    for row in rows(file):
     if not isinstance(row,dict): continue
     count+=1
     if stage!='intermediate':
      val=lookup(row,'transaction_code');code=str(val) if val is not None else '<MISSING>'
      codes[code]+=1
      if code not in examples: examples[code]={'file':str(file.relative_to(root)),'matched_field_names':[k for k in row if norm(k) in {norm(a) for a in ALIASES['transaction_code']} ]}
     else:
      identity=tuple(str(lookup(row,f)) for f in ('hicn','provider_id','admission_date','split_year_indicator'))
      identities[identity]+=1
      for f in ('hicn','provider_id','admission_date','split_year_indicator'):
       if lookup(row,f) is None: missing[f]+=1
   except Exception as exc: errors.append({'file':str(file.relative_to(root)),'error':str(exc)})
  duplicates=[v for v in identities.values() if v>1]
  summary[stage]={'files':len(files),'records':count,'transaction_codes':dict(codes),'missing_identity_fields':dict(missing),'duplicate_identity_groups':len(duplicates),'records_in_duplicate_groups':sum(duplicates),'examples':examples,'read_errors':errors[:20]}
 (out/'production_diagnosis_v2.json').write_text(json.dumps(summary,indent=2,default=str))
 print(json.dumps(summary,indent=2,default=str));print('Saved:',out/'production_diagnosis_v2.json')
if __name__=='__main__':main()
