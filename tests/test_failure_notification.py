import unittest
from datetime import datetime, timezone

from scripts.send_failure_notification import japan_timestamp


class FailureNotificationTests(unittest.TestCase):
    def test_timestamp_is_always_formatted_in_japan_time(self) -> None:
        utc_value = datetime(2026, 7, 23, 13, 8, tzinfo=timezone.utc)
        self.assertEqual(
            japan_timestamp(utc_value),
            "2026-07-23 22:08 JST",
        )


if __name__ == "__main__":
    unittest.main()
