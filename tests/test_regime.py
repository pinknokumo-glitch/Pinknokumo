"""Regression tests for market-regime classification and attribution."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

import pandas as pd

from modules.regime import MarketRegimeAnalyzer
from modules.regime_backtest import RegimeBacktestAnalyzer


CONFIG = {
    "market_regime": {
        "short_moving_average": 2,
        "long_moving_average": 3,
        "labels": {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral"},
    }
}


class MarketRegimeTestCase(unittest.TestCase):
    def test_classifies_bullish_and_bearish_only_after_long_average(self) -> None:
        analyzer = MarketRegimeAnalyzer(CONFIG)
        bullish = analyzer.classify(pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "close": [1.0, 2.0, 3.0],
        }))
        bearish = analyzer.classify(pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "close": [3.0, 2.0, 1.0],
        }))
        self.assertEqual(bullish.iloc[0]["regime"], "neutral")
        self.assertEqual(bullish.iloc[-1]["regime"], "bullish")
        self.assertEqual(bearish.iloc[-1]["regime"], "bearish")

    def test_groups_trades_by_signal_date_regime(self) -> None:
        trades = [
            SimpleNamespace(signal_date="2026-01-01", return_percent=10, max_drawdown_percent=-2),
            SimpleNamespace(signal_date="2026-01-01", return_percent=-5, max_drawdown_percent=-6),
            SimpleNamespace(signal_date="2026-01-02", return_percent=3, max_drawdown_percent=-1),
        ]
        result = RegimeBacktestAnalyzer().summarize(trades, {"2026-01-01": "bullish"})
        self.assertEqual(result["bullish"]["trade_count"], 2)
        self.assertEqual(result["bullish"]["win_rate_percent"], 50.0)
        self.assertEqual(result["unknown"]["average_return_percent"], 3.0)


if __name__ == "__main__":
    unittest.main()
