"""Full-input multiplicity evidence, independent of validation sampling."""
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
from medpar_qa.ingestion.row_selection import iter_records
from medpar_qa.enums import Stage,FileRole


def audit_populations(root,stage,paths,identity):
    counters={};result={};locations={}
    for role,files in paths.items():
        counts=Counter();examples=defaultdict(list);fingerprints=defaultdict(list);inventory=[]
        for file in dict.fromkeys(files):
            hashes=Counter();total=0
            for record in iter_records(Path(root)/file,Stage(stage),FileRole.SOURCE,root):
                if isinstance(record.data.get('record'),dict):record.data=record.data['record']
                key=identity(record);counts[key]+=1;total+=1
                if len(examples[key])<2:examples[key].append(dict(file=file,row=record.source.row_number))
                digest=hashlib.sha256(json.dumps(record.data,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest();hashes[digest]+=1
            fingerprint=hashlib.sha256(json.dumps(sorted(hashes.items())).encode()).hexdigest()
            fingerprints[fingerprint].append(file);inventory.append(dict(file=file,rows=total,content_sha256=fingerprint))
        counters[role]=counts;locations[role]=examples
        result[role]=dict(files=len(inventory),rows=sum(counts.values()),distinct_identities=len(counts),repeated_identity_rows=sum(counts.values())-len(counts),missing_identity_rows=counts[None],inventory=inventory,identical_file_groups=[dict(content_sha256=h,files=files) for h,files in fingerprints.items() if len(files)>1])
    source=counters['original'];output=counters['keep']+counters['drop'];excess=output-source;missing=source-output
    overlap=set(counters['keep'])&set(counters['drop']);overlap.discard(None)
    keys=list(excess)[:10]
    return dict(identity_basis='Configured comparison identity; repeated identities are evidence of multiplicity, not automatic proof of duplicate business records.',datasets=result,excess_output_occurrences=sum(excess.values()),missing_output_occurrences=sum(missing.values()),identities_in_both_outputs=len(overlap),examples=[dict(identity=key,original_occurrences=source[key],keep_occurrences=counters['keep'][key],drop_occurrences=counters['drop'][key],locations={role:locations[role].get(key,[]) for role in paths}) for key in keys],conclusion='The supplied outputs do not form a one-to-one partition of the supplied originals.' if excess or missing or overlap else 'Identity multiplicities balance; field and decision validation is still required.')


def render_population(audit):
    """Explain raw file populations without treating identity deduplication as acceptance."""
    import html
    table=''.join(f'<tr><td>{role.title()}</td><td>{d["files"]:,}</td><td>{d["rows"]:,}</td><td>{d["distinct_identities"]:,}</td><td>{d["repeated_identity_rows"]:,}</td><td>{len(d["identical_file_groups"])}</td></tr>' for role,d in audit['datasets'].items())
    return '<section><h3>Complete original / keep / drop population audit</h3><table><tr><th>Dataset</th><th>Files</th><th>Physical rows</th><th>Distinct comparison identities</th><th>Repeated identity occurrences</th><th>Identical-content file groups</th></tr>'+table+'</table><p><strong>'+html.escape(audit['conclusion'])+'</strong></p><p>Excess output occurrences: '+str(audit['excess_output_occurrences'])+' · Missing original occurrences: '+str(audit['missing_output_occurrences'])+' · Identities appearing in both keep and drop: '+str(audit['identities_in_both_outputs'])+'</p><p>All configured files are included once by path. The audit does not silently remove repeated records or choose a historical execution. Repeated identities can represent multiple claim versions; identical-content file groups separately prove repeated complete file content. Select matching original and output execution sets before claiming one-to-one reconciliation.</p><details><summary>File inventories, SHA-256 content fingerprints and row-location evidence</summary><pre>'+html.escape(json.dumps(audit,default=str))+'</pre></details></section>'
