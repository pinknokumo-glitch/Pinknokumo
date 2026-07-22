"""Network-free retry and persistence tests for market-data loading."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from modules.data_loader import DataLoader, clean
from modules.database import Database


SETTINGS = {
    "providers": {"yfinance": {
        "period": "1y", "interval": "1d", "auto_adjust": False, "repair": False,
        "retries": 2, "retry_delay_seconds": 0,
    }},
    "resampling": {"weekly_rule": "W-FRI", "monthly_rule": "ME"},
}


class DataLoaderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "stockai.db")
        self.db.initialize()
        self.loader = DataLoader(self.db, SETTINGS)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_empty_responses_raise_clear_error(self) -> None:
        with patch("modules.data_loader.yf.Ticker") as ticker:
            ticker.return_value.history.return_value = pd.DataFrame()
            with self.assertRaisesRegex(RuntimeError, "No price data returned for 7203.T"):
                self.loader.load_yfinance_prices("7203.T", "72030")
        self.assertEqual(ticker.return_value.history.call_count, 2)

    def test_retry_then_save_prices(self) -> None:
        prices = pd.DataFrame({
            "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
            "Close": [100.5, 101.5], "Volume": [1000, 2000], "Dividends": [0.0, 1.0],
            "Stock Splits": [0.0, 0.0],
        }, index=pd.date_range("2026-01-01", periods=2, freq="D"))
        with patch("modules.data_loader.yf.Ticker") as ticker:
            ticker.return_value.history.side_effect = [RuntimeError("temporary"), prices]
            saved = self.loader.load_yfinance_prices("7203.T", "72030")
        self.assertEqual(saved, 2)
        self.assertEqual(ticker.return_value.history.call_count, 2)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT close, dividends FROM price_daily WHERE code=? AND trade_date=?", ["72030", "2026-01-02"]
            ).fetchone()
        self.assertEqual((row["close"], row["dividends"]), (101.5, 1.0))

    def test_incremental_request_uses_start_instead_of_period(self) -> None:
        prices = pd.DataFrame({
            "Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [1000],
        }, index=pd.date_range("2026-01-10", periods=1, freq="D"))
        with patch("modules.data_loader.yf.Ticker") as ticker:
            ticker.return_value.history.return_value = prices
            self.loader.load_yfinance_prices("7203.T", "72030", period="1y", start="2026-01-03")
        kwargs = ticker.return_value.history.call_args.kwargs
        self.assertEqual(kwargs["start"], "2026-01-03")
        self.assertNotIn("period", kwargs)

    def test_jquants_v2_abbreviated_financial_columns_are_normalized(self) -> None:
        saved = self.loader._save_financial([{
            "Code": "72030", "DiscDate": "2026-01-05", "DocType": "FY", "CurFYEn": "2025-12-31",
            "CurPerType": "FY", "Sales": 1000, "OP": 100, "OdP": 90, "NP": 80, "EPS": 10,
            "BPS": 100, "TA": 2000, "Eq": 1000, "EqAR": 0.5, "CFO": 120, "CFI": -30, "CFF": -20,
        }])
        self.assertEqual(saved, 1)
        with self.db.connect() as connection:
            disclosed_date = connection.execute("SELECT disclosed_date FROM financial WHERE code=?", ["72030"]).fetchone()[0]
        self.assertEqual(disclosed_date, "2026-01-05")
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT net_sales, operating_profit, earnings_per_share, equity_ratio FROM financial WHERE code=?", ["72030"]
            ).fetchone()
        self.assertEqual((row["net_sales"], row["operating_profit"], row["earnings_per_share"], row["equity_ratio"]), (1000, 100, 10, 0.5))

    def test_jquants_dates_are_sqlite_compatible(self) -> None:
        self.assertEqual(clean(pd.Timestamp("2026-01-05")), "2026-01-05")
        saved = self.loader._save_financial([{
            "Code": "72030", "DiscDate": pd.Timestamp("2026-01-05"), "DocType": "FY",
            "CurFYEn": pd.Timestamp("2025-12-31"), "Sales": 1000,
        }])
        self.assertEqual(saved, 1)


if __name__ == "__main__":
    unittest.main()
