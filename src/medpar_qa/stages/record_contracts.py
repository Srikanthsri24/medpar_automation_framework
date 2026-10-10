"""V3 physical lengths. Field offsets still require approved copybooks."""
from medpar_qa.enums import Stage, FileRole, ValidationStatus
from medpar_qa.models import RuleResult

LENGTHS={Stage.FINAL_ACTION:(32004,32007),Stage.SPLIT:(32007,32007),
         Stage.STAY:(32007,32010),Stage.INTERMEDIATE:(32010,3050),Stage.FINAL_MEDPAR:(3050,3000)}


def validate_record_contracts(records,resolver,encoding="ascii"):
    results=[]
    for record in records:
        raw=resolver.get(record.data,"fixed_width_record")
        if raw is None:
            continue
        expected=LENGTHS[record.source.stage][0 if record.source.role==FileRole.SOURCE else 1]
        try:
            observed=len(raw if isinstance(raw,bytes) else raw.encode(encoding))
            status=ValidationStatus.PASS if observed==expected else ValidationStatus.FAIL
        except (UnicodeError,AttributeError) as exc:
            observed=type(exc).__name__
            status=ValidationStatus.FAIL
        results.append(RuleResult(stage=record.source.stage,rule_id="STAGE-PHYSICAL-RECORD-LENGTH",status=status,
            message="Physical record length matches stage contract" if status==ValidationStatus.PASS else "Physical record length mismatch",
            expected=expected,actual=observed,record_ids=[record.record_id],source_files=[record.source.file_path],
            evidence={"role":record.source.role.value,"encoding":encoding,"specification":"V3 processing flow, pp5–11"}))
    return results
