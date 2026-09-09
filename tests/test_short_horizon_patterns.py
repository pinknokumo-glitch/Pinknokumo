"""Focused tests for independent short-horizon pattern research."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from modules.database import Database
from modules.short_horizon_patterns import ShortHorizonPatternScanner
from scripts.confirm_short_patterns import confirmation


class ShortHorizonPatternTestCase(unittest.TestCase):
    def setUp(self) -> None:
        settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
        indicators = yaml.safe_load(Path("config/indicators.yaml").read_text(encoding="utf-8"))
        settings["short_horizon_patterns"] = {
            **settings["short_horizon_patterns"],
            "minimum_trade_count": 1,
            "minimum_oos_trade_count": 1,
            "minimum_probability_percent": 0,
        }
        self.scanner = ShortHorizonPatternScanner(indicators, settings)

    def test_outcome_enters_at_next_session_open_not_signal_close(self) -> None:
        frame = pd.DataFrame({
            "trade_date": pd.date_range("2026-01-01", periods=4),
            "open": [100.0, 110.0, 111.0, 112.0],
            "high": [101.0, 114.0, 115.0, 116.0],
            "low": [99.0, 109.0, 110.0, 111.0],
            "close": [100.0, 112.0, 114.0, 115.0],
            "volume": [1000.0] * 4,
        })
        outcome = self.scanner._outcome(frame, signal_index=0, horizon=2, direction="long")
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["target_hit"], 1.0)
        self.assertAlmostEqual(outcome["terminal_return"], (114 / 110 - 1) * 100)

    def test_short_outcome_uses_low_for_target_and_high_for_adverse(self) -> None:
        frame = pd.DataFrame({
            "trade_date": pd.date_range("2026-01-01", periods=4),
            "open": [100.0, 100.0, 96.0, 94.0],
            "high": [101.0, 104.0, 97.0, 95.0],
            "low": [99.0, 95.0, 92.0, 90.0],
            "close": [100.0, 96.0, 94.0, 92.0],
            "volume": [1000.0] * 4,
        })
        outcome = self.scanner._outcome(frame, signal_index=0, horizon=2, direction="short")
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["target_hit"], 1.0)
        self.assertAlmostEqual(outcome["adverse"], (100 / 104 - 1) * 100)

    def test_summary_uses_latest_chronological_slice_as_out_of_sample(self) -> None:
        summary = self.scanner._summary([
            {"signal_date": "2026-01-01", "target_hit": 0.0, "terminal_return": -1.0, "adverse": -2.0},
            {"signal_date": "2026-01-02", "target_hit": 0.0, "terminal_return": -1.0, "adverse": -2.0},
            {"signal_date": "2026-01-03", "target_hit": 0.0, "terminal_return": -1.0, "adverse": -2.0},
            {"signal_date": "2026-01-04", "target_hit": 0.0, "terminal_return": -1.0, "adverse": -2.0},
            {"signal_date": "2026-01-05", "target_hit": 1.0, "terminal_return": 4.0, "adverse": -1.0},
        ])
        self.assertEqual(summary["trade_count"], 5)
        self.assertEqual(summary["out_of_sample_trade_count"], 1)
        self.assertEqual(summary["out_of_sample_target_probability_percent"], 100.0)

    def test_eligibility_requires_recent_out_of_sample_probability(self) -> None:
        self.scanner.minimum_probability_percent = 55.0
        stats = {
            "trade_count": 30,
            "target_probability_percent": 80.0,
            "out_of_sample_trade_count": 6,
            "out_of_sample_target_probability_percent": 0.0,
        }
        self.assertFalse(self.scanner._eligible(stats))

    def test_confirmation_rebases_target_without_changing_probability(self) -> None:
        result = confirmation({
            "direction": "long", "target_percent": 3.0, "target_probability_percent": 61.5,
            "resistance_price": 105.0, "support_price": 90.0,
        }, {"price": 103.0, "observed_at": "2026-09-09T00:10:00+00:00"})
        self.assertEqual(result["target_probability_percent"], 61.5)
        self.assertAlmostEqual(result["morning_target_price"], 106.09)
        self.assertEqual(result["confirmation_status"], "目標までに節目の突破が必要")

    def test_local_results_are_replaced_atomically_by_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "stockai.db")
            database.initialize()
            database.replace_short_patterns("run-1", "2026-09-08", "source", [
                {"position": 1, "code": "11110", "direction": "long"},
            ])
            database.replace_short_patterns("run-1", "2026-09-08", "source", [
                {"position": 1, "code": "22220", "direction": "short"},
            ])
            metadata, rows = database.latest_short_patterns()
        self.assertEqual(metadata["run_id"], "run-1")
        self.assertEqual(rows, [{"position": 1, "code": "22220", "direction": "short"}])


if __name__ == "__main__":
    unittest.main()
