"""Verify source fields survive a stage boundary; additional derived fields are allowed."""
import re
from collections import defaultdict
from decimal import Decimal
from medpar_qa.models import RuleResult
from medpar_qa.enums import ValidationStatus
from medpar_qa.normalization.fields import nested_get


def unchanged_fields(stage, source, target, resolver, rule):
    def key(value): return re.sub(r'[^a-z0-9]','',value.lower())
    aliases={key(alias): canonical for canonical, names in resolver.aliases.items() for alias in [canonical,*names]}
    def fields(data,prefix=''):
        for name,value in data.items():
            if name.startswith('_') or name in {'dod_reference_available','dod_reference_matched','matched_date_of_death','matched_dod_verify_switch','ssi_reference_available','ssi_reference_matched','ssi_month_flags'}:continue
            path=prefix+name
            if isinstance(value,dict):yield from fields(value,path+'.')
            else:yield path,value
    def normalize(value):
        if isinstance(value,dict):return {k:normalize(v) for k,v in value.items() if not k.startswith('_')}
        if isinstance(value,list):return [normalize(v) for v in value]
        if value is None:return None
        return str(value).strip()
    differences={}; checked=[]
    for path,expected in fields(source.data):
        canonical=aliases.get(key(path),path)
        marker=object()
        observed=nested_get(target.data,path,marker)
        if observed is marker: observed=resolver.get(target.data,canonical)
        checked.append(path)
        if normalize(expected)!=normalize(observed): differences[path]={'expected':expected,'observed':observed}
    return RuleResult(stage,rule,ValidationStatus.FAIL if differences else ValidationStatus.PASS,
        'Original source fields differ from output' if differences else 'Every original source field is preserved',
        expected={'unchanged_source_fields':len(checked)},actual={'checked_fields':len(checked),'mismatch_count':len(differences)},
        record_ids=[source.record_id,target.record_id],source_files=[source.source.file_path,target.source.file_path],evidence={'fields_checked':checked,'differences':differences})
