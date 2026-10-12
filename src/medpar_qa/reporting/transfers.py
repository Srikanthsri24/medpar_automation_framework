"""Stage handoff navigation; never infer execution from a passing validation."""
import hashlib
from .status_navigation import e, page
from .stage_volume import summarize_stage_volume

STAGES = ('final_action', 'split', 'stay', 'intermediate', 'final_medpar')


def independent_transfers(master, by_stage):
    rows = []
    for number, stage in enumerate(STAGES):
        items = by_stage.get(stage, [])
        checks = [c for item in items for c in item['stage'].get('rule_results', [])]
        volume = summarize_stage_volume(checks)
        next_stage = STAGES[number + 1] if number + 1 < len(STAGES) else None
        detail_rows = []
        for path in sorted(volume['file_sets']['in']):
            state = 'Validation stopped' if path in volume['file_sets']['stopped'] else 'File checks passed; stage acceptance still required'
            proof = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
            detail_rows.append(f'<tr data-file="{e(path)}"><td><a href="{proof}">{e(path)}</a></td><td>{e(state)}</td><td>Not executed as a connected handoff</td></tr>')
        filename = f'{stage}_transfers.html'
        next_link = f'<p><a href="index.html#stage-{next_stage}">Open {e(next_stage.replace("_", " ").title())} supplied-input evidence</a></p>' if next_stage else ''
        body = '<p>These stages were reviewed independently. Passing file checks does not prove that retained records were sent to the next stage. Supplied later-stage files are reviewed separately; no connected transfer is recorded in this session.</p>' + next_link
        body += '<label>Search filename <input type="search" placeholder="Filename or path…"></label><table><tr><th>Input file — full evidence</th><th>Validation status</th><th>Movement status</th></tr>' + ''.join(detail_rows) + '</table>'
        (master / filename).write_text(page(stage.replace('_', ' ').title() + ' — Stage transfer evidence', body), encoding='utf-8')
        status = 'Reviewed independently — transfer not verified' if items else 'Not run'
        if next_stage is None and items:
            status = 'Final stage reviewed independently'
        rows.append(f'<tr><td>{e(stage.replace("_", " ").title())}</td><td>{e(next_stage.replace("_", " ").title()) if next_stage else "End of workflow"}</td><td><a href="{filename}">{volume["files_in"]:,} files — {e(status)}</a></td></tr>')
    return '<section id="stage-transfers"><h2>Moved to next stage — file status</h2><p>Click a status to see the files, their validation evidence and the next stage’s supplied-input reports.</p><table><tr><th>From stage</th><th>To stage</th><th>Movement status and file evidence</th></tr>' + ''.join(rows) + '</table></section>'


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
    return '<section id="stage-transfers"><h2>Moved to next stage — file status</h2><p>Expand a movement status to open both stage reports and the transferred records. Movement is verified from the recorded retained output and the next executed stage’s input. A later-stage failure does not undo an earlier transfer.</p><label>Search transfer filename <input id="transfer-search" type="search" placeholder="Filename or path…"></label><div class="scroll"><table id="transfer-table"><tr><th>Original input file</th><th>From stage</th><th>To stage</th><th>Movement status — click for evidence</th></tr>' + ''.join(rows) + '</table></div></section><script>document.getElementById("transfer-search").addEventListener("input",function(){document.querySelectorAll("#transfer-table tr[data-file]").forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(this.value.toLowerCase()));});</script>'
