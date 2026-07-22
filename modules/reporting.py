"""Create a portable daily summary from locally stored StockAI results."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from modules.health import HealthChecker
from modules.portfolio import PortfolioAnalyzer
from modules.repository import StockRepository


class DailyReportBuilder:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def build(self) -> dict[str, object]:
        repo = StockRepository(self.connection)
        watchlist = [dict(row) for row in self.connection.execute(
            "SELECT code, note, created_at FROM watchlist ORDER BY created_at DESC"
        )]
        market_regimes = [dict(row) for row in self.connection.execute(
            """SELECT r.market_code, r.trade_date, r.regime, r.close, r.sma_short, r.sma_long
               FROM market_regime r INNER JOIN (
                   SELECT market_code, MAX(trade_date) AS latest_date FROM market_regime GROUP BY market_code
               ) latest ON latest.market_code=r.market_code AND latest.latest_date=r.trade_date
               ORDER BY r.market_code"""
        )]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "health": HealthChecker(self.connection).report(),
            "top_rankings": repo.latest_rankings(limit=10),
            "score_changes": repo.score_changes(limit=10),
            "recent_jobs": repo.recent_jobs(limit=5),
            "market_regimes": market_regimes,
            "watchlist": watchlist,
            "portfolio": PortfolioAnalyzer(self.connection).positions(),
        }

    @staticmethod
    def write(report: dict[str, object], path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    @staticmethod
    def default_path(root: str | Path) -> Path:
        return Path(root) / "reports" / f"daily_summary_{date.today().isoformat()}.json"
