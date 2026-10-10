from __future__ import annotations

from typing import Any, Iterable, Mapping

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult


def validate_encoded_length(
    value: str | bytes,
    *,
    expected_bytes: int = 3000,
    encoding: str = "ascii",
) -> RuleResult:
    try:
        encoded = value if isinstance(value, bytes) else value.encode(encoding)
        actual = len(encoded)
        status = ValidationStatus.PASS if actual == expected_bytes else ValidationStatus.FAIL
        message = "Encoded record length matches" if status == ValidationStatus.PASS else "Encoded record length mismatch"
    except UnicodeEncodeError as exc:
        actual = str(exc)
        status = ValidationStatus.FAIL
        message = f"Record cannot be encoded using {encoding}"
    return RuleResult(
        stage=Stage.FINAL_MEDPAR,
        rule_id="FM-BYTE-LENGTH",
        status=status,
        message=message,
        expected=expected_bytes,
        actual=actual,
        evidence={"encoding": encoding},
    )


def validate_field_layout(
    value: str | bytes,
    *,
    field_layout: Iterable[Mapping[str, Any]],
    encoding: str = "ascii",
) -> list[RuleResult]:
    """Validate configured one-based inclusive fixed-width positions.

    Each layout item supports: name, start, length, expected, strip, required.
    This intentionally does not guess the proprietary MEDPAR 3000-byte layout.
    """
    try:
        encoded = value if isinstance(value, bytes) else value.encode(encoding)
    except UnicodeEncodeError:
        return [RuleResult(stage=Stage.FINAL_MEDPAR,rule_id="FM-BYTE-FIELD",status=ValidationStatus.FAIL,
                           message=f"Record cannot be encoded using {encoding}")]
    results: list[RuleResult] = []
    for spec in field_layout:
        name = str(spec.get("name") or "unnamed_field")
        try:
            start = int(spec["start"])
            length = int(spec["length"])
            if start < 1 or length < 1:
                raise ValueError("start and length must be positive")
            segment = encoded[start - 1 : start - 1 + length]
            text = segment.decode(encoding)
            actual = text.strip() if bool(spec.get("strip", True)) else text
            expected = spec.get("expected")
            required = bool(spec.get("required", False))
            valid = len(segment) == length
            if required and actual == "":
                valid = False
            if expected is not None and str(actual) != str(expected):
                valid = False
            status = ValidationStatus.PASS if valid else ValidationStatus.FAIL
            message = f"Byte field {name} matches layout" if valid else f"Byte field {name} does not match layout"
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            start = spec.get("start")
            length = spec.get("length")
            expected = spec.get("expected")
            actual = str(exc)
            status = ValidationStatus.FAIL
            message = f"Invalid byte-layout specification for {name}"
        results.append(
            RuleResult(
                stage=Stage.FINAL_MEDPAR,
                rule_id="FM-BYTE-FIELD",
                status=status,
                message=message,
                expected={"start": start, "length": length, "value": expected},
                actual=actual,
                field_name=name,
                evidence={"one_based_start": start, "length": length, "encoding": encoding},
            )
        )
    return results
