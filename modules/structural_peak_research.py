"""Research monthly trend/range peak roles across monthly, weekly and daily bars.

This is a descriptive research classifier, not a live chart-pattern signal.
It uses every available monthly local swing, then classifies its preceding
monthly context as a trend, a repeatedly tested range, or a range breakout.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from modules.multitimeframe_peak_research import _features, _resample, _snapshot, _summarize


MONTHLY_RADIUS = 2
WEEKLY_RADIUS = 2
DAILY_RADIUS = 5
RETEST_MONTHS = 18
RETEST_TOLERANCE_PERCENT = 3.0
RANGE_MIN_WIDTH_PERCENT = 6.0
RANGE_BREAKOUT_PERCENT = 2.0


def _pivots(frame: pd.DataFrame, side: str, radius: int) -> list[dict[str, Any]]:
    """Return local OHLC swing nodes, retaining equal separated highs/lows."""
    field = "high" if side == "top" else "low"
    values = frame[field].astype(float).reset_index(drop=True)
    output: list[dict[str, Any]] = []
    for index in range(radius, len(frame) - radius):
        window = values.iloc[index - radius:index + radius + 1]
        target = float(window.max() if side == "top" else window.min())
        value = float(values.iloc[index])
        if value != target:
            continue
        # A flat multi-bar plateau is one node, while separated equal levels
        # remain distinct for double/triple-top and bottom research.
        if index and value == float(values.iloc[index - 1]):
            continue
        output.append({"index": index, "date": str(frame.iloc[index].trade_date.date()), "price": value})
    return output


def _within_percent(left: float, right: float) -> bool:
    return abs(left - right) / max(abs(left), abs(right), 1e-9) * 100 <= RETEST_TOLERANCE_PERCENT


def _monthly_roles(monthly: pd.DataFrame, side: str) -> list[dict[str, Any]]:
    """Annotate every monthly local swing with same-level re-test counts."""
    nodes = _pivots(monthly, side, MONTHLY_RADIUS)
    for node in nodes:
        index, price = node["index"], node["price"]
        retests = [other for other in nodes if other["index"] != index
                   and abs(other["index"] - index) <= RETEST_MONTHS
                   and _within_percent(price, other["price"])]
        node["retest_count"] = len(retests)
    return nodes


def _range_levels(
    top_nodes: list[dict[str, Any]], bottom_nodes: list[dict[str, Any]], pivot_index: int,
) -> tuple[float, float] | None:
    """Return established support/resistance using only pivots before this month."""
    start = pivot_index - RETEST_MONTHS
    tops = [node["price"] for node in top_nodes if start <= node["index"] < pivot_index]
    bottoms = [node["price"] for node in bottom_nodes if start <= node["index"] < pivot_index]
    resistance = _retested_level(tops)
    support = _retested_level(bottoms)
    if resistance is None or support is None:
        return None
    if (resistance / max(support, 1e-9) - 1) * 100 < RANGE_MIN_WIDTH_PERCENT:
        return None
    return support, resistance


def _retested_level(prices: list[float]) -> float | None:
    """Find a repeated support/resistance cluster without rejecting internal swings."""
    candidates: list[tuple[int, float]] = []
    for price in prices:
        cluster = [other for other in prices if _within_percent(price, other)]
        if len(cluster) >= 2:
            candidates.append((len(cluster), float(pd.Series(cluster).median())))
    if not candidates:
        return None
    # Prefer the most repeatedly tested level.  Price is only a deterministic
    # tie breaker; no future date or outcome is used.
    return max(candidates, key=lambda item: (item[0], item[1]))[1]


def _trend_context(top_nodes: list[dict[str, Any]], bottom_nodes: list[dict[str, Any]], pivot_index: int) -> str:
    """Classify the preceding Dow-style swing sequence without future prices."""
    start = pivot_index - RETEST_MONTHS
    tops = [node for node in top_nodes if start <= node["index"] <= pivot_index]
    bottoms = [node for node in bottom_nodes if start <= node["index"] <= pivot_index]
    if len(tops) < 2 or len(bottoms) < 2:
        return "mixed_or_insufficient"
    newest_top, prior_top = tops[-1]["price"], tops[-2]["price"]
    newest_bottom, prior_bottom = bottoms[-1]["price"], bottoms[-2]["price"]
    if newest_top > prior_top and newest_bottom > prior_bottom:
        return "uptrend"
    if newest_top < prior_top and newest_bottom < prior_bottom:
        return "downtrend"
    return "mixed_or_insufficient"


def _monthly_regime(
    monthly: pd.DataFrame,
    side: str,
    node: dict[str, Any],
    top_nodes: list[dict[str, Any]],
    bottom_nodes: list[dict[str, Any]],
) -> str:
    """Return range first, then a trend label; breakout uses only prior range levels."""
    levels = _range_levels(top_nodes, bottom_nodes, node["index"])
    close = float(monthly.iloc[node["index"]].close)
    if levels is not None:
        support, resistance = levels
        if side == "top" and close >= resistance * (1 + RANGE_BREAKOUT_PERCENT / 100):
            return "range_breakout_up"
        if side == "bottom" and close <= support * (1 - RANGE_BREAKOUT_PERCENT / 100):
            return "range_breakout_down"
        return "range"
    return _trend_context(top_nodes, bottom_nodes, node["index"])


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    return round(100 * sum(bool(row[key]) for row in rows) / len(rows), 2) if rows else None


def _summarize_role(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **_summarize(rows),
        "weekly_structural_match_rate_percent": _rate(rows, "weekly_structural_match"),
        "daily_structural_match_rate_percent": _rate(rows, "daily_structural_match"),
        "mean_retest_count": round(sum(row["retest_count"] for row in rows) / len(rows), 3) if rows else None,
    }


def analyze_structural_peaks(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for code, prices in frames.items():
        try:
            daily = _features(prices, indicator_config)
            weekly = _features(_resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "W-FRI"), indicator_config)
            monthly = _features(_resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "ME"), indicator_config)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        weekly_periods = {row.trade_date.to_period("W-FRI"): row for _, row in weekly.iterrows()}
        daily_dates = {str(row.trade_date.date()): row for _, row in daily.iterrows()}
        monthly_nodes = {side: _monthly_roles(monthly, side) for side in ("top", "bottom")}
        for side in ("top", "bottom"):
            weekly_nodes = {node["date"] for node in _pivots(weekly, side, WEEKLY_RADIUS)}
            daily_nodes = {node["date"] for node in _pivots(daily, side, DAILY_RADIUS)}
            for node in monthly_nodes[side]:
                month_row = monthly.iloc[node["index"]]
                month_period = month_row.trade_date.to_period("M")
                in_month = daily.loc[daily.trade_date.dt.to_period("M") == month_period]
                field = "high" if side == "top" else "low"
                target = float(in_month[field].max() if side == "top" else in_month[field].min())
                peak_day = in_month.loc[in_month[field] == target].iloc[0]
                peak_date = str(peak_day.trade_date.date())
                week = peak_day.trade_date.to_period("W-FRI")
                week_row = weekly_periods.get(week)
                if week_row is None:
                    continue
                weekly_match = str(week_row.trade_date.date()) in weekly_nodes
                daily_match = peak_date in daily_nodes
                monthly_regime = _monthly_regime(
                    monthly, side, node, monthly_nodes["top"], monthly_nodes["bottom"],
                )
                retest_group = "retested_price_level" if node["retest_count"] else "single_price_level"
                for stage, row in (("monthly_structural_bar", month_row),
                                   ("weekly_bar_containing_monthly_extreme", week_row),
                                   ("daily_monthly_extreme", daily_dates[peak_date])):
                    rows.append({"code": str(code), "side": side, "monthly_regime": monthly_regime,
                                 "retest_group": retest_group, "retest_count": node["retest_count"], "stage": stage,
                                 "monthly_pivot_month": str(month_period), "peak_date": peak_date,
                                 "weekly_structural_match": weekly_match,
                                 "daily_structural_match": daily_match, "values": _snapshot(row)})
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["side"], row["monthly_regime"], row["retest_group"], row["stage"])].append(row)
    summary = [{"side": side, "monthly_regime": monthly_regime, "retest_group": retest_group, "stage": stage, **_summarize_role(items)}
               for (side, monthly_regime, retest_group, stage), items in sorted(groups.items())]
    return {"method": {
        "monthly_regime": "each peak is classified from only the preceding 18 months of local monthly swings; the entire available chart history is evaluated at every eligible month",
        "range": "at least two prior highs and two prior lows within 3% of their respective median levels, with support/resistance at least 6% apart",
        "range_breakout": "a top/bottom whose monthly close is at least 2% beyond the prior established range boundary",
        "trend": "the latest two monthly highs and lows both rise (uptrend) or both fall (downtrend); otherwise mixed_or_insufficient",
        "retested_price_level": "a same-side monthly swing within 18 months and within 3% in price; this is the double/triple or range-level axis, not a named-pattern label",
        "white_internal_nodes": "not a primary result group; internal turning points remain implicit in the pivot sequence",
        "monthly_pivot": "every local high/low across two completed months on each side, across the full available chart history; equal but separated highs/lows are retained",
        "weekly_daily_match": "reported for transparency only; monthly local pivots naturally tend to contain short-horizon pivots, so it is not used as the regime classifier",
        "warning": "This catalog does not yet label named head-and-shoulders, flag, wedge or triangle patterns. It first tests structural swing roles objectively.",
    }, "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
       "failures": failures, "summary": summary}
