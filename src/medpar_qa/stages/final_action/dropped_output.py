"""Reconcile supplied DROP outputs and validate their episode net indicator (WI01)."""
from collections import Counter,defaultdict
from medpar_qa.models import RuleResult
from medpar_qa.enums import Stage,ValidationStatus,RecordDecision
from .reconciler import record_identity
from .grouping import build_group_key


def validate_dropped_output(sources,actuals,decisions,resolver,settings):
    wanted={d.record_id for d in decisions if d.decision==RecordDecision.DROP}
    expected=[r for r in sources if r.record_id in wanted]
    left=Counter(record_identity(r,resolver,settings) for r in expected)
    right=Counter(record_identity(r,resolver,settings) for r in actuals)
    missing=set((left-right).elements());unexpected=list((right-left).elements())
    missing_sources=[r for r in expected if record_identity(r,resolver,settings) in missing]
    results=[RuleResult(Stage.FINAL_ACTION,'FA-DROPPED-OUTPUT-RECONCILIATION',ValidationStatus.FAIL if missing or unexpected else ValidationStatus.PASS,
        'Supplied dropped outputs compared with computed DROP identities',expected={'dropped_count':len(expected)},actual={'output_count':len(actuals)},record_ids=[r.record_id for r in missing_sources],source_files=sorted({r.source.file_path for r in [*missing_sources,*actuals]}),evidence={'missing_identities':list(missing),'unexpected_identities':unexpected})]
    indexed=defaultdict(list);groups=defaultdict(list)
    for r in sources:
        indexed[record_identity(r,resolver,settings)].append(r)
        try:groups[build_group_key(r,resolver,validate_transaction_codes=settings.validate_transaction_codes)].append(r)
        except (ValueError,TypeError):pass
    evaluated=0
    for actual in actuals:
        matches=indexed[record_identity(actual,resolver,settings)]
        if not matches:continue # Unmatched DROP identity is already failed above.
        evaluated+=1
        source=matches[0]
        group=groups[build_group_key(source,resolver,validate_transaction_codes=settings.validate_transaction_codes)]
        qcs={str(resolver.get(r.data,'query_code')).strip() for r in group}
        net=int('0' in qcs)+2*int('5' in qcs)
        observed=resolver.get(actual.data,'warning_indicator_01')
        if observed is None: observed=resolver.get(actual.data,'netIndicator',resolver.get(actual.data,'netInd'))
        try:status=ValidationStatus.BLOCKED if observed is None else ValidationStatus.PASS if int(observed)==net else ValidationStatus.FAIL
        except (TypeError,ValueError):status=ValidationStatus.FAIL
        results.append(RuleResult(Stage.FINAL_ACTION,'FA-DROPPED-NET-INDICATOR',status,'Dropped record net indicator derives from episode QC0/QC5 presence',net,observed,field_name='warning_indicator_01',record_ids=[source.record_id,actual.record_id],source_files=[source.source.file_path,actual.source.file_path],evidence={'episode_query_codes':sorted(qcs)}))
    results.append(RuleResult(Stage.FINAL_ACTION,"FA-DROPPED-NET-COVERAGE",ValidationStatus.PASS if evaluated==len(actuals) else ValidationStatus.BLOCKED,
        "Net checks require every supplied dropped record to match its source episode",expected={'dropped_records':len(actuals),'net_checks':len(actuals)},actual={'dropped_records':len(actuals),'net_checks':evaluated},source_files=sorted({r.source.file_path for r in actuals})))
    return results
