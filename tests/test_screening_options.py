from __future__ import annotations

import unittest

from modules.screening_options import ScreeningOptions


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


if __name__ == "__main__":
    unittest.main()
