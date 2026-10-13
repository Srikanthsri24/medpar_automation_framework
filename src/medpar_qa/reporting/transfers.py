"""Stage handoff navigation; never infer execution from a passing validation."""
import hashlib
from .status_navigation import e, page, number_file_tables
from .stage_volume import summarize_stage_volume

STAGES = ('final_action', 'split', 'stay', 'intermediate', 'final_medpar')


def independent_transfers(master, by_stage):
    """Verify saved-run boundary files and reuse explicit record-lineage audit proof."""
    import json
    import os
    from pathlib import Path
    from datetime import datetime
    project = next((p for p in master.resolve().parents if (p / 'run_commands.py').exists()), master.resolve().parent)
    def local(path):
        p = Path(path)
        return p if p.is_absolute() else project / p
    def paths(stage, role):
        return sorted({str(path) for item in by_stage.get(stage, []) for path in item['entry']['payload'].get('context', {}).get(role, [])})
    def link(path):
        return os.path.relpath(local(path), master.resolve()).replace(os.sep, '/')
    rows, verification = [], []
    for number, stage in enumerate(STAGES):
        next_stage = STAGES[number + 1] if number + 1 < len(STAGES) else None
        title = stage.replace('_', ' ').title()
        detail_rows, proofs = [], []
        outputs = paths(stage, 'actual_paths')
        next_inputs = paths(next_stage, 'source_paths') if next_stage else []
        destination = {local(path).resolve(): path for path in next_inputs}
        verified = 0
        for path in outputs:
            file = local(path)
            target = destination.get(file.resolve())
            digest = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
            # Successful reader checks demonstrate that the configured input actually ran.
            read_checks = [c for item in by_stage.get(next_stage, []) for c in item['stage'].get('rule_results', []) if c.get('rule_id') == 'INGEST-READ-FILE' and c.get('status') == 'PASS' and isinstance(c.get('actual'), dict) and c['actual'].get('role') == 'source' and target in c.get('source_files', [])] if target else []
            ok = bool(digest and read_checks)
            verified += ok
            status = 'PASS — output used as next-stage input' if ok else 'FAIL — next-stage input read not established'
            proofs.append(dict(output_file=path, next_input=target, sha256=digest, status='PASS' if ok else 'FAIL', next_stage_read_checks=len(read_checks)))
            detail_rows.append(f'<tr data-file="{e(path)}"><td><a href="{e(link(path))}">{e(path)}</a></td><td>{e(target or "No matching next-stage input")}</td><td>{e(status)}</td><td><code>{e(digest or "File unavailable")}</code></td></tr>')
        # Intermediate transforms into Final; exact field-preservation audit is the proof,
        # rather than assuming that their differently shaped files have the same bytes.
        lineage = [c for item in by_stage.get('final_medpar', []) for c in item['stage'].get('rule_results', []) if c.get('rule_id') == 'FM-ARCHIVE-EXACT-LINEAGE'] if stage == 'intermediate' else []
        if lineage:
            detail_rows = []
            for c in lineage:
                evidence_path = next((str(p) for p in c.get('source_files', []) if str(p) in paths('final_medpar', 'source_paths')), str(c.get('source_files', [''])[0]))
                proof_link = 'final_medpar_file_' + hashlib.sha256(evidence_path.encode()).hexdigest()[:20] + '.html'
                detail_rows.append(f'<tr data-file="{e(evidence_path)}"><td><a href="{proof_link}">{e(evidence_path)}</a></td><td>{e(json.dumps(c.get("actual"), ensure_ascii=False))}</td><td>{e(c["status"])}</td><td>{e(c["message"])}</td></tr>')
            verified = sum(c['status'] == 'PASS' for c in lineage)
            summary = f'{verified:,} / {len(lineage):,} Final files — exact Intermediate lineage verified' if verified == len(lineage) else f'{verified:,} / {len(lineage):,} Final files — lineage discrepancies found'
            headings = '<th>Final file — full proof</th><th>Matching source and fingerprint</th><th>Result</th><th>Verification</th>'
            proofs = lineage
        else:
            summary = f'{verified:,} / {len(outputs):,} output files — next-stage input verified' if outputs and verified == len(outputs) else f'{verified:,} / {len(outputs):,} output files — transfer discrepancies found' if outputs else 'No retained-output handoff recorded'
            headings = '<th>Output file</th><th>Next-stage input</th><th>Verification result</th><th>SHA-256 fingerprint</th>'
        if next_stage is None:
            summary = 'Final stage — workflow ends here'
        checks = [c for item in by_stage.get(stage, []) for c in item['stage'].get('rule_results', [])]
        volume = summarize_stage_volume(checks)
        input_rows = []
        for path in sorted(volume['file_sets']['in']):
            selected = [c for c in checks if path in c.get('source_files', [])]
            counts = {status: sum(c.get('status') == status for c in selected) for status in ('PASS', 'FAIL', 'BLOCKED')}
            proof = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
            result = 'FAIL / BLOCKED' if path in volume['file_sets']['stopped'] else 'File checks passed'
            input_rows.append(f'<tr data-file="{e(path)}"><td><a href="{proof}">{e(path)}</a></td><td>{result}</td><td>{len(selected)}</td><td>{counts["PASS"]}</td><td>{counts["FAIL"]}</td><td>{counts["BLOCKED"]}</td></tr>')
        input_summary = f'{volume["files_in"]:,} input files · {volume["files_passed"]:,} passed · {volume["files_failed"]:,} failed · {volume["files_blocked"]:,} blocked'
        filename = f'{stage}_transfers.html'
        body = f'<p><strong>Input-file results: {e(input_summary)}</strong></p><details><summary>Output-to-input verification — {e(summary)}</summary><p><strong>Conclusion: {e(summary)}</strong></p><p>Verification uses the saved run configuration, successful next-stage file-read checks and current local file fingerprints. Exact lineage checks verify transformed Final records against Intermediate. Boundary verification establishes which supplied outputs were used in the next stage. Open the stage reports for business-rule results and acceptance conclusions.</p>'
        body += f'<p><a href="index.html#stage-{stage}">Source-stage validation and original input-file evidence</a>' + (f' · <a href="index.html#stage-{next_stage}">Next-stage validation evidence</a>' if next_stage else '') + ' · <a href="transfer_verification.json">Download verification evidence</a></p>'
        body += '</details><label>Search input filename <input type="search" placeholder="Filename or path…"></label><details><summary>Input files — open a filename for its complete validation report</summary><table><tr><th>Input file</th><th>Result</th><th>Validations</th><th>Pass</th><th>Fail</th><th>Blocked</th></tr>' + ''.join(input_rows) + '</table></details><details><summary>Boundary file matches and fingerprints</summary><label>Search filename <input type="search" placeholder="Filename or path…"></label><table><tr>' + headings + '</tr>' + ''.join(detail_rows) + '</table></details>'
        (master / filename).write_text(page(title + ' — Stage boundary verification', body), encoding='utf-8')
        next_received = summarize_stage_volume([c for item in by_stage.get(next_stage, []) for c in item['stage'].get('rule_results', [])])['files_in'] if next_stage else None
        forwarded_sources = {path for c in lineage if c['status'] == 'PASS' for path in c.get('source_files', []) if path in outputs} if lineage else set()
        movement = f'{len(forwarded_sources) if lineage else verified:,} / {len(outputs):,}' if next_stage and outputs else '—'
        verification.append(dict(stage=stage, next_stage=next_stage, input_files=volume['files_in'], output_files=len(outputs), output_files_forwarded=len(forwarded_sources) if lineage else verified, next_stage_input_files=next_received, conclusion=summary, evidence=proofs))
        rows.append(f'<tr><td>{e(title)}</td><td>{e(next_stage.replace("_", " ").title()) if next_stage else "End of workflow"}</td><td>{volume["files_in"]:,}</td><td>{movement}</td><td>{next_received if next_received is not None else "End"}</td><td><a href="{filename}">{e(input_summary)}</a><details><summary>Transfer verification</summary>{e(summary)}</details></td></tr>')
    (master / 'transfer_verification.json').write_text(json.dumps(dict(verified_at=datetime.now().astimezone().isoformat(), boundaries=verification), indent=2), encoding='utf-8')
    return '<details id="stage-transfers"><summary>Stage transfer verification — input-file results</summary><p>Click a result for output-to-input file matches, fingerprints and validation evidence. Input counts are unique source files read in each stage. Movement counts are verified output files read by the next stage; merges and splits can change the file count. Original input files and transformed output files are counted separately.</p><table><tr><th>From stage</th><th>To stage</th><th>Input files received</th><th>Output files verified in next stage</th><th>Next-stage input files received</th><th>Result — open proof</th></tr>' + ''.join(rows) + '</table></details>'


def connected_transfers(journeys, index):
    rows = []
    for journey, directory in journeys:
        steps = journey['steps']
        relative = directory.relative_to(index.parent).as_posix()
        for number, step in enumerate(steps):
            following = steps[number + 1] if number + 1 < len(steps) else None
            moved = bool(following and step.get('output') and following['status'] != 'NOT_REACHED' and following.get('input') == step['output'])
            status = 'Moved to next stage' if moved else 'Completed final stage' if not following and step['status'] == 'KEEP' else 'Not reached' if step['status'] == 'NOT_REACHED' else 'Dropped — no retained records' if step['status'] == 'DROP' else 'Stopped — not moved'
            links = '' if step['status'] == 'NOT_REACHED' else f'<a href="{relative}/{step["stage"]}/report.html">Source stage proof</a>'
            if moved:
                links += f' · <a href="{relative}/{following["stage"]}/report.html">Next stage proof</a> · <a href="{relative}/{step["stage"]}/retained.json">Transferred records</a>'
            reason = f'{step.get("retained", 0)} retained record(s) supplied as the next stage input.' if moved else step['reason']
            proof = f'<details><summary>{e(status)}</summary><p>{e(reason)}</p><p>Output: {e(step.get("output") or "No retained output")}</p>' + (f'<p>Next input: {e(following.get("input"))}</p>' if moved else '') + f'<p>{links}</p></details>'
            rows.append(f'<tr data-file="{e(journey["source_file"])}"><td>{e(journey["source_file"])}</td><td>{e(step["stage"].replace("_", " ").title())}</td><td>{e(following["stage"].replace("_", " ").title()) if following else "End of workflow"}</td><td>{proof}</td></tr>')
    return number_file_tables('<details id="stage-transfers"><summary>Moved to next stage — file status</summary><p>Expand a movement status to open both stage reports and the transferred records. Movement is verified from the recorded retained output and the next executed stage’s input. A later-stage failure does not undo an earlier transfer.</p><label>Search transfer filename <input id="transfer-search" type="search" placeholder="Filename or path…"></label><div class="scroll"><table id="transfer-table"><tr><th>Original input file</th><th>From stage</th><th>To stage</th><th>Movement status — click for evidence</th></tr>' + ''.join(rows) + '</table></div></details><script>document.getElementById("transfer-search").addEventListener("input",function(){document.querySelectorAll("#transfer-table tr[data-file]").forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(this.value.toLowerCase()));});</script>')
