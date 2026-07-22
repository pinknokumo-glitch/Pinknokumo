"""Compare multi-timeframe RSI thresholds without modifying production settings."""
from __future__ import annotations

from collections.abc import Mapping, Sequence


def oversold_rule(thresholds: Mapping[str, object]) -> dict[str, object]:
    return {"all": [
        {"field": "daily.rsi_14", "operator": "<=", "value": float(thresholds["daily"])},
        {"field": "weekly.rsi_14", "operator": "<=", "value": float(thresholds["weekly"])},
        {"field": "monthly.rsi_14", "operator": "<=", "value": float(thresholds["monthly"])},
    ]}


def rank_threshold_results(
    results: Sequence[Mapping[str, object]], minimum_trades: int,
    target_min_hits: int, target_max_hits: int,
) -> list[dict[str, object]]:
    ranked = []
    for result in results:
        item = dict(result)
        trades = int(item["summary"]["trade_count"])
        hits = int(item["current_hit_count"])
        item["eligible"] = trades >= minimum_trades and target_min_hits <= hits <= target_max_hits
        item["eligibility_reason"] = (
            "評価条件を満たします。" if item["eligible"] else
            f"必要取引数{minimum_trades}件または現在ヒット数{target_min_hits}〜{target_max_hits}件を満たしません。"
        )
        ranked.append(item)
    return sorted(ranked, key=lambda item: (
        bool(item["eligible"]), float(item["expectation"]["score"]),
        int(item["summary"]["trade_count"]), -int(item["current_hit_count"]),
    ), reverse=True)
