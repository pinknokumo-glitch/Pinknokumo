"""Read-only diagnostics for local StockAI operation."""
from __future__ import annotations

import sqlite3
from datetime import date


EXPECTED_TABLES = {
    "master_stock", "price_daily", "price_weekly", "price_monthly", "financial",
    "analysis_snapshot", "notification_log", "market_regime", "watchlist",
    "portfolio_position", "job_run",
}
MAX_PRICE_AGE_DAYS = 7


class HealthChecker:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def report(self) -> dict[str, object]:
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(EXPECTED_TABLES - tables)
        latest = self.connection.execute("SELECT MAX(trade_date) FROM price_daily").fetchone()[0]
        today = date.today()
        price_age_days = None
        if latest:
            try:
                price_age_days = max((today - date.fromisoformat(latest)).days, 0)
            except ValueError:
                pass
        freshness = "missing" if latest is None else "stale" if price_age_days is None or price_age_days > MAX_PRICE_AGE_DAYS else "current"
        watchlist_count = self.connection.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        portfolio_count = self.connection.execute("SELECT COUNT(*) FROM portfolio_position").fetchone()[0]
        return {
            "status": "ok" if not missing and freshness == "current" else "degraded",
            "missing_tables": missing,
            "latest_price_date": latest,
            "price_age_days": price_age_days,
            "price_data_status": freshness,
            "watchlist_count": watchlist_count,
            "portfolio_position_count": portfolio_count,
            "database_date": today.isoformat(),
        }
