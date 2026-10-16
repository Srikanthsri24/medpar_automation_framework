"""Regression contracts for delivered Final data and flat intermediary values."""
from medpar_qa.enums import Stage,ValidationStatus
from medpar_qa.models import RuleResult
from medpar_qa.normalization.fields import _key_form


def forbidden_paths(value,names=('cacheDataInternal',),path='$'):
    forbidden={_key_form(name) for name in names};found=[]
    if isinstance(value,dict):
        for key,child in value.items():
            current=f'{path}.{key}'
            if _key_form(key) in forbidden:found.append(current)
            found.extend(forbidden_paths(child,names,current))
    elif isinstance(value,list):
        for i,child in enumerate(value):found.extend(forbidden_paths(child,names,f'{path}[{i}]'))
    return found


def remove_fields(value,names):
    forbidden={_key_form(name) for name in names}
    if isinstance(value,dict):return {k:remove_fields(v,names) for k,v in value.items() if _key_form(k) not in forbidden}
    if isinstance(value,list):return [remove_fields(v,names) for v in value]
    return value


def forbidden_result(record,names=('cacheDataInternal',)):
    paths=forbidden_paths(record.data,names)
    paths+= [f"schema:{f['path']}" for f in record.metadata.get('parquet_schema',[]) if _key_form(f['name']) in {_key_form(n) for n in names}]
    return RuleResult(Stage.FINAL_MEDPAR,'FM-NO-INTERNAL-FIELDS',ValidationStatus.FAIL if paths else ValidationStatus.PASS,'Forbidden internal fields found' if paths else 'No forbidden internal fields in delivered record or available Parquet schema',expected={'absent_fields':list(names)},actual=sorted(set(paths)),record_ids=[record.record_id],source_files=[record.source.file_path])


def intermediary_type(record,resolver,stage):
    value=resolver.get(record.data,'medpar_intmd_num_0580')
    columns=[f for f in record.metadata.get('parquet_schema',[]) if _key_form(f['name'])=='medparintmdnum0580']
    valid=isinstance(value,str) and all(f['type'] in ('string','large_string','string_view') for f in columns)
    return RuleResult(stage,'INT-TYPE-0580' if stage==Stage.INTERMEDIATE else 'FM-TYPE-0580',ValidationStatus.PASS if valid else ValidationStatus.FAIL,'0580 must be a flat string with leading zeros preserved',expected='JSON string / Parquet logical string',actual={'value':value,'python_type':type(value).__name__,'parquet_columns':columns},field_name='medpar_intmd_num_0580',record_ids=[record.record_id],source_files=[record.source.file_path])


def intermediary_id(value):
    if isinstance(value,dict):
        value=next((v for k,v in value.items() if _key_form(k)=='id'),None)
    if value is None:raise LookupError('Missing first-claim fiscalIntermediary.id')
    if isinstance(value,(dict,list,bool)):raise ValueError('fiscalIntermediary.id must be a character or numeric scalar')
    return str(value)


def carry_forward_contracts(source, target, resolver):
    """Final 0580/0611 must equal Intermediate values, including leading zeros/sign."""
    checks = []
    for field, rule in (('medpar_intmd_num_0580', 'FM-CARRY-0580'),
                        ('medpar_death_after_adm_0611', 'FM-CARRY-0611')):
        expected, actual = resolver.get(source.data, field), resolver.get(target.data, field)
        if expected is None:
            continue
        checks.append(RuleResult(Stage.FINAL_MEDPAR, rule,
            ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL,
            'Final field must preserve the Intermediate value and type',
            expected=expected, actual=actual, field_name=field,
            record_ids=[source.record_id, target.record_id],
            source_files=list(dict.fromkeys([source.source.file_path, target.source.file_path]))))
    return checks


def parquet_contracts(path, stage, forbidden_fields=('cacheDataInternal',)):
    """Validate footer-only schema, including empty files and all-null structs."""
    from medpar_qa.ingestion.schema_metadata import parquet_schema
    fields = parquet_schema(path)
    results = []
    if stage == Stage.FINAL_MEDPAR:
        forbidden = {_key_form(name) for name in forbidden_fields}
        found = [f['path'] for f in fields if _key_form(f['name']) in forbidden]
        results.append(RuleResult(stage, 'FM-NO-INTERNAL-FIELDS',
            ValidationStatus.FAIL if found else ValidationStatus.PASS,
            'Final Parquet schema must exclude internal cache fields, even with zero rows',
            expected={'absent_fields': list(forbidden_fields)}, actual=found,
            source_files=[str(path)], evidence={'schema_only': True}))
    for field in fields:
        if _key_form(field['name']) == 'medparintmdnum0580':
            valid = field['type'] in ('string', 'large_string', 'string_view')
            results.append(RuleResult(stage, 'INT-TYPE-0580' if stage == Stage.INTERMEDIATE else 'FM-TYPE-0580',
                ValidationStatus.PASS if valid else ValidationStatus.FAIL,
                '0580 Parquet logical type must be string', expected='string', actual=field,
                field_name='medpar_intmd_num_0580', source_files=[str(path)], evidence={'schema_only': True}))
        if _key_form(field['name']) == 'medpardeathafteradm0611':
            valid = field['type'] in ('int8', 'int16', 'int32', 'int64')
            results.append(RuleResult(stage, 'INT-TYPE-0611' if stage == Stage.INTERMEDIATE else 'FM-TYPE-0611',
                ValidationStatus.PASS if valid else ValidationStatus.FAIL,
                '0611 Parquet type must support signed day differences', expected='signed integer', actual=field,
                field_name='medpar_death_after_adm_0611', source_files=[str(path)], evidence={'schema_only': True}))
    return results
