"""Research structural red/yellow swing roles across monthly, weekly and daily bars.

This is a descriptive research classifier, not a live chart-pattern signal.
It uses every available monthly local swing, then separates multi-timeframe
red candidates from yellow secondary/range candidates without a fixed
long-horizon cutoff.
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
        for side in ("top", "bottom"):
            weekly_nodes = {node["date"] for node in _pivots(weekly, side, WEEKLY_RADIUS)}
            daily_nodes = {node["date"] for node in _pivots(daily, side, DAILY_RADIUS)}
            for node in _monthly_roles(monthly, side):
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
                role = "red_multitimeframe" if weekly_match and daily_match else "yellow_secondary"
                retest_group = "retested_price_level" if node["retest_count"] else "single_price_level"
                for stage, row in (("monthly_structural_bar", month_row),
                                   ("weekly_bar_containing_monthly_extreme", week_row),
                                   ("daily_monthly_extreme", daily_dates[peak_date])):
                    rows.append({"code": str(code), "side": side, "role": role,
                                 "retest_group": retest_group, "retest_count": node["retest_count"], "stage": stage,
                                 "monthly_pivot_month": str(month_period), "peak_date": peak_date,
                                 "weekly_structural_match": weekly_match,
                                 "daily_structural_match": daily_match, "values": _snapshot(row)})
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["side"], row["role"], row["retest_group"], row["stage"])].append(row)
    summary = [{"side": side, "role": role, "retest_group": retest_group, "stage": stage, **_summarize_role(items)}
               for (side, role, retest_group, stage), items in sorted(groups.items())]
    return {"method": {
        "red_multitimeframe": "every monthly local swing whose actual extreme is also a same-side weekly and daily local swing",
        "yellow_secondary": "every other monthly local swing; used as the range/shoulder/partial-alignment comparison group",
        "retested_price_level": "a same-side monthly swing within 18 months and within 3% in price; this is the double/triple or range-level axis, not a named-pattern label",
        "white_internal_nodes": "not a primary result group; internal turning points remain implicit in the pivot sequence",
        "monthly_pivot": "every local high/low across two completed months on each side, across the full available chart history; equal but separated highs/lows are retained",
        "weekly_daily_match": "whether the weekly/daily bar containing the actual monthly high/low is itself a local pivot using two weeks/five sessions on each side",
        "warning": "This catalog does not yet label named head-and-shoulders, flag, wedge or triangle patterns. It first tests structural swing roles objectively.",
    }, "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
       "failures": failures, "summary": summary}
