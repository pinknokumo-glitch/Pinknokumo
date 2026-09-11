"""Descriptive research of daily conditions at confirmed monthly Dow swings.

This module labels historic swing dates with later monthly data only for
evaluation. Feature values always use data available on the swing date. It does
not create a trading signal or probability.
"""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

import pandas as pd

from modules.technical import TechnicalAnalyzer


FEATURES = (
    "rsi_14_rakuten", "rci_9", "rci_27", "stoch_k_14_3", "psychological_12",
    "price_vs_sma_25_percent", "price_vs_sma_75_percent", "volume_ratio_20",
    "bb_percent_b", "macd_histogram",
)


def normalize_adjusted_ohlcv(prices: pd.DataFrame) -> pd.DataFrame:
    """Normalize historic OHLC for splits using the supplied adjusted close.

    A long-horizon pivot study cannot treat a stock split as a price collapse.
    Missing or invalid adjustment data is rejected instead of silently using
    incompatible raw and adjusted price histories.
    """
    frame = prices.copy()
    if "adjusted_close" not in frame.columns:
        raise ValueError("Missing adjusted_close for long-horizon research")
    raw_close = pd.to_numeric(frame["close"], errors="raise")
    adjusted = pd.to_numeric(frame["adjusted_close"], errors="raise")
    ratio = adjusted / raw_close
    if not ratio.map(lambda value: math.isfinite(float(value)) and value > 0).all():
        raise ValueError("Invalid adjusted_close for long-horizon research")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise") * ratio
    # Split-adjusted volume avoids an artificial volume surge at a split.
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise") / ratio
    return frame


def _rci(close: pd.Series, period: int) -> pd.Series:
    """Rank-correlation index, +100 for a perfectly rising window."""
    def calculate(values: pd.Series) -> float:
        ranks = values.rank(method="average").to_numpy()
        dates = pd.Series(range(1, period + 1), dtype="float64").to_numpy()
        return float((1 - 6 * ((ranks - dates) ** 2).sum() / (period * (period**2 - 1))) * 100)
    return close.rolling(period, min_periods=period).apply(calculate, raw=False)


def daily_features(prices: pd.DataFrame, indicator_config: dict) -> pd.DataFrame:
    frame = normalize_adjusted_ohlcv(prices).sort_values("trade_date").reset_index(drop=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame.trade_date.duplicated().any() or len(frame) < 75:
        raise ValueError("Need at least 75 unique daily rows")
    calculated = TechnicalAnalyzer(indicator_config).calculate(frame)
    calculated["rci_9"] = _rci(calculated.close, 9)
    calculated["rci_27"] = _rci(calculated.close, 27)
    calculated["psychological_12"] = calculated.close.diff().gt(0).rolling(12, min_periods=12).mean() * 100
    body = (calculated.close - calculated.open).abs()
    span = calculated.high - calculated.low
    calculated["bullish_lower_wick"] = (calculated.close > calculated.open) & (
        (calculated[["open", "close"]].min(axis=1) - calculated.low) >= body.combine(span * .25, max)
    )
    calculated["bearish_upper_wick"] = (calculated.close < calculated.open) & (
        (calculated.high - calculated[["open", "close"]].max(axis=1)) >= body.combine(span * .25, max)
    )
    calculated["ma_uptrend"] = (calculated.sma_25 > calculated.sma_75) & (calculated.close > calculated.sma_75)
    calculated["ma_downtrend"] = (calculated.sma_25 < calculated.sma_75) & (calculated.close < calculated.sma_75)
    return calculated


def _monthly_swings(frame: pd.DataFrame) -> list[dict[str, Any]]:
    work = frame.copy()
    work["month"] = work.trade_date.dt.to_period("M")
    monthly = work.groupby("month", sort=True).agg(high=("high", "max"), low=("low", "min"))
    swings: list[dict[str, Any]] = []
    # Two complete calendar months on either side give the pivot a fixed,
    # documented confirmation delay. Last two months are never labelled.
    for i in range(2, len(monthly) - 2):
        window = monthly.iloc[i - 2:i + 3]
        for side, field in (("top", "high"), ("bottom", "low")):
            value = float(monthly.iloc[i][field])
            target = window[field].max() if side == "top" else window[field].min()
            if value != float(target) or list(window[field]).count(target) != 1:
                continue
            in_month = work.loc[work.month == monthly.index[i]]
            hit = in_month.loc[in_month[field] == value].iloc[0]
            prior_highs = [x for x in swings if x["side"] == "top" and x["month_index"] < i]
            prior_lows = [x for x in swings if x["side"] == "bottom" and x["month_index"] < i]
            trend = "mixed"
            if len(prior_highs) >= 2 and len(prior_lows) >= 2:
                rising = prior_highs[-1]["price"] > prior_highs[-2]["price"] and prior_lows[-1]["price"] > prior_lows[-2]["price"]
                falling = prior_highs[-1]["price"] < prior_highs[-2]["price"] and prior_lows[-1]["price"] < prior_lows[-2]["price"]
                trend = "uptrend" if rising else "downtrend" if falling else "mixed"
            prominence = monthly.iloc[max(0, i - 12):min(len(monthly), i + 13)][field]
            major = i >= 12 and i + 12 < len(monthly) and value == (prominence.max() if side == "top" else prominence.min())
            swings.append({"side": side, "month": str(monthly.index[i]), "month_index": i,
                           "date": str(hit.trade_date.date()), "price": value, "trend_before": trend,
                           "major": bool(major), "confirmed_on": str((monthly.index[i + 2] + 1).start_time.date())})
    return swings


def _conditions(row: pd.Series, side: str) -> dict[str, bool]:
    low = side == "bottom"
    return {
        "rsi_extreme": row.rsi_14_rakuten <= 30 if low else row.rsi_14_rakuten >= 70,
        "rci9_extreme": row.rci_9 <= -80 if low else row.rci_9 >= 80,
        "rci27_extreme": row.rci_27 <= -80 if low else row.rci_27 >= 80,
        "stochastic_extreme": row.stoch_k_14_3 <= 20 if low else row.stoch_k_14_3 >= 80,
        "psychological_extreme": row.psychological_12 <= 25 if low else row.psychological_12 >= 75,
        "ma_deviation_extreme": row.price_vs_sma_75_percent <= -10 if low else row.price_vs_sma_75_percent >= 10,
        "volume_surge": row.volume_ratio_20 >= 150,
        "reversal_candle": bool(row.bullish_lower_wick if low else row.bearish_upper_wick),
        "ma_trend": bool(row.ma_uptrend if low else row.ma_downtrend),
    }


def analyze_universe(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    pivot_rows, control_rows, failures = [], [], []
    for code, prices in frames.items():
        try:
            daily = daily_features(prices, indicator_config)
            swings = _monthly_swings(daily)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        pivot_dates = {s["date"] for s in swings}
        by_date = {str(row.trade_date.date()): row for _, row in daily.iterrows()}
        for swing in swings:
            row = by_date[swing["date"]]
            if any(pd.isna(row.get(name)) for name in FEATURES):
                continue
            pivot_rows.append({"code": str(code), **swing, "conditions": _conditions(row, swing["side"]),
                               "features": {name: float(row[name]) for name in FEATURES}})
        # Controls use every 20th eligible day, excluding actual pivot days.
        for i in range(75, len(daily), 20):
            row = daily.iloc[i]
            if str(row.trade_date.date()) in pivot_dates or any(pd.isna(row.get(name)) for name in FEATURES):
                continue
            for side in ("bottom", "top"):
                control_rows.append({"side": side, "conditions": _conditions(row, side)})
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in pivot_rows:
        groups[(row["side"], "all")].append(row)
        groups[(row["side"], "major" if row["major"] else "other")].append(row)
        groups[(row["side"], row["trend_before"])].append(row)
    controls: dict[str, list[dict]] = defaultdict(list)
    for row in control_rows:
        controls[row["side"]].append(row)
    summary = []
    for (side, group), rows in sorted(groups.items()):
        base = controls[side]
        rates = {}
        for condition in _conditions(pd.Series({name: 0 for name in FEATURES} | {"bullish_lower_wick": False, "bearish_upper_wick": False, "ma_uptrend": False, "ma_downtrend": False}), side):
            count = sum(bool(row["conditions"][condition]) for row in rows)
            base_count = sum(bool(row["conditions"][condition]) for row in base)
            rate, base_rate = count / len(rows), base_count / len(base) if base else None
            rates[condition] = {"count": count, "rate_percent": round(rate * 100, 2),
                                "control_rate_percent": round(base_rate * 100, 2) if base_rate is not None else None,
                                "descriptive_lift": round(rate / base_rate, 2) if base_rate not in (None, 0) else None}
        summary.append({"side": side, "group": group, "pivot_count": len(rows),
                        "stock_count": len({row["code"] for row in rows}), "conditions": rates})
    return {"method": {"monthly_pivot": "unique 5-month high/low, two months either side",
                       "major": "unique 25-month extreme, twelve months either side",
                       "features": list(FEATURES), "control": "every 20th eligible non-pivot day"},
            "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
            "failures": failures, "pivots": pivot_rows, "summary": summary}
