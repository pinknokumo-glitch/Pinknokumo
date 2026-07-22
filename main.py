from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd
import yaml

from modules.database import Database
from modules.data_loader import DataLoader
from modules.screener import Screener
from modules.backtest import Backtester
from modules.expectation import ExpectationScorer
from modules.ai_comment import AnalysisCommentary
from modules.notifier import LineNotifier, format_screening_message
from modules.regime import MarketRegimeAnalyzer
from modules.sector import SectorAnalyzer
from modules.optimizer import HitCountOptimizer
from modules.simulation import PortfolioSimulator
from modules.portfolio import PortfolioAnalyzer
from modules.daily_job import DailyUpdateJob
from modules.health import HealthChecker
from modules.repository import StockRepository
from modules.config_validation import ConfigValidator
from modules.regime_backtest import RegimeBacktestAnalyzer
from modules.batch_backtest import BatchBacktester
from modules.reporting import DailyReportBuilder
from modules.chart import StockChartRenderer

ROOT = Path(__file__).resolve().parent

def load_timeframes(conn, code: str) -> dict[str, pd.DataFrame]:
    frames = {}
    for timeframe, table in (("daily", "price_daily"), ("weekly", "price_weekly"), ("monthly", "price_monthly")):
        frames[timeframe] = pd.read_sql_query(
            f"SELECT trade_date, open, high, low, close, volume, dividends FROM {table} WHERE code=? ORDER BY trade_date",
            conn, params=[code], parse_dates=["trade_date"],
        )
    return frames

def load_financials(conn, code: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT disclosed_date, earnings_per_share, book_value_per_share, profit, equity, total_assets,
                  operating_profit, net_sales, equity_ratio, cash_flows_from_operating_activities
           FROM financial WHERE code=? ORDER BY disclosed_date""",
        conn, params=[code], parse_dates=["disclosed_date"],
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="Load initial StockAI data")
    parser.add_argument("--ticker", default="7203.T")
    parser.add_argument("--code", default="72030", help="5-digit J-Quants security code")
    parser.add_argument("--period", default=None, help="yfinance period such as 1y or 10y")
    parser.add_argument("--skip-jquants", action="store_true")
    parser.add_argument("--screen", action="store_true", help="Screen data already stored in SQLite")
    parser.add_argument("--backtest", action="store_true", help="Backtest one stored security")
    parser.add_argument("--profile", default=None, help="Profile name in config/screening.yaml")
    parser.add_argument("--holding-days", type=int, default=60, help="Trading sessions to hold after entry")
    parser.add_argument("--history", action="store_true", help="Show saved analysis snapshots for a security")
    parser.add_argument("--notify", action="store_true", help="Send the screening result when LINE notifications are enabled")
    parser.add_argument("--market-regime", action="store_true", help="Classify a stored market index into regimes")
    parser.add_argument("--sector-report", action="store_true", help="Aggregate screening hits by 33-sector classification")
    parser.add_argument("--watchlist", action="store_true", help="List watchlist entries")
    parser.add_argument("--watch-add", metavar="CODE", help="Add a code to the watchlist")
    parser.add_argument("--watch-remove", metavar="CODE", help="Remove a code from the watchlist")
    parser.add_argument("--watch-import-scale", nargs="+", metavar="CATEGORY", help="Add listed master stocks in TOPIX scale categories")
    parser.add_argument("--note", default=None, help="Optional note for --watch-add")
    parser.add_argument("--optimize-hits", action="store_true", help="Suggest a threshold for a target screening count")
    parser.add_argument("--field", default=None, help="Indicator field for --optimize-hits, e.g. daily.rsi_14")
    parser.add_argument("--operator", default=None, help="<= or >= for --optimize-hits")
    parser.add_argument("--target-min", type=int, default=None, help="Minimum desired hit count")
    parser.add_argument("--target-max", type=int, default=None, help="Maximum desired hit count")
    parser.add_argument("--simulate", action="store_true", help="Simulate capital using backtest trades")
    parser.add_argument("--portfolio", action="store_true", help="Show portfolio valuation")
    parser.add_argument("--portfolio-add", metavar="CODE", help="Add or update a portfolio position")
    parser.add_argument("--portfolio-remove", metavar="CODE", help="Remove a portfolio position")
    parser.add_argument("--quantity", type=float, default=None, help="Quantity for --portfolio-add")
    parser.add_argument("--average-cost", type=float, default=None, help="Average cost for --portfolio-add")
    parser.add_argument("--daily-update", action="store_true", help="Refresh all watchlist prices and save a local job record")
    parser.add_argument("--healthcheck", action="store_true", help="Show read-only local system diagnostics")
    parser.add_argument("--score-changes", action="store_true", help="Show changes between the latest two backtest scores")
    parser.add_argument("--minimum-delta", type=float, default=0.0, help="Minimum absolute score change for --score-changes")
    parser.add_argument("--validate-config", action="store_true", help="Validate screening configuration without changing data")
    parser.add_argument("--backtest-by-regime", action="store_true", help="Break down a daily-rule backtest by market regime")
    parser.add_argument("--market-code", default="NIKKEI225", help="Stored index code used for regime breakdown")
    parser.add_argument("--batch-backtest", action="store_true", help="Backtest and save a profile for all stored securities")
    parser.add_argument("--batch-limit", type=int, default=None, help="Maximum securities for --batch-backtest")
    parser.add_argument("--backtest-horizons", action="store_true", help="Compare all configured holding periods")
    parser.add_argument("--daily-report", action="store_true", help="Write a local JSON summary report")
    parser.add_argument("--report-path", default=None, help="Output path for --daily-report")
    parser.add_argument("--job-history", action="store_true", help="Show recent local update job results")
    parser.add_argument("--chart", action="store_true", help="Write a local SVG candlestick chart from stored prices")
    parser.add_argument("--chart-path", default=None, help="Output path for --chart")
    args = parser.parse_args()

    with (ROOT / "config" / "settings.yaml").open(encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    db = Database(ROOT / settings["database"]["path"])
    db.initialize()
    if args.healthcheck:
        with db.connect() as conn:
            print(json.dumps(HealthChecker(conn).report(), ensure_ascii=False, indent=2))
        return
    if args.score_changes:
        with db.connect() as conn:
            result = StockRepository(conn).score_changes(minimum_delta=args.minimum_delta)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.validate_config:
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        errors = ConfigValidator().validate_screening(screening_config)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return
    if args.backtest_by_regime:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "backtest.yaml").open(encoding="utf-8") as file:
            backtest_config = yaml.safe_load(file)
        profile_name = args.profile or "rsi_rebound"
        profile = screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        with db.connect() as conn:
            frames = load_timeframes(conn, args.code)
            financials = load_financials(conn, args.code)
            regime_by_date = {row["trade_date"]: row["regime"] for row in conn.execute(
                "SELECT trade_date, regime FROM market_regime WHERE market_code=?", [args.market_code]
            )}
        trades = Backtester(indicator_config, backtest_config).run(frames["daily"], profile, args.holding_days, frames, financials)
        result = RegimeBacktestAnalyzer().summarize(trades, regime_by_date)
        print(json.dumps({"code": args.code, "profile": profile_name, "market_code": args.market_code, "regimes": result}, ensure_ascii=False, indent=2))
        return
    if args.batch_backtest:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "backtest.yaml").open(encoding="utf-8") as file:
            backtest_config = yaml.safe_load(file)
        with (ROOT / "config" / "scoring.yaml").open(encoding="utf-8") as file:
            scoring_config = yaml.safe_load(file)
        profile_name = args.profile or "rsi_rebound"
        profile = screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        result = BatchBacktester(db, indicator_config, backtest_config, scoring_config).run(
            profile_name, profile, args.holding_days, args.batch_limit
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.backtest_horizons:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "backtest.yaml").open(encoding="utf-8") as file:
            backtest_config = yaml.safe_load(file)
        profile_name = args.profile or "rsi_rebound"
        profile = screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        with db.connect() as conn:
            frames = load_timeframes(conn, args.code)
            financials = load_financials(conn, args.code)
        summaries = Backtester(indicator_config, backtest_config).run_horizons(
            frames["daily"], profile, backtest_config["backtest"]["holding_periods"], frames, financials
        )
        print(json.dumps({"code": args.code, "profile": profile_name, "horizons": summaries}, ensure_ascii=False, indent=2))
        return
    if args.daily_report:
        with db.connect() as conn:
            report = DailyReportBuilder(conn).build()
        path = DailyReportBuilder.write(report, args.report_path or DailyReportBuilder.default_path(ROOT))
        print(f"Report written: {path}")
        return
    if args.chart:
        with db.connect() as conn:
            repo = StockRepository(conn)
            prices = repo.prices(args.code, "daily", limit=180)
            overview = repo.overview(args.code)
        svg = StockChartRenderer.render(
            args.code, prices, (overview or {}).get("master", {}).get("company_name") if (overview or {}).get("master") else None,
        )
        path = StockChartRenderer.write(svg, args.chart_path or StockChartRenderer.default_path(ROOT, args.code))
        print(f"Chart written: {path}")
        return
    if args.job_history:
        with db.connect() as conn:
            print(json.dumps(StockRepository(conn).recent_jobs(), ensure_ascii=False, indent=2))
        return
    if args.daily_update:
        with (ROOT / "config" / "regime.yaml").open(encoding="utf-8") as file:
            regime_config = yaml.safe_load(file)
        print(json.dumps(DailyUpdateJob(db, settings, regime_config).run(), ensure_ascii=False, indent=2))
        return
    if args.portfolio_add:
        if args.quantity is None or args.average_cost is None:
            parser.error("--portfolio-add requires --quantity and --average-cost")
        db.save_portfolio_position(args.portfolio_add, args.quantity, args.average_cost, args.note)
        print(f"Saved portfolio position: {args.portfolio_add}")
        return
    if args.portfolio_remove:
        print("Removed." if db.remove_portfolio_position(args.portfolio_remove) else "Code was not in portfolio.")
        return
    if args.portfolio:
        with db.connect() as conn:
            result = PortfolioAnalyzer(conn).positions()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.watch_add:
        db.add_to_watchlist(args.watch_add, args.note)
        print(f"Added {args.watch_add} to watchlist.")
        return
    if args.watch_remove:
        print("Removed." if db.remove_from_watchlist(args.watch_remove) else "Code was not in watchlist.")
        return
    if args.watch_import_scale:
        count = db.import_watchlist_by_scale(args.watch_import_scale, args.note or "TOPIX scale import")
        print(f"Added {count} securities to the watchlist.")
        return
    if args.watchlist:
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT w.code, w.note, w.created_at, m.company_name, m.sector_33_name
                   FROM watchlist w LEFT JOIN master_stock m ON m.code=w.code
                   ORDER BY w.created_at DESC"""
            ).fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
        return
    if args.optimize_hits:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "optimization.yaml").open(encoding="utf-8") as file:
            optimization_config = yaml.safe_load(file)["hit_count_optimization"]
        with db.connect() as conn:
            snapshots = Screener(conn, indicator_config, screening_config).snapshots()
        suggestion = HitCountOptimizer().suggest(
            snapshots, args.field or optimization_config["default_field"], args.operator or optimization_config["default_operator"],
            args.target_min or optimization_config["target_min"], args.target_max or optimization_config["target_max"],
        )
        print(json.dumps(suggestion, ensure_ascii=False, indent=2))
        return
    if args.market_regime:
        with (ROOT / "config" / "regime.yaml").open(encoding="utf-8") as file:
            regime_config = yaml.safe_load(file)
        with db.connect() as conn:
            prices = pd.read_sql_query(
                "SELECT trade_date, close FROM price_daily WHERE code=? ORDER BY trade_date",
                conn, params=[args.code], parse_dates=["trade_date"],
            )
        classified = MarketRegimeAnalyzer(regime_config).classify(prices)
        rows = [{
            "market_code": args.code, "trade_date": row["trade_date"].date().isoformat(),
            "regime": row["regime"], "close": row["close"], "sma_short": row["sma_short"], "sma_long": row["sma_long"],
        } for _, row in classified.iterrows()]
        db.upsert_rows("market_regime", rows, ["market_code", "trade_date"])
        print(json.dumps(MarketRegimeAnalyzer.summary(classified), ensure_ascii=False, indent=2))
        return
    if args.history:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT as_of_date, profile_name, analysis_type, result_json, created_at FROM analysis_snapshot WHERE code=? ORDER BY as_of_date DESC, created_at DESC",
                [args.code],
            ).fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
        return
    if args.backtest:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "backtest.yaml").open(encoding="utf-8") as file:
            backtest_config = yaml.safe_load(file)
        with (ROOT / "config" / "scoring.yaml").open(encoding="utf-8") as file:
            scoring_config = yaml.safe_load(file)
        profile_name = args.profile or "rsi_rebound"
        profile = screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        with db.connect() as conn:
            frames = load_timeframes(conn, args.code)
            financials = load_financials(conn, args.code)
        backtester = Backtester(indicator_config, backtest_config)
        prices = frames["daily"]
        trades = backtester.run(prices, profile, args.holding_days, frames, financials)
        summary = backtester.summarize(trades)
        evaluation = ExpectationScorer(scoring_config).score(summary)
        comment = AnalysisCommentary().backtest_comment(summary, evaluation)
        result = {"code": args.code, "profile": profile_name, "holding_days": args.holding_days, "summary": summary, "expectation": evaluation, "comment": comment}
        as_of_date = prices.iloc[-1]["trade_date"].date().isoformat() if not prices.empty else "unknown"
        db.save_analysis_snapshot(args.code, as_of_date, profile_name, "backtest", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.simulate:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with (ROOT / "config" / "backtest.yaml").open(encoding="utf-8") as file:
            backtest_config = yaml.safe_load(file)
        with (ROOT / "config" / "simulation.yaml").open(encoding="utf-8") as file:
            simulation_config = yaml.safe_load(file)
        profile_name = args.profile or "rsi_rebound"
        profile = screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        with db.connect() as conn:
            frames = load_timeframes(conn, args.code)
            financials = load_financials(conn, args.code)
        trades = Backtester(indicator_config, backtest_config).run(frames["daily"], profile, args.holding_days, frames, financials)
        result = PortfolioSimulator().run(trades, simulation_config)
        result.update({"code": args.code, "profile": profile_name, "holding_days": args.holding_days})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.screen:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        with db.connect() as conn:
            hits = Screener(conn, indicator_config, screening_config).run(args.profile)
            screening_date = conn.execute("SELECT MAX(trade_date) FROM price_daily").fetchone()[0]
        print(f"{len(hits)} matching stocks")
        for hit in hits:
            score = "-" if hit["expectation_score"] is None else f"{hit['expectation_score']:.1f}"
            print(f"{hit['code']} [score {score}]: {hit['reason']}")
        if args.notify:
            with (ROOT / "config" / "notification.yaml").open(encoding="utf-8") as file:
                notification_config = yaml.safe_load(file)
            profile_name = args.profile or screening_config["active_profile"]
            with db.connect() as conn:
                repository = StockRepository(conn)
                comments = {
                    str(hit["code"]): str(result["comment"])
                    for hit in hits
                    if (result := repository.latest_backtest_result(str(hit["code"]), profile_name)) and result.get("comment")
                }
            message = format_screening_message(
                profile_name, hits, notification_config["notification"]["line"]["max_candidates"], comments,
                screening_date,
            )
            notifier = LineNotifier(notification_config)
            chart_urls = notifier.chart_urls([str(hit["code"]) for hit in hits])
            result = notifier.send(message, chart_urls)
            db.save_notification(result.provider, result.status, message, result.response_text)
            print(f"Notification: {result.provider} / {result.status}")
        return
    if args.sector_report:
        with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
            indicator_config = yaml.safe_load(file)
        with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
            screening_config = yaml.safe_load(file)
        profile_name = args.profile or screening_config["active_profile"]
        with db.connect() as conn:
            hits = Screener(conn, indicator_config, screening_config).run(profile_name)
            sectors = SectorAnalyzer(conn).summarize_hits(hits)
        print(json.dumps({"profile": profile_name, "hit_count": len(hits), "sectors": sectors}, ensure_ascii=False, indent=2))
        return
    loader = DataLoader(db, settings)

    prices = loader.load_yfinance_prices(args.ticker, args.code, args.period)
    print(f"Saved {prices} daily price rows for {args.ticker}.")
    if not args.skip_jquants:
        master, financial = loader.load_jquants(args.code)
        print(f"Saved {master} master rows and {financial} financial rows.")

if __name__ == "__main__":
    main()
