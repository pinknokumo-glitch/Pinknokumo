import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import yaml

from modules.database import Database
from modules.evening_universe import EveningUniverseJob


class EveningUniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.tempdir.name) / "stockai.db")
        self.database.initialize()
        with Path("config/indicators.yaml").open(encoding="utf-8") as file:
            indicators = yaml.safe_load(file)
        self.settings = {
            "screening_universe": {
                "minimum_coverage_ratio": 0.95,
            },
        }
        self.job = EveningUniverseJob(self.database, self.settings, indicators)
        self.database.upsert_rows("master_stock", [
            {"code": "11110", "market_name": "プライム"},
            {"code": "22220", "market_name": "スタンダード"},
        ], ["code"])
        self.database.sync_screening_universe(["プライム", "スタンダード"])

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def price_rows(code: str, descending: bool) -> list[dict[str, object]]:
        rows = []
        for index in range(20):
            close = 100 - index if descending else 100 + index
            trade_date = date(2025, 1, 3) + timedelta(days=index * 14)
            rows.append({
                "code": code,
                "trade_date": trade_date.isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adjusted_close": close,
                "volume": 100,
                "dividends": 0,
                "stock_splits": 0,
            })
        return rows

    def test_prefilter_keeps_only_weekly_and_monthly_rsi_candidates(self) -> None:
        for table in ("price_weekly", "price_monthly"):
            self.database.upsert_rows(
                table,
                self.price_rows("11110", True) + self.price_rows("22220", False),
                ["code", "trade_date"],
            )
        self.database.upsert_rows("price_daily", [{
            **self.price_rows("11110", True)[-1],
            "trade_date": "2026-07-23",
        }], ["code", "trade_date"])
        result = self.job._build_pool(
            ["11110", "22220"],
            {"weekly_rsi_max": 50, "monthly_rsi_max": 25},
            failed_count=0,
        )
        self.assertEqual(result["candidate_count"], 1)
        metadata, codes = self.database.latest_candidate_pool()
        self.assertEqual(metadata["status"], "success")
        self.assertEqual(codes, ["11110"])


if __name__ == "__main__":
    unittest.main()
