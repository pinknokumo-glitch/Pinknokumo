import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from modules.database import Database
from modules.morning_candidates import MorningCandidateJob


class MorningCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.tempdir.name) / "stockai.db")
        self.database.initialize()
        self.settings = {
            "screening_universe": {"maximum_pool_age_days": 4},
            "providers": {"yfinance": {
                "suffix": ".T", "bulk_incremental_period": "10d",
                "bulk_chunk_size": 100,
            }},
            "resampling": {"weekly_rule": "W-FRI", "monthly_rule": "ME"},
        }
        self.job = MorningCandidateJob(self.database, self.settings)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_loads_a_current_successful_empty_pool(self) -> None:
        today = date.today().isoformat()
        self.database.replace_candidate_pool(
            today, [], universe_count=10, evaluated_count=10, failed_count=0,
        )
        metadata, codes = self.job.load_valid_pool()
        self.assertEqual(metadata["pool_date"], today)
        self.assertEqual(codes, [])

    def test_rejects_a_stale_pool(self) -> None:
        old = (date.today() - timedelta(days=5)).isoformat()
        self.database.replace_candidate_pool(
            old, [], universe_count=10, evaluated_count=10, failed_count=0,
        )
        with self.assertRaisesRegex(RuntimeError, "候補プールが古い"):
            self.job.load_valid_pool()

    def test_rejects_an_incomplete_evening_refresh(self) -> None:
        today = date.today().isoformat()
        self.database.replace_candidate_pool(
            today, [], universe_count=10, evaluated_count=9, failed_count=1,
        )
        with self.assertRaisesRegex(RuntimeError, "未完了"):
            self.job.load_valid_pool()


if __name__ == "__main__":
    unittest.main()
