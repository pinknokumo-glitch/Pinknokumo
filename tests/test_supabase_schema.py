from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def compact_sql(name: str) -> str:
    return " ".join(
        (ROOT / "supabase" / name).read_text(encoding="utf-8").lower().split()
    )


class SupabaseSchemaTests(unittest.TestCase):
    def test_service_role_can_read_preferences(self) -> None:
        sql = compact_sql("screening_preferences.sql")
        self.assertIn(
            "grant select on table public.screening_preferences to service_role;",
            sql,
        )

    def test_service_role_can_publish_screening_results(self) -> None:
        sql = compact_sql("screening_results.sql")
        self.assertIn(
            "grant select, insert, delete on table public.screening_results to service_role;",
            sql,
        )
        self.assertIn(
            "grant select, insert, update on table public.screening_runs to service_role;",
            sql,
        )

    def test_service_role_can_publish_candidate_pool(self) -> None:
        sql = compact_sql("screening_candidates.sql")
        self.assertIn(
            "grant select, insert, delete on table public.screening_candidates to service_role;",
            sql,
        )
        self.assertIn(
            "grant select, insert, delete on table public.screening_candidate_runs to service_role;",
            sql,
        )

    def test_service_role_can_process_backtest_requests(self) -> None:
        sql = compact_sql("backtest_requests.sql")
        self.assertIn(
            "grant select, update on table public.backtest_requests to service_role;",
            sql,
        )

    def test_combined_upgrade_contains_runtime_grants(self) -> None:
        sql = compact_sql("multi_user_upgrade.sql")
        expected = (
            "grant select on table public.screening_preferences to service_role;",
            "grant select, insert, delete on table public.screening_results to service_role;",
            "grant select, insert, update on table public.screening_runs to service_role;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)


if __name__ == "__main__":
    unittest.main()
