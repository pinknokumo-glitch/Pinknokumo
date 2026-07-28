"""Aggregate one rule's per-stock backtests across sectors and the market."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math


WEIGHTED_FIELDS = (
    "average_return_percent",
    "win_rate_percent",
    "outcome_probability_percent",
)
OOS_WEIGHTED_FIELDS = (
    "out_of_sample_average_return_percent",
    "out_of_sample_win_rate_percent",
    "out_of_sample_outcome_probability_percent",
)


def aggregate_summaries(
    results: Mapping[str, Mapping[str, object]],
    sector_names: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Return market and sector summaries, weighted by actual trade counts."""
    market = _aggregate(list(results.items()))
    grouped: dict[str, list[tuple[str, Mapping[str, object]]]] = defaultdict(list)
    for code, summary in results.items():
        sector = str(sector_names.get(code) or "業種未分類")
        grouped[sector].append((code, summary))
    sectors = {
        sector: _aggregate(items)
        for sector, items in grouped.items()
    }
    return market, sectors


def _aggregate(
    items: Sequence[tuple[str, Mapping[str, object]]],
) -> dict[str, object]:
    usable = [
        (code, summary)
        for code, summary in items
        if int(summary.get("trade_count") or 0) > 0
    ]
    trade_count = sum(int(summary.get("trade_count") or 0) for _, summary in usable)
    oos_count = sum(
        int(summary.get("out_of_sample_trade_count") or 0)
        for _, summary in usable
    )
    output: dict[str, object] = {
        "stock_count": len(usable),
        "trade_count": trade_count,
        "out_of_sample_trade_count": oos_count,
    }
    for field in WEIGHTED_FIELDS:
        output[field] = _weighted(usable, field, "trade_count")
    for field in OOS_WEIGHTED_FIELDS:
        output[field] = _weighted(
            usable, field, "out_of_sample_trade_count"
        )
    drawdowns = [
        value
        for _, summary in usable
        if (value := _finite(summary.get("max_drawdown_percent"))) is not None
    ]
    oos_drawdowns = [
        value
        for _, summary in usable
        if (
            value := _finite(summary.get("out_of_sample_max_drawdown_percent"))
        ) is not None
    ]
    output["max_drawdown_percent"] = min(drawdowns) if drawdowns else None
    output["out_of_sample_max_drawdown_percent"] = (
        min(oos_drawdowns) if oos_drawdowns else None
    )
    return output


def attach_scope_comparisons(
    hits: Sequence[dict[str, object]],
    individual_results: Mapping[str, Mapping[str, object]],
    sector_names: Mapping[str, object],
    universe_count: int,
) -> dict[str, object]:
    market, sectors = aggregate_summaries(individual_results, sector_names)
    tested_count = len(individual_results)
    coverage = tested_count / universe_count if universe_count else 0.0
    for hit in hits:
        code = str(hit["code"])
        sector = str(sector_names.get(code) or "業種未分類")
        individual = individual_results.get(code, {})
        hit["individual_trade_count"] = int(
            individual.get("trade_count") or 0
        )
        hit["individual_out_of_sample_trade_count"] = int(
            individual.get("out_of_sample_trade_count") or 0
        )
        hit["individual_out_of_sample_average_return_percent"] = individual.get(
            "out_of_sample_average_return_percent"
        )
        hit["individual_out_of_sample_win_rate_percent"] = individual.get(
            "out_of_sample_win_rate_percent"
        )
        hit["sector_name"] = sector
        hit["sector_backtest"] = sectors.get(sector, _aggregate([]))
        hit["market_backtest"] = market
        hit["backtest_coverage_ratio"] = coverage
        hit["backtest_confidence"] = confidence_label(
            individual, hit["sector_backtest"], market, coverage
        )
    return {
        "universe_count": universe_count,
        "tested_stock_count": tested_count,
        "coverage_ratio": coverage,
        "market": market,
        "sector_count": len(sectors),
    }


def confidence_label(
    individual: Mapping[str, object],
    sector: Mapping[str, object],
    market: Mapping[str, object],
    coverage_ratio: float,
) -> str:
    """Describe data sufficiency; this is deliberately not a probability."""
    individual_trades = int(individual.get("trade_count") or 0)
    sector_trades = int(sector.get("trade_count") or 0)
    market_trades = int(market.get("trade_count") or 0)
    oos_trades = int(market.get("out_of_sample_trade_count") or 0)
    if (
        coverage_ratio >= 0.9
        and individual_trades >= 20
        and sector_trades >= 100
        and market_trades >= 500
        and oos_trades >= 100
    ):
        return "高"
    if (
        coverage_ratio >= 0.6
        and sector_trades >= 30
        and market_trades >= 150
        and oos_trades >= 30
    ):
        return "中"
    return "低"


def _weighted(
    items: Sequence[tuple[str, Mapping[str, object]]],
    field: str,
    weight_field: str,
) -> float | None:
    weighted_total = 0.0
    weight_total = 0
    for _, summary in items:
        value = _finite(summary.get(field))
        weight = int(summary.get(weight_field) or 0)
        if value is None or weight <= 0:
            continue
        weighted_total += value * weight
        weight_total += weight
    return weighted_total / weight_total if weight_total else None


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
