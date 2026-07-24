from __future__ import annotations

import os
import json
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_preferences import CloudPreferenceClient, apply_preference
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


if __name__ == "__main__":
    unittest.main()
