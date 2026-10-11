import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from medpar_qa.ingestion.readers import read_parquet_records, InputReadError
from medpar_qa.enums import Stage, FileRole


def test_hive_fields_keep_leading_zeros_and_spaces(tmp_path):
    path = tmp_path / 'claimcan=001234567' / 'claimcannchequatable=A%20' / 'providerid=001234' / 'input.parquet'
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({'querycode': ['1']}), path)
    record = read_parquet_records(path, Stage.FINAL_ACTION, FileRole.SOURCE)[0]
    assert record.data['claimcan'] == '001234567'
    assert record.data['claimcannchequatable'] == 'A '
    assert record.data['providerid'] == '001234'
    assert record.data['querycode'] == '1'


def test_conflicting_hive_field_is_not_silently_overwritten(tmp_path):
    path = tmp_path / 'providerid=001234' / 'input.parquet'
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({'providerId': ['999999']}), path)
    with pytest.raises(InputReadError, match='conflicts'):
        read_parquet_records(path, Stage.FINAL_ACTION, FileRole.SOURCE)
