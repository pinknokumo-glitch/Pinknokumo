"""Research complete daily exhaustion confluence away from monthly pivot months.

This is retrospective validation only.  It separates daily five-condition
confluence that occurs in a confirmed monthly pivot month from the same
confluence in all other months, and reports the prior completed-month regime.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from modules.complete_condition_precision import HORIZON, _available_mask, _outcome, _profile_mask
from modules.multitimeframe_peak_research import _features, _resample, _snapshot, _summarize
from modules.structural_peak_research import _monthly_regime, _monthly_roles


FUTURE_PIVOT_SESSIONS = 60


def _future_pivot_within(index: int, pivot_positions: set[int]) -> bool:
    """Return whether a same-side actual monthly extreme occurs in the next 60 sessions."""
    return any(index < position <= index + FUTURE_PIVOT_SESSIONS for position in pivot_positions)


def _monthly_peak_positions(
    daily: pd.DataFrame, monthly: pd.DataFrame, nodes: list[dict[str, Any]], side: str,
) -> tuple[set[pd.Period], set[int]]:
    """Return pivot months and dates of the actual daily high/low that set them."""
    dates_to_position = {str(row.trade_date.date()): index for index, row in daily.iterrows()}
    months: set[pd.Period] = set()
    positions: set[int] = set()
    field = "high" if side == "top" else "low"
    for node in nodes:
        period = monthly.iloc[node["index"]].trade_date.to_period("M")
        in_month = daily.loc[daily.trade_date.dt.to_period("M") == period]
        target = float(in_month[field].max() if side == "top" else in_month[field].min())
        date = str(in_month.loc[in_month[field] == target].iloc[0].trade_date.date())
        position = dates_to_position.get(date)
        if position is not None:
            months.add(period)
            positions.add(position)
    return months, positions


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = _summarize(rows)
    count = len(rows)
    if not count:
        return result | {
            "future_same_side_monthly_pivot_within_60_sessions_rate_percent": None,
            "win_rate_percent": None,
            "mean_20_session_return_percent": None,
            "mean_adverse_percent": None,
            "continued_against_signal_5_percent_rate": None,
        }
    return result | {
        "future_same_side_monthly_pivot_within_60_sessions_rate_percent": round(
            100 * sum(row["future_same_side_monthly_pivot_within_60_sessions"] for row in rows) / count, 3,
        ),
        "win_rate_percent": round(100 * sum(row["outcome"]["terminal_return_percent"] > 0 for row in rows) / count, 3),
        "mean_20_session_return_percent": round(
            sum(float(row["outcome"]["terminal_return_percent"]) for row in rows) / count, 3,
        ),
        "mean_adverse_percent": round(sum(float(row["outcome"]["adverse_percent"]) for row in rows) / count, 3),
        "continued_against_signal_5_percent_rate": round(
            100 * sum(row["outcome"]["continued_against_signal_5_percent"] for row in rows) / count, 3,
        ),
    }


def analyze_nonpeak_confluence(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    """Compare complete daily confluence in confirmed monthly-pivot and non-pivot months."""
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for code, prices in frames.items():
        try:
            daily = _features(prices, indicator_config)
            monthly = _features(
                _resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "ME"),
                indicator_config,
            )
            nodes = {side: _monthly_roles(monthly, side) for side in ("top", "bottom")}
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        pivot_months: set[pd.Period] = set()
        pivot_positions: dict[str, set[int]] = {}
        for side in ("top", "bottom"):
            months, positions = _monthly_peak_positions(daily, monthly, nodes[side], side)
            pivot_months.update(months)
            pivot_positions[side] = positions
        monthly_index = {row.trade_date.to_period("M"): index for index, row in monthly.iterrows()}
        available = _available_mask(daily)
        for side in ("bottom", "top"):
            profile = _profile_mask(daily, side)
            for index in range(len(daily) - HORIZON):
                if not bool(available.iloc[index]) or not bool(profile.iloc[index]):
                    continue
                period = daily.iloc[index].trade_date.to_period("M")
                completed_index = monthly_index.get(period, 0) - 1
                if completed_index < 0:
                    prior_regime = "mixed_or_insufficient"
                else:
                    prior_regime = _monthly_regime(
                        monthly, side, {"index": completed_index}, nodes["top"], nodes["bottom"],
                    )
                location = "monthly_pivot_month" if period in pivot_months else "monthly_nonpeak_month"
                rows.append({
                    "code": str(code), "side": side, "location": location,
                    "prior_completed_month_regime": prior_regime,
                    "future_same_side_monthly_pivot_within_60_sessions": _future_pivot_within(index, pivot_positions[side]),
                    "outcome": _outcome(daily, index, side), "values": _snapshot(daily.iloc[index]),
                })
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["side"], row["location"], row["prior_completed_month_regime"])].append(row)
    summary = [
        {"side": side, "location": location, "prior_completed_month_regime": regime, **_summary(items)}
        for (side, location, regime), items in sorted(groups.items())
    ]
    return {
        "method": {
            "core_confluence": {
                "bottom": "RSI14<=30 AND RCI9<=-70 AND Stochastic14<=20 AND price_vs_SMA75<=-10% AND volume>=150% of 20-day average",
                "top": "RSI14>=70 AND RCI9>=70 AND Stochastic14>=80 AND price_vs_SMA75>=10% AND volume>=150% of 20-day average",
            },
            "monthly_nonpeak_month": "the daily signal's calendar month is not a confirmed local monthly top or bottom month",
            "prior_completed_month_regime": "range/trend classification uses only the monthly bars completed before the signal month",
            "future_pivot": "for retrospective context only: actual same-side confirmed monthly pivot within the following 60 trading sessions",
            "additional_indicators": "Bollinger, Ichimoku, MACD, psychological, and candlestick metrics are reported as distributions, not added as arbitrary mandatory gates",
            "future_outcome": "entry at next session open and exit after 20 sessions; top-side return is calculated as a short sale",
            "warning": "Confirmed monthly-pivot labels and future-pivot rates require later data. This output is research, not a live trading signal.",
        },
        "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
        "failures": failures, "summary": summary,
    }
