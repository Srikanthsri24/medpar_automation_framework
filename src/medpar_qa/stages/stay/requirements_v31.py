"""Source-derived Stay checks from BxB pp7–8, separate from golden comparison."""
from decimal import Decimal
from medpar_qa.models import RuleResult
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import to_decimal
from medpar_qa.stages.intermediate.business_rules import line_value, whole_dollars


def validate_stay_calculations(records, actual, resolver):
    results = []
    def get(record, *names):
        for name in names:
            value = resolver.get(record.data, name)
            if value not in (None, ''): return value
        raise LookupError('Missing source operand: '+names[0])
    def compare(field, rule, calculate, normalize=lambda x:x):
        observed = resolver.get(actual.data, field)
        try:
            expected = calculate()
            status = ValidationStatus.NOT_APPLICABLE if observed is None else ValidationStatus.PASS if normalize(observed)==normalize(expected) else ValidationStatus.FAIL
            message = 'Source-derived Stay expectation matches' if status==ValidationStatus.PASS else 'Stay source calculation differs from output' if status==ValidationStatus.FAIL else 'Calculated expectation; output field absent'
        except LookupError as exc:
            expected = 'Complete source operands';status=ValidationStatus.BLOCKED if observed is not None else ValidationStatus.NOT_APPLICABLE;message=str(exc)
        except (ValueError,TypeError,ArithmeticError) as exc:
            expected='Valid source operands';status=ValidationStatus.FAIL;message=str(exc)
        results.append(RuleResult(Stage.STAY,rule,status,message,'' if expected is None else expected,observed,field_name=field,record_ids=[r.record_id for r in records],source_files=sorted({r.source.file_path for r in records}),evidence={'specification':'BxB pp7–8 / v3.1 ST-1, ST-2', 'source_bill_count':len(records)}))
    def price():
        total=Decimal(0)
        for record in records:
            for names in [('claim_payment_amount','claimPaymentAmount','reimbursement_amount'),('primary_payer_amount','primary_payment_amount'),('coinsurance_amount','coinsuranceAmount'),('inpatient_deductible_amount','inPatientDeduction'),('blood_deductible_amount','bloodDeductable')]:
                total+=to_decimal(get(record,*names))
            total-=to_decimal(get(record,'outlier_payment_amount','outlierAmount'))
        return whole_dollars(total)
    compare('medpar_drg_price_0380','ST-DRG-PRICE-CALCULATION',price,to_decimal)
    def covered_end():
        snf = str(resolver.get(records[0].data,'transaction_code')) in ('0','4')
        if not snf: return None
        dates=[]
        for record in records:
            lines=resolver.get(record.data,'occurrence_span_lines')
            if lines is None: raise LookupError('Missing occurrence-span collection')
            for line in lines:
                if str(line_value(line,'code','spanCode','occurrenceSpanCode')).strip()=='22':
                    dates.append(parse_date(line_value(line,'thru','toDate','thruDate','thru_date','spanThruDate','occurrenceSpanThruDate')))
        return max(dates).strftime('%Y%j') if dates else None
    compare('medpar_dte_cr_ended_0220','ST-COVERED-CARE-END',covered_end,lambda x:parse_date(x,allow_none=True))
    def latest_device():
        ordered=sorted(records,key=lambda r: parse_date(resolver.get(r.data,'processing_date'),allow_none=True) or __import__('datetime').date.min,reverse=True)
        return next((resolver.get(r.data,'investigationalDeviceExemption') for r in ordered if resolver.get(r.data,'investigationalDeviceExemption') not in (None,'')), None)
    compare('investigationalDeviceExemption','ST-LATEST-NONBLANK-IDE',latest_device)
    def representative_payee():
        values=[resolver.get(r.data,'rpInd') for r in records]
        return 'R' if any(str(v).strip()=='R' for v in values) else ''
    compare('rpInd','ST-REPRESENTATIVE-PAYEE',representative_payee,lambda x:str(x or '').strip())
    if len(records)>1:
        compare('bill_count','ST-MERGED-BILL-COUNT',lambda:len(records),int)
    # Single-bill 0 versus 1 remains a documented specification conflict.
    return results
