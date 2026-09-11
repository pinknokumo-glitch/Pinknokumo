import unittest
import pandas as pd
import yaml

from modules.dow_peak_research import _monthly_swings, daily_features, analyze_universe


class DowPeakResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/indicators.yaml", encoding="utf-8") as stream:
            cls.config = yaml.safe_load(stream)

    @staticmethod
    def prices():
        dates = pd.bdate_range("2021-01-01", periods=600)
        # Repeated multi-month waves make unambiguous monthly pivots.
        month_number = pd.Series(pd.factorize(dates.to_period("M"))[0], dtype="int64")
        levels = [100, 130, 160, 125, 90, 120]
        close = month_number.map(lambda value: levels[value % len(levels)]).astype("float64")
        close += pd.Series(range(len(dates)), dtype="float64") * .01
        value = pd.Series(range(len(dates)), dtype="float64")
        return pd.DataFrame({"trade_date": dates, "open": close - .2, "high": close + 1,
                             "low": close - 1, "close": close, "volume": 1000 + value})

    def test_daily_features_produce_requested_oscillators(self):
        daily = daily_features(self.prices(), self.config)
        latest = daily.iloc[-1]
        self.assertTrue(-100 <= latest.rci_9 <= 100)
        self.assertTrue(-100 <= latest.rci_27 <= 100)
        self.assertTrue(0 <= latest.psychological_12 <= 100)
        self.assertTrue(0 <= latest.stoch_k_14_3 <= 100)

    def test_swing_is_confirmed_only_after_two_following_months(self):
        daily = daily_features(self.prices(), self.config)
        swings = _monthly_swings(daily)
        self.assertTrue(swings)
        last_month = daily.trade_date.dt.to_period("M").max()
        self.assertTrue(all(pd.Period(row["month"], freq="M") < last_month - 1 for row in swings))
        self.assertTrue(all(pd.Timestamp(row["confirmed_on"]) > pd.Timestamp(row["date"]) for row in swings))

    def test_report_is_descriptive_and_has_controls(self):
        result = analyze_universe({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertTrue(result["pivots"])
        self.assertTrue(result["summary"])
        self.assertIn("descriptive_lift", result["summary"][0]["conditions"]["rsi_extreme"])
