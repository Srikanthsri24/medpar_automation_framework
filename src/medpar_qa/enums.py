from enum import StrEnum


class Stage(StrEnum):
    FINAL_ACTION = "final_action"
    SPLIT = "split"
    STAY = "stay"
    INTERMEDIATE = "intermediate"
    FINAL_MEDPAR = "final_medpar"


class FileRole(StrEnum):
    SOURCE = "source"
    ACTUAL_OUTPUT = "actual_output"
    EXPECTED_OUTPUT = "expected_output"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


class RecordDecision(StrEnum):
    KEEP = "KEEP"
    DROP = "DROP"
