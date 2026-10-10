"""Complete field-register comparisons, independent of calculation coverage."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from medpar_qa.enums import ValidationStatus
from medpar_qa.models import RuleResult
from medpar_qa.stages.comparison import compare_values


@lru_cache(maxsize=1)
def field_contract():
    path=Path(__file__).resolve().parents[3]/"config/v3_field_contract.json"
    return json.loads(path.read_text())["fields"]


def compare_v3_fields(expected,actual,resolver):
    results=[]
    for spec in field_contract():
        for field in spec["fields"]:
            left=resolver.get(expected.data,field)
            right=resolver.get(actual.data,field)
            if spec["deleted"]:
                valid=right is None or (isinstance(right,str) and not right.strip())
                result=RuleResult(stage=actual.source.stage,rule_id="V3-DELETED-FIELD-FILLER",
                    status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
                    message="Deleted field must remain blank/filler",field_name=field,expected="Blank/filler",actual=right)
            elif left is None and right is None:
                result=RuleResult(stage=actual.source.stage,rule_id="V3-FIELD-GOLDEN",
                    status=ValidationStatus.NOT_APPLICABLE,message="Field absent from both golden and actual; coverage not demonstrated",
                    field_name=field,expected=None,actual=None)
            else:
                result=compare_values(stage=actual.source.stage,rule_id="V3-FIELD-GOLDEN",field_name=field,
                    expected=left,actual=right,record_ids=[expected.record_id,actual.record_id],
                    source_files=[expected.source.file_path,actual.source.file_path])
            result.evidence.update({"register_field_id":spec["id"],"v3_page":spec["page"],"validation_kind":"comparison, not independent calculation"})
            results.append(result)
    return results


def validate_whole_dollar_fields(source,actual,resolver):
    from medpar_qa.normalization.decimal_values import to_decimal
    from medpar_qa.stages.intermediate.business_rules import whole_dollars
    results=[]
    for spec in field_contract():
        is_money = spec["group"] == "float to integer" or any(token in spec["name"] for token in ("AMT","AMOUNT","CHRG","PERDIEM"))
        if not is_money or spec["deleted"]:
            continue
        field=spec["fields"][0]
        observed=resolver.get(actual.data,field)
        raw=resolver.get(source.data,field)
        if observed is None or isinstance(observed,list):
            continue
        try:
            amount=to_decimal(observed)
            expected=whole_dollars(raw) if raw is not None else "Whole-dollar integer; source amount not supplied"
            valid=amount==amount.to_integral_value() and (raw is None or amount==expected)
            status=ValidationStatus.PASS if valid else ValidationStatus.FAIL
            message="Whole-dollar storage matches" if valid else "Whole-dollar rounding/storage mismatch"
        except (ValueError,TypeError,ArithmeticError) as exc:
            expected,status,message="Finite integer amount",ValidationStatus.FAIL,str(exc)
        results.append(RuleResult(stage=actual.source.stage,rule_id="V3-WHOLE-DOLLAR",status=status,message=message,
            field_name=field,expected=str(expected),actual=observed,record_ids=[source.record_id,actual.record_id],
            evidence={"register_field_id":spec["id"],"recalculated_from_source":raw is not None}))
    return results
