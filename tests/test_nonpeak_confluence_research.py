import unittest

import pandas as pd
import yaml

from modules.nonpeak_confluence_research import _future_pivot_within, _monthly_peak_positions, analyze_nonpeak_confluence
from modules.structural_peak_research import _monthly_roles
from modules.multitimeframe_peak_research import _features, _resample


class NonpeakConfluenceResearchTests(unittest.TestCase):
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

    def test_future_pivot_window_excludes_signal_day(self):
        self.assertTrue(_future_pivot_within(10, {11, 70}))
        self.assertFalse(_future_pivot_within(10, {10, 71}))

    def test_monthly_peak_positions_map_to_actual_daily_extreme(self):
        daily = _features(self.prices(), self.config)
        monthly = _features(_resample(daily[["trade_date", "open", "high", "low", "close", "volume", "adjusted_close"]], "ME"), self.config)
        nodes = _monthly_roles(monthly, "top")
        months, positions = _monthly_peak_positions(daily, monthly, nodes, "top")
        self.assertTrue(months)
        self.assertTrue(positions)

    def test_report_has_monthly_location_and_prior_regime_fields(self):
        result = analyze_nonpeak_confluence({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertEqual(result["usable_stock_count"], 1)
        for row in result["summary"]:
            self.assertIn(row["location"], {"monthly_pivot_month", "monthly_nonpeak_month"})
            self.assertIn("prior_completed_month_regime", row)
            self.assertIn("future_same_side_monthly_pivot_within_60_sessions_rate_percent", row)
