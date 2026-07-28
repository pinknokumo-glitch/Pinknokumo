from __future__ import annotations

import json
from io import BytesIO
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

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
                [{
                    "code": "72030",
                    "expectation_score": 61.2,
                    "average_return_percent": 8.4,
                    "win_rate_percent": 62.5,
                    "max_drawdown_percent": -12.3,
                    "reference_price": 1000.0,
                    "estimated_price_median": 1080.0,
                    "estimated_price_low": 1030.0,
                    "estimated_price_high": 1140.0,
                    "estimate_sample_count": 42,
                    "median_days_to_outcome": 18.0,
                    "individual_trade_count": 25,
                    "individual_out_of_sample_trade_count": 5,
                    "individual_out_of_sample_average_return_percent": 4.2,
                    "individual_out_of_sample_win_rate_percent": 60.0,
                    "sector_name": "輸送用機器",
                    "sector_backtest": {
                        "stock_count": 20,
                        "trade_count": 300,
                        "average_return_percent": 3.1,
                    },
                    "market_backtest": {
                        "stock_count": 200,
                        "trade_count": 3000,
                        "average_return_percent": 2.2,
                    },
                    "backtest_coverage_ratio": 0.97,
                    "backtest_confidence": "高",
                }],
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
        self.assertEqual(payload[0]["average_return_percent"], 8.4)
        self.assertEqual(payload[0]["win_rate_percent"], 62.5)
        self.assertEqual(payload[0]["max_drawdown_percent"], -12.3)
        self.assertEqual(payload[0]["holding_days"], 20)
        self.assertEqual(payload[0]["condition_summary"], '{"all":[]}')
        self.assertEqual(
            payload[0]["expectation_condition_summary"], '{"any":[]}'
        )
        self.assertEqual(payload[0]["trade_direction"], "short")
        self.assertEqual(payload[0]["reference_price"], 1000.0)
        self.assertEqual(payload[0]["estimated_price_median"], 1080.0)
        self.assertEqual(payload[0]["estimated_price_low"], 1030.0)
        self.assertEqual(payload[0]["estimated_price_high"], 1140.0)
        self.assertEqual(payload[0]["estimate_sample_count"], 42)
        self.assertEqual(payload[0]["median_days_to_outcome"], 18.0)
        self.assertEqual(payload[0]["individual_trade_count"], 25)
        self.assertEqual(payload[0]["sector_name"], "輸送用機器")
        self.assertEqual(payload[0]["sector_backtest"]["stock_count"], 20)
        self.assertEqual(payload[0]["market_backtest"]["trade_count"], 3000)
        self.assertEqual(payload[0]["backtest_coverage_ratio"], 0.97)
        self.assertEqual(payload[0]["backtest_confidence"], "高")
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

    def test_publish_replaces_non_finite_numbers_with_null(self) -> None:
        publisher = CloudResultPublisher(
            "https://example.supabase.co", "sb_secret_test", "user-1"
        )
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("modules.cloud_results.urlopen", return_value=response) as send:
            publisher.publish(
                "2026-07-25",
                "cloud-profile",
                [{
                    "code": "72030",
                    "expectation_score": float("nan"),
                    "outcome_probability_percent": float("inf"),
                }],
                {},
                [],
            )
        payload = json.loads(send.call_args.args[0].data.decode("utf-8"))
        self.assertIsNone(payload[0]["expectation_score"])
        self.assertIsNone(payload[0]["outcome_probability_percent"])

    def test_publish_error_contains_supabase_response_body(self) -> None:
        publisher = CloudResultPublisher(
            "https://example.supabase.co", "sb_secret_test", "user-1"
        )
        error = HTTPError(
            "https://example.supabase.co/rest/v1/screening_results",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"message":"missing column"}'),
        )
        with patch("modules.cloud_results.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "missing column"):
                publisher.publish(
                    "2026-07-25",
                    "cloud-profile",
                    [{"code": "72030"}],
                    {},
                    [],
                )


if __name__ == "__main__":
    unittest.main()
