"""Run one price-based backtest profile across stored securities."""
from __future__ import annotations

from collections.abc import Mapping
import sqlite3

import pandas as pd

from modules.ai_comment import AnalysisCommentary
from modules.backtest import Backtester
from modules.database import Database
from modules.expectation import ExpectationScorer


class BatchBacktester:
    def __init__(
        self, database: Database, indicator_config: Mapping[str, object], backtest_config: Mapping[str, object], scoring_config: Mapping[str, object]
    ) -> None:
        self.db = database
        self.backtester = Backtester(indicator_config, backtest_config)
        self.scorer = ExpectationScorer(scoring_config)
        self.commentary = AnalysisCommentary()

    def run(self, profile_name: str, rule: Mapping[str, object], holding_days: int, limit: int | None = None) -> dict[str, object]:
        with self.db.connect() as conn:
            codes = [row[0] for row in conn.execute(
                """SELECT DISTINCT code FROM price_daily
                   WHERE code NOT IN (SELECT DISTINCT market_code FROM market_regime)
                   ORDER BY code"""
            )]
        if limit is not None:
            codes = codes[:limit]
        completed, failed = [], []
        for code in codes:
            try:
                with self.db.connect() as conn:
                    frames = {}
                    for timeframe, table in (("daily", "price_daily"), ("weekly", "price_weekly"), ("monthly", "price_monthly")):
                        frames[timeframe] = pd.read_sql_query(
                            f"SELECT trade_date, open, high, low, close, volume, dividends FROM {table} WHERE code=? ORDER BY trade_date",
                            conn, params=[code], parse_dates=["trade_date"],
                        )
                    prices = frames["daily"]
                    financials = pd.read_sql_query(
                        """SELECT disclosed_date, earnings_per_share, book_value_per_share, profit, equity, total_assets,
                                  operating_profit, net_sales, equity_ratio, cash_flows_from_operating_activities
                           FROM financial WHERE code=? ORDER BY disclosed_date""",
                        conn, params=[code], parse_dates=["disclosed_date"],
                    )
                if prices.empty:
                    continue
                trades = self.backtester.run(prices, rule, holding_days, frames, financials)
                summary = self.backtester.summarize(trades)
                expectation = self.scorer.score(summary)
                result = {
                    "code": code, "profile": profile_name, "holding_days": holding_days,
                    "summary": summary, "expectation": expectation,
                    "comment": self.commentary.backtest_comment(summary, expectation),
                }
                as_of_date = prices.iloc[-1]["trade_date"].date().isoformat()
                self.db.save_analysis_snapshot(code, as_of_date, profile_name, "backtest", result)
                completed.append({"code": code, "score": expectation["score"], "trade_count": summary["trade_count"]})
            except Exception as error:
                failed.append({"code": code, "error": str(error)})
        return {
            "profile": profile_name, "processed_count": len(completed), "failed_count": len(failed),
            "results": sorted(completed, key=lambda item: item["score"], reverse=True), "failed": failed,
        }
