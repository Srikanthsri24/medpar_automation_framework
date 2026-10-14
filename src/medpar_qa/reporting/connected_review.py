"""Concise connected journey review with expandable, unchanged validation evidence."""
import html
import json
from datetime import datetime
from pathlib import Path
from collections import Counter
from .stage_volume import volume_strip
from .transfers import connected_transfers


def _esc(value):
    return html.escape(str(value))


def _value(value):
    return 'Not supplied' if value is None else json.dumps(value, ensure_ascii=False, default=str)


def write_connected_review(journeys, index, *, synthetic=False):
    """Separate stage outcomes, executed checks and unassessed coverage without masking errors."""
    sections = []
    stage_counts = {}
    stage_records = {}
    totals = {key: 0 for key in ('PASS', 'FAIL', 'BLOCKED', 'NOT_APPLICABLE', 'KNOWN_DIFFERENCE')}
    for journey, directory in journeys:
        stages = []
        for step in journey['steps']:
            name = step['stage'].replace('_', ' ').title()
            stage_counts.setdefault(name, Counter())[step['status']] += len(step.get('input_files',[])) or (0 if step['status']=='BEFORE_START' else 1)
            stage_records.setdefault(name, Counter()).update({key: step.get(key, 0) for key in ('input_records', 'retained', 'dropped')})
            stage_records[name]['stopped'] += step['input_records'] if step['status'] in ('FAIL','BLOCKED') else 0
            relative = Path(directory).relative_to(index.parent).as_posix()
            report_link = f'{relative}/{step["stage"]}/report.html'
            output_link = f'{relative}/{step["stage"]}/retained.json'
            if step['status'] in ('NOT_REACHED','BEFORE_START'):
                stages.append(f'<section><h3>{_esc(name)} — Not run</h3><p>{_esc(step["reason"])}</p>'
                              '<p>No checks were executed. The stage is before the selected start, or an earlier stage stopped the journey.</p></section>')
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
        routes = _esc(json.dumps({step['stage'].replace('_', ' ').title(): step['status'] for step in journey['steps']}))
        volumes = _esc(json.dumps({step["stage"].replace("_", " ").title(): {"records_in": step.get("input_records", 0), "kept": step.get("retained", 0), "dropped": step.get("dropped", 0), "records_stopped": max(0, step.get("input_records", 0)-step.get("retained", 0)-step.get("dropped", 0))} for step in journey["steps"]}))
        originals = "<ol>"+"".join("<li>"+_esc(path)+"</li>" for path in journey.get("source_files",[journey["source_file"]]))+"</ol>"
        readiness = journey.get('export_readiness', {})
        readiness_html = ('<details><summary>Final output readiness: '+_esc(readiness.get('status','Not evaluated'))+'</summary><p>'+_esc(readiness.get('acceptance',''))+'</p><ul>'+''.join('<li>'+_esc(item)+'</li>' for item in readiness.get('unresolved_requirements',[]))+'</ul><a href="'+relative+'/export_readiness.json">Readiness evidence</a></details>') if readiness else ''
        search_names = _esc(' '.join(journey.get('source_files',[journey['source_file']])).lower())
        sections.append(f'<details class="file-card" data-filenames="{search_names}" data-routes="{routes}" data-volumes="{volumes}"><summary>#{len(sections)+1} · File: {_esc(journey["source_file"])}</summary>'
                        f'<p>Starting stage: {_esc(journey.get("start_stage","final_action"))}. Source files: {journey.get("source_file_count",1)}. Output scope: supported JSON processing; see generation coverage.</p><details><summary>Original source files</summary>{originals}</details><p><b>File conclusion:</b> {_esc(journey["conclusion"])}</p>' + readiness_html + ''.join(stages) + '</details>')
    completed = sum(journey['completed'] for journey,_ in journeys)
    stage_table = '<section id="stage-results"><h2>Files and records by stage</h2><p>Kept: continues. Dropped: removed by a business rule. Stopped: not processed after a failed check or missing prerequisite. Click a count for its file evidence. Files passed includes valid business drops; known differences remain disclosed in full reports.</p>'
    for name, counts in stage_counts.items():
        records = stage_records[name]
        reached = sum(counts.values())-counts['NOT_REACHED']-counts['BEFORE_START']
        volume = dict(files_in=reached, files_passed=counts['KEEP']+counts['DROP'], files_stopped=counts['FAIL']+counts['BLOCKED'], records_in=records['input_records'], kept=records['retained'], dropped=records['dropped'], records_stopped=records.get('stopped',0))
        strip = volume_strip(volume)
        for key in volume:
            value = f'{volume[key]:,}'
            strip = strip.replace(f'<strong>{value}</strong>', f'<strong><a href="#file-evidence" data-stage="{_esc(name)}" data-metric="{key}" onclick="event.stopPropagation();selectOutcome(this)">{value}</a></strong>', 1)
        body = []
        for journey, directory in journeys:
            step = next((step for step in journey['steps'] if step['stage'].replace('_',' ').title() == name), None)
            if step is None or step['status'] == 'NOT_REACHED': continue
            relative = directory.relative_to(index.parent).as_posix()
            body.append(f'<tr><td>{_esc(journey["source_file"])}</td><td>{_esc(step["status"])}</td><td>{_esc(step["reason"])}</td><td><a href="{relative}/{step["stage"]}/report.html">Open full report</a></td></tr>')
        stage_table += f'<details class="journey-stage"><summary><span class="stage-title">{_esc(name)}</span>{strip if reached else " — Not reached"}</summary><p>{reached} files reached; {counts["NOT_REACHED"]} not reached. File and record counts are not validation-event counts.</p><div class="scroll"><table><tr><th>Input file</th><th>Outcome</th><th>Conclusion</th><th>Evidence</th></tr>{"".join(body)}</table></div></details>'
    stage_table += '</section>'
    label = 'Synthetic demonstration' if synthetic else 'Connected validation'
    scope = ('Fictitious inputs; all five real validators run. Final Action and Split calculate retained records. '
             'Stay, Intermediate and Final either generate supported JSON fields or validate supplied candidates. This is workflow evidence, not production acceptance. '
             'Approved golden outputs, external reference calculations and the complete 3000-byte layout are not certified.' if synthetic else 'Stage processing and validation. BEFORE_START means the stage was not requested. Source-generated JSON covers supported calculations; generation coverage lists unresolved references and layouts. A completed journey would establish only the executed checks; approved golden outputs and full physical layout certification remain separate acceptance requirements.')
    source_link = '<p><a href="../input_sources.html">Local/S3 input sources — file counts and download evidence</a></p>' if (index.parent.parent / 'input_sources.html').exists() else ''
    index.write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MEDPAR evidence report</title><style>body{font:16px system-ui;line-height:1.55;background:#f3f6fa;color:#18324b;margin:0}'
        'header{background:#18324b;color:white;padding:30px}main{max-width:1200px;margin:auto;padding:24px}'
        'section,.summary,.file-card,.journey-stage{background:white;border:1px solid #d9e2eb;border-radius:10px;padding:20px;margin:16px 0}'
        '.volume-strip{display:grid;grid-template-columns:repeat(7,minmax(70px,1fr));gap:10px;margin-top:12px}.volume-cell span{display:block;font-size:12px;font-weight:400}.volume-cell strong{display:block;font-size:22px}.volume-cell:nth-child(3){border-right:1px solid #cbd5e1}.volume-cell:nth-child(2) strong,.volume-cell:nth-child(5) strong{color:#087f5b}.volume-cell:nth-child(3) strong,.volume-cell:nth-child(7) strong{color:#c92a2a}.volume-cell:nth-child(6) strong{color:#996600}.volume-cell a{color:inherit}@media(max-width:700px){.volume-strip{grid-template-columns:repeat(3,1fr)}}input,select{padding:12px;border:1px solid #a8b8ca;border-radius:8px;margin:8px} .file-card{overflow-wrap:anywhere} [hidden]{display:none!important} summary{cursor:pointer;font-weight:600;padding:10px}table{border-collapse:collapse;width:100%;font-size:14px}'
        'td,th{border:1px solid #d9e2eb;padding:10px;text-align:left;vertical-align:top}.scroll{overflow:auto}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto}a{color:#1958a0}</style></head>'
        f'<body><header><h1>MEDPAR — {_esc(label)}</h1><p>Generated {_esc(datetime.now().astimezone().strftime("%d %B %Y, %I:%M:%S %p %Z (%z)"))}</p>{source_link}</header><main>'
        f'<p>{_esc(scope)}</p><details><summary>How to read this report</summary>'
        '<p>KEEP: retained records continue. DROP: business rules excluded records. FAIL: observed data differs from the requirement. '
        'BLOCKED: a required input or prerequisite prevents a decision. NOT REACHED: an earlier stage stopped the file, so this stage did not run. '
        'Not assessed / N/A: the individual check was not evaluated; its explanation records why. None of these skipped states is a pass.</p>'
        '<p>Software test reports can contain intentionally invalid examples. Their test outcome tells you whether the framework handled those examples correctly; it is not the business outcome of this demonstration.</p></details>'
        + stage_table + connected_transfers(journeys, index) + '<section id="file-evidence"><h2>File evidence</h2><p>Search the original input filename, then expand a file to review its stage conclusions and proof.</p><label for="file-search">Search filename</label><input id="file-search" type="search" placeholder="Filename or path…"><button onclick="clearOutcome()">Show all files</button><p id="file-count"></p></section>' + ''.join(sections) + '<script>const field=document.getElementById("file-search");let selectedStage="",selectedOutcome="",selectedMetric="";function selectOutcome(link){selectedStage=link.dataset.stage;selectedOutcome=link.dataset.outcome||"";selectedMetric=link.dataset.metric||"";field.value="";filterFiles();}function clearOutcome(){selectedStage="";selectedOutcome="";selectedMetric="";field.value="";filterFiles();}function matchesStage(el){const outcome=JSON.parse(el.dataset.routes)[selectedStage];if(selectedMetric==="files_in")return !["NOT_REACHED","BEFORE_START"].includes(outcome);if(selectedMetric==="files_passed")return ["KEEP","DROP"].includes(outcome);if(selectedMetric==="files_stopped")return ["FAIL","BLOCKED"].includes(outcome);if(selectedMetric)return (JSON.parse(el.dataset.volumes)[selectedStage]||{})[selectedMetric]>0;return outcome===selectedOutcome;}function filterFiles(){let n=0;document.querySelectorAll(".file-card").forEach(el=>{el.hidden=!(el.dataset.filenames||el.querySelector("summary").textContent.toLowerCase()).includes(field.value.toLowerCase())||(selectedStage&&!matchesStage(el));if(!el.hidden)n++;});document.getElementById("file-count").textContent=n+" processing batches shown; expand Original source files for individual filenames.";}field.addEventListener("input",filterFiles);filterFiles();</script></main></body></html>', encoding='utf-8')
