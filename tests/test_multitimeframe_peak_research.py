import unittest

import pandas as pd
import yaml

from modules.multitimeframe_peak_research import analyze_nested_peaks


class MultiTimeframePeakResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/indicators.yaml", encoding="utf-8") as stream:
            cls.config = yaml.safe_load(stream)

    @staticmethod
    def prices():
        dates = pd.bdate_range("2018-01-01", periods=2100)
        month_number = pd.Series(pd.factorize(dates.to_period("M"))[0], dtype="int64")
        levels = [100, 125, 150, 120, 85, 110, 135]
        close = month_number.map(lambda number: levels[number % len(levels)]).astype("float64")
        sequence = pd.Series(range(len(dates)), dtype="float64")
        close += sequence * .01
        return pd.DataFrame({"trade_date": dates, "open": close - .2,
                             "high": close + 1, "low": close - 1,
                             "close": close, "adjusted_close": close,
                             "volume": 1000 + sequence})

    def test_reports_three_nested_bars_and_requested_metric_ranges(self):
        result = analyze_nested_peaks({"1234": self.prices()}, {"1234": "電気機器"}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertEqual(result["usable_stock_count"], 1)
        self.assertEqual({item["stage"] for item in result["summary"]},
                         {"monthly_peak_bar", "weekly_peak_bar", "daily_peak_bar"})
        daily_bottom = next(item for item in result["summary"]
                            if item["side"] == "bottom" and item["stage"] == "daily_peak_bar" and item["scope"] == "all")
        self.assertGreater(daily_bottom["sample_count"], 0)
        self.assertGreater(daily_bottom["rsi_14_rakuten"]["count"], 0)
        self.assertIn("expanded_150_or_more", daily_bottom["participation_proxy"])
        self.assertIn("volume ratio", result["method"]["supply_demand_proxy"])
        self.assertIsInstance(result["major_observations"], list)
        self.assertTrue(all(item["major"] for item in result["major_observations"]))
