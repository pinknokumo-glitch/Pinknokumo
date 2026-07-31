from __future__ import annotations

import os
import json
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_preferences import (
    CloudPreferenceClient,
    apply_expectation_preference,
    apply_preference,
)
from modules.screening_options import ScreeningOptions


class CloudPreferenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.options = ScreeningOptions({"screening_options": {
            "genres": [{"id": "value", "label": "割安株", "profile": "value"}],
            "manual_fields": [{"field": "fundamental.per", "label": "PER", "min": 0, "max": 200,
                               "default_operator": "<="}],
        }}, {"active_profile": "value", "profiles": {"value": {"field": "fundamental.per", "operator": "<=", "value": 15}}})

    def test_environment_is_optional_and_requires_all_server_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(CloudPreferenceClient.from_environment())
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
            self.assertIsNone(CloudPreferenceClient.from_environment())
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
        }, clear=True):
            client = CloudPreferenceClient.from_environment()
            self.assertIsNotNone(client)
            self.assertIsNone(client.user_id)

    def test_auto_and_manual_preferences_are_validated(self) -> None:
        auto = CloudPreferenceClient.validate({"mode": "auto", "genre_id": "value"}, self.options)
        self.assertEqual(auto.genre_id, "value")
        manual = CloudPreferenceClient.validate({
            "mode": "manual", "manual_logic": "all",
            "manual_conditions": [{"field": "fundamental.per", "operator": "<=", "value": 12}],
        }, self.options)
        self.assertEqual(manual.manual_conditions[0]["value"], 12)
        with self.assertRaises(ValueError):
            CloudPreferenceClient.validate({"mode": "auto", "genre_id": "missing"}, self.options)

    def test_current_secret_key_is_not_used_as_a_bearer_token(self) -> None:
        current = CloudPreferenceClient("https://example.supabase.co", "sb_secret_example", "user")
        self.assertNotIn("Authorization", current.headers())
        legacy = CloudPreferenceClient("https://example.supabase.co", "eyJlegacy", "user")
        self.assertEqual(legacy.headers()["Authorization"], "Bearer eyJlegacy")

    def test_preference_is_applied_without_mutating_repository_config(self) -> None:
        source = {"active_profile": "value", "profiles": {"value": {"field": "fundamental.per"}}}
        manual = CloudPreferenceClient.validate({
            "mode": "manual", "manual_logic": "all",
            "manual_conditions": [{"field": "fundamental.per", "operator": "<=", "value": 12}],
        }, self.options)
        resolved, profile = apply_preference(manual, self.options, source)
        self.assertEqual(profile, "cloud_manual")
        self.assertIn("cloud_manual", resolved["profiles"])
        self.assertNotIn("cloud_manual", source["profiles"])

    def test_android_manual_payload_round_trips_to_screening_rule(self) -> None:
        options = ScreeningOptions({"screening_options": {
            "genres": [{"id": "value", "label": "割安株", "profile": "value"}],
            "manual_fields": [
                {"field": "daily.rsi_14", "label": "日足RSI", "min": 0, "max": 100,
                 "default_operator": "<="},
                {"field": "weekly.rsi_14", "label": "週足RSI", "min": 0, "max": 100,
                 "default_operator": "<="},
                {"field": "monthly.rsi_14", "label": "月足RSI", "min": 0, "max": 100,
                 "default_operator": "<="},
            ],
        }}, {"active_profile": "value", "profiles": {"value": {"field": "fundamental.per"}}})
        android_payload = {
            "mode": "manual",
            "genre_id": None,
            "manual_logic": "all",
            "manual_conditions": [
                {"field": f"{period}.rsi_14", "operator": "<=", "value": 20.0}
                for period in ("daily", "weekly", "monthly")
            ],
        }
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps([android_payload]).encode("utf-8")
        client = CloudPreferenceClient("https://example.supabase.co", "sb_secret_test", "user-1")
        with patch("modules.cloud_preferences.urlopen", return_value=response) as send:
            preference = client.fetch(options)
        self.assertIsNotNone(preference)
        resolved, profile = apply_preference(
            preference, options,
            {"active_profile": "value", "profiles": {"value": {"field": "fundamental.per"}}},
        )
        self.assertEqual(profile, "cloud_manual")
        self.assertEqual(
            resolved["profiles"]["cloud_manual"]["all"],
            android_payload["manual_conditions"],
        )
        self.assertIn("user_id=eq.user-1", send.call_args.args[0].full_url)

    def test_latest_saved_user_is_discovered_without_manual_user_secret(self) -> None:
        payload = [{
            "user_id": "user-2", "mode": "auto", "genre_id": "value",
            "manual_logic": "all", "manual_conditions": [],
        }]
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode("utf-8")
        client = CloudPreferenceClient("https://example.supabase.co", "sb_secret_test")
        with patch("modules.cloud_preferences.urlopen", return_value=response) as send:
            preference = client.fetch(self.options)
        self.assertEqual(preference.user_id, "user-2")
        self.assertIn("order=updated_at.desc", send.call_args.args[0].full_url)
        self.assertNotIn("user_id=eq.", send.call_args.args[0].full_url)

    def test_holding_days_is_validated_and_defaults_to_sixty(self) -> None:
        default = CloudPreferenceClient.validate(
            {"mode": "auto", "genre_id": "value"}, self.options
        )
        self.assertEqual(default.holding_days, 60)
        custom = CloudPreferenceClient.validate(
            {"mode": "auto", "genre_id": "value", "holding_days": 360}, self.options
        )
        self.assertEqual(custom.holding_days, 360)
        with self.assertRaises(ValueError):
            CloudPreferenceClient.validate(
                {"mode": "auto", "genre_id": "value", "holding_days": 1001},
                self.options,
            )

    def test_trade_direction_is_validated_and_defaults_to_long(self) -> None:
        default = CloudPreferenceClient.validate(
            {"mode": "auto", "genre_id": "value"}, self.options
        )
        self.assertEqual(default.trade_direction, "long")
        short = CloudPreferenceClient.validate(
            {
                "mode": "auto",
                "genre_id": "value",
                "trade_direction": "short",
            },
            self.options,
        )
        self.assertEqual(short.trade_direction, "short")
        with self.assertRaises(ValueError):
            CloudPreferenceClient.validate(
                {
                    "mode": "auto",
                    "genre_id": "value",
                    "trade_direction": "invalid",
                },
                self.options,
            )

    def test_expectation_evaluation_mode_and_target_are_validated(self) -> None:
        default = CloudPreferenceClient.validate(
            {"mode": "auto", "genre_id": "value"}, self.options
        )
        self.assertEqual(default.expectation_evaluation_mode, "condition_exit")
        self.assertEqual(default.target_return_percent, 5.0)
        target = CloudPreferenceClient.validate(
            {
                "mode": "auto",
                "genre_id": "value",
                "expectation_evaluation_mode": "target_return",
                "target_return_percent": 8.5,
            },
            self.options,
        )
        self.assertEqual(target.expectation_evaluation_mode, "target_return")
        self.assertEqual(target.target_return_percent, 8.5)
        with self.assertRaises(ValueError):
            CloudPreferenceClient.validate(
                {
                    "mode": "auto",
                    "genre_id": "value",
                    "expectation_evaluation_mode": "unknown",
                },
                self.options,
            )

    def test_expectation_rule_can_differ_from_screening_rule(self) -> None:
        preference = CloudPreferenceClient.validate({
            "mode": "auto",
            "genre_id": "value",
            "expectation_mode": "manual",
            "expectation_manual_logic": "all",
            "expectation_manual_conditions": [
                {"field": "fundamental.per", "operator": "<=", "value": 10}
            ],
        }, self.options)
        resolved, profile = apply_expectation_preference(
            preference,
            self.options,
            {"active_profile": "value", "profiles": {
                "value": {"field": "fundamental.per", "operator": "<=", "value": 15}
            }},
        )
        self.assertEqual(profile, "cloud_manual")
        self.assertEqual(
            resolved["profiles"][profile]["all"][0]["value"],
            10,
        )

    def test_empty_manual_expectation_means_period_end_settlement(self) -> None:
        preference = CloudPreferenceClient.validate({
            "mode": "auto",
            "genre_id": "value",
            "expectation_mode": "manual",
            "expectation_manual_conditions": [],
            "expectation_evaluation_mode": "condition_exit",
        }, self.options)

        self.assertEqual(preference.expectation_evaluation_mode, "period_end")
        resolved, profile = apply_expectation_preference(
            preference,
            self.options,
            {"active_profile": "value", "profiles": {
                "value": {"field": "fundamental.per", "operator": "<=", "value": 15}
            }},
        )
        self.assertEqual(profile, "cloud_expectation_none")
        self.assertEqual(resolved["profiles"][profile], {})

    def test_empty_manual_entry_conditions_remain_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "manual conditions"):
            CloudPreferenceClient.validate({
                "mode": "manual",
                "manual_conditions": [],
                "expectation_mode": "manual",
                "expectation_manual_conditions": [],
            }, self.options)

    def test_target_return_does_not_require_an_expectation_rule(self) -> None:
        preference = CloudPreferenceClient.validate({
            "mode": "auto",
            "genre_id": "value",
            "expectation_mode": "manual",
            "expectation_manual_conditions": [],
            "expectation_evaluation_mode": "target_return",
            "target_return_percent": 10,
        }, self.options)
        self.assertEqual(preference.expectation_evaluation_mode, "target_return")

    def test_fetch_all_skips_invalid_user_without_blocking_valid_users(self) -> None:
        payload = [
            {
                "user_id": "valid", "mode": "auto", "genre_id": "value",
                "manual_logic": "all", "manual_conditions": [], "holding_days": 20,
            },
            {
                "user_id": "invalid", "mode": "auto", "genre_id": "missing",
                "manual_logic": "all", "manual_conditions": [], "holding_days": 20,
            },
        ]
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode("utf-8")
        client = CloudPreferenceClient("https://example.supabase.co", "sb_secret_test")
        with patch("modules.cloud_preferences.urlopen", return_value=response):
            preferences = client.fetch_all(self.options)
        self.assertEqual([item.user_id for item in preferences], ["valid"])
        self.assertEqual(client.validation_errors[0]["user_id"], "invalid")


if __name__ == "__main__":
    unittest.main()
