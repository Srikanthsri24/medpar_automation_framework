"""V3 p15/p20: independently inspectable Final Action exception outputs."""
from __future__ import annotations
import json
from pathlib import Path
from medpar_qa.enums import ValidationStatus
from medpar_qa.models import StageResult


def write_final_action_audit(result: StageResult, directory: str | Path) -> dict[str, Path]:
    """Export retained/dropped Final Action decisions and failed/blocked record evidence."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    errors = [r.to_dict() for r in result.rule_results
              if r.status in {ValidationStatus.FAIL, ValidationStatus.BLOCKED}]
    bypass = [r for r in errors if r["rule_id"].startswith("FA-BYPASS")]
    questionable = [r for r in errors if r not in bypass]
    statistics = [r.to_dict() for r in result.rule_results if r.rule_id == "FA-NETTING-STATISTICS"]
    files = {"errors": directory / "final_action_error_file.json",
             "bypass": directory / "final_action_bypass_file.json",
             "statistics": directory / "final_action_statistics.json"}
    for name, rows in (("errors", questionable), ("bypass", bypass), ("statistics", statistics)):
        files[name].write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    return files
