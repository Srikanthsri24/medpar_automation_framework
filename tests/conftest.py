from __future__ import annotations

from pathlib import Path

import pytest

from medpar_qa.enums import FileRole, Stage
from medpar_qa.models import SourceLocation, SourceRecord
from medpar_qa.normalization.fields import FieldResolver


@pytest.fixture
def resolver() -> FieldResolver:
    return FieldResolver.from_yaml(Path("config/field_aliases.yaml"))


@pytest.fixture
def make_record():
    def _make(
        data,
        *,
        row=1,
        stage=Stage.FINAL_ACTION,
        file_name="fixture.json",
        role=FileRole.SOURCE,
        file_format="json",
    ):
        return SourceRecord(
            data=data,
            source=SourceLocation(
                file_path=file_name,
                row_number=row,
                file_format=file_format,
                stage=stage,
                role=role,
            ),
            record_id=f"record-{row}",
        )

    return _make


@pytest.fixture(autouse=True)
def _capture_medpar_validation_events(request):
    """Capture every RuleResult/ClaimDecision and print it into pytest HTML."""
    from medpar_qa.reporting.event_recorder import (
        finish_capture,
        format_events_text,
        start_capture,
    )

    token = start_capture()
    yield
    events = finish_capture(token)
    request.node._medpar_validation_events = events
    details = format_events_text(events)
    if details:
        print(details)
