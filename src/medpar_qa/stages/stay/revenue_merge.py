"""Sum like revenue occurrences without merging different service dates or drug IDs."""
from decimal import Decimal
from medpar_qa.normalization.decimal_values import to_decimal
from medpar_qa.stages.intermediate.business_rules import line_value

AMOUNTS=('units','unitCount','charges','amount','totalCharge','totalAmount','nonCoveredCharge','nonCoveredCharges','nonCoveredAmount')

def aggregate_revenue(lines):
    groups={}
    for line in lines:
        if not isinstance(line,dict):raise ValueError('Revenue line must be an object')
        identity=tuple(str(line_value(line,*names) or '') for names in [('code','revenueCode'),('serviceDate','revenueDate'),('ndcNumber','ndc')])
        if not identity[0]:raise ValueError('Revenue line has no code')
        if identity not in groups:groups[identity]={k:v for k,v in line.items() if not k.startswith('_')}
        else:
            for field in AMOUNTS:
                if field in line or field in groups[identity]:
                    if field not in line or field not in groups[identity]:raise LookupError('Missing matching revenue operand: '+field)
                    groups[identity][field]=str(to_decimal(groups[identity][field])+to_decimal(line[field]))
    return list(groups.values())


def coalesce_segments(records, resolver, identity_fields):
    """Accept multiple physical output segments only with stable fields and 45-line chunks."""
    from collections import defaultdict
    from medpar_qa.models import SourceRecord, RuleResult
    from medpar_qa.enums import Stage,ValidationStatus
    from medpar_qa.stages.common import record_identity
    from .code_precedence import strip_lineage
    groups=defaultdict(list)
    for record in records:groups[record_identity(record,resolver,identity_fields)].append(record)
    combined=[];checks=[]
    for identity,group in groups.items():
        if len(group)==1:
            combined.extend(group);continue
        keys=['revenue_lines',*resolver.aliases.get('revenue_lines',[])]
        def other(record):return strip_lineage([{k:v for k,v in record.data.items() if k not in keys}])[0]
        lengths=[len(resolver.get(record.data,'revenue_lines') or []) for record in group]
        valid=all(other(r)==other(group[0]) for r in group) and all(n==45 for n in lengths[:-1]) and 1<=lengths[-1]<=45
        if not valid:
            combined.extend(group);continue
        data=dict(group[0].data)
        field=next((key for key in keys if key in data),'revenue_lines')
        data[field]=[line for r in group for line in resolver.get(r.data,'revenue_lines')]
        combined.append(SourceRecord(data,group[0].source,group[0].record_id))
        checks.append(RuleResult(Stage.STAY,'ST-REVENUE-OUTPUT-SEGMENTS',ValidationStatus.PASS,'Physical revenue segments preserve stable stay fields and concatenate to one logical stay',expected='45 lines per non-final segment; 1..45 on final segment',actual={'segment_lengths':lengths,'logical_lines':sum(lengths)},record_ids=[r.record_id for r in group],source_files=sorted({r.source.file_path for r in group})))
    return combined,checks
