"""Automatic source-only MEDPAR runner.

Edit SOURCE_RUN only, then run python run_commands.py. The selected starting
stage reads the source paths; generated kept outputs feed all later stages.
"""

from __future__ import annotations

import json
import html
from collections import Counter
from datetime import datetime, timezone
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from medpar_qa.reporting.path_utils import (  # noqa: E402
    ensure_relative_user_path,
    relative_display,
    slugify,
)
from medpar_qa.reporting.run_layout import ReportSession  # noqa: E402
from medpar_qa.reporting.session_index import refresh_session_indexes  # noqa: E402

PYTHON = sys.executable
REPORTS_ROOT = "reports"
STOP_ON_FAILURE = False
STAGE_ORDER = ("final_action", "split", "stay", "intermediate", "final_medpar")

# =============================================================================
# ONLY EDIT THIS INPUT CONFIGURATION
# =============================================================================
# Choose source_type: local or s3. Each stage accepts files, folders, or both.
# Fill local and s3 sections once; source_type selects the saved section automatically.
# Use forward slashes for Windows paths, e.g. C:/MEDPAR/input.
# Start with final_action for raw claims; split for retained Final Action claims;
# stay for retained Split bills; intermediate for merged Stay records;
# final_medpar for Intermediate extracts. Generated outputs feed later stages.
SOURCE_RUN: dict[str, Any] = {
    "source_type": "local",  # "local" or "s3"; paths below must match this choice.
    "start_stage": "all",  # "all" reviews each supplied entry; or choose one stage.
    "run_date": None,  # Resolve today's local business date once at execution.
    "row_selection": {"mode": "first_n_per_file", "limit": 5, "include_related_records": False},  # Up to five rows per supplied file; mode="all" processes every row.
    "source_paths": {'local': {'final_action': {'original': {'files': [], 'folders': ['data/production/q61/1-quarterly-claims-parquet']},
                                'keep': {'files': [], 'folders': ['data/production/q61/2-final-action-rules-parquet']},
                                'drop': {'files': [], 'folders': ['data/production/q61/2-final-action-rules-dropped']}},
               'split': {'original': {'files': [], 'folders': ['data/production/q61/2-final-action-rules-parquet']},
                         'keep': {'files': [], 'folders': ['data/production/q61/3-4yr-window-parquet']},
                         'drop': {'files': [], 'folders': ['data/production/q61/3-4yr-window-parquet-dropped']}},
               'stay': {'original': {'files': [], 'folders': ['data/production/q61/3-4yr-window-parquet']},
                        'keep': {'files': [], 'folders': ['data/production/q61/4-stay-processing']},
                        'drop': {'files': [], 'folders': []}},
               'intermediate': {'original': {'files': [], 'folders': ['data/production/q61/4-stay-processing']},
                                'keep': {'files': [], 'folders': ['data/production/q61/5-intermediate-processing']},
                                'drop': {'files': [], 'folders': []}},
               'final_medpar': {'original': {'files': [], 'folders': ['data/production/r65/5-intermediate-processing']},
                                'keep': {'files': [], 'folders': ['data/production/r65/6-final-processing']},
                                'drop': {'files': [], 'folders': []}}},
     's3': {'final_action': {'original': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/1-quarterly-claims-parquet/']},
                             'keep': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/2-final-action-rules-parquet/']},
                             'drop': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/2-final-action-rules-dropped/']}},
            'split': {'original': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/2-final-action-rules-parquet/']},
                      'keep': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/3-4yr-window-parquet/']},
                      'drop': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/3-4yr-window-parquet-dropped/']}},
            'stay': {'original': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/3-4yr-window-parquet/']},
                     'keep': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/4-stay-processing/']},
                     'drop': {'files': [], 'folders': []}},
            'intermediate': {'original': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/4-stay-processing/']},
                             'keep': {'files': [], 'folders': ['s3://YOUR-BUCKET/q61/5-intermediate-processing/']},
                             'drop': {'files': [], 'folders': []}},
            'final_medpar': {'original': {'files': [], 'folders': ['s3://YOUR-BUCKET/r65/5-intermediate-processing/']},
                             'keep': {'files': [], 'folders': ['s3://YOUR-BUCKET/r65/6-final-processing/']},
                             'drop': {'files': [], 'folders': []}}}},
    "aws_credentials_file": "config/aws_credentials.local.json",
    "settings": {},  # Optional reference feeds and approved calculation/layout options.
}


def source_run_configuration(plan, *, start_stage=None, run_date=None):
    """Select one entry-stage source list; generated downstream outputs need no paths."""
    stage = start_stage or plan.get("start_stage")
    stages = STAGE_ORDER
    if stage not in stages:
        raise ValueError("SOURCE_RUN.start_stage must be a supported stage")
    source_type = plan.get('source_type')
    if source_type not in ('local','s3'):
        raise ValueError('SOURCE_RUN.source_type must be "local" or "s3"')
    sources = plan.get('source_paths',{}).get(source_type,{}) if isinstance(plan.get('source_paths'),dict) else {}
    entry = sources.get(stage) if isinstance(sources,dict) else None
    if not isinstance(entry,dict):
        raise ValueError(f'SOURCE_RUN.source_paths.{source_type}.{stage} must contain files and folders lists')
    role_entries=entry if 'original' in entry else None
    entry=entry.get('original',entry)
    if not isinstance(entry,dict):raise ValueError('original must contain files and folders lists')
    from medpar_qa.ingestion.input_sources import s3_location
    paths=[]
    for role in ('files','folders'):
        values=entry.get(role,[])
        if not isinstance(values,list) or any(not isinstance(value,str) or not value.strip() for value in values):
            raise ValueError(f'SOURCE_RUN.source_paths.{source_type}.{stage}.{role} must be a list of nonempty paths')
        for value in values:
            path=value.strip()
            if 'YOUR-BUCKET' in path:
                raise ValueError('Replace YOUR-BUCKET with your actual bucket')
            remote=s3_location(path)
            if (source_type=='s3') != (remote is not None):
                raise ValueError(f'{stage}.{role}: path does not match selected source_type {source_type}')
            if remote and role=='files' and (not remote[1] or remote[1].endswith('/')):
                raise ValueError(f'{stage}.files: S3 file must identify an object, not a folder')
            if remote and role=='folders':
                prefix=remote[1].rstrip('/')
                path='s3://'+remote[0]+'/'+(prefix+'/' if prefix else '')
            if not remote:
                local=Path(path)
                if not local.is_absolute():local=PROJECT_ROOT/local
                if local.exists() and ((role=='files' and not local.is_file()) or (role=='folders' and not local.is_dir())):
                    raise ValueError(f'{stage}.{role}: existing path is not a {"file" if role=="files" else "folder"}')
            paths.append(path)
    if not paths:
        raise ValueError(f'SOURCE_RUN.source_paths.{source_type}.{stage} needs one or more files or folders')
    paths=list(dict.fromkeys(paths))
    business_date = run_date or plan.get("run_date") or datetime.now().date().isoformat()
    datetime.strptime(str(business_date), "%Y-%m-%d")
    settings = plan.get("settings", {})
    if not isinstance(settings,dict):
        raise ValueError("SOURCE_RUN.settings must be an object")
    settings=dict(settings)
    if 'row_selection' in plan:
        from medpar_qa.ingestion.row_selection import options as selection_options
        settings['_row_selection']=selection_options(plan['row_selection'])
    configured = {stage:{"enabled":True,"run_date":str(business_date),"single_files":[
        {"name":f"Source processing from {stage}","source":paths}]}}
    if role_entries:
        for name,target in (('keep','actual'),('drop','dropped')):
            supplied=role_entries.get(name,{})
            if not isinstance(supplied,dict):raise ValueError(f'{name} must contain files and folders lists')
            if supplied.get('files') or supplied.get('folders'):
                from copy import deepcopy
                role_plan=deepcopy(plan);role_plan['source_paths'][source_type][stage]=supplied
                _,comparison,_=source_run_configuration(role_plan,start_stage=stage,run_date=business_date)
                configured[stage]['single_files'][0][target]=comparison[stage]['single_files'][0]['source']
    return stage, configured, settings


@dataclass(frozen=True)
class Command:
    """Represent command with the fields and methods declared below. Declared fields document the
    component contract.
    """
    name: str
    stage: str
    command_id: str
    args: list[str]
    enabled: bool = True
    expected_exit_codes: tuple[int, ...] = (0,)


def _append_paths(args: list[str], flag: str, paths: list[str]) -> None:
    """Append configured file or folder arguments to a stage command without dropping prior
    entries.
    """
    for path in paths:
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{flag} requires a nonempty path")
        args.extend([flag, path])


def _stage_command(stage: str, run_date: str, item: dict[str, Any], report_session: str) -> Command:
    """Translate one enabled stage run into the Python stage-runner argument list."""
    name = str(item["name"])
    command_id = slugify(name)
    args = [
        PYTHON,
        "scripts/run_stage.py",
        "--stage",
        stage,
        "--run-date",
        run_date,
        "--mode",
        str(item.get("mode", "calculate")),
        "--run-id",
        command_id,
        "--command-id",
        command_id,
        "--report-session",
        report_session,
        "--show-pass",
    ]
    if stage == "final_medpar" and item.get("mode", "calculate") == "calculate":
        args.extend(["--per-file", "--final-extract"])
    if stage == "final_action" and item.get("modern_final_action"):
        args.append("--modern-final-action")
    if stage == "split" and item.get("split_current_year") is not None:
        args.extend(["--split-current-year", str(item["split_current_year"])])
    _append_paths(args, "--source", list(item.get("source") or []))
    _append_paths(args, "--actual", list(item.get("actual") or []))
    _append_paths(args, "--dropped", list(item.get("dropped") or []))
    _append_paths(args, "--expected", list(item.get("expected") or []))
    if item.get("per_file"):
        args.append("--per-file")
    if item.get("require_matching_snapshot"):
        args.append("--require-matching-snapshot")
    return Command(name, stage, command_id, args, bool(item.get("enabled", True)), tuple(item.get("expected_exit_codes", (0,))))


def build_commands(report_session: str = "reports/_configured_preview", stage_runs=None) -> list[Command]:
    """Build independent commands from explicit configuration, without stored input paths."""
    ensure_relative_user_path(report_session, "report_session")
    commands: list[Command] = []
    if stage_runs is None:
        stages = STAGE_ORDER if SOURCE_RUN.get('start_stage')=='all' else (SOURCE_RUN.get('start_stage'),)
        stage_runs = {}
        for stage in stages:
            _, configuration, _ = source_run_configuration(SOURCE_RUN,start_stage=stage)
            stage_runs.update(configuration)
    for stage, stage_config in stage_runs.items():
        if not stage_config.get("enabled", True):
            continue
        run_date = str(stage_config["run_date"])
        for list_name in ("single_files", "folder_paths"):
            for item in stage_config.get(list_name, []):
                commands.append(_stage_command(stage, run_date, item, report_session))

    return commands


def _command_text(args: list[str]) -> str:
    # Keep paths and command output project-relative. The Python executable is shown
    # as "python" instead of its machine-specific absolute virtualenv path.
    """Render the argument list as readable shell command text for execution evidence."""
    display_args = ["python", *args[1:]] if args and args[0] == PYTHON else list(args)
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in display_args)


def _command_output_directory(session: ReportSession, command: Command) -> Path:
    """Choose the isolated report directory for this command inside its session."""
    if command.stage == "master":
        directory = session.master_directory / command.command_id
    elif command.stage in {"final_action", "split", "stay", "intermediate", "final_medpar"}:
        directory = session.command_directory(command.stage, command.command_id)
    else:
        # Pytest plugin may infer a business stage from its marker. Use this fallback
        # for execution metadata; generated reports are discovered recursively.
        directory = session.command_directory("pytest", command.command_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_quality_summary(session_root: Path, executions: list[dict[str, Any]]) -> None:
    """Generate a self-contained, honest execution dashboard and machine-readable audit."""
    rows = []
    for item in executions:
        expected_codes = tuple(item["expected_exit_codes"])
        code = item["returncode"]
        if code == 0:
            result = "PASS" if item["expected"] else "UNEXPECTED_PASS"
        elif code == 1 and 1 in expected_codes:
            result = "EXPECTED_VALIDATION_FAILURE"
        else:
            result = "FAIL" if code == 1 else "ERROR"
        rows.append({
            "name": item["name"], "stage": item["stage"],
            "command": item["command"], "exit_code": code,
            "expected_exit_codes": list(expected_codes), "result": result,
            "reports": [relative_display(x, project_root=PROJECT_ROOT) for x in item["report_files"]],
            "console_log": item["output"][-20000:],
        })
    counts = Counter(row["result"] for row in rows)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "execution_counts": dict(counts), "total_commands": len(rows),
        "business_compliance_verified": False,
        "disclaimer": "Passing execution checks does not prove V3 rule or field-level compliance. A calculate-only run without actual output is not an end-to-end comparison.",
        "executions": rows,
    }
    (session_root / "quality_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    table_rows = []
    for row in rows:
        links = " ".join(f'<a href="{html.escape(str(Path(r).relative_to(Path(session_root).relative_to(PROJECT_ROOT))), quote=True)}">report</a>' for r in row["reports"] if Path(r).is_relative_to(Path(session_root).relative_to(PROJECT_ROOT)))
        cells = [row["stage"], row["name"], row["result"], str(row["exit_code"])]
        table_rows.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+'<td>'+links+'</td></tr>')
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MEDPAR Run Quality Summary</title><style>body{font:15px system-ui,Arial;margin:36px auto;max-width:1200px;padding:0 20px;color:#182536;background:#f7f9fc}h1{font-size:28px}section{background:white;padding:24px;border:1px solid #dce4ee;border-radius:12px;margin:18px 0}table{border-collapse:collapse;width:100%}th,td{padding:12px;text-align:left;border-bottom:1px solid #e5eaf1}th{background:#edf3f9}a{color:#1359ac}.warning{border-left:5px solid #bb7722;padding:12px;background:#fff6e6}</style><h1>MEDPAR QA — Execution Quality Summary</h1><section><h2>Run overview</h2><p>Commands: __TOTAL__</p><p>__COUNTS__</p><p class="warning">Execution success is not proof of MEDPAR V3 compliance. Expected validation failures are reported separately from passing validations. Runs without actual outputs cannot verify final extract correctness.</p></section><section><h2>Stage and command results</h2><table><thead><tr><th>Stage</th><th>Command</th><th>Result</th><th>Exit</th><th>Details</th></tr></thead><tbody>__ROWS__</tbody></table></section><section><h2>Next verification steps</h2><p>Compare source JSON with actual output JSON for every stage; verify approved decision-tree outcomes, field derivations, record-level reconciliation, external lookup inputs, and exception counts. Unresolved specification conflicts remain unverified.</p><p><a href="master/index.html">Existing master report</a> · <a href="quality_summary.json">Machine-readable summary</a></p></section></html>"""
    page = page.replace("__TOTAL__", str(len(rows))).replace("__COUNTS__", html.escape(', '.join(f'{k}: {v}' for k,v in sorted(counts.items())))).replace("__ROWS__", ''.join(table_rows))
    (session_root / "quality_summary.html").write_text(page, encoding="utf-8")


def execution_args(command: Command, session: ReportSession) -> list[str]:
    """Keep stage process launches short even with hundreds of long production paths."""
    if command.args[1:2] != ["scripts/run_stage.py"]:
        return command.args
    directory = session.root / "command_arguments"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{command.command_id}.json"
    path.write_text(json.dumps(command.args[2:], ensure_ascii=False, indent=2), encoding="utf-8")
    return [command.args[0], command.args[1], "--arguments-file",
            relative_display(path, project_root=PROJECT_ROOT)]


def run_all_source_entries(options):
    """Review configured entry points separately; never pretend datasets share a handoff."""
    import io
    import re
    import os
    from contextlib import redirect_stdout
    session = ReportSession.create(REPORTS_ROOT,project_root=PROJECT_ROOT)
    moment = datetime.now().astimezone()
    business_date = options.run_date or SOURCE_RUN.get('run_date') or moment.date().isoformat()
    entries=[]
    destination=sys.stdout
    class Tee(io.StringIO):
        def write(self,value):
            destination.write(value)
            return super().write(value)
        def flush(self):destination.flush()
    for stage in STAGE_ORDER:
        print(f"Production entry review: {stage}",flush=True)
        args=['--start-stage',stage,'--run-date',str(business_date)]
        if options.aws_config:args.extend(['--aws-config',options.aws_config])
        stream=Tee()
        with redirect_stdout(stream):
            child_root=session.root/'entries'/stage
            child_session=ReportSession.create(REPORTS_ROOT,session_path=relative_display(child_root,project_root=PROJECT_ROOT),project_root=PROJECT_ROOT)
            code=main(args,report_session=child_session)
        matched=re.search(r'Connected pipeline report: (.+)',stream.getvalue())
        row={'entry_stage':stage,'return_code':code,'input_files':0,'steps':[]}
        if matched:
            index=PROJECT_ROOT/matched.group(1)
            journeys=[json.loads(path.read_text()) for path in index.parent.glob('*/journey.json')]
            completed=sum(journey.get('completed',False) for journey in journeys)
            selected_inventory=index.parent.parent/'row_selection.json'
            selection=json.loads(selected_inventory.read_text(encoding='utf-8')) if selected_inventory.exists() else {}
            processed_files=len({path for journey in journeys for path in journey.get('source_files',[journey.get('source_file','')])})
            row.update(input_files=len(selection['files']) if selection.get('files') is not None else processed_files,processed_input_files=processed_files,row_selection=selection,
                       conclusion=f'{completed} of {len(journeys)} independent business groups completed. Open evidence for retained, dropped and exception groups.',
                       steps=[step for journey in journeys for step in journey['steps']],
                       report=os.path.relpath(index,session.master_directory).replace(os.sep,'/'))
        else:
            row['conclusion']='Input preparation failed; see input evidence'
            evidence=re.search(r'Input evidence: (.+)',stream.getvalue())
            if evidence:row['report']=os.path.relpath(PROJECT_ROOT/evidence.group(1),session.master_directory).replace(os.sep,'/')
        entries.append(row)
    report={'business_run_date':str(business_date),'generated_at':moment.isoformat(),
            'scope':'Separate source-only entry runs; only generated outputs within one journey establish transfers',
            'entries':entries}
    write_source_entry_overview(session,report)
    from medpar_qa.reporting.compact import compact_reports
    compact_reports(session.root)
    print('Source file counts by starting stage:', flush=True)
    for row in entries:print(f"  {row['entry_stage']}: {row['input_files']} resolved input files",flush=True)
    print('Report HTML: one master page and one page per stage',flush=True)
    return int(any(row['return_code'] for row in entries))


def write_source_entry_overview(session,report):
    """Render verified child journeys; file counts stay separate from record counts."""
    entries=report['entries']
    business_date=report['business_run_date']
    (session.master_directory/'entry_reviews.json').write_text(json.dumps(report,indent=2), encoding="utf-8")
    rows=[]
    for number,row in enumerate(entries,1):
        movements=[]
        for step in row['steps']:
            if step['status'] in ('BEFORE_START','NOT_REACHED'):continue
            next_position=STAGE_ORDER.index(step['stage'])+1
            next_step=next((item for item in row['steps'] if next_position<len(STAGE_ORDER) and item['stage']==STAGE_ORDER[next_position] and item.get('input')==step.get('output')),None)
            transferred=bool(step.get('output') and next_step and next_step.get('input')==step['output'])
            transfer_note=("1 generated file received by "+next_step['stage']) if transferred else ("Final output: 1 generated file; no later stage" if step.get('output') and step['stage']=='final_medpar' else "0 files forwarded")
            movements.append(f"{step['stage']}: {len(step.get('input_files',[]))} files received, {step['input_records']} records read, {step['retained']} kept, {step['dropped']} dropped; {step['status']}. {transfer_note}")
        link=f'<a href="{html.escape(row.get("report",""),quote=True)}">Files, rules and transfer evidence</a>' if row.get('report') else 'No report produced'
        rows.append('<tr>'+''.join('<td>'+html.escape(str(value))+'</td>' for value in (number,row['entry_stage'],row['input_files'],row['conclusion']))+f'<td>{link}<details><summary>Executed stage counts</summary><ul>'+''.join('<li>'+html.escape(item)+'</li>' for item in movements)+'</ul></details></td></tr>')
    index=session.master_directory/'entry_overview.html'
    index.write_text('<!doctype html><html><meta charset="utf-8"><title>Production source entry reviews</title><style>body{font:16px system-ui;background:#f3f6fa;color:#19344e;margin:32px}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ccd6e0;padding:14px;text-align:left;vertical-align:top}summary{cursor:pointer}a{color:#195da2}</style><h1>MEDPAR production source entry reviews</h1><p>Business date: '+html.escape(str(business_date))+' · Execution started: '+html.escape(report['generated_at'])+'</p><p>These are separate entry runs. Q61 inputs and R65 inputs are not evidence of a shared transfer. Open a report for actual generated handoffs, numbered original files and validation evidence. File counts are original physical input files; record counts are separate.</p><table><tr><th>#</th><th>Starting stage</th><th>Input files</th><th>Conclusion</th><th>Evidence</th></tr>'+''.join(rows)+'</table><p><a href="entry_reviews.json">Machine-readable counts and proof</a></p></html>', encoding="utf-8")
    (session.root/'review_scope.json').write_text(json.dumps({'description':report['scope']+'; final export readiness and remaining requirements are shown in Entry-source counts and each journey. Successful JSON checks do not certify complete physical MEDPAR output.'}), encoding="utf-8")
    index=refresh_session_indexes(session.root)
    print('Production entry summary: '+relative_display(index,project_root=PROJECT_ROOT),flush=True)
    return index


def main(argv=None, *, report_session=None) -> int:
    """Run this script command-line workflow and return its process exit status. The team entry
    point. SOURCE_RUN selects the source paths, starting stage and business date;
    commands run sequentially and their reports are combined into a session.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Run connected MEDPAR validation or one configured stage")
    parser.add_argument('--stage', choices=STAGE_ORDER, help="Validate only this configured stage independently")
    parser.add_argument("--config", help="Optional explicit validation configuration; overrides SOURCE_RUN")
    parser.add_argument("--source", action="append", help="Source file/folder or S3 prefix; repeat for multiple inputs")
    parser.add_argument("--run-date", help="Business processing date YYYY-MM-DD for direct --source runs")
    parser.add_argument("--start-stage", choices=STAGE_ORDER, help="Connected entry stage; stages before it are not executed")
    parser.add_argument("--flow", choices=("connected", "independent"), help="Override the configuration: forward retained records or review stages independently")
    parser.add_argument("--aws-config", default=None, help="Local AWS credentials/profile settings JSON (not included in reports)")
    options = parser.parse_args(argv)
    use_source_plan = not (options.config or options.source)
    if use_source_plan and not options.start_stage and not options.stage and SOURCE_RUN.get('start_stage')=='all':
        return run_all_source_entries(options)
    selected_stage = options.stage
    connected = selected_stage is None
    start_stage = options.start_stage or "final_action"
    generate_outputs = None
    connected_settings = {}
    configured_stages = {}
    if options.config:
        try:
            configuration = json.loads(Path(options.config).read_text(encoding="utf-8-sig"))
            configured_stages = configuration["stage_runs"]
            if not isinstance(configured_stages, dict) or set(configured_stages) - set(STAGE_ORDER):
                raise ValueError("stage_runs must map supported stage names to configurations")
            for stage, entry in configured_stages.items():
                if not isinstance(entry, dict): raise ValueError(f"{stage} configuration must be an object")
                if entry.get("enabled", True):
                    if entry.get("run_date"):
                        datetime.strptime(str(entry["run_date"]), "%Y-%m-%d")
                    for list_name in ("single_files", "folder_paths"):
                        if not isinstance(entry.get(list_name, []), list) or any(not isinstance(item, dict) for item in entry.get(list_name, [])):
                            raise ValueError(f"{stage}.{list_name} must contain configuration objects")
            connected = bool(configuration.get("connected_pipeline_enabled", True)) and selected_stage is None
            start_stage = options.start_stage or configuration.get("start_stage") or next((stage for stage,entry in configured_stages.items() if entry.get("enabled",True) and (entry.get("single_files") or entry.get("folder_paths"))), "final_action")
            if start_stage not in STAGE_ORDER: raise ValueError("Invalid start_stage")
            generate_outputs = configuration.get("generate_outputs")
            connected_settings = configuration.get("connected_settings", {})
            if not isinstance(connected_settings, dict): raise ValueError("connected_settings must be an object")

        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f"Cannot load stage configuration: {exc}")
    if use_source_plan:
        try:
            start_stage, configured_stages, connected_settings = source_run_configuration(SOURCE_RUN,start_stage=options.start_stage or selected_stage,run_date=options.run_date)
        except (ValueError,TypeError,AttributeError) as exc:
            parser.error(f"Cannot use SOURCE_RUN: {exc}")
        connected=selected_stage is None; generate_outputs=True
        print(f"SOURCE_RUN: {SOURCE_RUN['source_type']} source, starting at {start_stage}",flush=True)
        for number,path in enumerate(configured_stages[start_stage]['single_files'][0]['source'],1):
            print(f"  {number}. {path}",flush=True)
        print('Row selection: '+str(SOURCE_RUN.get('row_selection',{'mode':'all'})),flush=True)
        print("Automatic route: "+" -> ".join(list(STAGE_ORDER)[list(STAGE_ORDER).index(start_stage):]),flush=True)
    elif options.source:
        if options.config or selected_stage: parser.error("Use --source with --start-stage, without --config or --stage")
        business_date = options.run_date or datetime.now().date().isoformat()
        try: datetime.strptime(business_date,"%Y-%m-%d")
        except ValueError: parser.error("--run-date must be YYYY-MM-DD")
        configured_stages = {start_stage:{"enabled":True,"run_date":business_date,"single_files":[{"name":f"Source processing from {start_stage}","source":options.source}]}}
        connected=True; generate_outputs=True; connected_settings={}
    elif options.run_date:
        parser.error("--run-date is for direct --source runs; configuration files hold their own dates")
    if options.start_stage:
        if selected_stage: parser.error("--start-stage is connected processing; omit --stage")
        connected = True
    if options.flow:
        if options.flow == "connected" and selected_stage:
            parser.error("--stage selects one independent stage; omit it for --flow connected")
        connected = options.flow == "connected"
    if connected:
        from copy import deepcopy
        configured_stages = deepcopy(configured_stages)
        seed = configured_stages.get(start_stage, {})
        if not seed.get("run_date"):
            parser.error(f"Connected flow requires {start_stage} run_date and source inputs")
        for stage in STAGE_ORDER:
            configured_stages.setdefault(stage, {}).setdefault("run_date", seed["run_date"])
        # A stage's actual outputs can also supply the downstream comparison inputs.
        for item in [*seed.get("single_files", []), *seed.get("folder_paths", [])]:
            outputs = item.setdefault("pipeline_outputs", {})
            for stage in ("stay", "intermediate", "final_medpar"):
                candidates = [path for entry in [*configured_stages[stage].get("single_files", []), *configured_stages[stage].get("folder_paths", [])]
                              if entry.get("enabled", True) for path in ([entry["actual"]] if isinstance(entry.get("actual"), str) else entry.get("actual") or [])]
                if candidates: outputs.setdefault(stage, candidates)
    if not connected:
        for stage, entry in configured_stages.items():
            if entry.get("enabled", True) and (not selected_stage or selected_stage == stage) and not entry.get("run_date"):
                parser.error(f"Independent {stage} configuration requires run_date")
    aws_path = Path(options.aws_config or SOURCE_RUN["aws_credentials_file"])
    if not aws_path.is_absolute(): aws_path = PROJECT_ROOT / aws_path
    if options.aws_config and not aws_path.is_file():
        parser.error("The explicit --aws-config file does not exist; copy the AWS credentials example or use your AWS profile/environment")
    print(f"Selected dataset: {'CONFIGURED' if options.config else 'SOURCE INPUTS'}", flush=True)
    print("Run mode: connected validation" if connected else "Run mode: independent stage validation", flush=True)
    session = report_session or ReportSession.create(REPORTS_ROOT, project_root=PROJECT_ROOT)
    session_relative = relative_display(session.root, project_root=PROJECT_ROOT)
    from medpar_qa.ingestion.input_sources import InputSources, InputSourceError
    sources = InputSources(PROJECT_ROOT, session.root, credentials_file=aws_path)
    try:
        configured_stages = sources.prepare(configured_stages, selected_stage=selected_stage, connected=connected, start_stage=start_stage, generate_outputs=generate_outputs)
    except InputSourceError as exc:
        print(f"Input preparation failed: {exc}", flush=True)
        print(f"Input evidence: {relative_display(session.root / 'input_sources.html', project_root=PROJECT_ROOT)}", flush=True)
        return 2
    print(f"Unique resolved local/S3 files: {len(sources.files)}", flush=True)
    backends={"s3" if item["origin"].startswith("s3://") else "local" for item in sources.files.values()}
    print("Source: "+(" / ".join(sorted(backends)) or SOURCE_RUN.get("source_type","local")),flush=True)
    source_stages=[start_stage] if connected else [selected_stage] if selected_stage else list(configured_stages)
    for source_stage in source_stages:
        configured_entry=configured_stages.get(source_stage,{})
        given=set()
        for item in [*configured_entry.get('single_files',[]),*configured_entry.get('folder_paths',[])]:
            if not item.get('enabled',True):continue
            paths=item.get('source',[])
            given.update([paths] if isinstance(paths,str) else paths or [])
        print(f"Source input count — {source_stage}: {len(given)} resolved files",flush=True)
    if connected:
        from medpar_qa.orchestration.connected import run_configured
        journeys, index = run_configured(PROJECT_ROOT, session, configured_stages, connected_settings, **({"start_stage":start_stage} if start_stage != "final_action" else {}), **({"generate_outputs":generate_outputs} if generate_outputs is not None else {}))
        if report_session is None:
            from medpar_qa.reporting.compact import compact_reports
            refresh_session_indexes(session.root)
            index=compact_reports(session.root)
        print(f"Connected pipeline report: {relative_display(index, project_root=PROJECT_ROOT)}")
        for payload, directory in journeys:
            print(f"{payload['source_file']}: {payload['conclusion']}")
        comparison=session.root/start_stage/'row_review.json'
        comparison_failed=comparison.exists() and json.loads(comparison.read_text(encoding='utf-8')).get('comparison_status') in ('FAIL','BLOCKED')
        return 1 if comparison_failed or any(any(step['status'] in ('FAIL', 'BLOCKED') for step in payload['steps'])
                        for payload, _ in journeys) else 0
    commands = [command for command in build_commands(session_relative, configured_stages) if command.enabled and (selected_stage is None or command.stage == selected_stage)]
    if not commands:
        print("No commands are enabled. Set enabled=True for at least one stage/file/folder/pytest item.")
        return 0

    executions: list[dict[str, Any]] = []
    unexpected_failures = 0
    print("=" * 118)
    print("MEDPAR QA STAGE-WISE COMMAND RUNNER")
    print(f"Report session: {session_relative}")
    print(f"Enabled commands: {len(commands)}")
    print("All configured input and report paths are relative to the project folder.")
    print("=" * 118)

    for index, command in enumerate(commands, start=1):
        print("\n" + "#" * 118)
        print(f"COMMAND {index}/{len(commands)}: {command.name}")
        print(f"CATEGORY/STAGE: {command.stage}")
        print(f"EXPECTED EXIT CODE(S): {command.expected_exit_codes}")
        launch_args = execution_args(command, session)
        text = _command_text(launch_args)
        print(f"RELATIVE COMMAND: {text}")
        print("#" * 118)

        print("Executing stage validation. Results will appear when this stage finishes; large folders may take time.", flush=True)
        before = {path for path in session.root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            launch_args,
            cwd=PROJECT_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        output_text = completed.stdout or ""
        # Do not leak machine-specific project locations into shareable reports.
        output_text = output_text.replace(str(PROJECT_ROOT), ".")
        output_text = output_text.replace(str(PROJECT_ROOT).replace("/", "\\"), ".")
        print(output_text, end="" if output_text.endswith("\n") else "\n")
        after = {path for path in session.root.rglob("*") if path.is_file()}
        report_files = sorted(path for path in (after - before) if path.suffix.lower() in {".html", ".json", ".txt", ".xml"})

        expected = completed.returncode in command.expected_exit_codes
        outcome = "COMPLETED AS EXPECTED" if expected else "UNEXPECTED COMMAND RESULT"
        if not expected:
            unexpected_failures += 1
        command_dir = _command_output_directory(session, command)
        (command_dir / "console.log").write_text(output_text, encoding="utf-8")
        execution_payload = {
            "name": command.name,
            "stage": command.stage,
            "command": text,
            "returncode": completed.returncode,
            "expected_exit_codes": command.expected_exit_codes,
            "completed_as_expected": expected,
            "outcome": outcome,
            "report_files": [relative_display(path, project_root=PROJECT_ROOT) for path in report_files],
        }
        (command_dir / "execution.json").write_text(json.dumps(execution_payload, indent=2), encoding="utf-8")

        print(f"COMMAND OUTCOME: {outcome}")
        print(f"ACTUAL EXIT CODE: {completed.returncode}")
        if completed.returncode == 1 and expected:
            print("EXPLANATION: A business validation failure was expected and was detected correctly.")
        if report_files:
            print("GENERATED REPORT FILES:")
            for report in report_files:
                print(f"  - {relative_display(report, project_root=PROJECT_ROOT)}")

        executions.append(
            {
                "name": command.name,
                "stage": command.stage,
                "command": text,
                "returncode": completed.returncode,
                "expected_exit_codes": command.expected_exit_codes,
                "expected": expected,
                "outcome": outcome,
                "output": output_text,
                "report_files": report_files,
            }
        )
        if unexpected_failures and STOP_ON_FAILURE:
            break

    master = refresh_session_indexes(session.root, executions=executions)
    write_quality_summary(session.root, executions)
    from medpar_qa.reporting.compact import compact_reports
    master=compact_reports(session.root)
    print("\n" + "=" * 118)
    print(f"FINISHED. Unexpected command results: {unexpected_failures}")
    print(f"Timestamped report folder: {session_relative}")
    print(f"Master HTML report: {relative_display(master, project_root=PROJECT_ROOT)}")
    print("Open master/index.html for the overview, stage details and evidence screens.")
    print("=" * 118)
    return 1 if unexpected_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
