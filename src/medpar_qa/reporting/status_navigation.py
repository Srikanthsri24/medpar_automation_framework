"""Small file navigation pages with the existing full validation-card format."""
import hashlib
import html
from collections import defaultdict


def e(value):
    return html.escape(str(value), quote=True)


def page(title, body):
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>body{{font:16px/1.5 system-ui;background:#f4f6f9;color:#172033;margin:24px}}main{{max-width:1400px;margin:auto}}article,section,details{{background:white;padding:16px;border:1px solid #d0d5dd;border-radius:8px;margin:12px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border:1px solid #d0d5dd;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;overflow:auto}}input{{padding:10px;width:min(90%,600px)}}a{{color:#1864ab}}[hidden]{{display:none!important}}summary{{cursor:pointer}}.three,.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}}.badge,.field{{display:inline-block;padding:4px 8px;border-radius:20px;font-weight:700}}.pass{{background:#d3f9d8}}.fail{{background:#ffe3e3}}.blocked{{background:#fff3bf}}</style></head><body><main><a href="index.html#stage-results">← Master report</a><h1>{e(title)}</h1>{body}</main><script>const field=document.querySelector('input');if(field)field.addEventListener('input',()=>{{document.querySelectorAll('tr[data-file]').forEach(row=>row.hidden=!row.dataset.file.toLowerCase().includes(field.value.toLowerCase()));}});</script></body></html>'''


def write_status_navigation(master, stage, checks, render):
    """Count checks once and provide full-file conclusions separately from status links."""
    files = defaultdict(list)
    for index, check in enumerate(checks, 1):
        for path in set(check.get('source_files', [])):
            files[str(path)].append((index, check))
    links = {}
    written_shared = set()
    for path, items in files.items():
        filename = stage + '_file_' + hashlib.sha256(path.encode()).hexdigest()[:20] + '.html'
        links[path] = filename
        states = {check['status'] for _, check in items}
        conclusion = 'FAIL' if 'FAIL' in states else 'BLOCKED' if 'BLOCKED' in states else 'REVIEW DIFFERENCES' if 'KNOWN_DIFFERENCE' in states else 'Recorded applicable checks pass' if 'PASS' in states else 'Not assessed'
        cards = []
        for index, check in items:
            if len(check.get('source_files', [])) > 30:
                shared = f'{stage}_shared_{index}.html'
                if shared not in written_shared:
                    written_shared.add(shared)
                    (master / shared).write_text(page('Shared rule evidence', render(check, stage, index, stage+'-selected')), encoding='utf-8')
                cards.append(f'<section><b>{e(check["status"])} · {e(check["rule_id"])}</b><p>{e(check.get("message", ""))}</p><a href="{shared}">Full shared-check proof</a></section>')
            else:
                cards.append(render(check, stage, index, stage+'-selected'))
        body = f'<p>{e(path)}</p><p><strong>File conclusion: {conclusion}</strong> — based on all checks linked to this file, including failed and blocked checks. Stage-wide findings still affect acceptance; this is not physical-byte certification.</p>' + ''.join(cards)
        (master / filename).write_text(page(stage.replace('_', ' ').title()+' — File evidence', body), encoding='utf-8')
    for status in ('PASS', 'FAIL', 'BLOCKED'):
        matching = [check for check in checks if check['status'] == status]
        rows = []
        for path, items in sorted(files.items()):
            selected = [c for _, c in items if c['status'] == status]
            if not selected:
                continue
            examples = list(dict.fromkeys(c.get('message', '') for c in selected))[:3]
            rows.append(f'<tr data-file="{e(path)}"><td><a href="{links[path]}">{e(path)}</a></td><td>{len(selected)}</td><td>{e("; ".join(examples))}</td></tr>')
        global_checks = [c for c in matching if not c.get('source_files')]
        body = f'<p>{len(matching):,} matching checks · {len(rows):,} linked evidence files. A file can contain both passed and failed checks. Click its filename for the complete file conclusion and full proof. Counts are validation events, not exclusive file outcomes.</p><label>Search filename <input type="search" placeholder="Filename or path…"></label><table><tr><th>File — open full report</th><th>Matching checks</th><th>Explanation</th></tr>' + ''.join(rows) + '</table>'
        body += '<h2>Stage-wide checks without file attribution</h2>' + ''.join(render(c, stage, n, stage+'-global') for n,c in enumerate(global_checks,1))
        (master / f'{stage}_{status.lower()}_files.html').write_text(page(stage.replace('_',' ').title()+' — '+status+' file evidence', body),encoding='utf-8')
