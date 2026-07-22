"""Suggest a numeric threshold that brings a single condition near a target hit count."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


class HitCountOptimizer:
    def suggest(
        self, snapshots: Iterable[Mapping[str, object]], field: str, operator: str, target_min: int, target_max: int
    ) -> dict[str, object]:
        if operator not in {"<=", ">="}:
            raise ValueError("operator must be <= or >=")
        if target_min < 1 or target_max < target_min:
            raise ValueError("target range is invalid")
        values = sorted({float(snapshot[field]) for snapshot in snapshots if self._is_number(snapshot.get(field))})
        if not values:
            return {"field": field, "operator": operator, "suggestion": None, "reason": "有効な指標値がありません。"}
        target = (target_min + target_max) / 2
        candidates = []
        for threshold in values:
            count = sum(value <= threshold if operator == "<=" else value >= threshold for value in values)
            candidates.append((abs(count - target), 0 if target_min <= count <= target_max else 1, threshold, count))
        _, _, threshold, count = min(candidates)
        return {
            "field": field, "operator": operator, "suggested_threshold": threshold,
            "estimated_hit_count": count, "target_min": target_min, "target_max": target_max,
            "reason": "設定ファイルは変更していません。候補を確認してから手動で反映してください。",
        }

    @staticmethod
    def _is_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value))
