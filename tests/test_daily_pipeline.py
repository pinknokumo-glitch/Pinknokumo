import unittest

from scripts.run_daily_pipeline import (
    require_complete_candidate_update,
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

    def test_candidate_delivery_rejects_incomplete_latest_prices(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "通常配信を停止"):
            require_complete_candidate_update(
                True, {"failed": [{"code": "72030"}]}
            )

    def test_regular_update_can_report_partial_failure_without_pool_guard(self) -> None:
        require_complete_candidate_update(
            False, {"failed": [{"code": "72030"}]}
        )


if __name__ == "__main__":
    unittest.main()
