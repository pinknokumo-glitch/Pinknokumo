from __future__ import annotations

import unittest

from modules.cloud_batch import (
    _codes_requiring_backtest,
    group_preferences,
    preference_signature,
)
from modules.cloud_preferences import ScreeningPreference
from modules.database import Database
from pathlib import Path
from tempfile import TemporaryDirectory


class CloudBatchTests(unittest.TestCase):
    def preference(self, user_id: str, holding_days: int = 60) -> ScreeningPreference:
        return ScreeningPreference(
            user_id=user_id,
            mode="manual",
            genre_id=None,
            manual_logic="all",
            manual_conditions=[
                {"field": "daily.rsi_14", "operator": "<=", "value": 20},
                {"field": "weekly.rsi_14", "operator": "<=", "value": 20},
            ],
            holding_days=holding_days,
        )

    def test_identical_rules_share_one_computation_group(self) -> None:
        groups = group_preferences([self.preference("a"), self.preference("b")])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(next(iter(groups.values()))), 2)

    def test_holding_period_changes_expectation_group(self) -> None:
        short = self.preference("a", 20)
        long = self.preference("b", 60)
        self.assertNotEqual(preference_signature(short), preference_signature(long))
        self.assertEqual(len(group_preferences([short, long])), 2)

    def test_technical_threshold_changes_expectation_group(self) -> None:
        first = self.preference("a")
        second = ScreeningPreference(
            user_id="b",
            mode="manual",
            genre_id=None,
            manual_logic="all",
            manual_conditions=[
                {"field": "daily.rsi_14", "operator": "<=", "value": 30},
                {"field": "weekly.rsi_14", "operator": "<=", "value": 20},
            ],
            holding_days=60,
        )
        self.assertNotEqual(preference_signature(first), preference_signature(second))

    def test_anonymous_rows_are_not_processed(self) -> None:
        anonymous = self.preference("", 20)
        self.assertEqual(group_preferences([anonymous]), {})

    def test_current_day_backtest_is_reused(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize()
            database.save_analysis_snapshot(
                "7203", "2026-07-24", "cloud_signature_0", "backtest", {"ok": True}
            )
            missing = _codes_requiring_backtest(
                database,
                ["7203", "6758"],
                "cloud_signature_0",
                "2026-07-24",
            )
            self.assertEqual(missing, ["6758"])

    def test_previous_day_backtest_is_not_reused(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize()
            database.save_analysis_snapshot(
                "7203", "2026-07-23", "cloud_signature_0", "backtest", {"ok": True}
            )
            missing = _codes_requiring_backtest(
                database, ["7203"], "cloud_signature_0", "2026-07-24"
            )
            self.assertEqual(missing, ["7203"])


if __name__ == "__main__":
    unittest.main()
