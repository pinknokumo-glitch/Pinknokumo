"""SQLite schema and persistence helpers for StockAI."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS master_stock (
    code TEXT PRIMARY KEY, company_name TEXT, company_name_en TEXT,
    market_code TEXT, market_name TEXT, sector_17_code TEXT, sector_17_name TEXT,
    sector_33_code TEXT, sector_33_name TEXT, scale_category TEXT,
    listed_date TEXT, delisted_date TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS price_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
    volume INTEGER, dividends REAL, stock_splits REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);
CREATE TABLE IF NOT EXISTS price_weekly (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
    volume INTEGER, dividends REAL, stock_splits REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);
CREATE TABLE IF NOT EXISTS price_monthly (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
    volume INTEGER, dividends REAL, stock_splits REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);
CREATE TABLE IF NOT EXISTS financial (
    code TEXT NOT NULL, disclosed_date TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT '', fiscal_year TEXT, fiscal_quarter TEXT,
    net_sales REAL, operating_profit REAL, ordinary_profit REAL, profit REAL,
    earnings_per_share REAL, book_value_per_share REAL,
    total_assets REAL, equity REAL, equity_ratio REAL,
    cash_flows_from_operating_activities REAL,
    cash_flows_from_investing_activities REAL,
    cash_flows_from_financing_activities REAL,
    raw_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, disclosed_date, document_type)
);
CREATE TABLE IF NOT EXISTS analysis_snapshot (
    code TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, as_of_date, profile_name, analysis_type)
);
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    response_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS market_regime (
    market_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    regime TEXT NOT NULL,
    close REAL NOT NULL,
    sma_short REAL,
    sma_long REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market_code, trade_date)
);
CREATE TABLE IF NOT EXISTS watchlist (
    code TEXT PRIMARY KEY,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS screening_universe (
    code TEXT PRIMARY KEY,
    market_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS screening_candidate_pool (
    pool_date TEXT NOT NULL,
    code TEXT NOT NULL,
    weekly_rsi REAL,
    monthly_rsi REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pool_date, code)
);
CREATE TABLE IF NOT EXISTS screening_pool_run (
    pool_date TEXT PRIMARY KEY,
    universe_count INTEGER NOT NULL,
    evaluated_count INTEGER NOT NULL,
    candidate_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS portfolio_position (
    code TEXT PRIMARY KEY,
    quantity REAL NOT NULL CHECK(quantity > 0),
    average_cost REAL NOT NULL CHECK(average_cost >= 0),
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS job_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON price_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_financial_code ON financial(code);
CREATE INDEX IF NOT EXISTS idx_market_regime_date ON market_regime(trade_date);
CREATE INDEX IF NOT EXISTS idx_candidate_pool_date ON screening_candidate_pool(pool_date);
"""

class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_rows(self, table: str, rows: Iterable[Mapping[str, object]], key_columns: list[str]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        columns = list(rows[0])
        if any(set(row) != set(columns) for row in rows):
            raise ValueError("All rows must contain identical columns")
        placeholders = ", ".join(f":{column}" for column in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in key_columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(key_columns)}) DO UPDATE SET {updates}"
        )
        with self.connect() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def save_financial_rows(self, rows: Iterable[Mapping[str, object]]) -> int:
        prepared = []
        for row in rows:
            item = dict(row)
            item["raw_json"] = json.dumps(item.get("raw_json", {}), ensure_ascii=False, default=str)
            prepared.append(item)
        return self.upsert_rows("financial", prepared, ["code", "disclosed_date", "document_type"])

    def save_analysis_snapshot(
        self, code: str, as_of_date: str, profile_name: str, analysis_type: str, result: Mapping[str, object]
    ) -> None:
        self.upsert_rows("analysis_snapshot", [{
            "code": code, "as_of_date": as_of_date, "profile_name": profile_name,
            "analysis_type": analysis_type,
            "result_json": json.dumps(result, ensure_ascii=False, default=str),
        }], ["code", "as_of_date", "profile_name", "analysis_type"])

    def save_notification(self, provider: str, status: str, message: str, response_text: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO notification_log (provider, status, message, response_text) VALUES (?, ?, ?, ?)",
                [provider, status, message, response_text],
            )

    def was_notification_sent(self, provider: str, message: str) -> bool:
        """Return whether the exact dated/candidate message has already been delivered."""
        with self.connect() as conn:
            row = conn.execute(
                """SELECT 1 FROM notification_log
                   WHERE provider=? AND status='sent' AND message=? LIMIT 1""",
                [provider, message],
            ).fetchone()
        return row is not None

    def add_to_watchlist(self, code: str, note: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO watchlist (code, note) VALUES (?, ?)
                   ON CONFLICT(code) DO UPDATE SET note=excluded.note, updated_at=CURRENT_TIMESTAMP""",
                [code, note],
            )

    def remove_from_watchlist(self, code: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM watchlist WHERE code=?", [code])
        return cursor.rowcount > 0

    def import_watchlist_by_scale(self, scale_categories: Iterable[str], note: str | None = None) -> int:
        """Add currently listed master securities in selected TOPIX scale categories."""
        categories = [str(value).strip() for value in scale_categories if str(value).strip()]
        if not categories:
            raise ValueError("At least one scale category is required")
        placeholders = ", ".join("?" for _ in categories)
        with self.connect() as conn:
            cursor = conn.execute(
                f"""INSERT OR IGNORE INTO watchlist (code, note)
                    SELECT code, ? FROM master_stock
                    WHERE scale_category IN ({placeholders})
                      AND (delisted_date IS NULL OR delisted_date='')""",
                [note, *categories],
            )
        return cursor.rowcount

    def sync_screening_universe(self, market_names: Iterable[str]) -> int:
        """Replace the automatic-screening universe with currently listed target markets."""
        markets = [str(value).strip() for value in market_names if str(value).strip()]
        if not markets:
            raise ValueError("At least one market name is required")
        placeholders = ", ".join("?" for _ in markets)
        with self.connect() as conn:
            conn.execute("UPDATE screening_universe SET enabled=0, updated_at=CURRENT_TIMESTAMP")
            conn.execute(
                f"""INSERT INTO screening_universe (code, market_name, enabled)
                    SELECT code, market_name, 1 FROM master_stock
                    WHERE market_name IN ({placeholders})
                      AND (delisted_date IS NULL OR delisted_date='')
                    ON CONFLICT(code) DO UPDATE SET
                      market_name=excluded.market_name,
                      enabled=1,
                      updated_at=CURRENT_TIMESTAMP""",
                markets,
            )
            return int(conn.execute(
                "SELECT COUNT(*) FROM screening_universe WHERE enabled=1"
            ).fetchone()[0])

    def screening_universe_codes(self) -> list[str]:
        with self.connect() as conn:
            return [str(row[0]) for row in conn.execute(
                "SELECT code FROM screening_universe WHERE enabled=1 ORDER BY code"
            )]

    def replace_candidate_pool(
        self,
        pool_date: str,
        candidates: Iterable[Mapping[str, object]],
        universe_count: int,
        evaluated_count: int,
        failed_count: int,
        minimum_coverage_ratio: float = 0.95,
    ) -> int:
        rows = [
            {
                "pool_date": pool_date,
                "code": str(item["code"]),
                "weekly_rsi": item.get("weekly_rsi"),
                "monthly_rsi": item.get("monthly_rsi"),
            }
            for item in candidates
        ]
        with self.connect() as conn:
            conn.execute("DELETE FROM screening_candidate_pool WHERE pool_date=?", [pool_date])
        if rows:
            self.upsert_rows(
                "screening_candidate_pool", rows, ["pool_date", "code"]
            )
        coverage = evaluated_count / universe_count if universe_count else 0.0
        status = (
            "success"
            if failed_count == 0 and coverage >= minimum_coverage_ratio
            else "partial_failure"
        )
        self.upsert_rows("screening_pool_run", [{
            "pool_date": pool_date,
            "universe_count": universe_count,
            "evaluated_count": evaluated_count,
            "candidate_count": len(rows),
            "failed_count": failed_count,
            "status": status,
        }], ["pool_date"])
        return len(rows)

    def latest_candidate_pool(self) -> tuple[dict[str, object] | None, list[str]]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT pool_date, universe_count, evaluated_count, candidate_count,
                          failed_count, status
                   FROM screening_pool_run ORDER BY pool_date DESC LIMIT 1"""
            ).fetchone()
            if row is None:
                return None, []
            metadata = dict(row)
            pool_date = str(metadata["pool_date"])
            codes = [str(item[0]) for item in conn.execute(
                "SELECT code FROM screening_candidate_pool WHERE pool_date=? ORDER BY code",
                [pool_date],
            )]
        return metadata, codes

    def save_portfolio_position(self, code: str, quantity: float, average_cost: float, note: str | None = None) -> None:
        if quantity <= 0 or average_cost < 0:
            raise ValueError("quantity must be positive and average_cost cannot be negative")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO portfolio_position (code, quantity, average_cost, note) VALUES (?, ?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET quantity=excluded.quantity, average_cost=excluded.average_cost,
                   note=excluded.note, updated_at=CURRENT_TIMESTAMP""",
                [code, quantity, average_cost, note],
            )

    def remove_portfolio_position(self, code: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM portfolio_position WHERE code=?", [code])
        return cursor.rowcount > 0

    def save_job_run(self, job_name: str, status: str, details: Mapping[str, object]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO job_run (job_name, status, details_json) VALUES (?, ?, ?)",
                [job_name, status, json.dumps(details, ensure_ascii=False, default=str)],
            )
