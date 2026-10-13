"""Three-way record and source-charge reconciliation; errors are separate from drops."""
from decimal import Decimal
from medpar_qa.models import RuleResult
from medpar_qa.enums import RecordDecision,ValidationStatus
from medpar_qa.normalization.decimal_values import to_decimal


def three_way_balance(stage,records,decisions,resolver):
    outcomes={d.record_id:d.decision for d in decisions}
    counts={'input':len(records),'kept':0,'dropped':0,'error':0}
    charges={key:Decimal(0) for key in counts};missing=[];invalid=[]
    for record in records:
        route='kept' if outcomes.get(record.record_id)==RecordDecision.KEEP else 'dropped' if outcomes.get(record.record_id)==RecordDecision.DROP else 'error'
        counts[route]+=1
        amount=resolver.get(record.data,'totalCharges',resolver.get(record.data,'medpar_tot_chrg_0400'))
        if amount in (None,''):missing.append(record.record_id);continue
        try:
            value=to_decimal(amount);charges['input']+=value;charges[route]+=value
        except (ValueError,TypeError,ArithmeticError):invalid.append(record.record_id)
    return [RuleResult(stage,'FA-THREE-WAY-RECORD-BALANCE',ValidationStatus.PASS if counts['input']==sum(counts[k] for k in ('kept','dropped','error')) else ValidationStatus.FAIL,
        'Input records accounted for as kept, dropped or error; balanced errors remain business failures',expected='input = kept + dropped + error',actual=counts),
        RuleResult(stage,'FA-THREE-WAY-CHARGE-BALANCE',ValidationStatus.FAIL if invalid else ValidationStatus.NOT_APPLICABLE if missing else ValidationStatus.PASS if charges['input']==sum(charges[k] for k in ('kept','dropped','error')) else ValidationStatus.FAIL,
        'Source charges accounted for by disposition',expected='input charges = kept + dropped + error charges',actual={k:str(v) for k,v in charges.items()},evidence={'missing_charge_operands':missing,'invalid_charge_operands':invalid})]
