import unittest

import pandas as pd
import yaml

from modules.monthly_peak_condition_research import _condition_flags, analyze_monthly_peak_conditions


class MonthlyPeakConditionResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/indicators.yaml", encoding="utf-8") as stream:
            cls.config = yaml.safe_load(stream)

    @staticmethod
    def prices():
        dates = pd.bdate_range("2006-01-02", periods=4800)
        month_number = pd.Series(pd.factorize(dates.to_period("M"))[0], dtype="int64")
        levels = [100, 130, 160, 120, 85, 110, 135]
        close = month_number.map(lambda value: levels[value % len(levels)]).astype("float64")
        close += pd.Series(range(len(dates)), dtype="float64") * .01
        return pd.DataFrame({"trade_date": dates, "open": close - .2, "high": close + 1,
                             "low": close - 1, "close": close, "adjusted_close": close,
                             "volume": 1000 + pd.Series(range(len(dates)), dtype="float64")})

    def test_directional_thresholds_are_not_mixed(self):
        row = pd.Series({"rsi_14_rakuten": 20, "rci_9": -80, "stoch_k_14_3": 15,
                         "price_vs_sma_75_percent": -2, "bb_percent_b_20": -5,
                         "ichimoku_cloud_distance_percent": -1, "macd_histogram_12_26_9": -1,
                         "bullish_lower_wick": True, "close_near_low": True})
        bottom = _condition_flags(row, "bottom")
        top = _condition_flags(row, "top")
        self.assertTrue(bottom["rsi_14_extreme"])
        self.assertTrue(bottom["rci_9_extreme"])
        self.assertTrue(bottom["reversal_candle"])
        self.assertFalse(top["rsi_14_extreme"])
        self.assertFalse(top["rci_9_extreme"])

    def test_report_is_strictly_monthly_with_peak_and_control_groups(self):
        result = analyze_monthly_peak_conditions({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertEqual(result["usable_stock_count"], 1)
        self.assertEqual({(row["side"], row["group"]) for row in result["summary"]}, {
            ("bottom", "monthly_local_peak"), ("bottom", "monthly_nonpeak_bar"),
            ("top", "monthly_local_peak"), ("top", "monthly_nonpeak_bar"),
        })
        peak = next(row for row in result["summary"] if row["side"] == "bottom" and row["group"] == "monthly_local_peak")
        self.assertGreater(peak["sample_count"], 0)
        self.assertIn("rsi_14_extreme", peak["condition_rates"])
        self.assertEqual(result["method"]["scope"], "monthly bars only; weekly and daily indicators are not calculated or included")
