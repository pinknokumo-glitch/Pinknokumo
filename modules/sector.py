"""Sector-level aggregation for screening results."""
from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping


class SectorAnalyzer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def summarize_hits(self, hits: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
        codes = [str(hit["code"]) for hit in hits]
        if not codes:
            return []
        placeholders = ", ".join("?" for _ in codes)
        rows = self.connection.execute(
            f"SELECT code, sector_33_name FROM master_stock WHERE code IN ({placeholders})", codes
        ).fetchall()
        sector_by_code = {row["code"]: row["sector_33_name"] or "未分類" for row in rows}
        counts = Counter(sector_by_code.get(code, "未分類") for code in codes)
        return [
            {"sector_33_name": sector, "hit_count": count}
            for sector, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
