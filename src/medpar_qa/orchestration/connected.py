"""Run each configured input through gated stages with immutable evidence and handoffs.

FA and Split materialize decisions; subsequent writers calculate supported JSON fields.
Comparison mode is optional. Missing physical layouts/reference definitions remain disclosed.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
from datetime import date, datetime
from pathlib import Path

from medpar_qa.enums import FileRole, RecordDecision, Stage, ValidationStatus
from medpar_qa.ingestion.discovery import discover_files
from medpar_qa.ingestion.readers import read_records
from medpar_qa.models import ManifestFile, RuleResult, RunManifest, SourceRecord, StageResult
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.reporting.path_utils import relative_display, relative_link, slugify, ensure_relative_user_path
from medpar_qa.reporting.report_bundle import write_report_bundle
from medpar_qa.reporting.rule_catalog import KNOWN_STAGE_RULE_IDS as STAGE_RULES
from .execution_control import StageStopped, observing
from .pipeline import Pipeline
from medpar_qa.processing.writers import GenerationBlocked

STAGES = tuple(Stage)


def _dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def _failfast(processor, records):
    """Observe real validation construction order; do not run checks beyond a stop."""
    result = StageResult(processor.stage)
    def emitted(value):
        if isinstance(value, RuleResult):
            result.rule_results.append(value)
            if value.status in (ValidationStatus.FAIL, ValidationStatus.BLOCKED):
                raise StageStopped(value.message)
        else:
            result.decisions.append(value)
    try:
        with observing(emitted):
            processor.validate(records)
    except StageStopped:
        pass
    except Exception as exc:
        result.rule_results.append(RuleResult(
            stage=processor.stage, rule_id='PIPELINE-EXECUTION', status=ValidationStatus.BLOCKED,
            message=f'Stage execution could not complete: {type(exc).__name__}: {exc}',
            expected='Successful stage execution', actual=type(exc).__name__))
    return result


def _terminal(result):
    return next((r for r in result.rule_results if r.status in
                 (ValidationStatus.FAIL, ValidationStatus.BLOCKED)), None)


def _not_reached(result, reason):
    seen = {r.rule_id for r in result.rule_results}
    for rule_id in STAGE_RULES.get(result.stage.value, ()):
        if rule_id not in seen:
            result.rule_results.append(RuleResult(
                stage=result.stage, rule_id=rule_id, status=ValidationStatus.NOT_APPLICABLE,
                message=f'Not reached: {reason}', expected='Earlier stage checks must complete',
                actual='NOT_REACHED', evidence={'execution_state': 'NOT_REACHED'}))


def _read(paths, stage, role, root):
    records = []
    for pattern in paths:
        ensure_relative_user_path(pattern, role.value)
        matches = discover_files(pattern, root)
        if not matches:
            raise ValueError(f'No files matched {pattern}')
        for path in matches:
            loaded=read_records(path, stage, role, display_base=root)
            if role == FileRole.SOURCE and not loaded:raise ValueError(f'Source file contains no records: {relative_display(path,project_root=root)}')
            records.extend(loaded)
    return records


class CandidateInputRejected(Exception):
    """A source prerequisite prevented output calculation; carry the exact rule evidence."""
    def __init__(self, validation):
        self.validation = validation
        super().__init__(validation.message)


def _candidate_split(records, processor):
    """Preserve claim fields and append the calculated indicator using stay-wide last thru."""
    from medpar_qa.normalization.dates import parse_date
    groups = {}
    for record in records:
        raw_code = processor.resolver.get(record.data, 'transaction_code')
        try:
            code = processor._transaction_code(record)
        except (TypeError, ValueError):
            code = None
        if code not in processor.settings.allowed_transaction_codes:
            raise CandidateInputRejected(RuleResult(
                stage=Stage.SPLIT, rule_id='SP-INVALID-TRANSACTION-CODE', status=ValidationStatus.FAIL,
                message='Split input transaction code is outside the documented IP/SNF domain; output cannot be calculated',
                expected=list(processor.settings.allowed_transaction_codes), actual=raw_code,
                field_name='transaction_code', record_ids=[record.record_id], source_files=[record.source.file_path]))
        key = processor.stay_key(record)
        thru = parse_date(processor.resolver.get(record.data, 'stay_thru_date'))
        groups[key] = max(groups.get(key, thru), thru)
    payload = []
    for record in records:
        key = processor.stay_key(record)
        indicator = processor.calculate_indicator(record, last_thru=groups[key])
        if indicator != processor.settings.outside_window_indicator:
            row = copy.deepcopy(record.data)
            # Update existing aliases to prevent stale indicator values shadowing the new value.
            for alias in ['split_year_indicator', *processor.resolver.aliases.get('split_year_indicator', [])]:
                if alias in row:
                    row[alias] = indicator
            row['split_year_indicator'] = indicator
            payload.append(row)
    return payload


class ConnectedPipeline:
    def __init__(self, root, session, resolver=None, settings=None):
        self.root = Path(root)
        self.session = session
        self.resolver = resolver or FieldResolver.from_yaml(self.root / 'config/field_aliases.yaml')
        self.settings = settings or {}

    def run_file(self, source, run_dates, outputs=None, *, start_stage="final_action", generate_outputs=None, original_inputs=None):
        """One input file owns a five-stage journey; failure never forwards its data."""
        source = relative_display(Path(source), project_root=self.root)
        identity = slugify(Path(source).stem)[:60] + '-' + hashlib.sha256(source.encode()).hexdigest()[:10]
        directory = self.session.root / 'connected' / identity
        directory.mkdir(parents=True, exist_ok=True)
        original_inputs = original_inputs or [source]
        current = source
        history, results = [], []
        stop_reason = None
        outputs = outputs or {}
        generate_outputs = not bool(outputs) if generate_outputs is None else generate_outputs
        start_index = [s.value for s in STAGES].index(start_stage)
        for stage_index, stage in enumerate(STAGES):
            stage_dir = directory / stage.value
            manifest = RunManifest(run_id=identity, run_date=date.fromisoformat(run_dates[stage.value]),
                files=[ManifestFile(path=current, stage=stage, role=FileRole.SOURCE)],
                settings=copy.deepcopy(self.settings), base_directory=self.root)
            if stage_index < start_index:
                result = StageResult(stage)
                step = {'stage':stage.value,'status':'BEFORE_START','reason':f'Not requested: input starts at {start_stage}', 'input':None,'output':None,'input_records':0,'retained':0,'dropped':0}
            elif stop_reason:
                result = StageResult(stage)
                _not_reached(result, stop_reason)
                step = {'stage': stage.value, 'status': 'NOT_REACHED', 'reason': stop_reason,
                        'input': None, 'output': None, 'input_records': 0, 'retained': 0, 'dropped': 0}
                result.rule_results.insert(0, RuleResult(
                    stage=stage, rule_id='PIPELINE-NOT-REACHED', status=ValidationStatus.BLOCKED,
                    message=f'Stage not executed because an earlier stage stopped this input: {stop_reason}',
                    expected='Retained output from the preceding stage', actual='NOT_REACHED'))
            else:
                result = StageResult(stage)
                source_records, candidate = [], []
                generation_notes, generated_dropped = [], []
                try:
                    source_records = _read(original_inputs if stage_index==start_index else [current], stage, FileRole.SOURCE, self.root)
                    if not source_records:
                        raise ValueError('Input file contains no records')
                    if manifest.settings.get('reference_feeds'):
                        from medpar_qa.reference_data import ReferenceData
                        reference_data = ReferenceData(manifest.settings['reference_feeds'],self.root)
                        for record in source_records: record.data = reference_data.enrich(record.data,self.resolver)
                    config = manifest.settings.setdefault(stage.value, {})
                    if stage == Stage.SPLIT:
                        config['require_actual_output'] = True
                    if stage in (Stage.STAY, Stage.INTERMEDIATE, Stage.FINAL_MEDPAR):
                        config['require_actual_output'] = True
                        # Golden validation is opt-in; candidate validation is independent evidence.
                        config.setdefault('require_expected_output', False)
                    if stage == Stage.FINAL_MEDPAR and generate_outputs:
                        config.setdefault('split_indicator_in_output',False)
                        config.setdefault('identity_fields',['hicn','provider_id','admission_date'])
                    processor = Pipeline(manifest, self.resolver)._processors()[stage]
                    if stage == Stage.INTERMEDIATE and generate_outputs:
                        from medpar_qa.stages.stay.revenue_merge import coalesce_segments
                        source_records, segment_proofs = coalesce_segments(source_records,self.resolver,processor.settings.identity_fields)
                        # Physical segments are grouped into one logical Stay before extraction.
                        if segment_proofs:_dump(stage_dir/'source_segments.json',{'physical_segments':sum(len(c.record_ids) for c in segment_proofs),'logical_records':len(source_records),'source_files':sorted({p for c in segment_proofs for p in c.source_files})})
                    if stage == Stage.SPLIT:
                        candidate_path = stage_dir / 'candidate.json'
                        _dump(candidate_path, _candidate_split(source_records, processor))
                        candidate = _read([relative_display(candidate_path, project_root=self.root)], stage, FileRole.ACTUAL_OUTPUT, self.root)
                    elif stage in (Stage.STAY, Stage.INTERMEDIATE, Stage.FINAL_MEDPAR):
                        if generate_outputs:
                            from medpar_qa.processing import writers
                            function = getattr(writers,stage.value)
                            generated = function(source_records,processor)
                            payload,generation_notes = generated[:2]
                            if stage == Stage.FINAL_MEDPAR: generated_dropped = generated[2]
                            generated_path = stage_dir / 'generated.json'
                            _dump(generated_path,payload)
                            _dump(stage_dir / 'generation.json',{'mode':'source_processing','source':current,'records_written':len(payload),'unassessed_calculations':generation_notes,'scope':'Supported JSON calculations; shared formula checks are not independent golden acceptance or complete fixed-width certification'})
                            available = _read([relative_display(generated_path,project_root=self.root)],stage,FileRole.ACTUAL_OUTPUT,self.root)
                        else:
                            available = _read(outputs.get(stage.value, []), stage, FileRole.ACTUAL_OUTPUT, self.root)
                        from medpar_qa.stages.common import record_identity
                        fields = processor.settings.identity_fields
                        keys = {record_identity(r, self.resolver, fields) for r in source_records}
                        # A shared stage folder can contain other files' stays. Validate only this
                        # journey's identities, retaining duplicate candidates so they are checked.
                        candidate = [r for r in available if record_identity(r, self.resolver, fields) in keys]
                        if not candidate and not (generate_outputs and generated_dropped):
                            result.rule_results.append(RuleResult(
                                stage=stage, rule_id='PIPELINE-OUTPUT-REQUIRED', status=ValidationStatus.BLOCKED,
                                message=(f'{stage.value}: supplied candidate output has no matching input identities; supply the matching extraction'
                                         if available else f'{stage.value} needs candidate output; a complete production writer is unavailable'),
                                expected='Candidate output validated against the previous stage output',
                                actual={'candidate_records_read': len(available), 'matching_records': 0,
                                        'matching_fields': list(fields)}, source_files=[current]))
                    if not _terminal(result):
                        result = _failfast(processor, source_records + candidate)
                except GenerationBlocked as exc:
                    result.rule_results.append(RuleResult(stage=stage,rule_id='PROCESSING-INPUT-REQUIRED',status=ValidationStatus.BLOCKED,message=str(exc),expected='Complete required source operands / approved export definitions',actual='Generation stopped',source_files=[current]))
                except CandidateInputRejected as exc:
                    result.rule_results.append(exc.validation)
                except Exception as exc:
                    result.rule_results.append(RuleResult(stage=stage, rule_id='PIPELINE-INPUT',
                        status=ValidationStatus.FAIL, message=f'Cannot prepare stage input: {exc}',
                        expected='Readable input and valid candidate output', actual=str(exc), source_files=[current]))
                if source_records:
                    by_file={}
                    for record in source_records: by_file.setdefault(record.source.file_path,[]).append(record)
                    for path,read_records_for_file in by_file.items():
                        result.rule_results.insert(0,RuleResult(stage=stage,rule_id='INGEST-READ-FILE',status=ValidationStatus.PASS,message='Stage source file read successfully',expected='At least one readable source record',actual={'file':path,'role':'source','record_count':len(read_records_for_file)},source_files=[path],record_ids=[r.record_id for r in read_records_for_file]))
                terminal = _terminal(result)
                retained, dropped = [], []
                if not terminal:
                    if stage in (Stage.FINAL_ACTION, Stage.SPLIT):
                        decisions = {d.record_id: d for d in result.decisions}
                        if set(decisions) != {r.record_id for r in source_records}:
                            terminal = RuleResult(stage=stage, rule_id='PIPELINE-DECISION-COVERAGE',
                                status=ValidationStatus.BLOCKED, message='Not every input record has a KEEP/DROP decision',
                                expected='One decision per input record', actual=len(decisions))
                            result.rule_results.append(terminal)
                        else:
                            retained = ([r.data for r in source_records if decisions[r.record_id].decision == RecordDecision.KEEP]
                                        if stage == Stage.FINAL_ACTION else [r.data for r in candidate])
                            dropped = [{'record': r.data, 'decision': decisions[r.record_id].reason,
                                        'rule': decisions[r.record_id].rule_id, 'source_record_id': r.record_id}
                                       for r in source_records if decisions[r.record_id].decision == RecordDecision.DROP]
                    else:
                        retained = [r.data for r in candidate]
                        dropped = generated_dropped
                if not terminal and generate_outputs and stage in (Stage.STAY,Stage.INTERMEDIATE,Stage.FINAL_MEDPAR):
                    result.rule_results.append(RuleResult(stage=stage,rule_id="PROCESSING-COVERAGE",status=ValidationStatus.KNOWN_DIFFERENCE,message="Source-generated JSON; checks cover populated supported fields; this is not CMS certification",expected="Complete approved field/layout/reference coverage for production certification",actual={"unassessed_calculations":generation_notes,"scope":"No independent golden comparison; physical layout requires approved copybook"},source_files=[current]))
                output = None
                if terminal:
                    stop_reason = f'{stage.value}: {terminal.rule_id}: {terminal.message}'
                    status = terminal.status.value
                    _not_reached(result, stop_reason)
                else:
                    _dump(stage_dir / 'dropped.json', dropped)
                    if retained:
                        output_path = stage_dir / 'retained.json'
                        _dump(output_path, retained)
                        output = relative_display(output_path, project_root=self.root)
                        status = 'KEEP'
                    else:
                        status = 'DROP'
                        stop_reason = f'{stage.value}: all input records were dropped; no records remain to forward'
                step = {'stage': stage.value, 'status': status, 'reason': stop_reason or 'Checks completed; retained output can proceed',
                        'input': current, 'output': output, 'input_records': len(source_records),
                        'retained': len(retained), 'dropped': len(dropped),
                        'input_files':original_inputs if stage_index==start_index else [step_input for step_input in [current] if step_input],
                        'generation_notes':sorted(set(generation_notes)),
                        'output_origin': 'calculated_decisions' if stage in (Stage.FINAL_ACTION, Stage.SPLIT) else 'source_generated' if generate_outputs else 'validated_candidate'}
                if not terminal:
                    seen = {r.rule_id for r in result.rule_results}
                    for rule_id in STAGE_RULES.get(stage.value, ()):
                        if rule_id not in seen:
                            result.rule_results.append(RuleResult(
                                stage=stage, rule_id=rule_id, status=ValidationStatus.NOT_APPLICABLE,
                                message='Rule prerequisites did not apply to this input or selected decision path',
                                expected='Applicable rule prerequisites', actual='NOT_APPLICABLE',
                                source_files=[current], evidence={'execution_state': 'NOT_APPLICABLE'}))
                if output:
                    current = output
            write_report_bundle(run_id=identity, results=[result], output_directory=stage_dir,
                                manifest=manifest, title=f'Connected pipeline — {stage.value}', parent_link='../index.html',
                                context={'mode': 'connected', 'original_input': source, 'handoff': step})
            _dump(stage_dir / 'handoff.json', {'original_input': source, **step})
            results.append(result)
            history.append(step)
        payload = {'source_file': source, 'steps': history, 'conclusion': stop_reason or ('All five stages completed' if start_stage=='final_action' else f'All requested stages completed from {start_stage}'),
                   'source_files':original_inputs,'source_file_count':len(original_inputs),'start_stage':start_stage, 'production_certified':False, 'processing_mode':'source_generated' if generate_outputs else 'candidate_validation',
                   'completed': all(s['status'] == 'KEEP' for s in history[start_index:])}
        _dump(directory / 'journey.json', payload)
        rows = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(s[k]))}</td>' for k in
                       ('stage', 'status', 'input_records', 'retained', 'dropped', 'reason')) +
                       f'<td><a href="{s["stage"]}/report.html">Rules and evidence</a></td></tr>' for s in history)
        links = ''.join(f'<li>{html.escape(s["stage"])}: <a href="{html.escape(relative_link(directory,self.root/s["output"]), quote=True)}">Retained output</a></li>'
                        for s in history if s['output'])
        (directory / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Connected MEDPAR journey</title>'
            '<style>body{font:16px Arial;margin:40px;background:#f3f6fa;color:#142b43}p{overflow-wrap:anywhere}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:1000px;background:white}td,th{padding:14px;border:1px solid #d7e0ea}h1{color:#174777}</style>'
            f'<h1>Input file journey</h1><p>{html.escape(source)}</p><p><b>Conclusion:</b> {html.escape(payload["conclusion"])}</p>'
            '<p>KEEP means records remain for the next stage. DROP is a business decision, not a failed validation. '
            'FAIL/BLOCKED stops progression. NOT REACHED means an earlier stage stopped this input.</p>'
            '<div class="tablewrap"><table><tr><th>Stage</th><th>Outcome</th><th>Input records</th><th>Retained</th><th>Dropped</th><th>Explanation</th><th>Report</th></tr>'
            +rows+'</table></div><h2>Generated outputs</h2><ul>'+links+'</ul>', encoding='utf-8')
        return payload, directory


def run_configured(root, session, stage_runs, settings=None, *, start_stage="final_action", generate_outputs=None):
    pipeline = ConnectedPipeline(root, session, settings=settings)
    dates = {s.value: stage_runs[s.value]['run_date'] for s in STAGES}
    journeys = []
    seed = stage_runs[start_stage]
    if not seed.get('enabled', True):
        raise ValueError(f'Connected mode requires {start_stage} to be enabled')
    items=[item for item in [*seed.get('single_files', []), *seed.get('folder_paths', [])] if item.get('enabled',True)]
    generating = generate_outputs is True or generate_outputs is None and all(not item.get('pipeline_outputs') for item in items)
    if generating:
        files=[]
        for item in items:
            for pattern in item.get('source',[]):
                matches=discover_files(pattern,root)
                files.extend(relative_display(path,project_root=root) for path in (matches or [Path(root)/pattern]))
        files=list(dict.fromkeys(files))
        if files:
            if len(files)==1: working=Path(root)/files[0]
            else:
                working=session.root/'connected_inputs'/'source_batch.json'
                try: rows=[record.data for record in _read(files,Stage(start_stage),FileRole.SOURCE,root)]
                except Exception: rows=[]  # run_file repeats original reads and records the precise failure.
                _dump(working,rows)
                _dump(working.with_name('ingestion.json'),{'source_files':files,'source_file_count':len(files),'working_record_count':len(rows),'purpose':'Aggregate before rule grouping: related claims and bills can span physical files'})
            journeys.append(pipeline.run_file(working,dates,start_stage=start_stage,generate_outputs=True,original_inputs=files))
    else:
        seen = set()
        for item in [*seed.get('single_files', []), *seed.get('folder_paths', [])]:
            if not item.get('enabled', True):
                continue
            for pattern in item.get('source', []):
                ensure_relative_user_path(pattern, 'source')
                matches = discover_files(pattern, root)
                # Keep unmatched paths visible as failed journeys rather than silently omitting them.
                for path in matches or [Path(root) / pattern]:
                    name = relative_display(path, project_root=root)
                    if name not in seen:
                        seen.add(name)
                        journeys.append(pipeline.run_file(path, dates, item.get('pipeline_outputs'), start_stage=start_stage, generate_outputs=generate_outputs))
    if not journeys:
        raise ValueError('No connected input files are configured')
    index = session.root / 'connected' / 'index.html'
    source_file_total=sum(payload.get('source_file_count',1) for payload,_ in journeys)
    completed = sum(payload['completed'] for payload, _ in journeys)
    stopped = len(journeys) - completed
    generated = datetime.now().astimezone().strftime('%d %B %Y, %I:%M:%S %p %Z (%z)')
    links = ''.join(
        f'<tr><td><a href="{html.escape(relative_link(index.parent,directory / "index.html"),quote=True)}">{html.escape(payload["source_file"])}</a></td>'
        f'<td>{"COMPLETED" if payload["completed"] else next((s["status"] for s in payload["steps"] if s["status"] != "KEEP"), "STOPPED")}</td>'
        f'<td>{html.escape(payload["conclusion"])}</td></tr>' for payload,directory in journeys)
    index.write_text('<!doctype html><meta charset="utf-8"><title>MEDPAR connected pipelines</title>'
        '<style>body{font:16px Arial;margin:40px;background:#f3f6fa;color:#142b43}header{background:#173b5c;color:white;padding:30px;border-radius:12px}'
        '.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:800px;table-layout:fixed;background:white}td,th{padding:14px;border:1px solid #d7e0ea;text-align:left;overflow-wrap:anywhere}td:nth-child(2),th:nth-child(2){width:110px;white-space:nowrap}'
        '.cards{display:flex;gap:20px;margin:25px 0}.card{background:white;padding:20px;border-radius:10px;flex:1}.card b{display:block;font-size:30px}a{color:#1661a6}</style>'
        f'<header><h1>MEDPAR connected pipeline report</h1><p>Generated: {html.escape(generated)}</p>'
        f'<p>Starting stage: {html.escape(start_stage.replace("_"," "))}. Earlier stages are not executed.</p></header>'
        f'<div class="cards"><div class="card">Starting input files<b>{source_file_total}</b></div>'
        f'<div class="card">Processing batches completed<b>{completed}</b></div><div class="card">Batches stopped or dropped<b>{stopped}</b></div></div>'
        '<p>Each file proceeds only while checks permit it. Open its journey to see applied rules, outputs and the stopping reason. '
        'Dropped claims are preserved separately; retained claims continue. Stay, Intermediate and Final MEDPAR generate supported JSON outputs from source data, or compare supplied outputs. Generation coverage discloses missing operands, external references and physical-layout certification.</p>'
        '<div class="tablewrap"><table><tr><th>Original input file</th><th>Outcome</th><th>Final explanation</th></tr>'+links+'</table></div>', encoding='utf-8')
    master = session.root / 'master' / 'index.html'
    master.parent.mkdir(parents=True, exist_ok=True)
    target = html.escape(relative_link(master.parent, index), quote=True)
    master.write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={target}">'
                      f'<a href="{target}">Open the connected pipeline report</a>', encoding='utf-8')
    from medpar_qa.reporting.connected_review import write_connected_review
    write_connected_review(journeys, index)
    return journeys, index
