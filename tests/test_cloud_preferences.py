from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from modules.cloud_preferences import CloudPreferenceClient
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


if __name__ == "__main__":
    unittest.main()
