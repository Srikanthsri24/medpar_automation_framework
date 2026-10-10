"""The abstract stage-processor interface; concrete processors must implement validate(records)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from medpar_qa.enums import Stage
from medpar_qa.models import SourceRecord, StageResult


class BaseStageProcessor(ABC):
    """Implement this stage through the BaseStageProcessor validation interface and hold its
    resolver/settings.
    """
    stage: Stage

    @abstractmethod
    def validate(self, records: list[SourceRecord]) -> StageResult:
        """Declare the required processor validation contract; subclasses must provide the
        implementation.
        """
        raise NotImplementedError
