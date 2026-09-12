import unittest

import pandas as pd
import yaml

from modules.complete_condition_precision import _available_mask, _major_research_window, _profile_mask, validate_complete_conditions


class CompleteConditionPrecisionTests(unittest.TestCase):
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

    def test_profile_requires_each_agreed_condition(self):
        rows = pd.DataFrame({"rsi_14_rakuten": [29, 71], "rci_9": [-71, 71],
                             "stoch_k_14_3": [19, 81], "price_vs_sma_75_percent": [-11, 11],
                             "volume_ratio_20": [151, 151]})
        self.assertEqual(_profile_mask(rows, "bottom").tolist(), [True, False])
        self.assertEqual(_profile_mask(rows, "top").tolist(), [False, True])
        rows.loc[0, "volume_ratio_20"] = 149
        self.assertFalse(_profile_mask(rows, "bottom").iloc[0])
        rows.loc[0, "volume_ratio_20"] = None
        self.assertFalse(_available_mask(rows).iloc[0])

    def test_window_excludes_months_without_complete_major_labels(self):
        dates = pd.bdate_range("2018-01-01", periods=900)
        frame = pd.DataFrame({"trade_date": dates})
        window = _major_research_window(frame)
        self.assertTrue(window.any())
        self.assertFalse(window.iloc[0])
        self.assertFalse(window.iloc[-1])

    def test_report_compares_complete_conditions_with_all_eligible_days(self):
        result = validate_complete_conditions({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertEqual(result["usable_stock_count"], 1)
        profiles = {item["profile"] for item in result["summary"]}
        self.assertEqual(profiles, {"eligible_day_baseline", "complete_five_condition_profile"})
        baseline = next(item for item in result["summary"] if item["profile"] == "eligible_day_baseline")
        self.assertGreater(baseline["candidate_count"], 0)
        self.assertIn("major_pivot_exact_rate_percent", baseline)
        self.assertIn("major_pivot_exact_rate_percent_lift_vs_baseline", baseline)
