import json

import pytest

from medpar_qa.enums import FileRole, Stage
from medpar_qa.ingestion.readers import read_json_records


@pytest.mark.unit
def test_json_reader_adds_lineage(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps([{"claimCan": "A"}, {"claimCan": "B"}]), encoding="utf-8")

    records = read_json_records(path, Stage.FINAL_ACTION, FileRole.SOURCE)

    assert len(records) == 2
    assert records[0].source.row_number == 1
    assert records[1].source.row_number == 2
    assert records[0].record_id != records[1].record_id
