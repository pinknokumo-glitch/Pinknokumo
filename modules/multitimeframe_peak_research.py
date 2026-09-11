"""Describe indicator distributions across nested monthly, weekly and daily peaks.

The output is historical research. A monthly or weekly bar is only complete at
its close, so each row includes its stage rather than pretending it was an
intrabar real-time signal.
"""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

import pandas as pd

from modules.dow_peak_research import _monthly_swings, _rci, normalize_adjusted_ohlcv
from modules.technical import TechnicalAnalyzer


NUMERIC_METRICS = (
    "rsi_9_rakuten", "rsi_14_rakuten", "rci_9", "rci_27", "stoch_k_9_3", "stoch_k_14_3",
    "psychological_12", "psychological_25", "price_vs_sma_25_percent",
    "price_vs_sma_75_percent", "price_vs_sma_200_percent", "volume_ratio_5",
    "volume_ratio_20", "volume_ratio_60", "bb_percent_b_20", "bb_percent_b_60",
    "bb_width_percent_20", "ichimoku_tenkan_kijun_percent", "ichimoku_cloud_distance_percent",
    "atr_14_percent", "macd_histogram_5_25_9", "macd_histogram_12_26_9", "macd_histogram_25_75_14",
)
BOOLEAN_METRICS = ("bullish_lower_wick", "bearish_upper_wick", "long_body",
                   "close_near_high", "close_near_low")
SECTOR_METRICS = ("rsi_14_rakuten", "rci_9", "stoch_k_14_3", "price_vs_sma_75_percent", "volume_ratio_20")


def _features(prices: pd.DataFrame, indicator_config: dict) -> pd.DataFrame:
    frame = normalize_adjusted_ohlcv(prices).sort_values("trade_date").reset_index(drop=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    calculated = TechnicalAnalyzer(indicator_config).calculate(frame)
    calculated["rci_9"] = _rci(calculated.close, 9)
    calculated["rci_27"] = _rci(calculated.close, 27)
    calculated["psychological_12"] = calculated.close.diff().gt(0).rolling(12, min_periods=12).mean() * 100
    calculated["psychological_25"] = calculated.close.diff().gt(0).rolling(25, min_periods=25).mean() * 100
    for period in (5, 20, 60):
        calculated[f"volume_ratio_{period}"] = calculated.volume / calculated.volume.rolling(period, min_periods=period).mean() * 100
    for period in (20, 60):
        middle = calculated.close.rolling(period, min_periods=period).mean()
        std = calculated.close.rolling(period, min_periods=period).std()
        upper, lower = middle + 2 * std, middle - 2 * std
        width = (upper - lower).replace(0, pd.NA)
        calculated[f"bb_percent_b_{period}"] = (calculated.close - lower) / width * 100
        calculated[f"bb_width_percent_{period}"] = width / middle * 100
    tenkan = (calculated.high.rolling(9, min_periods=9).max() + calculated.low.rolling(9, min_periods=9).min()) / 2
    kijun = (calculated.high.rolling(26, min_periods=26).max() + calculated.low.rolling(26, min_periods=26).min()) / 2
    span_a = (tenkan + kijun) / 2
    span_b = (calculated.high.rolling(52, min_periods=52).max() + calculated.low.rolling(52, min_periods=52).min()) / 2
    calculated["ichimoku_tenkan_kijun_percent"] = (tenkan / kijun - 1) * 100
    cloud_top, cloud_bottom = pd.concat([span_a, span_b], axis=1).max(axis=1), pd.concat([span_a, span_b], axis=1).min(axis=1)
    # Signed distance to the cloud: positive above, negative below, zero inside.
    cloud_distance = pd.Series(0.0, index=calculated.index)
    cloud_distance = cloud_distance.mask(calculated.close > cloud_top, (calculated.close / cloud_top - 1) * 100)
    cloud_distance = cloud_distance.mask(calculated.close < cloud_bottom, (calculated.close / cloud_bottom - 1) * 100)
    calculated["ichimoku_cloud_distance_percent"] = cloud_distance
    body, span = (calculated.close - calculated.open).abs(), calculated.high - calculated.low
    calculated["bullish_lower_wick"] = (calculated.close > calculated.open) & ((calculated[["open", "close"]].min(axis=1) - calculated.low) >= body.combine(span * .25, max))
    calculated["bearish_upper_wick"] = (calculated.close < calculated.open) & ((calculated.high - calculated[["open", "close"]].max(axis=1)) >= body.combine(span * .25, max))
    calculated["long_body"] = body >= span * .6
    calculated["close_near_high"] = (calculated.high - calculated.close) <= span * .2
    calculated["close_near_low"] = (calculated.close - calculated.low) <= span * .2
    return calculated


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    indexed = frame.set_index("trade_date")
    output = indexed.resample(rule).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    output = output.dropna(subset=["open", "high", "low", "close"]).reset_index()
    output["adjusted_close"] = output["close"]
    return output


def _snapshot(row: pd.Series) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in NUMERIC_METRICS:
        value = row.get(name)
        values[name] = float(value) if value is not None and pd.notna(value) and math.isfinite(float(value)) else None
    for name in BOOLEAN_METRICS:
        values[name] = bool(row.get(name, False))
    return values


def _summarize(rows: list[dict[str, Any]], metrics: tuple[str, ...] = NUMERIC_METRICS) -> dict[str, Any]:
    output: dict[str, Any] = {"sample_count": len(rows), "stock_count": len({row["code"] for row in rows})}
    for name in metrics:
        values = [row["values"][name] for row in rows if row["values"].get(name) is not None]
        if values:
            series = pd.Series(values)
            output[name] = {"count": len(values), "median": round(float(series.median()), 3),
                            "p25": round(float(series.quantile(.25)), 3), "p75": round(float(series.quantile(.75)), 3)}
        else:
            output[name] = {"count": 0, "median": None, "p25": None, "p75": None}
    for name in BOOLEAN_METRICS:
        values = [bool(row["values"].get(name)) for row in rows]
        output[name] = {"count": len(values), "true_rate_percent": round(100 * sum(values) / len(values), 2) if values else None}
    return output


def _participation(rows: list[dict[str, Any]]) -> dict[str, int]:
    buckets = {"contracted_under_80": 0, "normal_80_to_under_150": 0, "expanded_150_or_more": 0, "unavailable": 0}
    for row in rows:
        value = row["values"].get("volume_ratio_20")
        key = "unavailable" if value is None else "contracted_under_80" if value < 80 else "normal_80_to_under_150" if value < 150 else "expanded_150_or_more"
        buckets[key] += 1
    return buckets


def analyze_nested_peaks(frames: dict[str, pd.DataFrame], sectors: dict[str, str], indicator_config: dict) -> dict[str, Any]:
    rows, failures = [], []
    for code, prices in frames.items():
        try:
            daily = _features(prices, indicator_config)
            weekly = _features(_resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "W-FRI"), indicator_config)
            monthly = _features(_resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "ME"), indicator_config)
            swings = _monthly_swings(daily)
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue
        weekly_by_period = {row.trade_date.to_period("W-FRI"): row for _, row in weekly.iterrows()}
        monthly_by_period = {row.trade_date.to_period("M"): row for _, row in monthly.iterrows()}
        daily_by_date = {str(row.trade_date.date()): row for _, row in daily.iterrows()}
        for swing in swings:
            day = daily_by_date.get(swing["date"])
            month = pd.Period(swing["month"], freq="M")
            week = pd.Timestamp(swing["date"]).to_period("W-FRI")
            for stage, row in (("monthly_peak_bar", monthly_by_period.get(month)),
                               ("weekly_peak_bar", weekly_by_period.get(week)),
                               ("daily_peak_bar", day)):
                if row is None:
                    continue
                rows.append({"code": str(code), "sector_33_name": sectors.get(str(code), "未分類"),
                             "side": swing["side"], "major": bool(swing["major"]), "stage": stage,
                             "monthly_pivot_month": swing["month"], "daily_peak_date": swing["date"],
                             "bar_date": str(row.trade_date.date()), "values": _snapshot(row)})
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for scope in ("all", "major" if row["major"] else "other"):
            grouped[(row["side"], row["stage"], scope)].append(row)
    summary = [{"side": side, "stage": stage, "scope": scope, "participation_proxy": _participation(items), **_summarize(items)}
               for (side, stage, scope), items in sorted(grouped.items())]
    sector_summary = []
    for (side, stage, scope), items in sorted(grouped.items()):
        if scope != "all":
            continue
        by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_sector[item["sector_33_name"]].append(item)
        for sector, sector_rows in sorted(by_sector.items()):
            if len(sector_rows) >= 30:
                sector_summary.append({"side": side, "stage": stage, "sector_33_name": sector,
                                       **_summarize(sector_rows, SECTOR_METRICS)})
    return {"method": {
        "monthly_dow_pivot": "unique five-month high/low; confirmed after two following months",
        "major": "unique 25-month high/low; descriptive classification only",
        "nested_bars": "weekly and daily rows contain the actual daily extreme that set the monthly pivot",
        "timeframe_availability": "monthly and weekly values are complete only after their respective bar closes",
        "supply_demand_proxy": "volume ratio versus its 20-bar average; no order-book, credit balance, float, or shares-outstanding data is used",
        "short_long_parameters": "RSI 9/14; RCI 9/27; Stochastic 9/14; Psychological 12/25; SMA 25/75/200; volume 5/20/60; Bollinger 20/60; Ichimoku 9/26/52",
        "summary_statistics": "count, median, p25 and p75 are descriptive distributions, not a predictive rule",
        "major_observations": "one compact observation per bar for 25-month major pivots; retained for later combination research",
    }, "universe_stock_count": len(frames), "usable_stock_count": len(frames) - len(failures),
       "failures": failures, "summary": summary, "sector_summary": sector_summary,
       "major_observations": [row for row in rows if row["major"]]}
