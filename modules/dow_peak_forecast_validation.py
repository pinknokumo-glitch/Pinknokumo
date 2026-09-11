"""Forward-only validation of fixed daily exhaustion profiles.

The historic Dow-pivot report is descriptive. This module instead samples dates
without using later prices to choose a signal, then measures the following 20
sessions. It is research-only and deliberately separate from app delivery.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from modules.dow_peak_research import _conditions, _monthly_swings, daily_features


HORIZON = 20
SAMPLE_INTERVAL = 21


def _known_monthly_trend(swings: list[dict[str, Any],], date: pd.Timestamp) -> str:
    """Return a Dow state using pivots confirmed before this trading date."""
    known = [row for row in swings if pd.Timestamp(row["confirmed_on"]) <= date]
    highs = [row for row in known if row["side"] == "top"]
    lows = [row for row in known if row["side"] == "bottom"]
    if len(highs) < 2 or len(lows) < 2:
        return "unavailable"
    rising = highs[-1]["price"] > highs[-2]["price"] and lows[-1]["price"] > lows[-2]["price"]
    falling = highs[-1]["price"] < highs[-2]["price"] and lows[-1]["price"] < lows[-2]["price"]
    return "uptrend" if rising else "downtrend" if falling else "mixed"


def _profile_matches(row: pd.Series, side: str, monthly_trend: str) -> dict[str, bool]:
    conditions = _conditions(row, side)
    if side == "bottom":
        core = monthly_trend in {"downtrend", "mixed"} and all(conditions[name] for name in (
            "rsi_extreme", "rci9_extreme", "stochastic_extreme", "ma_deviation_extreme", "volume_surge"))
    else:
        core = monthly_trend in {"uptrend", "mixed"} and all(conditions[name] for name in (
            "rsi_extreme", "rci9_extreme", "ma_deviation_extreme", "volume_surge"))
    return {
        "core_exhaustion_profile": core,
        "oscillator_confluence_profile": core and all(conditions[name] for name in (
            "rci27_extreme", "stochastic_extreme", "psychological_extreme")),
    }


def _period(signal_date: pd.Timestamp, end_date: pd.Timestamp) -> str | None:
    if end_date <= pd.Timestamp("2021-12-31"):
        return "development_to_2021"
    if signal_date >= pd.Timestamp("2022-01-01") and end_date <= pd.Timestamp("2023-12-31"):
        return "validation_2022_2023"
    if signal_date >= pd.Timestamp("2024-01-01"):
        return "late_period_2024_onward"
    return None


def _outcome(frame: pd.DataFrame, index: int, side: str) -> dict[str, float | bool | str]:
    signal = frame.iloc[index]
    future = frame.iloc[index:index + HORIZON + 1]
    entry = frame.iloc[index + 1]
    exit_row = frame.iloc[index + HORIZON]
    close, entry_open = float(signal.close), float(entry.open)
    if side == "bottom":
        future_extreme = float(future.low.min())
        near_extreme = close <= future_extreme * 1.03
        terminal_return = (float(exit_row.close) / entry_open - 1) * 100
        adverse = min(0.0, (future.low.min() / entry_open - 1) * 100)
    else:
        future_extreme = float(future.high.max())
        near_extreme = future_extreme <= close * 1.03
        terminal_return = (entry_open / float(exit_row.close) - 1) * 100
        adverse = min(0.0, (1 - future.high.max() / entry_open) * 100)
    return {"signal_date": str(signal.trade_date.date()), "end_date": str(exit_row.trade_date.date()),
            "near_extreme": bool(near_extreme), "terminal_return_percent": float(terminal_return),
            "adverse_percent": float(adverse)}


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"sample_count": 0, "stock_count": 0, "near_extreme_rate_percent": None,
                "win_rate_percent": None, "mean_return_percent": None, "mean_adverse_percent": None}
    return {"sample_count": len(rows), "stock_count": len({row["code"] for row in rows}),
            "near_extreme_rate_percent": round(100 * sum(row["near_extreme"] for row in rows) / len(rows), 2),
            "win_rate_percent": round(100 * sum(row["terminal_return_percent"] > 0 for row in rows) / len(rows), 2),
            "mean_return_percent": round(sum(row["terminal_return_percent"] for row in rows) / len(rows), 3),
            "mean_adverse_percent": round(sum(row["adverse_percent"] for row in rows) / len(rows), 3)}


def validate_universe(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    samples: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    failures = []
    for code, prices in frames.items():
        try:
            daily = daily_features(prices, indicator_config)
            swings = _monthly_swings(daily)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        for index in range(75, len(daily) - HORIZON, SAMPLE_INTERVAL):
            row = daily.iloc[index]
            date = pd.Timestamp(row.trade_date)
            period = _period(date, pd.Timestamp(daily.iloc[index + HORIZON].trade_date))
            trend = _known_monthly_trend(swings, date)
            if period is None or trend == "unavailable":
                continue
            for side in ("bottom", "top"):
                # The baseline has the same known monthly-regime gate as the profile.
                gate = trend in ({"downtrend", "mixed"} if side == "bottom" else {"uptrend", "mixed"})
                if not gate:
                    continue
                outcome = _outcome(daily, index, side)
                base_row = {"code": str(code), "monthly_trend": trend, **outcome}
                samples[(period, side, "monthly_regime_baseline")].append(base_row)
                for profile, matches in _profile_matches(row, side, trend).items():
                    if matches:
                        samples[(period, side, profile)].append(base_row)
    summary = []
    profiles = ("monthly_regime_baseline", "core_exhaustion_profile", "oscillator_confluence_profile")
    periods_and_sides = sorted({(period, side) for period, side, _ in samples})
    for period, side in periods_and_sides:
        for profile in profiles:
            summary.append({"period": period, "side": side, "profile": profile,
                            **_summarize(samples[(period, side, profile)])})
    return {"method": {
        "horizon_sessions": HORIZON, "sample_interval_sessions": SAMPLE_INTERVAL,
        "near_extreme": "signal close is within 3% of the lowest/highest price from signal day through the next 20 sessions",
        "entry": "next session open", "exit": "20th following session close",
        "profiles": {
            "core_bottom": "monthly downtrend/mixed + RSI14<=30 + RCI9<=-80 + Stoch14<=20 + price_vs_SMA75<=-10% + volume>=150% of 20-day average",
            "core_top": "monthly uptrend/mixed + RSI14>=70 + RCI9>=80 + price_vs_SMA75>=10% + volume>=150% of 20-day average",
            "oscillator_confluence": "core profile + RCI27 extreme + Stoch14 extreme + Psychological12 extreme",
        },
        "time_splits": "development through 2021; validation 2022-2023; late period 2024 onward. Profiles were informed by earlier descriptive research, so this reduces but does not eliminate selection bias.",
    }, "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
       "failures": failures, "summary": summary}
