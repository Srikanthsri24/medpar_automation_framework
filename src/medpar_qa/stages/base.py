from __future__ import annotations

from abc import ABC, abstractmethod

from medpar_qa.enums import Stage
from medpar_qa.models import SourceRecord, StageResult


class BaseStageProcessor(ABC):
    stage: Stage

    @abstractmethod
    def validate(self, records: list[SourceRecord]) -> StageResult:
        raise NotImplementedError
