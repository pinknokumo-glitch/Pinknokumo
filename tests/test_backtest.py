"""Regression tests for point-in-time backtesting behavior."""
from __future__ import annotations

import unittest

import pandas as pd

from modules.backtest import Backtester, Trade
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

    def test_summary_describes_only_reached_outcomes_for_price_estimates(self) -> None:
        common = {
            "signal_date": "2026-01-01",
            "entry_date": "2026-01-02",
            "exit_date": "2026-01-06",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "max_favorable_excursion_percent": 20.0,
            "max_drawdown_percent": -5.0,
        }
        trades = [
            Trade(**common, return_percent=10.0, target_reached=True, sessions_held=3),
            Trade(**common, return_percent=20.0, target_reached=True, sessions_held=5),
            Trade(**common, return_percent=-5.0, target_reached=False, sessions_held=20),
        ]

        summary = self.backtester.summarize(trades)

        self.assertEqual(summary["target_reached_count"], 2)
        self.assertEqual(summary["conditional_median_return_percent"], 15.0)
        self.assertEqual(summary["conditional_return_p25_percent"], 12.5)
        self.assertEqual(summary["conditional_return_p75_percent"], 17.5)
        self.assertEqual(summary["median_sessions_to_outcome"], 4.0)

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

    def test_long_trade_buys_low_and_exits_after_high_signal(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 6)])
        daily["open"] = [80.0, 82.0, 100.0, 112.0, 113.0]
        daily["high"] = [81.0, 84.0, 111.0, 114.0, 115.0]
        daily["low"] = [79.0, 81.0, 99.0, 111.0, 112.0]
        daily["close"] = [80.0, 83.0, 110.0, 113.0, 114.0]

        trades = self.backtester.run(
            daily,
            {"field": "daily.close", "operator": "<=", "value": 80},
            holding_days=3,
            exit_rule={"field": "daily.close", "operator": ">=", "value": 110},
            position_side="long",
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_price, 82.0)
        self.assertEqual(trades[0].exit_price, 112.0)
        self.assertEqual(trades[0].exit_reason, "condition")
        self.assertGreater(trades[0].return_percent, 0)

    def test_short_trade_sells_high_and_covers_after_low_signal(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 6)])
        daily["open"] = [120.0, 118.0, 100.0, 88.0, 87.0]
        daily["high"] = [121.0, 119.0, 101.0, 89.0, 88.0]
        daily["low"] = [119.0, 117.0, 89.0, 87.0, 86.0]
        daily["close"] = [120.0, 117.0, 90.0, 88.0, 87.0]

        trades = self.backtester.run(
            daily,
            {"field": "daily.close", "operator": ">=", "value": 120},
            holding_days=3,
            exit_rule={"field": "daily.close", "operator": "<=", "value": 90},
            position_side="short",
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_price, 118.0)
        self.assertEqual(trades[0].exit_price, 88.0)
        self.assertEqual(trades[0].position_side, "short")
        self.assertGreater(trades[0].return_percent, 0)

    def test_probability_of_price_rising_within_period(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 7)])
        daily["open"] = [80.0, 100.0, 99.0, 98.0, 97.0, 96.0]
        daily["close"] = [80.0, 99.0, 101.0, 98.0, 97.0, 96.0]
        daily["high"] = daily["close"] + 1
        daily["low"] = daily["close"] - 1

        trades = self.backtester.run(
            daily,
            {"field": "daily.close", "operator": "<=", "value": 80},
            holding_days=3,
            evaluation_mode="within_period_up",
        )
        summary = self.backtester.summarize(trades)

        self.assertEqual(trades[0].exit_reason, "price_improvement")
        self.assertTrue(trades[0].target_reached)
        self.assertEqual(summary["outcome_probability_percent"], 100.0)

    def test_target_return_probability_uses_intraday_high(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 7)])
        daily["open"] = [80.0, 100.0, 101.0, 102.0, 103.0, 104.0]
        daily["close"] = [80.0, 100.0, 101.0, 102.0, 103.0, 104.0]
        daily["high"] = [81.0, 101.0, 106.0, 103.0, 104.0, 105.0]
        daily["low"] = daily["close"] - 1

        trades = self.backtester.run(
            daily,
            {"field": "daily.close", "operator": "<=", "value": 80},
            holding_days=3,
            evaluation_mode="target_return",
            target_return_percent=5.0,
        )

        self.assertTrue(trades[0].target_reached)
        self.assertEqual(trades[0].exit_reason, "target_return")
        self.assertAlmostEqual(trades[0].return_percent, 5.0)

    def test_short_target_probability_uses_intraday_low(self) -> None:
        daily = prices([f"2026-01-0{day}" for day in range(1, 7)])
        daily["open"] = [120.0, 100.0, 99.0, 98.0, 97.0, 96.0]
        daily["close"] = [120.0, 100.0, 99.0, 98.0, 97.0, 96.0]
        daily["high"] = daily["close"] + 1
        daily["low"] = [119.0, 99.0, 94.0, 97.0, 96.0, 95.0]

        trades = self.backtester.run(
            daily,
            {"field": "daily.close", "operator": ">=", "value": 120},
            holding_days=3,
            position_side="short",
            evaluation_mode="target_return",
            target_return_percent=5.0,
        )

        self.assertTrue(trades[0].target_reached)
        self.assertAlmostEqual(trades[0].return_percent, 5.0)

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
