"""Executable V3 document-backed demo pipeline.

This is an integration demo, NOT a replacement for unavailable COBOL field layouts,
3M grouper, SSA eligibility or payment formulae. Unsupported data is never invented.
"""
from __future__ import annotations

import argparse
import json
import html
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from medpar_qa.enums import FileRole, RecordDecision, Stage
from medpar_qa.models import SourceLocation, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.final_action.processor import FinalActionProcessor


def iso(value: Any) -> str:
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError(f"Missing date: {value!r}")
    return parsed.isoformat()


def load_claims(path: Path) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        obj = obj.get("claims")
    if not isinstance(obj, list) or not all(isinstance(x, dict) for x in obj):
        raise ValueError("Expected JSON array or object containing a claims array")
    seen = set()
    for i, record in enumerate(obj):
        for field in ("claim_id", "hicn", "provider_id", "admission_date", "stay_from_date", "stay_thru_date", "transaction_code", "query_code", "icn", "processing_date"):
            if field not in record or record[field] is None:
                raise ValueError(f"Claim {i+1}: missing {field}")
        if record["claim_id"] in seen:
            raise ValueError(f"Duplicate claim_id: {record['claim_id']}")
        seen.add(record["claim_id"])
        if str(record["transaction_code"]) not in {"0", "1", "2", "3", "4"}:
            raise ValueError(f"Claim {record['claim_id']}: invalid transaction code")
        if str(record["query_code"]) not in {"0", "1", "3", "5"}:
            raise ValueError(f"Claim {record['claim_id']}: invalid query code")
        if iso(record["stay_from_date"]) > iso(record["stay_thru_date"]):
            raise ValueError(f"Claim {record['claim_id']}: inverted stay dates")
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")


def final_action(claims: list[dict[str, Any]], resolver: FieldResolver) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    processor = FinalActionProcessor(resolver)
    records = [SourceRecord(data=claim, record_id=str(claim["claim_id"]), source=SourceLocation(
        file_path="demo_claims.json", row_number=i+1, file_format="json", stage=Stage.FINAL_ACTION, role=FileRole.SOURCE
    )) for i, claim in enumerate(claims)]
    from medpar_qa.stages.final_action.grouping import group_records
    kept, dropped, exceptions, decisions = [], [], [], []
    for _, group in group_records(records, resolver).items():
        result = processor.validate_group(group)
        if not result.passed:
            exceptions.extend({"claim_id": r.record_id, "reason": [x.message for x in result.rule_results if x.status.value in {"FAIL", "BLOCKED"}]} for r in group)
            continue
        mapped = {x.record_id: x for x in group}
        for decision in result.decisions:
            decisions.append({"claim_id": decision.record_id, "decision": decision.decision.value, "rule_id": decision.rule_id, "reason": decision.reason})
            if decision.decision == RecordDecision.KEEP:
                kept.append(deepcopy(mapped[decision.record_id].data))
            else:
                dropped.append(decision.record_id)
    if len(kept) + len(dropped) + len(exceptions) != len(claims):
        raise AssertionError("Final Action input/output accounting mismatch")
    return kept, {"input": len(claims), "kept": len(kept), "dropped": len(dropped), "exceptions": len(exceptions), "decisions": decisions, "exception_records": exceptions, "dropped_claim_ids": dropped}


def split_claims(claims: list[dict[str, Any]], run_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        if int(claim["transaction_code"]) in (0, 4):
            key = (str(claim["claim_id"]), "SNF", "")
        else:
            key = (str(claim["hicn"]), str(claim["provider_id"]), iso(claim["admission_date"]))
        groups[key].append(claim)
    output, exclusions, exceptions, over_capacity = [], [], [], []
    exception_bills = 0
    for key, group in groups.items():
        if len(group) > 75:
            over_capacity.append({"stay": key, "bill_count": len(group), "reason": "Audit only: MM removes the legacy 75-bill cap"})
        ordered = sorted(group, key=lambda r: (iso(r["processing_date"]), iso(r.get("accrete_date") or r["processing_date"]), str(r["claim_id"])))
        is_snf = int(ordered[0]["transaction_code"]) in (0, 4)
        routing_date = iso(ordered[0]["admission_date"]) if is_snf else iso(ordered[-1]["stay_thru_date"])
        d = date.fromisoformat(routing_date)
        if not (run_year - 3 <= d.year <= run_year):
            exclusions.extend(str(x["claim_id"]) for x in group)
            continue
        bucket = f"Y{run_year-d.year}{'0109' if d.month <= 9 else '1012'}"
        for claim in ordered:
            item = deepcopy(claim)
            item["split_bucket"] = bucket
            item["split_type"] = "SNF" if is_snf else "INP"
            item["split_routing_date"] = routing_date
            item["sample_0_1pct"] = str(item.get("claim_can", "")).endswith("595")
            output.append(item)
    if len(output) + len(exclusions) + exception_bills != len(claims):
        raise AssertionError("Split count balancing mismatch")
    return output, {"input": len(claims), "output": len(output), "outside_window": exclusions, "exception_bills": exception_bills, "exceptions": exceptions, "over_75_bill_audit": over_capacity, "buckets": dict(Counter(x["split_bucket"] for x in output))}


def _unique_items(groups: list[dict[str, Any]], name: str) -> list[Any]:
    result = []
    for claim in groups:
        for value in claim.get(name, []):
            if value not in result:
                result.append(deepcopy(value))
    return result


def stay_claims(claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups = defaultdict(list)
    for c in claims:
        key = (str(c["hicn"]), str(c["provider_id"]), iso(c["admission_date"])) if c["split_type"] == "INP" else (str(c["claim_id"]), "SNF", "")
        groups[key].append(c)
    output = []
    for group in groups.values():
        ordered = sorted(group, key=lambda r: (iso(r["processing_date"]), iso(r.get("accrete_date") or r["processing_date"]), str(r["claim_id"])))
        last = ordered[-1]
        combined = deepcopy(last)
        combined["source_claim_ids"] = [str(r["claim_id"]) for r in ordered]
        combined["bill_count"] = len(ordered)
        combined["stay_from_date"] = min(iso(r["stay_from_date"]) for r in ordered)
        combined["stay_thru_date"] = max(iso(r["stay_thru_date"]) for r in ordered)
        # V3 p23: diagnosis and procedure codes come from LAST bill, not union.
        for name in ("diagnosis_codes", "procedure_codes"):
            if name in last:
                combined[name] = deepcopy(last[name])
        # V3 p11: first-to-last unique entries in code trailers.
        for name in ("condition_codes", "occurrence_codes", "span_codes", "value_codes"):
            if any(name in r for r in ordered):
                combined[name] = _unique_items(ordered, name)
        # Numeric totals are limited to explicitly declared demonstration fields;
        # no undisclosed COBOL 54-field mapping is guessed.
        for name in ("covered_days", "total_charges"):
            if all(name in r and r[name] is not None for r in ordered):
                from decimal import Decimal
                combined[name] = str(sum((Decimal(str(r[name])) for r in ordered), Decimal("0")))
        output.append(combined)
    return output, {"input_bills": len(claims), "output_stays": len(output), "bills_in_stays": sum(r["bill_count"] for r in output)}


def intermediate_claims(claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from medpar_qa.stages.intermediate.business_rules import length_of_stay, validate_business_rules
    resolver = FieldResolver.from_yaml(Path(__file__).resolve().parents[2]/"config/field_aliases.yaml")
    result = []
    for c in claims:
        row = deepcopy(c)
        start = date.fromisoformat(iso(c["admission_date"]))
        thru = date.fromisoformat(iso(c["stay_thru_date"]))
        if thru < start:
            raise ValueError(f"Claim {c['claim_id']}: thru before admission")
        row["medpar_lgth_stay_0260"] = length_of_stay(start,thru,c.get("discharge_status",1))
        row["medpar_adm_date_0200_julian"] = start.strftime("%Y%j")
        row["medpar_dischg_date_0210_julian"] = thru.strftime("%Y%j")
        source=SourceRecord(data=c,record_id=str(c["claim_id"]),source=SourceLocation(file_path="demo_stay",row_number=1,file_format="json",stage=Stage.INTERMEDIATE,role=FileRole.SOURCE))
        rules=validate_business_rules(source,source,resolver)
        for rule in rules:
            if rule.evidence.get("calculation_completed") and rule.expected is not None:
                row[rule.field_name]=rule.expected
        # Do not invent SSA/3M/DRG, payment and revenue derivations.
        row["external_calculation_status"] = "NOT_COMPUTED_WITHOUT_REFERENCE_INPUTS"
        result.append(row)
    return result, {"input": len(claims), "output": len(result), "external_calculations": "not computed (reference data unavailable)"}


def final_medpar(claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output, excluded, bypass = [], [], []
    for c in claims:
        is_snf = c["split_type"] == "SNF"
        if c.get("covered_days") is not None and c.get("medpar_lgth_stay_0260") is not None and int(c["covered_days"])>int(c["medpar_lgth_stay_0260"]):
            bypass.append(str(c["claim_id"]))
            continue
        if not is_snf and not c.get("discharge_date"):
            excluded.append(str(c["claim_id"]))
            continue
        output.append(deepcopy(c))
    return output, {"input": len(claims), "output": len(output), "excluded_undischarged_inpatient": excluded, "bypass_covered_days_gt_los":bypass, "fixed_width_3000_bytes": "not emitted: approved copybook offsets unavailable"}


def run_pipeline(source: Path, destination: Path, run_year: int, aliases: Path) -> dict[str, Any]:
    if not (1997 <= run_year <= 2100):
        raise ValueError("run_year must be 1997–2100")
    destination.mkdir(parents=True, exist_ok=True)
    resolver = FieldResolver.from_yaml(aliases)
    claims = load_claims(source)
    stages = (
        ("final_action", lambda x: final_action(x, resolver)),
        ("split", lambda x: split_claims(x, run_year)),
        ("stay", stay_claims),
        ("intermediate", intermediate_claims),
        ("final_medpar", final_medpar),
    )
    audit = {"run_year": run_year, "input_file": str(source), "stages": {}, "scope": "document-backed integration demo; not certified legacy COBOL equivalence"}
    for name, fn in stages:
        claims, stage_audit = fn(claims)
        write_json(destination / name / "output.json", claims)
        write_json(destination / name / "audit.json", stage_audit)
        audit["stages"][name] = stage_audit
    write_json(destination / "audit_summary.json", audit)
    rows = []
    for name, info in audit["stages"].items():
        in_count = info.get("input", info.get("input_bills", "–"))
        out_count = info.get("output", info.get("kept", info.get("output_stays", "–")))
        rows.append(f"<tr><td>{html.escape(name.replace('_', ' ').title())}</td><td>{in_count}</td><td>{out_count}</td><td><a href='{name}/output.json'>Output</a> · <a href='{name}/audit.json'>Audit</a></td></tr>")
    page = """<!doctype html><html lang='en'><meta charset='utf-8'><title>MEDPAR V3 Demonstration</title>
    <style>body{font:16px system-ui,Arial;background:#f3f6fa;color:#15253a;max-width:1050px;margin:45px auto;padding:0 20px}
    section{background:white;padding:26px;border-radius:14px;box-shadow:0 2px 12px #17263c12;margin:20px 0}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px;border-bottom:1px solid #e4e9f1}
    th{background:#eaf0f7}a{color:#145cba}h1{font-size:32px}.warn{border-left:5px solid #b47c23;background:#fff9ec;padding:14px}</style>
    <h1>MEDPAR V3 — Five-stage Integration Demonstration</h1><section><h2>Actual chained execution</h2>
    <p>Final Action → Split → Stay → Intermediate → Final MEDPAR</p>
    <table><thead><tr><th>Stage</th><th>Input</th><th>Output</th><th>Evidence</th></tr></thead><tbody>__ROWS__</tbody></table></section>
    <section><h2>Evidence and limitations</h2><p>Every stage's input is the previous stage's generated in-memory output; its output is also saved to JSON.</p>
    <p class='warn'><strong>Not a production compliance certificate.</strong> Exact COBOL copybook byte layouts, DRG/SSI external feed calculations, and undocumented monetary mappings are not simulated or asserted as complete. See audit JSON.</p>
    <p><a href='audit_summary.json'>Full machine-readable audit</a></p></section></html>"""
    (destination / "index.html").write_text(page.replace("__ROWS__", "".join(rows)), encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="MEDPAR V3 document-backed five-stage demo")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--aliases", type=Path, default=Path("config/field_aliases.yaml"))
    args = parser.parse_args()
    audit = run_pipeline(args.input, args.output, args.year, args.aliases)
    print(json.dumps({"output": str(args.output), "stage_counts": {k: {n: v for n, v in a.items() if n in {"input", "output", "kept", "dropped", "exceptions", "input_bills", "output_stays"}} for k, a in audit["stages"].items()}}, indent=2))


if __name__ == "__main__":
    main()
