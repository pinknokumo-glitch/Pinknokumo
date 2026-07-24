from __future__ import annotations

import unittest

from modules.cloud_batch import group_preferences, preference_signature
from modules.cloud_preferences import ScreeningPreference


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


if __name__ == "__main__":
    unittest.main()
