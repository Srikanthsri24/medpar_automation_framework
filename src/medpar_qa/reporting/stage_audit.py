"""Separate route, exception, and balance evidence for every validated stage."""
import json
from pathlib import Path
from medpar_qa.enums import ValidationStatus


def write_stage_audit(result, directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    rows={
        "errors":[r.to_dict() for r in result.rule_results if r.status in {ValidationStatus.FAIL,ValidationStatus.BLOCKED}],
        "bypass":[r.to_dict() for r in result.rule_results if r.evidence.get("route")=="bypass"],
        "statistics":[r.to_dict() for r in result.rule_results if "BALANCE" in r.rule_id or "STATISTICS" in r.rule_id or "BILL-LIMIT" in r.rule_id],
        "decisions":[{"record_id":d.record_id,"decision":d.decision.value,"rule_id":d.rule_id,"reason":d.reason} for d in result.decisions],
    }
    paths={}
    for name,items in rows.items():
        path=directory/f"{result.stage.value}_{name}.json"
        path.write_text(json.dumps(items,indent=2,default=str)+"\n")
        paths[name]=path
    return paths
