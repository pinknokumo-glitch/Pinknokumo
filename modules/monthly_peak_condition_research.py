"""Describe indicators on all historical monthly local highs and lows only.

This is the first stage of the peak research.  It deliberately does not
calculate or report weekly or daily values: every indicator is calculated from
completed monthly OHLCV bars.  A local peak is retrospective, because two
following completed monthly bars are required to confirm it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from modules.multitimeframe_peak_research import _features, _resample, _snapshot, _summarize
from modules.structural_peak_research import _monthly_roles


def _is_at_most(value: Any, threshold: float) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(float(value) <= threshold)


def _is_at_least(value: Any, threshold: float) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(float(value) >= threshold)


def _condition_flags(row: pd.Series, side: str) -> dict[str, bool | None]:
    """Return descriptive monthly states, not an entry or exit rule."""
    lower = side == "bottom"
    at_limit = _is_at_most if lower else _is_at_least
    return {
        "rsi_9_extreme": at_limit(row.get("rsi_9_rakuten"), 30 if lower else 70),
        "rsi_14_extreme": at_limit(row.get("rsi_14_rakuten"), 30 if lower else 70),
        "rci_9_extreme": at_limit(row.get("rci_9"), -70 if lower else 70),
        "rci_27_extreme": at_limit(row.get("rci_27"), -70 if lower else 70),
        "stochastic_9_extreme": at_limit(row.get("stoch_k_9_3"), 20 if lower else 80),
        "stochastic_14_extreme": at_limit(row.get("stoch_k_14_3"), 20 if lower else 80),
        "psychological_12_extreme": at_limit(row.get("psychological_12"), 25 if lower else 75),
        "psychological_25_extreme": at_limit(row.get("psychological_25"), 25 if lower else 75),
        "sma_25_side": at_limit(row.get("price_vs_sma_25_percent"), 0),
        "sma_75_side": at_limit(row.get("price_vs_sma_75_percent"), 0),
        "sma_200_side": at_limit(row.get("price_vs_sma_200_percent"), 0),
        "volume_5_expanded": _is_at_least(row.get("volume_ratio_5"), 150),
        "volume_20_expanded": _is_at_least(row.get("volume_ratio_20"), 150),
        "volume_60_expanded": _is_at_least(row.get("volume_ratio_60"), 150),
        "bollinger_20_extreme": at_limit(row.get("bb_percent_b_20"), 0 if lower else 100),
        "bollinger_60_extreme": at_limit(row.get("bb_percent_b_60"), 0 if lower else 100),
        "ichimoku_cloud_side": at_limit(row.get("ichimoku_cloud_distance_percent"), 0),
        "tenkan_kijun_side": at_limit(row.get("ichimoku_tenkan_kijun_percent"), 0),
        "macd_5_25_9_side": at_limit(row.get("macd_histogram_5_25_9"), 0),
        "macd_12_26_9_side": at_limit(row.get("macd_histogram_12_26_9"), 0),
        "macd_25_75_14_side": at_limit(row.get("macd_histogram_25_75_14"), 0),
        "reversal_candle": bool(row.get("bullish_lower_wick", False)) if lower else bool(row.get("bearish_upper_wick", False)),
        "close_at_extreme": bool(row.get("close_near_low", False)) if lower else bool(row.get("close_near_high", False)),
    }


def _condition_rates(rows: list[dict[str, Any]]) -> dict[str, dict[str, int | float | None]]:
    keys = tuple(rows[0]["conditions"]) if rows else ()
    output: dict[str, dict[str, int | float | None]] = {}
    for key in keys:
        available = [row["conditions"][key] for row in rows if row["conditions"][key] is not None]
        count = sum(bool(value) for value in available)
        output[key] = {
            "available_count": len(available),
            "match_count": count,
            "match_rate_percent": round(100 * count / len(available), 2) if available else None,
        }
    return output


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {**_summarize(rows), "condition_rates": _condition_rates(rows)}


def analyze_monthly_peak_conditions(frames: dict[str, pd.DataFrame], indicator_config: dict) -> dict[str, Any]:
    """Summarize completed monthly conditions at every historic local high/low."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    failures: list[dict[str, str]] = []
    for code, prices in frames.items():
        try:
            # Aggregate raw OHLCV first.  Indicators are then calculated only
            # from the completed monthly bars, never from daily indicators.
            monthly = _features(_resample(prices, "ME"), indicator_config)
            nodes = {side: _monthly_roles(monthly, side) for side in ("bottom", "top")}
        except (KeyError, TypeError, ValueError) as error:
            failures.append({"code": str(code), "error": str(error)})
            continue

        pivot_indices = {node["index"] for side_nodes in nodes.values() for node in side_nodes}
        for side in ("bottom", "top"):
            peak_indices = {node["index"] for node in nodes[side]}
            for index, row in monthly.iterrows():
                group = "monthly_local_peak" if index in peak_indices else "monthly_nonpeak_bar"
                if group == "monthly_nonpeak_bar" and index in pivot_indices:
                    continue
                grouped[(side, group)].append({
                    "code": str(code),
                    "bar_date": str(row.trade_date.date()),
                    "values": _snapshot(row),
                    "conditions": _condition_flags(row, side),
                })

    summary = [
        {"side": side, "group": group, **_summary(rows)}
        for (side, group), rows in sorted(grouped.items())
    ]
    return {
        "method": {
            "scope": "monthly bars only; weekly and daily indicators are not calculated or included",
            "monthly_local_peak": "every local high or low over the full available chart history, confirmed by two completed monthly bars on each side",
            "monthly_nonpeak_bar": "monthly bars that are neither a local high nor a local low under the same rule",
            "indicator_parameters": "RSI 9/14; RCI 9/27; Stochastic 9/14; Psychological 12/25; SMA 25/75/200; volume 5/20/60; Bollinger 20/60; Ichimoku 9/26/52; MACD 5/25/9, 12/26/9, 25/75/14",
            "condition_rates": "descriptive threshold frequencies at confirmed monthly peaks versus non-peak monthly bars; they are not a combined trading rule",
            "availability": "the peak label is retrospective and is known only after two later monthly closes",
        },
        "universe_stock_count": len(frames),
        "usable_stock_count": len(frames) - len(failures),
        "failures": failures,
        "summary": summary,
    }
