"""Check the mandatory source fields, allowed query/transaction codes, numeric values and valid
date order before routing claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver

from .grouping import derive_record_type
from .settings import FinalActionSettings


@dataclass(frozen=True)
class RecordValidationError:
    """Represent record validation error with the fields and methods declared below. Declared
    dataclass fields are the component contract.
    """
    record: SourceRecord
    field_name: str
    message: str
    actual: Any = None
    expected: Any = "A valid value for this field"


_REQUIRED_FIELDS = (
    "hicn",
    "provider_id",
    "stay_from_date",
    "stay_thru_date",
    "transaction_code",
    "query_code",
    "icn",
    "processing_date",
)


def _is_blank(value: Any) -> bool:
    """Determine whether a mandatory schema value is absent or empty."""
    return value is None or (isinstance(value, str) and not value.strip())


def validate_source_record(
    record: SourceRecord,
    resolver: FieldResolver,
    settings: FinalActionSettings,
) -> list[RecordValidationError]:
    """Check source fields and approved code/date domains before Final Action rules can make
    decisions.
    """
    errors: list[RecordValidationError] = []

    for field_name in _REQUIRED_FIELDS:
        if field_name == "transaction_code" and not settings.validate_transaction_codes:
            continue
        value = resolver.get(record.data, field_name)
        if _is_blank(value):
            errors.append(
                RecordValidationError(
                    record,
                    field_name,
                    f"Required Final Action field '{field_name}' is missing or blank",
                    value,
                    expected="Present and non-blank",
                )
            )

    if errors:
        return errors

    if settings.validate_transaction_codes:
        transaction_code = resolver.get(record.data, "transaction_code")
        try:
            numeric_transaction_code = int(transaction_code)
            if numeric_transaction_code not in settings.allowed_transaction_codes:
                raise ValueError
            derive_record_type(numeric_transaction_code)
        except (TypeError, ValueError):
            errors.append(
                RecordValidationError(
                    record,
                    "transaction_code",
                    "Unsupported Final Action transaction code",
                    transaction_code,
                    expected=list(settings.allowed_transaction_codes),
                )
            )

    query_code = resolver.get(record.data, "query_code")
    try:
        numeric_query_code = int(query_code)
        if numeric_query_code not in settings.allowed_query_codes:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(
            RecordValidationError(
                record,
                "query_code",
                "Unsupported Final Action query code. Query code is converted to an integer "
                f"and checked against {list(settings.allowed_query_codes)}; "
                "action codes 4/6 are separate fields and do not extend this list",
                query_code,
                expected=list(settings.allowed_query_codes),
            )
        )

    parsed_dates: dict[str, Any] = {}
    for field_name in ("stay_from_date", "stay_thru_date", "processing_date"):
        value = resolver.get(record.data, field_name)
        try:
            parsed_dates[field_name] = parse_date(value)
        except (TypeError, ValueError):
            errors.append(
                RecordValidationError(
                    record,
                    field_name,
                    f"Invalid date in '{field_name}'",
                    value,
                    expected="A valid calendar date in a supported format",
                )
            )

    accrete_value = resolver.get(record.data, "accrete_date")
    if settings.require_accrete_date and _is_blank(accrete_value):
        errors.append(
            RecordValidationError(
                record,
                "accrete_date",
                "Accrete date is required by Final Action settings",
                accrete_value,
                expected="Present and non-blank accretion date",
            )
        )
    elif not _is_blank(accrete_value):
        try:
            parse_date(accrete_value)
        except (TypeError, ValueError):
            errors.append(
                RecordValidationError(
                    record,
                    "accrete_date",
                    "Invalid date in 'accrete_date'",
                    accrete_value,
                    expected="A valid calendar date in a supported format",
                )
            )

    stay_from = parsed_dates.get("stay_from_date")
    stay_thru = parsed_dates.get("stay_thru_date")
    if stay_from is not None and stay_thru is not None and stay_from > stay_thru:
        errors.append(
            RecordValidationError(
                record,
                "stay_date_range",
                "Stay from date must be on or before stay thru date",
                {
                    "stay_from_date": stay_from.isoformat(),
                    "stay_thru_date": stay_thru.isoformat(),
                },
                expected="stay_from_date <= stay_thru_date",
            )
        )

    return errors
