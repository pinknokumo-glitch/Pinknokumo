from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def compact_sql(name: str) -> str:
    return " ".join(
        (ROOT / "supabase" / name).read_text(encoding="utf-8").lower().split()
    )


class SupabaseSchemaTests(unittest.TestCase):
    def test_manual_condition_limit_upgrade_matches_the_expanded_catalog(self) -> None:
        sql = compact_sql("manual_condition_limit_upgrade.sql")
        self.assertIn("jsonb_array_length(manual_conditions) <= 128", sql)
        self.assertIn(
            "jsonb_array_length(expectation_manual_conditions) <= 128", sql,
        )
        self.assertNotIn("delete from", sql)

    def test_service_role_can_read_preferences(self) -> None:
        sql = compact_sql("screening_preferences.sql")
        self.assertIn(
            "grant select on table public.screening_preferences to service_role;",
            sql,
        )

    def test_service_role_can_publish_screening_results(self) -> None:
        sql = compact_sql("screening_results.sql")
        self.assertIn(
            "grant select, insert, update, delete on table public.screening_results to service_role;",
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
            "grant select, insert, update, delete on table public.screening_results to service_role;",
            "grant select, insert, update on table public.screening_runs to service_role;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)

    def test_trade_strategy_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("trade_strategy_upgrade.sql")
        expected = (
            "add column if not exists trade_direction text not null default 'long';",
            "add column if not exists expectation_condition_summary text;",
            "add column if not exists relaxation_label text;",
            "add column if not exists relaxation_counts jsonb not null default '[]'::jsonb;",
            "check (trade_direction in ('long', 'short'));",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)

    def test_expectation_evaluation_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("expectation_evaluation_upgrade.sql")
        expected = (
            "add column if not exists expectation_evaluation_mode text not null default 'condition_exit';",
            "add column if not exists target_return_percent double precision not null default 5.0;",
            "add column if not exists outcome_probability_percent double precision;",
            "'condition_exit', 'period_end', 'within_period_up', 'target_return'",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)

    def test_screening_result_upsert_grant_is_rerunnable(self) -> None:
        sql = compact_sql("screening_results_update_grant.sql")
        self.assertIn(
            "grant select, insert, update, delete on table public.screening_results to service_role;",
            sql,
        )

    def test_holding_period_upgrade_preserves_rows_and_allows_360_days(self) -> None:
        sql = compact_sql("holding_period_upgrade.sql")
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)
        for table in ("screening_preferences", "screening_results", "screening_runs"):
            with self.subTest(table=table):
                self.assertIn(
                    f"alter table public.{table} drop constraint if exists {table}_holding_days_check;",
                    sql,
                )
        self.assertGreaterEqual(sql.count("between 1 and 1000"), 3)

    def test_conditional_price_estimate_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("conditional_price_estimate_upgrade.sql")
        expected = (
            "add column if not exists reference_price double precision;",
            "add column if not exists estimated_price_median double precision;",
            "add column if not exists estimated_price_low double precision;",
            "add column if not exists estimated_price_high double precision;",
            "add column if not exists estimate_sample_count integer not null default 0;",
            "add column if not exists median_days_to_outcome double precision;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)

    def test_outcome_probability_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("outcome_probability_upgrade.sql")
        expected = (
            "add column if not exists profit_10_probability_percent double precision;",
            "add column if not exists profit_20_probability_percent double precision;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)

    def test_screening_result_summary_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("screening_result_summary_upgrade.sql")
        expected = (
            "add column if not exists average_return_percent double precision;",
            "add column if not exists win_rate_percent double precision;",
            "add column if not exists max_drawdown_percent double precision;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)

    def test_pooled_backtest_upgrade_is_rerunnable(self) -> None:
        sql = compact_sql("pooled_backtest_upgrade.sql")
        expected = (
            "add column if not exists individual_trade_count integer not null default 0;",
            "add column if not exists sector_backtest jsonb not null default '{}'::jsonb;",
            "add column if not exists market_backtest jsonb not null default '{}'::jsonb;",
            "add column if not exists backtest_coverage_ratio double precision;",
            "add column if not exists backtest_confidence text;",
        )
        for statement in expected:
            with self.subTest(statement=statement):
                self.assertIn(statement, sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)


if __name__ == "__main__":
    unittest.main()
