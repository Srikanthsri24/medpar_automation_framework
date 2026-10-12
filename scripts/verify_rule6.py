"""Execute the lead's eleven Rule 6 scenarios against the real default processor."""
import json
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
from medpar_qa.models import SourceRecord, SourceLocation
from medpar_qa.enums import Stage, FileRole
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.final_action.processor import FinalActionProcessor


def verify():
    resolver = FieldResolver.from_yaml(PROJECT_ROOT / 'config/field_aliases.yaml')
    scenarios = [
        (1, False, False, 4, False, False, 'KEEP_QC5'),
        (2, True, False, 4, False, False, 'DROP_BOTH'),
        (3, True, True, 6, False, False, 'DROP_BOTH'),
        (4, True, False, 1, False, False, 'KEEP_QC5'),
        (5, True, False, 2, False, False, 'KEEP_QC5'),
        (6, True, False, None, False, False, 'BLOCKED'),
        (7, True, False, 4, True, False, 'DROP_BOTH'),
        (8, False, False, 4, False, True, 'KEEP_QC5'),
        (9, True, False, 4, False, True, 'DROP_BOTH'),
        (10, True, False, ' 4 ', False, False, 'DROP_BOTH'),
        (11, True, False, 4, False, False, 'DROP_BOTH'),
    ]
    results = []
    for number, same_icn, qc0_newer, action, tied, invalid_tc, expected in scenarios:
        records=[]
        for row, qc in enumerate((5,0),1):
            data={'claimCan':'DEMO-ACCOUNT','claimCanNchEquatable':'DEMO-HICN','provider':{'providerId':'DEMO-PROVIDER'},'stayFromDate':'20260101','stayThruDate':'20260105','queryCode':qc,'transactionCode':'C' if invalid_tc and qc==0 else 1,'internalControlNumber':'A' if same_icn or qc==5 else 'B','actionCode':action if qc==0 else 1,'nchWeeklyProcessingDate':'20260110' if tied else '20260112' if (qc==0)==qc0_newer else '20260109','accreteDate':'20260113','sourceSequence':1 if tied else row}
            records.append(SourceRecord(data,SourceLocation('controlled_rule6_fixture.json',row,'json',Stage.FINAL_ACTION,FileRole.SOURCE),f'case-{number}-qc{qc}'))
        result=FinalActionProcessor(resolver).validate(records)
        rule=next((check for check in result.rule_results if check.rule_id=='FA-RULE-06'),None)
        decisions={decision.record_id.split('-')[-1]:decision.decision.value for decision in result.decisions}
        actual='BLOCKED' if rule and rule.status.value=='BLOCKED' else 'DROP_BOTH' if len(decisions)==2 and set(decisions.values())=={'DROP'} else 'KEEP_QC5' if decisions.get('qc5')=='KEEP' and decisions.get('qc0')=='DROP' else 'UNEXPECTED'
        results.append(dict(case=number,same_icn=same_icn,qc0_newer=qc0_newer,qc0_action=action,invalid_transaction_pair=invalid_tc,expected=expected,observed=actual,rule=rule.rule_id if rule else None,passed=actual==expected and rule is not None,decisions=decisions,explanation=rule.message if rule else 'Rule 6 was not reached'))
    return {'scope':'Controlled fixtures; actual default FinalActionProcessor. Case 6 preserves the current missing-action BLOCKED policy pending PO confirmation. This is software verification, not production acceptance.','passed':all(item['passed'] for item in results),'scenarios':results}


if __name__ == '__main__':
    payload=verify()
    output=PROJECT_ROOT/'reviews/rule6_verification_current.json'
    output.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(f'Rule 6: {sum(item["passed"] for item in payload["scenarios"])}/11 scenarios passed. Evidence: {output.relative_to(PROJECT_ROOT)}')
    raise SystemExit(0 if payload['passed'] else 1)
