"""Derive comparable financial ratios from the latest disclosed financial record."""
from __future__ import annotations

from collections.abc import Mapping


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: object, denominator: object) -> float | None:
    top, bottom = _number(numerator), _number(denominator)
    return top / bottom * 100 if top is not None and bottom not in (None, 0) else None


class FundamentalAnalyzer:
    def latest_values(self, financial: Mapping[str, object], close: object, trailing_dividends: object = None) -> dict[str, float]:
        values: dict[str, float] = {}
        eps, bps, price = _number(financial.get("earnings_per_share")), _number(financial.get("book_value_per_share")), _number(close)
        if price is not None and eps not in (None, 0):
            values["per"] = price / eps
        if price is not None and bps not in (None, 0):
            values["pbr"] = price / bps
        for name, numerator, denominator in (
            ("roe", financial.get("profit"), financial.get("equity")),
            ("roa", financial.get("profit"), financial.get("total_assets")),
            ("operating_margin", financial.get("operating_profit"), financial.get("net_sales")),
        ):
            value = _ratio(numerator, denominator)
            if value is not None:
                values[name] = value
        equity_ratio = _number(financial.get("equity_ratio"))
        if equity_ratio is not None:
            values["equity_ratio"] = equity_ratio * 100 if 0 <= equity_ratio <= 1 else equity_ratio
        operating_cash_flow = _number(financial.get("cash_flows_from_operating_activities"))
        if operating_cash_flow is not None:
            values["operating_cash_flow"] = operating_cash_flow
        dividends = _number(trailing_dividends)
        if price not in (None, 0) and dividends is not None:
            values["dividend_yield"] = dividends / price * 100
        return values
