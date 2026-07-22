"""Regression tests for point-in-time backtesting behavior."""
from __future__ import annotations

import unittest

import pandas as pd

from modules.backtest import Backtester
from modules.threshold_research import oversold_rule, rank_threshold_results


INDICATORS_DISABLED = {
    "indicators": {
        "rsi": {"enabled": False}, "macd": {"enabled": False},
        "moving_average": {"enabled": False}, "bollinger_bands": {"enabled": False},
        "stochastic": {"enabled": False}, "adx": {"enabled": False}, "atr": {"enabled": False},
    }
}


def prices(dates: list[str], close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": pd.to_datetime(dates), "open": [close] * len(dates),
        "high": [close + 1] * len(dates), "low": [close - 1] * len(dates),
        "close": [close] * len(dates), "volume": [100] * len(dates), "dividends": [0] * len(dates),
    })


class BacktestPointInTimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backtester = Backtester(INDICATORS_DISABLED, {"backtest": {}})

    def test_financial_values_are_not_visible_before_disclosure(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 7)])
        financials = pd.DataFrame({
            "disclosed_date": pd.to_datetime(["2026-01-04"]),
            "earnings_per_share": [10.0], "book_value_per_share": [100.0],
        })
        rule = {"field": "fundamental.per", "operator": "<=", "value": 10}

        trades = self.backtester.run(daily, rule, holding_days=1, financials=financials)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].signal_date, "2026-01-04")
        self.assertEqual(trades[0].entry_date, "2026-01-05")

    def test_weekly_values_are_not_visible_before_weekly_candle_date(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 6)])
        weekly = prices(["2026-01-03"], close=50.0)

        values = self.backtester._add_timeframe_values(daily, {"weekly": weekly})

        self.assertTrue(pd.isna(values.loc[1, "weekly__close"]))
        self.assertEqual(values.loc[2, "weekly__close"], 50.0)

    def test_threshold_research_ranks_only_eligible_candidates_first(self) -> None:
        rule = oversold_rule({"daily": 60, "weekly": 50, "monthly": 50})
        self.assertEqual([condition["value"] for condition in rule["all"]], [60.0, 50.0, 50.0])
        results = [
            {"thresholds": {"daily": 60}, "current_hit_count": 1,
             "summary": {"trade_count": 40}, "expectation": {"score": 65}},
            {"thresholds": {"daily": 30}, "current_hit_count": 0,
             "summary": {"trade_count": 100}, "expectation": {"score": 90}},
        ]
        ranked = rank_threshold_results(results, minimum_trades=30, target_min_hits=1, target_max_hits=5)
        self.assertEqual(ranked[0]["thresholds"]["daily"], 60)
        self.assertTrue(ranked[0]["eligible"])
        self.assertFalse(ranked[1]["eligible"])


if __name__ == "__main__":
    unittest.main()
