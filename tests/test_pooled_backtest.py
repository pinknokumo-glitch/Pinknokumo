from __future__ import annotations

import unittest

from modules.pooled_backtest import (
    aggregate_summaries,
    attach_scope_comparisons,
    confidence_label,
)


class PooledBacktestTests(unittest.TestCase):
    def test_market_metrics_are_weighted_by_trade_count(self) -> None:
        results = {
            "11110": {
                "trade_count": 10,
                "average_return_percent": 10.0,
                "win_rate_percent": 80.0,
                "outcome_probability_percent": 60.0,
                "max_drawdown_percent": -8.0,
                "out_of_sample_trade_count": 2,
                "out_of_sample_average_return_percent": 5.0,
                "out_of_sample_win_rate_percent": 50.0,
            },
            "22220": {
                "trade_count": 30,
                "average_return_percent": 0.0,
                "win_rate_percent": 40.0,
                "outcome_probability_percent": 20.0,
                "max_drawdown_percent": -20.0,
                "out_of_sample_trade_count": 6,
                "out_of_sample_average_return_percent": -1.0,
                "out_of_sample_win_rate_percent": 25.0,
            },
        }
        market, sectors = aggregate_summaries(
            results, {"11110": "機械", "22220": "機械"}
        )
        self.assertEqual(market["stock_count"], 2)
        self.assertEqual(market["trade_count"], 40)
        self.assertEqual(market["average_return_percent"], 2.5)
        self.assertEqual(market["win_rate_percent"], 50.0)
        self.assertEqual(market["max_drawdown_percent"], -20.0)
        self.assertAlmostEqual(
            market["out_of_sample_average_return_percent"], 0.5
        )
        self.assertEqual(sectors["機械"]["trade_count"], 40)

    def test_scope_comparison_reports_coverage_and_sector(self) -> None:
        hits = [{"code": "11110"}]
        result = attach_scope_comparisons(
            hits,
            {
                "11110": {
                    "trade_count": 20,
                    "average_return_percent": 3.0,
                    "win_rate_percent": 55.0,
                    "out_of_sample_trade_count": 4,
                }
            },
            {"11110": "機械"},
            universe_count=2,
        )
        self.assertEqual(result["tested_stock_count"], 1)
        self.assertEqual(result["coverage_ratio"], 0.5)
        self.assertEqual(hits[0]["sector_name"], "機械")
        self.assertEqual(hits[0]["individual_trade_count"], 20)
        self.assertEqual(hits[0]["backtest_confidence"], "低")

    def test_confidence_requires_individual_sector_market_and_holdout_data(self) -> None:
        self.assertEqual(
            confidence_label(
                {"trade_count": 20},
                {"trade_count": 100},
                {"trade_count": 500, "out_of_sample_trade_count": 100},
                0.95,
            ),
            "高",
        )
        self.assertEqual(
            confidence_label(
                {"trade_count": 2},
                {"trade_count": 100},
                {"trade_count": 500, "out_of_sample_trade_count": 100},
                0.95,
            ),
            "中",
        )


if __name__ == "__main__":
    unittest.main()
