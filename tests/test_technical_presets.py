from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd
import yaml

from modules.technical import TechnicalAnalyzer


class TechnicalPresetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        with Path("config/indicators.yaml").open(encoding="utf-8") as file:
            self.config = yaml.safe_load(file)
        rows = 260
        base = pd.Series(range(rows), dtype="float64")
        close = 100.0 + base * 0.2 + (base % 11 - 5) * 0.4
        self.prices = pd.DataFrame({
            "trade_date": pd.date_range("2025-01-01", periods=rows),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0 + base,
        })

    def test_calculates_bounded_short_standard_and_long_presets(self) -> None:
        frame = TechnicalAnalyzer(self.config).calculate(self.prices)
        expected = {
            "rsi_9", "rsi_14", "rsi_9_rakuten", "rsi_9_wilder",
            "rsi_14_rakuten", "rsi_14_wilder",
            "macd_5_25_9", "macd_12_26_9", "macd_25_75_14",
            "macd_histogram_5_25_9", "macd_histogram_12_26_9",
            "macd_histogram_25_75_14",
            "stoch_k_9_3", "stoch_k_14_3",
            "price_vs_sma_5_percent", "price_vs_sma_25_percent",
            "price_vs_sma_75_percent", "price_vs_sma_200_percent",
        }
        self.assertTrue(expected <= set(frame.columns))
        pd.testing.assert_series_equal(
            frame["macd"], frame["macd_12_26_9"], check_names=False,
        )
        pd.testing.assert_series_equal(
            frame["macd_histogram"], frame["macd_histogram_12_26_9"],
            check_names=False,
        )
        pd.testing.assert_series_equal(
            frame["stoch_k"], frame["stoch_k_14_3"], check_names=False,
        )
        pd.testing.assert_series_equal(
            frame["rsi_14"], frame["rsi_14_rakuten"], check_names=False,
        )

    def test_rakuten_and_canonical_wilder_rsi_use_distinct_smoothing(self) -> None:
        close = pd.Series(
            [44.0, 44.3, 44.1, 44.8, 45.2, 44.9, 45.6, 45.1,
             45.9, 46.3, 45.7, 46.8, 47.2, 46.4, 47.5, 48.0, 47.1,
             48.4, 49.0, 48.2, 49.4],
            dtype="float64",
        )
        prices = pd.DataFrame({
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close, "volume": 1000.0,
        })
        frame = TechnicalAnalyzer(self.config).calculate(prices)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        expected_simple = 100 - 100 / (
            1 + gain.iloc[-14:].mean() / loss.iloc[-14:].mean()
        )
        self.assertAlmostEqual(frame["rsi_14_rakuten"].iloc[-1], expected_simple)
        self.assertNotAlmostEqual(
            frame["rsi_14_rakuten"].iloc[-1],
            frame["rsi_14_wilder"].iloc[-1],
        )

    def test_legacy_single_period_configuration_remains_supported(self) -> None:
        config = yaml.safe_load(yaml.safe_dump(self.config))
        config["indicators"]["rsi"].pop("periods")
        config["indicators"]["macd"].pop("presets")
        config["indicators"]["stochastic"].pop("presets")
        frame = TechnicalAnalyzer(config).calculate(self.prices)
        self.assertIn("rsi_14", frame)
        self.assertIn("macd", frame)
        self.assertIn("stoch_k", frame)


if __name__ == "__main__":
    unittest.main()
