"""Concise connected journey review with expandable, unchanged validation evidence."""
import html
import json
from datetime import datetime
from pathlib import Path


def _esc(value):
    return html.escape(str(value))


def _value(value):
    return 'Not supplied' if value is None else json.dumps(value, ensure_ascii=False, default=str)


def write_connected_review(journeys, index, *, synthetic=False):
    """Separate stage outcomes, executed checks and unassessed coverage without masking errors."""
    sections = []
    totals = {key: 0 for key in ('PASS', 'FAIL', 'BLOCKED', 'NOT_APPLICABLE', 'KNOWN_DIFFERENCE')}
    for journey, directory in journeys:
        stages = []
        for step in journey['steps']:
            name = step['stage'].replace('_', ' ').title()
            relative = Path(directory).relative_to(index.parent).as_posix()
            report_link = f'{relative}/{step["stage"]}/report.html'
            output_link = f'{relative}/{step["stage"]}/retained.json'
            if step['status'] == 'NOT_REACHED':
                stages.append(f'<section><h3>{_esc(name)} — Not run</h3><p>{_esc(step["reason"])}</p>'
                              '<p>No checks were executed in this stage. This is a consequence of the earlier stop, not another independent defect.</p></section>')
                continue
            report = json.loads((directory / step['stage'] / 'report.json').read_text())
            checks = report['stages'][0]['rule_results']
            counts = {key: sum(check['status'] == key for check in checks) for key in totals}
            for key in totals:
                totals[key] += counts[key]
            rows, unassessed = [], []
            for check in checks:
                evidence = {'source_files': check.get('source_files'), 'record_ids': check.get('record_ids'),
                            'evidence': check.get('evidence')}
                proof = '<details><summary>Source proof</summary><pre>' + _esc(json.dumps(evidence, indent=2, default=str)) + '</pre></details>'
                row = '<tr>' + ''.join(f'<td>{_esc(value)}</td>' for value in
                    (check['rule_id'], check.get('field_name') or 'Stage check', check['status'],
                     _value(check.get('expected')), _value(check.get('actual')), check['message'])) + f'<td>{proof}</td></tr>'
                (unassessed if check['status'] == 'NOT_APPLICABLE' else rows).append(row)
            headings = '<tr><th>Rule</th><th>Field</th><th>Result</th><th>Expected</th><th>Observed</th><th>Explanation</th><th>Evidence</th></tr>'
            table = lambda items: '<div class="scroll"><table>' + headings + ''.join(items) + '</table></div>'
            stages.append(f'<section><h3>{_esc(name)} — {_esc(step["status"])}</h3>'
                f'<p>{step["input_records"]} input record(s) · {step["retained"]} retained · {step["dropped"]} dropped. '
                f'{counts["PASS"]} pass · {counts["FAIL"]} fail · {counts["BLOCKED"]} blocked · {counts["NOT_APPLICABLE"]} not assessed · {counts["KNOWN_DIFFERENCE"]} known differences.</p>'
                f'<p><b>Conclusion:</b> {_esc(step["reason"])}</p>'
                f'<details><summary>Executed checks and proof ({len(rows)})</summary>{table(rows)}</details>'
                f'<details><summary>Not assessed / not applicable ({len(unassessed)}) — reasons</summary>'
                '<p>These are not passes. Read each reason to distinguish an optional absent field from missing reference or golden coverage.</p>' + table(unassessed) + '</details>'
                f'<p><a href="{report_link}">Full rule explanations and evidence</a>'
                + (f' · <a href="{output_link}">Retained output</a>' if step["output"] else "") + '</p></section>')
        sections.append(f'<h2>File: {_esc(journey["source_file"])}</h2>'
                        f'<p><b>File conclusion:</b> {_esc(journey["conclusion"])}</p>' + ''.join(stages))
    completed = sum(journey['completed'] for journey, _ in journeys)
    label = 'Synthetic demonstration' if synthetic else 'Connected validation'
    scope = ('Fictitious inputs; all five real validators run. Final Action and Split calculate retained records. '
             'Stay, Intermediate and Final validate supplied candidate JSON outputs. This is workflow evidence, not production acceptance. '
             'Approved golden outputs, external reference calculations and the complete 3000-byte layout are not certified.' if synthetic else '')
    index.write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MEDPAR evidence report</title><style>body{font:16px system-ui;line-height:1.55;background:#f3f6fa;color:#18324b;margin:0}'
        'header{background:#18324b;color:white;padding:30px}main{max-width:1200px;margin:auto;padding:24px}'
        'section,.summary{background:white;border:1px solid #d9e2eb;border-radius:10px;padding:20px;margin:16px 0}'
        'summary{cursor:pointer;font-weight:600;padding:10px}table{border-collapse:collapse;width:100%;font-size:14px}'
        'td,th{border:1px solid #d9e2eb;padding:10px;text-align:left;vertical-align:top}.scroll{overflow:auto}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto}a{color:#1958a0}</style></head>'
        f'<body><header><h1>MEDPAR — {_esc(label)}</h1><p>Generated {_esc(datetime.now().astimezone().strftime("%d %B %Y, %I:%M:%S %p %Z (%z)"))}</p></header><main>'
        f'<div class="summary"><b>{len(journeys)} starting file(s) · {completed} completed · {len(journeys)-completed} stopped</b>'
        f'<p>{totals["PASS"]} passed checks · {totals["FAIL"]} failed · {totals["BLOCKED"]} blocked · {totals["NOT_APPLICABLE"]} not assessed · {totals["KNOWN_DIFFERENCE"]} known differences.</p>'
        f'<p>{_esc(scope)}</p></div><details><summary>How to read this report</summary>'
        '<p>KEEP: retained records continue. DROP: business rules excluded records. FAIL: observed data differs from the requirement. '
        'BLOCKED: a required input or prerequisite prevents a decision. NOT REACHED: an earlier stage stopped the file, so this stage did not run. '
        'Not assessed / N/A: the individual check was not evaluated; its explanation records why. None of these skipped states is a pass.</p>'
        '<p>Software test reports can contain intentionally invalid examples. Their test outcome tells you whether the framework handled those examples correctly; it is not the business outcome of this demonstration.</p></details>'
        + ''.join(sections) + '</main></body></html>', encoding='utf-8')
