from datetime import date
import pytest
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver

@pytest.mark.parametrize("raw,expected", [
    ("2024060", date(2024, 2, 29)),
    ("2024366", date(2024, 12, 31)),
    ("24060", date(2024, 2, 29)),
    ("2024001", date(2024, 1, 1)),
    ("2026064", date(2026, 3, 5)),
])
def test_julian_dates(raw, expected):
    assert parse_date(raw) == expected

@pytest.mark.parametrize("raw", ["2023366", "2024000", "2024367"])
def test_invalid_julian_dates(raw):
    with pytest.raises(ValueError):
        parse_date(raw)

def test_lowercase_parquet_field_aliases():
    resolver = FieldResolver({
        "query_code": ["QUERYCODE"],
        "internal_control_number": ["INTERNALCONTROLNUMBER"],
        "provider_id": ["PROVIDERID"],
    })
    data = {"querycode": 3, "internalcontrolnumber": "A", "providerid": "B"}
    assert resolver.get(data, "query_code") == 3
    assert resolver.get(data, "internal_control_number") == "A"
    assert resolver.get(data, "provider_id") == "B"

def test_ambiguous_aliases_fail_closed():
    resolver = FieldResolver({})
    assert resolver.get({"query-code": 3, "QUERY_CODE": 5}, "querycode") is None

def test_parquet_nested_groups(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    from medpar_qa.ingestion.readers import read_parquet_records
    from medpar_qa.enums import Stage, FileRole
    path = tmp_path / "nested.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"querycode": 3, "value_codes": [{"code": "18", "amount": 12.5}],
         "revenue": [{"code": "0200", "charges": 10}]}
    ]), path)
    record = read_parquet_records(path, Stage.FINAL_ACTION, FileRole.SOURCE)[0].data
    assert record["value_codes"] == [{"code": "18", "amount": 12.5}]
    assert record["revenue"][0]["code"] == "0200"
