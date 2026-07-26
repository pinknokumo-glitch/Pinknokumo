from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_results import CloudResultPublisher


class CloudResultPublisherTests(unittest.TestCase):
    def test_explicit_preference_user_replaces_optional_environment_user(self) -> None:
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            "STOCKAI_USER_ID": "legacy-user",
        }, clear=True):
            publisher = CloudResultPublisher.from_environment("latest-user")
        self.assertIsNotNone(publisher)
        self.assertEqual(publisher.user_id, "latest-user")

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
                holding_days=20,
                condition_summary='{"all":[]}',
                expectation_condition_summary='{"any":[]}',
                trade_direction="short",
            )
        self.assertEqual(count, 1)
        request = send.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload[0]["user_id"], "user-1")
        self.assertEqual(payload[0]["position"], 1)
        self.assertEqual(payload[0]["expectation_score"], 61.2)
        self.assertEqual(payload[0]["holding_days"], 20)
        self.assertEqual(payload[0]["condition_summary"], '{"all":[]}')
        self.assertEqual(
            payload[0]["expectation_condition_summary"], '{"any":[]}'
        )
        self.assertEqual(payload[0]["trade_direction"], "short")
        self.assertIn("on_conflict=user_id,screening_date,profile_name,code", request.full_url)

    def test_replace_deletes_only_the_target_users_previous_results(self) -> None:
        publisher = CloudResultPublisher(
            "https://example.supabase.co", "sb_secret_test", "user-1"
        )
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("modules.cloud_results.urlopen", return_value=response) as send:
            count = publisher.replace("2026-07-25", "cloud-profile", [], {})
        self.assertEqual(count, 0)
        request = send.call_args.args[0]
        self.assertEqual(request.method, "DELETE")
        self.assertIn("user_id=eq.user-1", request.full_url)

    def test_publish_run_records_zero_hit_completion(self) -> None:
        publisher = CloudResultPublisher(
            "https://example.supabase.co", "sb_secret_test", "user-1"
        )
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("modules.cloud_results.urlopen", return_value=response) as send:
            publisher.publish_run(
                "2026-07-25",
                "cloud-profile",
                20,
                '{"all":[]}',
                0,
                expectation_condition_summary='{"any":[]}',
                trade_direction="long",
                relaxation_label="日足・週足を緩和",
                relaxation_counts=[
                    {"stage": "基準条件", "hit_count": 0},
                    {"stage": "日足・週足を緩和", "hit_count": 2},
                ],
            )
        request = send.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload[0]["hit_count"], 0)
        self.assertEqual(payload[0]["holding_days"], 20)
        self.assertEqual(payload[0]["relaxation_counts"][1]["hit_count"], 2)
        self.assertIn("on_conflict=user_id", request.full_url)


if __name__ == "__main__":
    unittest.main()
