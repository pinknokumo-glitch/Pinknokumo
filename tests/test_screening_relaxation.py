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

    def test_manual_cloud_rule_uses_same_staged_relaxation(self) -> None:
        stages = staged_rules("cloud_manual", self.rule, self.config)
        self.assertEqual(
            [stage[1] for stage in stages],
            ["基準条件", "日足のみ緩和", "日足・週足を緩和"],
        )
        self.assertEqual(self.values(stages[-1][2])["monthly.rsi_14"], 20)

    def test_new_oscillator_periods_relax_daily_then_weekly_only(self) -> None:
        rule = {"all": [
            {"field": "daily.rsi_9", "operator": "<=", "value": 20},
            {"field": "weekly.rsi_9", "operator": "<=", "value": 20},
            {"field": "monthly.rsi_9", "operator": "<=", "value": 20},
            {"field": "daily.stoch_k_9_3", "operator": ">=", "value": 80},
            {"field": "weekly.macd_5_25_9", "operator": ">=", "value": 5},
            {"field": "daily.macd_histogram_25_75_14", "operator": "<=", "value": -5},
        ]}
        config = {"enabled_profiles": ["oversold"], "stages": [
            {
                "id": "daily", "label": "日足のみ緩和",
                "timeframe_relaxation": {
                    "daily": {
                        "oscillator_le": 60, "oscillator_ge": 40,
                        "zero_centered": True,
                    },
                },
            },
            {
                "id": "daily_weekly", "label": "日足・週足を緩和",
                "timeframe_relaxation": {
                    "daily": {
                        "oscillator_le": 60, "oscillator_ge": 40,
                        "zero_centered": True,
                    },
                    "weekly": {
                        "oscillator_le": 50, "oscillator_ge": 50,
                        "zero_centered": True,
                    },
                },
            },
        ]}

        stages = staged_rules("cloud_manual", rule, config)
        daily = self.values(stages[1][2])
        self.assertEqual(daily["daily.rsi_9"], 60)
        self.assertEqual(daily["weekly.rsi_9"], 20)
        self.assertEqual(daily["monthly.rsi_9"], 20)
        self.assertEqual(daily["daily.stoch_k_9_3"], 40)
        self.assertEqual(daily["weekly.macd_5_25_9"], 5)
        self.assertEqual(daily["daily.macd_histogram_25_75_14"], 0)

        daily_weekly = self.values(stages[2][2])
        self.assertEqual(daily_weekly["daily.rsi_9"], 60)
        self.assertEqual(daily_weekly["weekly.rsi_9"], 50)
        self.assertEqual(daily_weekly["monthly.rsi_9"], 20)
        self.assertEqual(daily_weekly["weekly.macd_5_25_9"], 0)

    def test_relaxation_never_tightens_an_already_permissive_condition(self) -> None:
        rule = {"all": [
            {"field": "daily.rsi_9", "operator": "<=", "value": 80},
            {"field": "daily.rsi_14", "operator": ">=", "value": 20},
            {"field": "daily.macd", "operator": ">=", "value": -5},
        ]}
        config = {"stages": [{
            "id": "daily", "timeframe_relaxation": {
                "daily": {
                    "oscillator_le": 60, "oscillator_ge": 40,
                    "zero_centered": True,
                },
            },
        }]}

        values = self.values(staged_rules("cloud_manual", rule, config)[1][2])
        self.assertEqual(values["daily.rsi_9"], 80)
        self.assertEqual(values["daily.rsi_14"], 20)
        self.assertEqual(values["daily.macd"], -5)


if __name__ == "__main__":
    unittest.main()
