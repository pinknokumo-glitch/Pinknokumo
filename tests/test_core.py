"""Regression tests for StockAI modules that do not require network access."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.database import Database
from modules.ai_comment import AnalysisCommentary
from modules.daily_job import DailyUpdateJob
from modules.fundamentals import FundamentalAnalyzer
from modules.health import HealthChecker
from modules.notifier import LineNotifier, format_candidate_message, format_screening_message
from modules.optimizer import HitCountOptimizer
from modules.portfolio import PortfolioAnalyzer
from modules.reporting import DailyReportBuilder
from modules.chart import StockChartRenderer
from modules.github_publisher import GitHubPublisher
from scripts.render_chart_png import _render_pixels, _write_png
from modules.rule_engine import RuleEngine
from modules.repository import StockRepository
from modules.simulation import PortfolioSimulator


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "stockai.db")
        self.db.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_notification_duplicate_detection_only_counts_sent_messages(self) -> None:
        message = "判定基準日: 2026-07-22\n銘柄: 72030"
        self.assertFalse(self.db.was_notification_sent("line", message))
        self.db.save_notification("line", "network_error", message)
        self.assertFalse(self.db.was_notification_sent("line", message))
        self.db.save_notification("line", "sent", message)
        self.assertTrue(self.db.was_notification_sent("line", message))
        self.assertFalse(self.db.was_notification_sent("line", message + " changed"))

    def test_watchlist_and_portfolio(self) -> None:
        self.db.add_to_watchlist("72030", "initial")
        self.db.add_to_watchlist("72030", "updated")
        self.db.save_portfolio_position("72030", 100, 2000)
        self.db.upsert_rows("price_daily", [{
            "code": "72030", "trade_date": "2026-01-01", "open": 2000, "high": 2150, "low": 1950,
            "close": 2100, "adjusted_close": 2100, "volume": 100, "dividends": 0, "stock_splits": 0,
        }], ["code", "trade_date"])
        with self.db.connect() as connection:
            watch = connection.execute("SELECT note FROM watchlist WHERE code='72030'").fetchone()
            portfolio = PortfolioAnalyzer(connection).positions()
        self.assertEqual(watch["note"], "updated")
        self.assertEqual(portfolio["positions"][0]["unrealized_profit_loss"], 10000)

    def test_import_watchlist_by_scale_preserves_existing_entries(self) -> None:
        self.db.upsert_rows("master_stock", [
            {"code": "11110", "scale_category": "TOPIX Core30", "delisted_date": None},
            {"code": "22220", "scale_category": "TOPIX Core30", "delisted_date": "2025-01-01"},
            {"code": "33330", "scale_category": "TOPIX Large70", "delisted_date": None},
        ], ["code"])
        self.db.add_to_watchlist("11110", "existing")
        added = self.db.import_watchlist_by_scale(["TOPIX Core30"], "bulk")
        self.assertEqual(0, added)
        with self.db.connect() as connection:
            rows = connection.execute("SELECT code, note FROM watchlist ORDER BY code").fetchall()
        self.assertEqual([("11110", "existing")], [(row["code"], row["note"]) for row in rows])

    def test_market_universe_and_empty_candidate_pool_are_persisted(self) -> None:
        self.db.upsert_rows("master_stock", [
            {"code": "11110", "market_name": "プライム", "delisted_date": None},
            {"code": "22220", "market_name": "スタンダード", "delisted_date": None},
            {"code": "33330", "market_name": "その他", "delisted_date": None},
        ], ["code"])
        count = self.db.sync_screening_universe(["プライム", "スタンダード", "グロース"])
        self.assertEqual(count, 2)
        self.assertEqual(self.db.screening_universe_codes(), ["11110", "22220"])
        saved = self.db.replace_candidate_pool(
            "2026-07-23", [], universe_count=2, evaluated_count=2, failed_count=0,
        )
        self.assertEqual(saved, 0)
        metadata, codes = self.db.latest_candidate_pool()
        self.assertEqual(metadata["candidate_count"], 0)
        self.assertEqual(metadata["status"], "success")
        self.assertEqual(codes, [])

    def test_daily_report_contains_local_summary(self) -> None:
        self.db.add_to_watchlist("72030", "report target")
        self.db.save_job_run("daily_update", "success", {"updated": ["72030"]})
        self.db.upsert_rows("market_regime", [{
            "market_code": "NIKKEI225", "trade_date": "2026-01-10", "regime": "bullish",
            "close": 40000, "sma_short": 39000, "sma_long": 38000,
        }], ["market_code", "trade_date"])
        with self.db.connect() as connection:
            report = DailyReportBuilder(connection).build()
        self.assertIn("generated_at", report)
        self.assertIn("health", report)
        self.assertEqual(report["watchlist"][0]["code"], "72030")
        self.assertEqual(report["recent_jobs"][0]["details"]["updated"], ["72030"])
        self.assertEqual(report["market_regimes"][0]["regime"], "bullish")

    def test_operations_status_combines_evening_and_morning_runs(self) -> None:
        self.db.replace_candidate_pool(
            "2026-07-23", [{"code": "72030"}],
            universe_count=3800, evaluated_count=3798, failed_count=2,
        )
        self.db.save_job_run("evening_universe", "partial_failure", {
            "updated_count": 3798, "failed_count": 2,
        })
        self.db.save_job_run("morning_candidates", "success", {
            "updated_count": 1, "failed_count": 0,
        })
        self.db.save_job_run("morning_screening", "success", {
            "screening_date": "2026-07-24", "effective_profile": "rsi_relaxed_daily",
            "relaxation_label": "日足のみ緩和", "hit_count": 1,
        })
        with self.db.connect() as connection:
            status = StockRepository(connection).operations_status()
        self.assertFalse(status["ready"])
        self.assertEqual(status["pool"]["universe_count"], 3800)
        self.assertEqual(status["evening_update"]["details"]["failed_count"], 2)
        self.assertEqual(status["morning_screening"]["details"]["hit_count"], 1)

    def test_chart_renderer_creates_svg_from_stored_prices(self) -> None:
        rows = []
        for day in range(1, 81):
            close = 100 + day
            rows.append({"trade_date": f"2026-01-{(day - 1) % 28 + 1:02d}", "open": close - 1, "high": close + 2, "low": close - 3, "close": close})
        svg = StockChartRenderer.render("72030", rows, "テスト会社")
        self.assertIn("テスト会社 (72030) 日足", svg)
        self.assertIn("25日移動平均", svg)
        self.assertIn("<rect", svg)

    def test_png_chart_renderer_writes_valid_png(self) -> None:
        prices = [
            {"trade_date": f"2026-01-{day:02d}", "open": 100 + day, "high": 103 + day,
             "low": 98 + day, "close": 101 + day}
            for day in range(1, 80)
        ]
        width, height, pixels = _render_pixels(prices)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.png"
            _write_png(path, width, height, pixels)
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_github_publisher_url_and_validation(self) -> None:
        publisher = GitHubPublisher("pinknokumo-glitch/Pinknokumo", "token")
        self.assertEqual(
            publisher.public_url("charts/72030.png"),
            "https://pinknokumo-glitch.github.io/Pinknokumo/charts/72030.png",
        )
        with self.assertRaises(ValueError):
            GitHubPublisher("invalid", "token")

    def test_stock_overview_combines_local_data(self) -> None:
        with self.db.connect() as connection:
            connection.execute("INSERT INTO master_stock (code, company_name, sector_33_name) VALUES (?, ?, ?)", ["72030", "テスト", "輸送用機器"])
            connection.execute(
                """INSERT INTO price_daily (code, trade_date, open, high, low, close, adjusted_close, volume, dividends, stock_splits)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ["72030", "2026-01-10", 100, 101, 99, 100, 100, 1000, 5, 0],
            )
            connection.execute(
                """INSERT INTO financial (code, disclosed_date, document_type, earnings_per_share, book_value_per_share,
                   profit, equity, total_assets, equity_ratio, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ["72030", "2026-01-05", "FY", 10, 100, 20, 100, 200, 0.5, "{}"],
            )
            overview = StockRepository(connection).overview("72030")
        self.assertEqual(overview["master"]["company_name"], "テスト")
        self.assertEqual(overview["latest_price"]["close"], 100)
        self.assertEqual(overview["fundamentals"]["per"], 10)
        self.assertEqual(overview["fundamentals"]["dividend_yield"], 5)

    def test_relative_performance_uses_common_trade_dates(self) -> None:
        rows = []
        for code, closes in (("72030", [100, 110, 120]), ("NIKKEI225", [200, 210, 216])):
            for day, close in enumerate(closes, start=1):
                rows.append({
                    "code": code, "trade_date": f"2026-01-0{day}", "open": close, "high": close,
                    "low": close, "close": close, "adjusted_close": close, "volume": 100,
                    "dividends": 0, "stock_splits": 0,
                })
        self.db.upsert_rows("price_daily", rows, ["code", "trade_date"])
        with self.db.connect() as connection:
            performance = StockRepository(connection).relative_performance("72030", "NIKKEI225")
        self.assertEqual(performance, [])  # Fewer than the minimum 20-session comparison window.

    def test_market_indices_are_excluded_from_rankings(self) -> None:
        result = {"expectation": {"score": 60, "grade": "B"}, "summary": {}}
        self.db.save_analysis_snapshot("NIKKEI225", "2026-01-10", "momentum", "backtest", result)
        self.db.save_analysis_snapshot("72030", "2026-01-10", "momentum", "backtest", result)
        self.db.upsert_rows("market_regime", [{
            "market_code": "NIKKEI225", "trade_date": "2026-01-10", "regime": "bullish",
            "close": 40000, "sma_short": 39000, "sma_long": 38000,
        }], ["market_code", "trade_date"])
        with self.db.connect() as connection:
            rankings = StockRepository(connection).latest_rankings()
        self.assertEqual([item["code"] for item in rankings], ["72030"])

    def test_health_reports_missing_and_current_price_data(self) -> None:
        with self.db.connect() as connection:
            missing = HealthChecker(connection).report()
        self.assertEqual(missing["price_data_status"], "missing")
        self.assertEqual(missing["status"], "degraded")
        self.db.upsert_rows("price_daily", [{
            "code": "72030", "trade_date": date.today().isoformat(), "open": 100, "high": 101, "low": 99,
            "close": 100, "adjusted_close": 100, "volume": 100, "dividends": 0, "stock_splits": 0,
        }], ["code", "trade_date"])
        with self.db.connect() as connection:
            current = HealthChecker(connection).report()
        self.assertEqual(current["price_data_status"], "current")
        self.assertEqual(current["price_age_days"], 0)
        self.assertEqual(current["status"], "ok")


class RuleAndMetricTestCase(unittest.TestCase):
    def test_integrated_comment_includes_fundamentals_and_missing_data_state(self) -> None:
        comment = AnalysisCommentary.integrated_comment({
            "daily.rsi_14": 42.5, "weekly.rsi_14": 47.0, "monthly.rsi_14": 49.0,
            "daily.close": 1200, "daily.sma_25": 1250, "daily.sma_75": 1100,
            "daily.macd": -2, "daily.macd_signal": -1,
            "fundamental.disclosed_date": "2026-06-30", "fundamental.per": 12,
            "fundamental.pbr": 0.9, "fundamental.roe": 11, "fundamental.equity_ratio": 55,
            "fundamental.operating_cash_flow": 100, "expectation_score": 65,
        }, "過去シグナルは十分です。")
        self.assertIn("【テクニカル】", comment)
        self.assertIn("日足42.5", comment)
        self.assertIn("【ファンダメンタル】", comment)
        self.assertIn("開示日2026-06-30", comment)
        self.assertIn("PER12.0倍", comment)
        self.assertIn("【バックテスト】", comment)
        self.assertIn("【総合所見】", comment)
        missing = AnalysisCommentary.integrated_comment({}, None)
        self.assertIn("ファンダメンタル評価は未実施", missing)
        self.assertIn("バックテスト結果は未算出", missing)

    def test_notification_format_and_disabled_state(self) -> None:
        message = format_screening_message(
            "momentum", [{"code": "72030", "company_name": "テスト自動車", "expectation_score": 50.8,
                          "reason": "daily.close > daily.sma_25"}],
            comments_by_code={"72030": "統計コメント"}, as_of_date="2026-07-21",
            evaluated_count=31,
        )
        self.assertIn("テスト自動車（72030）", message)
        self.assertIn("期待値スコア: 50.8/100", message)
        self.assertIn("判定基準日: 2026-07-21", message)
        self.assertIn("判定対象: 31銘柄", message)
        self.assertIn("抽出理由:", message)
        self.assertIn("統計コメント", message)
        result = LineNotifier({"notification": {"line": {"enabled": False}}}).send(message)
        self.assertEqual(result.status, "disabled")

    def test_line_chart_urls_are_opt_in_and_https_only(self) -> None:
        notifier = LineNotifier({"notification": {"line": {
            "enabled": False, "chart_public_url_template": "https://example.com/charts/{code}.png", "max_chart_images": 1,
        }}})
        urls = notifier.chart_urls(["72030", "99840"])
        self.assertEqual(urls, ["https://example.com/charts/72030.png"])
        messages = notifier.build_messages("summary", urls)
        self.assertEqual(messages[1]["type"], "image")
        self.assertEqual(messages[1]["originalContentUrl"], urls[0])

        invalid = LineNotifier({"notification": {"line": {"enabled": False, "chart_public_url_template": "http://example.com/{code}.png"}}})
        with self.assertRaises(ValueError):
            invalid.chart_urls(["72030"])

    def test_candidate_message_pairs_one_comment_with_one_chart(self) -> None:
        hit = {"code": "72030", "company_name": "テスト自動車", "expectation_score": 61.2,
               "reason": "all conditions matched"}
        message = format_candidate_message(
            "oversold", hit, 2, 3, "この銘柄専用のコメント", "2026-07-22",
        )
        self.assertIn("候補 2/3", message)
        self.assertIn("テスト自動車（72030）", message)
        self.assertIn("この銘柄専用のコメント", message)
        messages = LineNotifier.build_messages(message, ["https://example.com/charts/72030.png"])
        self.assertEqual([item["type"] for item in messages], ["text", "image"])
        self.assertIn("72030", messages[1]["originalContentUrl"])

    def test_daily_update_ticker_translation(self) -> None:
        self.assertEqual(DailyUpdateJob.ticker_for_code("72030", ".T"), "7203.T")
        self.assertEqual(DailyUpdateJob.ticker_for_code("7203", ".T"), "7203.T")
        self.assertEqual(DailyUpdateJob.ticker_for_code("^N225", ".T"), "^N225")
        self.assertEqual(DailyUpdateJob.ticker_for_code("AAPL", ".T"), "AAPL")
        self.assertEqual(DailyUpdateJob.incremental_start("2026-01-10", 7), "2026-01-03")
        self.assertIsNone(DailyUpdateJob.incremental_start(None, 7))

    def test_daily_update_includes_configured_market_index(self) -> None:
        settings = {
            "providers": {"yfinance": {"suffix": ".T", "daily_update_overlap_days": 7}},
            "market_indices": [{"code": "NIKKEI225", "ticker": "^N225"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "stockai.db")
            database.initialize()
            job = DailyUpdateJob(database, settings)
            job.loader = MagicMock()
            job.loader.load_yfinance_prices.return_value = 1
            result = job.run()
            job.loader.load_yfinance_prices.assert_called_once_with("^N225", "NIKKEI225", period="10y", start=None)
            self.assertEqual(result["market_index_count"], 1)

    def test_daily_update_refreshes_domestic_watchlist_financials(self) -> None:
        settings = {
            "providers": {
                "yfinance": {"suffix": ".T", "daily_update_overlap_days": 7},
                "jquants": {"daily_financial_update": True},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "stockai.db")
            database.initialize()
            database.add_to_watchlist("72030")
            job = DailyUpdateJob(database, settings)
            job.loader = MagicMock()
            job.loader.load_yfinance_prices.return_value = 1
            job.loader.load_jquants_financial.return_value = 2
            result = job.run()
            job.loader.load_jquants_financial.assert_called_once_with("72030")
            self.assertEqual(result["financial_updated"], [{"code": "72030", "financial_rows": 2}])

    def test_daily_update_persists_market_regime(self) -> None:
        settings = {"providers": {"yfinance": {"suffix": ".T"}}}
        regime_config = {
            "market_regime": {
                "short_moving_average": 2, "long_moving_average": 3,
                "labels": {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral"},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "stockai.db")
            database.initialize()
            database.upsert_rows("price_daily", [{
                "code": "NIKKEI225", "trade_date": f"2026-01-0{day}", "open": value, "high": value,
                "low": value, "close": value, "adjusted_close": value, "volume": 100, "dividends": 0, "stock_splits": 0,
            } for day, value in enumerate([1, 2, 3], start=1)], ["code", "trade_date"])
            result = DailyUpdateJob(database, settings, regime_config)._update_market_regime("NIKKEI225")
            with database.connect() as connection:
                regime = connection.execute(
                    "SELECT regime FROM market_regime WHERE market_code=? AND trade_date=?", ["NIKKEI225", "2026-01-03"]
                ).fetchone()["regime"]
        self.assertEqual(result["current_regime"], "bullish")
        self.assertEqual(regime, "bullish")

    def test_rule_engine(self) -> None:
        rule = {"all": [{"field": "rsi", "operator": "<=", "value": 30}, {"not": {"field": "close", "operator": "<", "value": 100}}]}
        self.assertTrue(RuleEngine().evaluate(rule, {"rsi": 25.0, "close": 120.0}).matched)

    def test_financial_ratios(self) -> None:
        values = FundamentalAnalyzer().latest_values({
            "earnings_per_share": 100, "book_value_per_share": 1000, "profit": 100,
            "equity": 800, "total_assets": 2000, "operating_profit": 150,
            "net_sales": 1000, "equity_ratio": 0.4,
        }, 1200, 60)
        self.assertEqual(values["per"], 12)
        self.assertEqual(values["roe"], 12.5)
        self.assertEqual(values["equity_ratio"], 40)
        self.assertEqual(values["dividend_yield"], 5)

    def test_optimizer_does_not_mutate_input(self) -> None:
        snapshots = [{"daily.rsi_14": value} for value in [10, 20, 30, 40, 50]]
        result = HitCountOptimizer().suggest(snapshots, "daily.rsi_14", "<=", 2, 3)
        self.assertIn(result["estimated_hit_count"], {2, 3})
        self.assertEqual(len(snapshots), 5)


class SimulationTestCase(unittest.TestCase):
    def test_capital_and_position_limits(self) -> None:
        trades = [
            SimpleNamespace(entry_date="2025-01-01", exit_date="2025-01-10", return_percent=10.0),
            SimpleNamespace(entry_date="2025-01-05", exit_date="2025-01-12", return_percent=20.0),
            SimpleNamespace(entry_date="2025-01-11", exit_date="2025-01-20", return_percent=-10.0),
        ]
        result = PortfolioSimulator().run(trades, {"simulation": {"initial_capital": 1000, "position_size": 500, "max_positions": 1}})
        self.assertEqual(result["realised_trade_count"], 2)
        self.assertEqual(result["skipped_trade_count"], 1)
        self.assertEqual(result["final_capital"], 1000)


if __name__ == "__main__":
    unittest.main()
