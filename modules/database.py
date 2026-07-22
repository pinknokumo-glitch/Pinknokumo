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
