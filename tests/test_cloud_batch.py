from __future__ import annotations

import unittest

from modules.cloud_batch import (
    _codes_requiring_backtest,
    _estimated_price_fields,
    add_industry_benchmarks,
    group_preferences,
    preference_signature,
    should_stop_relaxation,
    verified_expectation_score,
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

    def test_trade_direction_changes_computation_group(self) -> None:
        long = self.preference("a")
        short = ScreeningPreference(
            **{**long.__dict__, "user_id": "b", "trade_direction": "short"}
        )
        self.assertNotEqual(preference_signature(long), preference_signature(short))

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
                "7203", "2026-07-24", "cloud_signature_0", "backtest",
                {"summary": {"conditional_median_return_percent": 5.0}},
            )
            missing = _codes_requiring_backtest(
                database,
                ["7203", "6758"],
                "cloud_signature_0",
                "2026-07-24",
            )
            self.assertEqual(missing, ["6758"])

    def test_legacy_backtest_without_price_distribution_is_recomputed(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize()
            database.save_analysis_snapshot(
                "7203", "2026-07-24", "cloud_signature_0", "backtest",
                {"summary": {"trade_count": 10}},
            )
            self.assertEqual(
                _codes_requiring_backtest(
                    database, ["7203"], "cloud_signature_0", "2026-07-24"
                ),
                ["7203"],
            )

    def test_price_estimate_uses_reached_outcome_distribution(self) -> None:
        summary = {
            "target_reached_count": 40,
            "conditional_median_return_percent": 10.0,
            "conditional_return_p25_percent": 5.0,
            "conditional_return_p75_percent": 20.0,
            "median_sessions_to_outcome": 12.0,
        }
        long_result = _estimated_price_fields(1000, summary, "long")
        short_result = _estimated_price_fields(1000, summary, "short")

        self.assertEqual(long_result["estimated_price_median"], 1100.0)
        self.assertEqual(long_result["estimated_price_low"], 1050.0)
        self.assertEqual(long_result["estimated_price_high"], 1200.0)
        self.assertEqual(short_result["estimated_price_median"], 900.0)
        self.assertEqual(short_result["estimated_price_low"], 800.0)
        self.assertEqual(short_result["estimated_price_high"], 950.0)
        self.assertEqual(long_result["estimate_sample_count"], 40)
        self.assertEqual(long_result["median_days_to_outcome"], 12.0)

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

    def test_backtest_score_can_sort_without_rescreening_candidates(self) -> None:
        hits = [
            {"code": "11110", "expectation_score": 30.0},
            {"code": "22220", "expectation_score": 80.0},
            {"code": "33330", "expectation_score": None},
        ]
        ordered = sorted(
            hits,
            key=lambda item: (
                item["expectation_score"]
                if item.get("expectation_score") is not None
                else float("-inf")
            ),
            reverse=True,
        )
        self.assertEqual(
            [item["code"] for item in ordered],
            ["22220", "11110", "33330"],
        )

    def test_zero_trade_backtest_does_not_publish_a_zero_score(self) -> None:
        result = {
            "summary": {"trade_count": 0},
            "expectation": {"score": 0.0},
        }
        self.assertIsNone(verified_expectation_score(result))

    def test_backtest_with_trades_publishes_its_score(self) -> None:
        result = {
            "summary": {"trade_count": 12},
            "expectation": {"score": 64.5},
        }
        self.assertEqual(verified_expectation_score(result), 64.5)

    def test_relaxation_continues_when_first_stage_has_only_one_hit(self) -> None:
        self.assertFalse(should_stop_relaxation(1, 5, 0, 3))
        self.assertTrue(should_stop_relaxation(5, 5, 1, 3))
        self.assertTrue(should_stop_relaxation(2, 5, 2, 3))

    def test_industry_benchmarks_are_added_per_sector(self) -> None:
        enriched = add_industry_benchmarks(
            [
                {
                    "code": "11110",
                    "fundamental.per": 10.0,
                    "fundamental.roe": 12.0,
                },
                {
                    "code": "22220",
                    "fundamental.per": 20.0,
                    "fundamental.roe": 8.0,
                },
                {
                    "code": "33330",
                    "fundamental.per": 30.0,
                    "fundamental.roe": 4.0,
                },
            ],
            {"11110": "機械", "22220": "機械", "33330": "小売"},
        )
        first = enriched[0]
        self.assertEqual(first["fundamental.sector_name"], "機械")
        self.assertEqual(first["industry.per"], 15.0)
        self.assertEqual(first["industry.roe"], 10.0)
        self.assertEqual(first["industry.sample_count"], 2)
        self.assertNotIn("industry.per", enriched[2])


if __name__ == "__main__":
    unittest.main()
