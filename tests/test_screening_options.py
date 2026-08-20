from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from modules.screening_options import ScreeningOptions
from modules.screening_options import MAX_MANUAL_CONDITIONS


class ScreeningOptionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.options = ScreeningOptions({"screening_options": {
            "genres": [{"id": "value", "label": "割安株", "profile": "value"}],
            "manual_fields": [{"field": "fundamental.per", "label": "PER", "min": 0, "max": 200,
                               "default_operator": "<="}],
        }}, {"active_profile": "value", "profiles": {"value": {"field": "fundamental.per", "operator": "<=", "value": 15}}})

    def test_catalog_marks_available_genres(self) -> None:
        self.assertTrue(self.options.catalog()["genres"][0]["available"])

    def test_manual_rules_are_bounded_and_declarative(self) -> None:
        rule = self.options.manual_rule([{"field": "fundamental.per", "operator": "<=", "value": 12}])
        self.assertEqual(rule["all"][0]["value"], 12.0)
        with self.assertRaises(ValueError):
            self.options.manual_rule([{"field": "fundamental.per", "operator": "<=", "value": 999}])
        with self.assertRaises(ValueError):
            self.options.manual_rule([{"field": "os.system", "operator": "<=", "value": 1}])

    def test_manual_rule_limit_supports_the_expanded_catalog(self) -> None:
        condition = {"field": "fundamental.per", "operator": "<=", "value": 12}
        rule = self.options.manual_rule([condition] * MAX_MANUAL_CONDITIONS)
        self.assertEqual(len(rule["all"]), MAX_MANUAL_CONDITIONS)
        with self.assertRaisesRegex(ValueError, "1 to 128"):
            self.options.manual_rule([condition] * (MAX_MANUAL_CONDITIONS + 1))

    def test_period_presets_are_available_for_every_timeframe(self) -> None:
        with Path("config/screening_options.yaml").open(encoding="utf-8") as file:
            options_config = yaml.safe_load(file)
        with Path("config/screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        options = ScreeningOptions(options_config, screening_config)
        fields = {
            item["field"] for item in options.catalog()["manual_fields"]
        }
        for timeframe in ("daily", "weekly", "monthly"):
            self.assertIn(f"{timeframe}.rsi_9", fields)
            self.assertIn(f"{timeframe}.rsi_14", fields)
            self.assertIn(f"{timeframe}.macd_5_25_9", fields)
            self.assertIn(f"{timeframe}.macd", fields)
            self.assertIn(f"{timeframe}.macd_25_75_14", fields)
            self.assertIn(f"{timeframe}.stoch_k_9_3", fields)
            self.assertIn(f"{timeframe}.stoch_k", fields)
            for period in (5, 25, 75, 200):
                self.assertIn(
                    f"{timeframe}.price_vs_sma_{period}_percent", fields,
                )
        rule = options.manual_rule([
            {"field": "daily.rsi_9", "operator": "<=", "value": 30},
            {"field": "weekly.macd_25_75_14", "operator": ">=", "value": 0},
        ])
        self.assertEqual(len(rule["all"]), 2)


if __name__ == "__main__":
    unittest.main()
