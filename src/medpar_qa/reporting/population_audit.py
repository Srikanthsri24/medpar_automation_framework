"""Full-input multiplicity evidence, independent of validation sampling."""
from medpar_qa.progress import tracked, emit, Progress

import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
from medpar_qa.ingestion.row_selection import iter_records
from medpar_qa.enums import Stage,FileRole


@tracked('Audit full source/KEEP/DROP identity populations')
def audit_populations(root,stage,paths,identity,exception_predicate=None,one_to_one=True):
    counters={};result={};locations={};exceptions=Counter()
    for role,files in paths.items():
        counts=Counter();examples=defaultdict(list);fingerprints=defaultdict(list);inventory=[]
        unique_files=list(dict.fromkeys(files));progress=Progress(f'Population audit {role}',len(unique_files),'files')
        for file_number,file in enumerate(unique_files,1):
            emit(f'Population audit {role}: scanning {file_number}/{len(unique_files)} {file}')
            hashes=Counter();total=0
            for record in iter_records(Path(root)/file,Stage(stage),FileRole.SOURCE,root):
                if isinstance(record.data.get('record'),dict):record.data=record.data['record']
                key=identity(record);counts[key]+=1;total+=1
                if total%10000==0:emit(f'Population audit {role}: {total:,} rows scanned in current file')
                if role=='original' and exception_predicate and exception_predicate(record):exceptions[key]+=1
                if len(examples[key])<2:examples[key].append(dict(file=file,row=record.source.row_number))
                digest=hashlib.sha256(json.dumps(record.data,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest();hashes[digest]+=1
            fingerprint=hashlib.sha256(json.dumps(sorted(hashes.items())).encode()).hexdigest()
            fingerprints[fingerprint].append(file);inventory.append(dict(file=file,rows=total,content_sha256=fingerprint))
            progress.update(file_number,force=True)
        counters[role]=counts;locations[role]=examples
        result[role]=dict(files=len(inventory),rows=sum(counts.values()),distinct_identities=len(counts),repeated_identity_rows=sum(counts.values())-len(counts),missing_identity_rows=counts[None],inventory=inventory,identical_file_groups=[dict(content_sha256=h,files=files) for h,files in fingerprints.items() if len(files)>1])
    source=counters['original']-exceptions;output=counters['keep']+counters['drop'];excess=output-source;missing=source-output
    overlap=set(counters['keep'])&set(counters['drop']);overlap.discard(None)
    keys=list(excess)[:10]
    return dict(count_comparison_applicable=one_to_one,source_exception_rows=sum(exceptions.values()),expected_keep_drop_rows=sum(source.values()) if one_to_one else None,identity_basis='Configured comparison identity; repeated identities are evidence of multiplicity, not automatic proof of duplicate business records.',datasets=result,excess_output_occurrences=sum(excess.values()) if one_to_one else None,missing_output_occurrences=sum(missing.values()) if one_to_one else None,identities_in_both_outputs=len(overlap),examples=[dict(identity=key,original_occurrences=counters['original'][key],expected_keep_drop_occurrences=source[key],exception_occurrences=exceptions[key],keep_occurrences=counters['keep'][key],drop_occurrences=counters['drop'][key],locations={role:locations[role].get(key,[]) for role in paths}) for key in (keys if one_to_one else [])],conclusion='Physical counts are descriptive for this stage: merging or derivation can change output row counts. Verify logical identities, generated outputs and field values instead of requiring equal physical counts.' if not one_to_one else 'The supplied outputs do not form a one-to-one partition of the supplied originals.' if excess or missing or overlap else 'Identity multiplicities balance; field and decision validation is still required.')


def render_population(audit):
    """Explain raw file populations without treating identity deduplication as acceptance."""
    import html
    table=''.join(f'<tr><td>{role.title()}</td><td>{d["files"]:,}</td><td>{d["rows"]:,}</td><td>{d["distinct_identities"]:,}</td><td>{d["repeated_identity_rows"]:,}</td><td>{len(d["identical_file_groups"])}</td></tr>' for role,d in audit['datasets'].items())
    if audit.get('count_comparison_applicable',True):
        count_note='<p>Excess output occurrences: '+str(audit['excess_output_occurrences'])+' · Missing expected occurrences: '+str(audit['missing_output_occurrences'])+'</p><p>Source exception rows: '+str(audit.get('source_exception_rows',0))+'; expected KEEP + DROP population: '+str(audit.get('expected_keep_drop_rows',0))+'. Split balances input = KEEP + DROP + exception.</p>'
    else:
        count_note='<p>Physical count equality: NOT APPLICABLE. Source segments and generated logical records have different granularities. Use generated-output and next-stage read counts for transfer reconciliation.</p>'
    return '<section id="population-proof"><h3>Complete original / keep / drop population audit</h3><table><tr><th>Dataset</th><th>Files</th><th>Physical rows</th><th>Distinct comparison identities</th><th>Repeated identity occurrences</th><th>Identical-content file groups</th></tr>'+table+'</table><p><strong>'+html.escape(audit['conclusion'])+'</strong></p>'+count_note+'<p>Identities appearing in both supplied keep and drop: '+str(audit['identities_in_both_outputs'])+'</p><p>Every configured file is included once by path. No repeated records are silently removed and no historical execution is selected automatically. Identity repetition and identical-content file groups are reported separately. The inventory and row-location evidence below identify the supplied reference populations.</p><details><summary>File inventories, SHA-256 content fingerprints and row-location evidence</summary><pre>'+html.escape(json.dumps(audit,default=str))+'</pre></details></section>'
