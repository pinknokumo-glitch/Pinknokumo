from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_candidates import CloudCandidatePublisher


class CloudCandidatePublisherTests(unittest.TestCase):
    def test_zero_candidate_run_still_publishes_coverage_metadata(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        publisher = CloudCandidatePublisher(
            "https://example.supabase.co", "sb_secret_test"
        )
        with patch("modules.cloud_candidates.urlopen", return_value=response) as send:
            count = publisher.replace(
                "2026-07-27",
                [],
                {
                    "universe_count": 3800,
                    "evaluated_count": 3750,
                    "failed_count": 50,
                    "coverage_ratio": 0.9868,
                    "status": "success",
                    "usable": True,
                },
            )
        self.assertEqual(count, 0)
        self.assertEqual(send.call_count, 2)
        run_request = send.call_args.args[0]
        payload = json.loads(run_request.data.decode("utf-8"))[0]
        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(payload["universe_count"], 3800)
        self.assertEqual(payload["evaluated_count"], 3750)
        self.assertEqual(payload["failed_count"], 50)
        self.assertTrue(payload["usable"])
        self.assertIn("on_conflict=pool_date", run_request.full_url)

    def test_candidate_rows_and_run_metadata_are_both_published(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        publisher = CloudCandidatePublisher(
            "https://example.supabase.co", "sb_secret_test"
        )
        with patch("modules.cloud_candidates.urlopen", return_value=response) as send:
            count = publisher.replace(
                "2026-07-27",
                ["72030", "67580"],
                {"candidate_count": 99, "usable": True},
            )
        self.assertEqual(count, 2)
        self.assertEqual(send.call_count, 3)
        run_request = send.call_args.args[0]
        payload = json.loads(run_request.data.decode("utf-8"))[0]
        self.assertEqual(payload["candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
