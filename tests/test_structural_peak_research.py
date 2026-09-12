import unittest

import pandas as pd
import yaml

from modules.structural_peak_research import _monthly_roles, analyze_structural_peaks


class StructuralPeakResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/indicators.yaml", encoding="utf-8") as stream:
            cls.config = yaml.safe_load(stream)

    @staticmethod
    def prices():
        dates = pd.bdate_range("2017-01-02", periods=2400)
        month_number = pd.Series(pd.factorize(dates.to_period("M"))[0], dtype="int64")
        levels = [100, 130, 160, 120, 85, 110, 135]
        close = month_number.map(lambda value: levels[value % len(levels)]).astype("float64")
        close += pd.Series(range(len(dates)), dtype="float64") * .01
        return pd.DataFrame({"trade_date": dates, "open": close - .2, "high": close + 1,
                             "low": close - 1, "close": close, "adjusted_close": close,
                             "volume": 1000 + pd.Series(range(len(dates)), dtype="float64")})

    def test_monthly_roles_keep_retested_equal_levels(self):
        dates = pd.date_range("2018-01-31", periods=32, freq="ME")
        high = [100.0] * 32
        high[5], high[8], high[15], high[25] = 120.0, 118.0, 200.0, 108.0
        frame = pd.DataFrame({"trade_date": dates, "high": high, "low": [80.0] * 32})
        roles = _monthly_roles(frame, "top")
        by_index = {item["index"]: item for item in roles}
        self.assertGreater(by_index[5]["retest_count"], 0)
        self.assertGreater(by_index[8]["retest_count"], 0)
        self.assertEqual(by_index[15]["retest_count"], 0)
        self.assertEqual(by_index[25]["retest_count"], 0)

    def test_report_links_monthly_roles_to_containing_week_and_day(self):
        result = analyze_structural_peaks({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertEqual(result["usable_stock_count"], 1)
        self.assertTrue(result["summary"])
        self.assertEqual({item["stage"] for item in result["summary"]},
                         {"monthly_structural_bar", "weekly_bar_containing_monthly_extreme", "daily_monthly_extreme"})
        self.assertIn("weekly_structural_match_rate_percent", result["summary"][0])
        self.assertIn("retest_group", result["summary"][0])
