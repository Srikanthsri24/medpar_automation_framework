from medpar_qa.normalization.fields import FieldResolver

def test_v3_spelling_aliases():
    resolver = FieldResolver.from_yaml("config/field_aliases.yaml")
    assert resolver.get({"MEDPAR-NO-OF-BILLS-0150": 4}, "bill_count") == 4
    assert resolver.get({"MEDPAR-HIMASTER-DOD-IND-0240": "B"}, "medpar_dod_ind_0240") == "B"
    assert resolver.get({"MEDPAR-EXPNDD-ACS-SW-1570": "Y"}, "medpar_expndd_acc_sw_1570") == "Y"
