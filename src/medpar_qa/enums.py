"""The permitted stage, file-role, status and KEEP/DROP values. Shared enums prevent components
from using different spellings.
"""
from enum import StrEnum


class Stage(StrEnum):
    """Represent stage with the fields and methods declared below. This class groups the related
    operations below.
    """
    FINAL_ACTION = "final_action"
    SPLIT = "split"
    STAY = "stay"
    INTERMEDIATE = "intermediate"
    FINAL_MEDPAR = "final_medpar"


class FileRole(StrEnum):
    """Represent file role with the fields and methods declared below. This class groups the
    related operations below.
    """
    SOURCE = "source"
    ACTUAL_OUTPUT = "actual_output"
    EXPECTED_OUTPUT = "expected_output"


class ValidationStatus(StrEnum):
    """Represent validation status with the fields and methods declared below. This class groups
    the related operations below.
    """
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


class RecordDecision(StrEnum):
    """Represent record decision with the fields and methods declared below. This class groups the
    related operations below.
    """
    KEEP = "KEEP"
    DROP = "DROP"
