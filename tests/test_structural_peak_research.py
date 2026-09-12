import unittest

import pandas as pd
import yaml

from modules.structural_peak_research import _monthly_regime, _monthly_roles, analyze_structural_peaks


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
        self.assertIn("monthly_regime", result["summary"][0])

    def test_monthly_regime_recognizes_range_and_breakout(self):
        dates = pd.date_range("2018-01-31", periods=26, freq="ME")
        monthly = pd.DataFrame({
            "trade_date": dates,
            "high": [110, 100, 111, 99, 109, 98, 110, 99, 111, 98, 110, 99,
                     111, 98, 110, 99, 111, 98, 110, 99, 111, 98, 130, 100, 90, 91],
            "low": [90, 80, 89, 79, 90, 78, 89, 79, 90, 78, 89, 79,
                     90, 78, 89, 79, 90, 78, 89, 79, 90, 78, 100, 80, 75, 76],
            "close": [100] * 22 + [125, 90, 85, 86],
        })
        tops = _monthly_roles(monthly, "top")
        bottoms = _monthly_roles(monthly, "bottom")
        range_top = next(node for node in tops if node["index"] == 16)
        self.assertEqual(_monthly_regime(monthly, "top", range_top, tops, bottoms), "range")
        breakout = next(node for node in tops if node["index"] == 22)
        self.assertEqual(_monthly_regime(monthly, "top", breakout, tops, bottoms), "range_breakout_up")

    def test_range_keeps_retested_boundaries_when_internal_swings_exist(self):
        dates = pd.date_range("2018-01-31", periods=24, freq="ME")
        monthly = pd.DataFrame({
            "trade_date": dates,
            "high": [110, 100, 111, 99, 106, 98, 110, 99, 105, 98, 111, 99,
                     106, 98, 110, 99, 105, 98, 111, 99, 106, 98, 90, 91],
            "low": [90, 80, 89, 79, 84, 78, 89, 79, 84, 78, 90, 79,
                    84, 78, 89, 79, 84, 78, 90, 79, 84, 78, 75, 76],
            "close": [100] * 24,
        })
        tops = _monthly_roles(monthly, "top")
        bottoms = _monthly_roles(monthly, "bottom")
        node = next(item for item in tops if item["index"] == 18)
        self.assertEqual(_monthly_regime(monthly, "top", node, tops, bottoms), "range")
