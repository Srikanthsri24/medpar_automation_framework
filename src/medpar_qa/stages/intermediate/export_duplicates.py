"""Collapse only proven identical cross-file exports, ignoring filename metadata alone."""
import json
from collections import defaultdict
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult


def deduplicate_exports(records):
    """Retain differing business payloads and duplicates within one file for normal rejection."""
    grouped = defaultdict(list)
    for record in records:
        payload = {key: value for key, value in record.data.items() if key != 'filename'}
        grouped[json.dumps(payload, sort_keys=True, default=str)].append(record)
    retained, removed = [], []
    for group in grouped.values():
        if len(group) > 1 and len({record.source.file_path for record in group}) == len(group):
            ordered = sorted(group, key=lambda record: (record.source.file_path, record.source.row_number))
            retained.append(ordered[0])
            removed.extend(ordered[1:])
        else:
            retained.extend(group)
    proof = None
    if removed:
        proof = RuleResult(stage=Stage.INTERMEDIATE, rule_id='INT-IDENTICAL-EXPORT-COPIES',
            status=ValidationStatus.PASS, message='Cross-file exports have identical business fields; filename metadata alone differs',
            expected='No differing business field may be deduplicated', actual={'supplied':len(records),'retained':len(retained),'duplicate_export_copies':len(removed)},
            source_files=sorted({record.source.file_path for record in records}),
            record_ids=[record.record_id for record in removed], evidence={'ignored_metadata_fields':['filename'],'original_files_preserved':True})
    return retained, proof
