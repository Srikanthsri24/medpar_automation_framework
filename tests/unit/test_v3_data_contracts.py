"""Regression tests and local fixtures for v3 data contracts. Tests describe controlled examples;
passing them does not certify all production files.
"""
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
    """Verify julian dates. The assertions below state exactly what this test proves for its
    fixtures.
    """
    assert parse_date(raw) == expected

@pytest.mark.parametrize("raw", ["2023366", "2024000", "2024367"])
def test_invalid_julian_dates(raw):
    """Verify invalid julian dates. The assertions below state exactly what this test proves for
    its fixtures.
    """
    with pytest.raises(ValueError):
        parse_date(raw)

def test_lowercase_parquet_field_aliases():
    """Verify lowercase parquet field aliases. The assertions below state exactly what this test
    proves for its fixtures.
    """
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
    """Verify ambiguous aliases fail closed. The assertions below state exactly what this test
    proves for its fixtures.
    """
    resolver = FieldResolver({})
    assert resolver.get({"query-code": 3, "QUERY_CODE": 5}, "querycode") is None

def test_claim_account_and_eq_bic_form_distinct_hicns():
    """Verify claim account and eq bic form distinct hicns. The assertions below state exactly what
    this test proves for its fixtures.
    """
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    assert resolver.get({"claimCan": "123456789", "claimCanNchEquatable": "A"}, "hicn") == "123456789A"
    assert resolver.get({"claimCan": "987654321", "claimCanNchEquatable": "A"}, "hicn") == "987654321A"
    assert resolver.get({"claimCanNchEquatable": "A"}, "hicn") is None
    assert resolver.get({"claimCanNchEquatable": "H001"}, "hicn") == "H001"
    assert resolver.get({"hicn": "explicit", "claimCan": "123456789", "claimCanNchEquatable": "A"}, "hicn") == "explicit"

def test_medpar_identity_uses_ccn_before_extended_provider_field():
    """Verify medpar identity uses ccn before extended provider field. The assertions below state
    exactly what this test proves for its fixtures.
    """
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    assert resolver.get({"medparProvider0130": "123456", "medparPrvdrFullNum1660": "0000000000000"}, "provider_id") == "123456"

def test_parquet_nested_groups(tmp_path):
    """Verify parquet nested groups. The assertions below state exactly what this test proves for
    its fixtures.
    """
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

@pytest.mark.parametrize('raw', [0, '0', '0000000', '00000000', '   '])
def test_optional_zero_dates_are_missing_but_required_dates_fail(raw):
    """Verify optional zero dates are missing but required dates fail. The assertions below state
    exactly what this test proves for its fixtures.
    """
    assert parse_date(raw) is None
    with pytest.raises(ValueError, match='required'):
        parse_date(raw, allow_none=False)
