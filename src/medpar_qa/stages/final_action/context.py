"""Read-only features of one newest-first claim group: counts, query-code/ICN distributions and
newest claim.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from medpar_qa.models import SourceRecord


@dataclass(frozen=True)
class FinalActionGroupContext:
    """Represent final action group context with the fields and methods declared below. Declared
    dataclass fields are the component contract.
    """
    records: tuple[SourceRecord, ...]
    group_key: dict[str, Any]
    query_codes: tuple[int, ...]
    icns: tuple[str, ...]
    action_codes: tuple[str | None, ...]
    transaction_codes: tuple[str | None, ...]

    @property
    def count(self) -> int:
        """Return the number of claims in this Final Action group."""
        return len(self.records)

    @property
    def latest_record(self) -> SourceRecord:
        """Return the first claim from the already newest-first group."""
        return self.records[0]

    @property
    def latest_qc(self) -> int:
        """Return the query code of the newest claim."""
        return self.query_codes[0]

    @property
    def qc_counts(self) -> Counter[int]:
        """Count claims for each query code in the group."""
        return Counter(self.query_codes)

    @property
    def icn_counts(self) -> Counter[str]:
        """Count occurrences of each internal control number in the group."""
        return Counter(self.icns)

    @property
    def all_query_codes_same(self) -> bool:
        """Determine whether the group has one unique query code."""
        return len(set(self.query_codes)) == 1

    @property
    def all_icns_same(self) -> bool:
        """Determine whether every group claim has the same ICN."""
        return len(set(self.icns)) == 1

    def qc_count(self, code: int) -> int:
        """Return the number of claims having the requested query code."""
        return self.qc_counts.get(code, 0)

    @property
    def has_qc5(self) -> bool:
        """Determine whether any claim in this group has query code 5."""
        return self.qc_count(5) > 0

    @property
    def non_qc0_count(self) -> int:
        """Count claims whose query code is not zero."""
        return sum(qc != 0 for qc in self.query_codes)
