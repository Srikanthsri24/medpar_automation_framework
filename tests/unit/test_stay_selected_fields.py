import pytest

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.stay.selected_fields import validate_stay_decimal_field


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
@pytest.mark.decimal_precision
@pytest.mark.parametrize(
    "field_name",
    [
        "MEDPAR-TOT-CHRG-0400",
        "MEDPAR-DRG-PRICE-0380",
        "MEDPAR-SQSTRTN-RDCTN-AMT-1130",
    ],
)
def test_stay_selected_fields_use_three_decimal_precision(make_record, field_name):
    record = make_record({}, stage=Stage.STAY)
    result = validate_stay_decimal_field(
        record,
        field_name=field_name,
        expected_value="125.5554",
        actual_value="125.555",
    )
    assert result.status == ValidationStatus.PASS
