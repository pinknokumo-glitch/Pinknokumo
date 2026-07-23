import unittest

from modules.screening_relaxation import staged_rules


class ScreeningRelaxationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = {"all": [
            {"field": "daily.rsi_14", "operator": "<=", "value": 20},
            {"field": "weekly.rsi_14", "operator": "<=", "value": 20},
            {"field": "monthly.rsi_14", "operator": "<=", "value": 20},
        ]}
        self.config = {
            "enabled_profiles": ["oversold"],
            "stages": [
                {"id": "daily", "label": "日足のみ緩和",
                 "thresholds": {"daily.rsi_14": 60}},
                {"id": "daily_weekly", "label": "日足・週足を緩和",
                 "thresholds": {"daily.rsi_14": 60, "weekly.rsi_14": 50}},
            ],
        }

    @staticmethod
    def values(rule: dict) -> dict[str, float]:
        return {item["field"]: item["value"] for item in rule["all"]}

    def test_relaxes_daily_then_weekly_while_monthly_stays_fixed(self) -> None:
        stages = staged_rules("oversold", self.rule, self.config)
        self.assertEqual([stage[1] for stage in stages],
                         ["基準条件", "日足のみ緩和", "日足・週足を緩和"])
        self.assertEqual(self.values(stages[0][2]),
                         {"daily.rsi_14": 20, "weekly.rsi_14": 20, "monthly.rsi_14": 20})
        self.assertEqual(self.values(stages[1][2]),
                         {"daily.rsi_14": 60.0, "weekly.rsi_14": 20, "monthly.rsi_14": 20})
        self.assertEqual(self.values(stages[2][2]),
                         {"daily.rsi_14": 60.0, "weekly.rsi_14": 50.0, "monthly.rsi_14": 20})

    def test_does_not_mutate_the_base_rule(self) -> None:
        staged_rules("oversold", self.rule, self.config)
        self.assertEqual(self.values(self.rule)["daily.rsi_14"], 20)

    def test_disabled_profile_uses_only_base_rule(self) -> None:
        self.assertEqual(len(staged_rules("value", self.rule, self.config)), 1)


if __name__ == "__main__":
    unittest.main()
