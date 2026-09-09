import unittest

from scripts.run_daily_pipeline import (
    available_candidate_codes,
    require_fresh_update_for_notification,
)


class DailyPipelineTests(unittest.TestCase):
    def test_notification_rejects_skipped_data_update(self) -> None:
        with self.assertRaisesRegex(ValueError, "当日のデータ更新が必須"):
            require_fresh_update_for_notification(True, True)

    def test_non_notification_preview_can_use_stored_data(self) -> None:
        require_fresh_update_for_notification(False, True)

    def test_notification_with_update_is_allowed(self) -> None:
        require_fresh_update_for_notification(True, False)

    def test_candidate_delivery_excludes_only_failed_latest_price_codes(self) -> None:
        available, excluded = available_candidate_codes(
            True, ["72030", "67580", "51030"],
            {"failed": [{"code": "51030"}, {"code": "not-in-pool"}]},
        )
        self.assertEqual(available, ["72030", "67580"])
        self.assertEqual(excluded, ["51030"])

    def test_all_failed_candidates_are_empty_not_stale(self) -> None:
        available, excluded = available_candidate_codes(
            True, ["72030"], {"failed": [{"code": "72030"}]}
        )
        self.assertEqual(available, [])
        self.assertEqual(excluded, ["72030"])

    def test_regular_update_is_unchanged(self) -> None:
        available, excluded = available_candidate_codes(
            False, None, {"failed": [{"code": "72030"}]}
        )
        self.assertIsNone(available)
        self.assertEqual(excluded, [])


if __name__ == "__main__":
    unittest.main()
