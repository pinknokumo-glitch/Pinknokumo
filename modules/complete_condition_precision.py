"""Validate whether complete daily exhaustion conditions occur only at Dow peaks.

The conditions are evaluated using the signal day's data only.  Future monthly
bars are used solely to label historic pivots for this research report; this
module never produces an app signal.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from modules.dow_peak_forecast_validation import HORIZON, _period
from modules.dow_peak_research import _monthly_swings, daily_features


NEAR_SESSIONS = 3
REQUIRED_COLUMNS = (
    "rsi_14_rakuten", "rci_9", "stoch_k_14_3",
    "price_vs_sma_75_percent", "volume_ratio_20",
)


def _available_mask(frame: pd.DataFrame) -> pd.Series:
    """Return bars that can fairly be compared with the five-condition profile."""
    return frame.loc[:, REQUIRED_COLUMNS].notna().all(axis=1)


def _profile_mask(frame: pd.DataFrame, side: str) -> pd.Series:
    """Return the agreed five-condition profile without any future data."""
    available = _available_mask(frame)
    if side == "bottom":
        matched = (
            (frame.rsi_14_rakuten <= 30)
            & (frame.rci_9 <= -70)
            & (frame.stoch_k_14_3 <= 20)
            & (frame.price_vs_sma_75_percent <= -10)
            & (frame.volume_ratio_20 >= 150)
        )
    else:
        matched = (
            (frame.rsi_14_rakuten >= 70)
            & (frame.rci_9 >= 70)
            & (frame.stoch_k_14_3 >= 80)
            & (frame.price_vs_sma_75_percent >= 10)
            & (frame.volume_ratio_20 >= 150)
        )
    return available & matched


def _major_research_window(frame: pd.DataFrame) -> pd.Series:
    """Keep only dates for which a 25-month pivot label could be known later."""
    periods = frame.trade_date.dt.to_period("M")
    ordered = sorted(periods.unique())
    if len(ordered) < 25:
        return pd.Series(False, index=frame.index)
    return (periods >= ordered[12]) & (periods <= ordered[-13])


def _near_dates(frame: pd.DataFrame, dates: set[str]) -> set[str]:
    positions = {str(value.date()): index for index, value in enumerate(frame.trade_date)}
    output: set[str] = set()
    for date in dates:
        index = positions.get(date)
        if index is None:
            continue
        for candidate in range(max(0, index - NEAR_SESSIONS), min(len(frame), index + NEAR_SESSIONS + 1)):
            output.add(str(frame.iloc[candidate].trade_date.date()))
    return output


def _outcome(frame: pd.DataFrame, index: int, side: str) -> dict[str, float | bool]:
    signal, entry, exit_row = frame.iloc[index], frame.iloc[index + 1], frame.iloc[index + HORIZON]
    future = frame.iloc[index:index + HORIZON + 1]
    entry_open = float(entry.open)
    if side == "bottom":
        terminal = (float(exit_row.close) / entry_open - 1) * 100
        adverse = min(0.0, (float(future.low.min()) / entry_open - 1) * 100)
        continued = float(future.low.min()) < float(signal.close) * .95
    else:
        terminal = (entry_open / float(exit_row.close) - 1) * 100
        adverse = min(0.0, (1 - float(future.high.max()) / entry_open) * 100)
        continued = float(future.high.max()) > float(signal.close) * 1.05
    return {"terminal_return_percent": terminal, "adverse_percent": adverse,
            "continued_against_signal_5_percent": bool(continued)}


def _empty() -> dict[str, Any]:
    return {"candidate_count": 0, "codes": set(), "monthly_exact": 0,
            "monthly_near": 0, "major_exact": 0, "major_near": 0,
            "terminal_return_sum": 0.0, "wins": 0, "adverse_sum": 0.0,
            "continued": 0}


def _add(bucket: dict[str, Any], code: str, labels: dict[str, bool], outcome: dict[str, float | bool]) -> None:
    bucket["candidate_count"] += 1
    bucket["codes"].add(code)
    bucket["monthly_exact"] += int(labels["monthly_exact"])
    bucket["monthly_near"] += int(labels["monthly_near"])
    bucket["major_exact"] += int(labels["major_exact"])
    bucket["major_near"] += int(labels["major_near"])
    bucket["terminal_return_sum"] += float(outcome["terminal_return_percent"])
    bucket["wins"] += int(float(outcome["terminal_return_percent"]) > 0)
    bucket["adverse_sum"] += float(outcome["adverse_percent"])
    bucket["continued"] += int(outcome["continued_against_signal_5_percent"])


def _summary(bucket: dict[str, Any]) -> dict[str, Any]:
    count = bucket["candidate_count"]
    base = {"candidate_count": count, "stock_count": len(bucket["codes"])}
    if not count:
        return base | {name: None for name in (
            "monthly_pivot_exact_rate_percent", "monthly_pivot_within_3_sessions_rate_percent",
            "major_pivot_exact_rate_percent", "major_pivot_within_3_sessions_rate_percent",
            "non_monthly_pivot_count", "win_rate_percent", "mean_terminal_return_percent",
            "mean_adverse_percent", "continued_against_signal_5_percent_rate")}
    rate = lambda value: round(100 * value / count, 3)
    return base | {
        "monthly_pivot_exact_rate_percent": rate(bucket["monthly_exact"]),
        "monthly_pivot_within_3_sessions_rate_percent": rate(bucket["monthly_near"]),
        "major_pivot_exact_rate_percent": rate(bucket["major_exact"]),
        "major_pivot_within_3_sessions_rate_percent": rate(bucket["major_near"]),
        "non_monthly_pivot_count": count - bucket["monthly_exact"],
        "win_rate_percent": rate(bucket["wins"]),
        "mean_terminal_return_percent": round(bucket["terminal_return_sum"] / count, 3),
        "mean_adverse_percent": round(bucket["adverse_sum"] / count, 3),
        "continued_against_signal_5_percent_rate": rate(bucket["continued"]),
    }


def validate_complete_conditions(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(_empty)
    failures: list[dict[str, str]] = []
    for code, prices in frames.items():
        try:
            daily = daily_features(prices, indicator_config)
            window = _major_research_window(daily)
            swings = _monthly_swings(daily)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        for side in ("bottom", "top"):
            side_swings = [item for item in swings if item["side"] == side]
            dates = {item["date"] for item in side_swings}
            major_dates = {item["date"] for item in side_swings if item["major"]}
            near_dates = _near_dates(daily, dates)
            major_near_dates = _near_dates(daily, major_dates)
            available = _available_mask(daily)
            profile = _profile_mask(daily, side)
            for index in range(len(daily) - HORIZON):
                if not bool(window.iloc[index]) or not bool(available.iloc[index]):
                    continue
                date = str(daily.iloc[index].trade_date.date())
                period = _period(pd.Timestamp(daily.iloc[index].trade_date), pd.Timestamp(daily.iloc[index + HORIZON].trade_date))
                if period is None:
                    continue
                labels = {"monthly_exact": date in dates, "monthly_near": date in near_dates,
                          "major_exact": date in major_dates, "major_near": date in major_near_dates}
                outcome = _outcome(daily, index, side)
                _add(buckets[(period, side, "eligible_day_baseline")], str(code), labels, outcome)
                if bool(profile.iloc[index]):
                    _add(buckets[(period, side, "complete_five_condition_profile")], str(code), labels, outcome)
    summary = []
    for period, side in sorted({(period, side) for period, side, _ in buckets}):
        baseline = _summary(buckets[(period, side, "eligible_day_baseline")])
        for profile in ("eligible_day_baseline", "complete_five_condition_profile"):
            row = _summary(buckets[(period, side, profile)])
            for field in ("monthly_pivot_exact_rate_percent", "monthly_pivot_within_3_sessions_rate_percent",
                          "major_pivot_exact_rate_percent", "major_pivot_within_3_sessions_rate_percent"):
                value, base = row[field], baseline[field]
                row[f"{field}_lift_vs_baseline"] = round(value / base, 3) if value is not None and base not in (None, 0) else None
            summary.append({"period": period, "side": side, "profile": profile, **row})
    return {"method": {
        "conditions": {
            "bottom": "RSI14<=30 AND RCI9<=-70 AND Stochastic14<=20 AND price_vs_SMA75<=-10% AND volume>=150% of 20-day average",
            "top": "RSI14>=70 AND RCI9>=70 AND Stochastic14>=80 AND price_vs_SMA75>=10% AND volume>=150% of 20-day average",
        },
        "evaluation_universe": "every eligible daily bar with all five indicators available, excluding the first and last 12 calendar months needed to label a 25-month major pivot",
        "monthly_pivot": "unique five-month high/low; exact means the signal day is the historic extreme",
        "major_pivot": "unique 25-month high/low; exact means the signal day is the historic extreme",
        "near_peak": "within three trading sessions of the historic pivot date, for practical timing analysis only",
        "future_outcome": "entry at next session open, exit at 20th following session close; short-side returns are calculated as a short sale",
        "warning": "This is retrospective validation, not a live trading signal. Pivot labels require future bars and are used only after the fact.",
    }, "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
       "failures": failures, "summary": summary}
