"""Blood-pints physical encoding check; offsets must come from an approved layout."""
from decimal import Decimal
from medpar_qa.models import RuleResult, Stage, ValidationStatus


def validate_blood_overflow(record, resolver, layout, physical, encoding='ascii'):
    field = 'medpar_blood_pints_0520'
    spec = next((s for s in layout if s.get('name') in [field,*resolver.aliases.get(field,[])]),None)
    expected = actual = None
    evidence = {}
    status = ValidationStatus.BLOCKED
    message = 'Approved three-byte 0520 layout and physical record are required'
    if spec is not None and physical is not None:
        try:
            if int(spec['length']) != 3: raise ValueError('0520 layout must be three bytes')
            value = Decimal(str(resolver.get(record.data,field)))
            if not value.is_finite() or value < 0 or value != value.to_integral_value():
                raise ValueError('0520 JSON value must be a nonnegative integer')
            expected = f'{min(int(value),999):03d}'
            raw = physical if isinstance(physical,bytes) else physical.encode(encoding)
            start = int(spec['start'])-1
            if start < 0: raise ValueError('Invalid 0520 byte start')
            actual = raw[start:start+3].decode(encoding)
            status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
            message = '0520 physical value agrees with capped JSON value' if actual == expected else '0520 physical value differs from capped JSON value'
            evidence = dict(original_value=int(value),cap_required=value>999,capped_value=min(int(value),999),one_based_start=start+1)
        except (ValueError,TypeError,ArithmeticError,KeyError) as exc:
            status,message = ValidationStatus.FAIL,str(exc)
    return RuleResult(stage=Stage.FINAL_MEDPAR,rule_id='FM-OVERFLOW-0520',status=status,message=message,
        field_name=field,expected=expected,actual=actual,evidence=evidence,
        record_ids=[record.record_id],source_files=[record.source.file_path])
