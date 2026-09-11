import unittest
import pandas as pd
import yaml

from modules.dow_peak_forecast_validation import _outcome, _period, validate_universe


class DowPeakForecastValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config/indicators.yaml", encoding="utf-8") as stream:
            cls.config = yaml.safe_load(stream)

    @staticmethod
    def prices():
        dates = pd.bdate_range("2018-01-01", periods=1800)
        month_number = pd.Series(pd.factorize(dates.to_period("M"))[0])
        levels = [100, 130, 160, 125, 90, 120]
        close = month_number.map(lambda value: levels[value % len(levels)]).astype("float64")
        close += pd.Series(range(len(dates)), dtype="float64") * .02
        return pd.DataFrame({"trade_date": dates, "open": close - .2, "high": close + 1,
                             "low": close - 1, "close": close, "adjusted_close": close,
                             "volume": 1000 + pd.Series(range(len(dates)), dtype="float64")})

    def test_periods_are_purged_at_boundaries(self):
        self.assertEqual(_period(pd.Timestamp("2021-12-01"), pd.Timestamp("2021-12-31")), "development_to_2021")
        self.assertIsNone(_period(pd.Timestamp("2021-12-20"), pd.Timestamp("2022-01-20")))
        self.assertEqual(_period(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-01")), "late_period_2024_onward")

    def test_outcome_uses_only_configured_horizon(self):
        frame = self.prices().iloc[:100].copy()
        outcome = _outcome(frame, 75, "bottom")
        modified = frame.copy()
        modified.loc[96:, "low"] = 1
        self.assertEqual(outcome, _outcome(modified, 75, "bottom"))

    def test_validation_is_read_only_report_with_baseline(self):
        result = validate_universe({"1234": self.prices()}, self.config)
        self.assertEqual(result["universe_stock_count"], 1)
        self.assertTrue(result["summary"])
        self.assertTrue(any(row["profile"] == "monthly_regime_baseline" for row in result["summary"]))
        self.assertTrue(all(row["profile"] in {"monthly_regime_baseline", "core_exhaustion_profile", "oscillator_confluence_profile"} for row in result["summary"]))
        self.assertEqual(len(result["summary"]), 3 * len({(row["period"], row["side"]) for row in result["summary"]}))
        self.assertEqual(result["method"]["horizon_sessions"], 20)
