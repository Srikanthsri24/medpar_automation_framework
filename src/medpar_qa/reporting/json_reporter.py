"""Persist structured StageResult evidence as JSON for tooling and the master report."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from medpar_qa.models import StageResult


def write_json_report(
    run_id: str,
    results: Iterable[StageResult],
    output_directory: str | Path,
    *,
    run_date: date | str | None = None,
    filename: str = "report.json",
    context: dict[str, Any] | None = None,
) -> Path:
    """Serialize run results and metadata as machine-readable JSON."""
    stage_results = list(results)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / filename
    counts: Counter[str] = Counter(
        item.status.value
        for stage_result in stage_results
        for item in stage_result.rule_results
    )
    payload = {
        "run_id": run_id,
        "run_date": str(run_date) if run_date is not None else None,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": all(result.passed for result in stage_results),
        "context": context or {},
        "summary": {
            "stage_count": len(stage_results),
            "validation_count": sum(counts.values()),
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "blocked": counts["BLOCKED"],
            "not_applicable": counts["NOT_APPLICABLE"],
            "record_decisions": sum(len(item.decisions) for item in stage_results),
        },
        "stages": [result.to_dict() for result in stage_results],
    }
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return output
