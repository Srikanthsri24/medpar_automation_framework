from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from medpar_qa.models import SourceRecord


@dataclass(frozen=True)
class FinalActionGroupContext:
    records: tuple[SourceRecord, ...]
    group_key: dict[str, Any]
    query_codes: tuple[int, ...]
    icns: tuple[str, ...]
    action_codes: tuple[str | None, ...]
    transaction_codes: tuple[str | None, ...]

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def latest_record(self) -> SourceRecord:
        return self.records[0]

    @property
    def latest_qc(self) -> int:
        return self.query_codes[0]

    @property
    def qc_counts(self) -> Counter[int]:
        return Counter(self.query_codes)

    @property
    def icn_counts(self) -> Counter[str]:
        return Counter(self.icns)

    @property
    def all_query_codes_same(self) -> bool:
        return len(set(self.query_codes)) == 1

    @property
    def all_icns_same(self) -> bool:
        return len(set(self.icns)) == 1

    def qc_count(self, code: int) -> int:
        return self.qc_counts.get(code, 0)

    @property
    def has_qc5(self) -> bool:
        return self.qc_count(5) > 0

    @property
    def non_qc0_count(self) -> int:
        return sum(qc != 0 for qc in self.query_codes)
