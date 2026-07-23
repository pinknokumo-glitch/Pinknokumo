import unittest

from scripts.run_daily_pipeline import require_fresh_update_for_notification


class DailyPipelineTests(unittest.TestCase):
    def test_notification_rejects_skipped_data_update(self) -> None:
        with self.assertRaisesRegex(ValueError, "当日のデータ更新が必須"):
            require_fresh_update_for_notification(True, True)

    def test_non_notification_preview_can_use_stored_data(self) -> None:
        require_fresh_update_for_notification(False, True)

    def test_notification_with_update_is_allowed(self) -> None:
        require_fresh_update_for_notification(True, False)


if __name__ == "__main__":
    unittest.main()
