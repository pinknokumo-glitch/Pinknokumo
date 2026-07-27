from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from modules.backtest_history import BacktestHistoryBackfill
from modules.database import Database


SETTINGS = {
    "providers": {
        "yfinance": {
            "suffix": ".T",
            "period": "2y",
            "interval": "1d",
            "auto_adjust": False,
            "repair": False,
            "retries": 1,
        },
    },
    "resampling": {"weekly_rule": "W-FRI", "monthly_rule": "ME"},
    "cloud_screening": {
        "backtest_history_period": "10y",
        "backtest_history_chunk_size": 2,
        "backtest_minimum_signal_sessions": 252,
    },
}


class BacktestHistoryBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.database = Database(Path(self.directory.name) / "stockai.db")
        self.database.initialize()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_only_codes_with_too_few_rows_are_requested(self) -> None:
        rows = [
            {
                "code": "11110",
                "trade_date": f"2026-01-{day:02d}",
                "close": 100.0,
            }
            for day in range(1, 6)
        ]
        self.database.upsert_rows("price_daily", rows, ["code", "trade_date"])
        backfill = BacktestHistoryBackfill(self.database, SETTINGS)

        self.assertEqual(
            backfill.codes_requiring_history(
                ["11110", "22220", "11110"], required_rows=5
            ),
            ["22220"],
        )

    def test_long_horizon_uses_ten_year_bounded_batches(self) -> None:
        backfill = BacktestHistoryBackfill(self.database, SETTINGS)
        backfill.loader = MagicMock()
        backfill.loader.load_yfinance_batch.side_effect = [
            {
                "updated": [
                    {"code": "11110", "ticker": "1111.T"},
                    {"code": "22220", "ticker": "2222.T"},
                ],
                "failed": [],
            },
            {
                "updated": [{"code": "33330", "ticker": "3333.T"}],
                "failed": [],
            },
        ]

        result = backfill.run(["11110", "22220", "33330"], holding_days=360)

        self.assertEqual(result["required_rows"], 614)
        self.assertEqual(result["requested_count"], 3)
        self.assertEqual(result["updated_count"], 3)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(backfill.loader.load_yfinance_batch.call_count, 2)
        first_pairs, first_period = (
            backfill.loader.load_yfinance_batch.call_args_list[0].args
        )
        self.assertEqual(first_period, "10y")
        self.assertEqual(
            first_pairs, [("1111.T", "11110"), ("2222.T", "22220")]
        )


if __name__ == "__main__":
    unittest.main()
