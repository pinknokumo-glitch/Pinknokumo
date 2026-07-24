from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_results import CloudResultPublisher


class CloudResultPublisherTests(unittest.TestCase):
    def test_publish_uses_user_scoped_upsert_rows(self) -> None:
        publisher = CloudResultPublisher(
            "https://example.supabase.co", "sb_secret_test", "user-1"
        )
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("modules.cloud_results.urlopen", return_value=response) as send:
            count = publisher.publish(
                "2026-07-24", "oversold_daily_relaxed",
                [{"code": "72030", "expectation_score": 61.2}],
                {"72030": "comment"}, ["https://example.com/72030.png"],
            )
        self.assertEqual(count, 1)
        request = send.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload[0]["user_id"], "user-1")
        self.assertEqual(payload[0]["position"], 1)
        self.assertEqual(payload[0]["expectation_score"], 61.2)
        self.assertIn("on_conflict=user_id,screening_date,profile_name,code", request.full_url)


if __name__ == "__main__":
    unittest.main()
