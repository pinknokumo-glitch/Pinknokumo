"""Read-only SQLite queries shared by the API and future client applications."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from modules.fundamentals import FundamentalAnalyzer

VALID_TIMEFRAMES = {
    "daily": "price_daily",
    "weekly": "price_weekly",
    "monthly": "price_monthly",
}

class StockRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def prices(self, code: str, timeframe: str, limit: int = 300) -> list[dict[str, object]]:
        table = VALID_TIMEFRAMES.get(timeframe)
        if table is None:
            raise ValueError("timeframe must be daily, weekly, or monthly")
        rows = self.conn.execute(
            f"SELECT trade_date, open, high, low, close, adjusted_close, volume, dividends, stock_splits FROM {table} WHERE code=? ORDER BY trade_date DESC LIMIT ?",
            [code, limit],
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def overview(self, code: str, benchmark_code: str | None = None) -> dict[str, object] | None:
        master = self.conn.execute(
            "SELECT code, company_name, market_name, sector_33_name FROM master_stock WHERE code=?", [code]
        ).fetchone()
        latest_price = self.conn.execute(
            "SELECT trade_date, close FROM price_daily WHERE code=? ORDER BY trade_date DESC LIMIT 1", [code]
        ).fetchone()
        financial = self.conn.execute(
            """SELECT disclosed_date, earnings_per_share, book_value_per_share, profit, equity, total_assets,
                      operating_profit, net_sales, equity_ratio, cash_flows_from_operating_activities
               FROM financial WHERE code=? ORDER BY disclosed_date DESC LIMIT 1""",
            [code],
        ).fetchone()
        if master is None and latest_price is None and financial is None:
            return None
        trailing_dividends = 0.0
        if latest_price is not None:
            trailing_dividends = self.conn.execute(
                """SELECT COALESCE(SUM(dividends), 0) FROM price_daily
                   WHERE code=? AND trade_date > date(?, '-365 days') AND trade_date <= ?""",
                [code, latest_price["trade_date"], latest_price["trade_date"]],
            ).fetchone()[0]
        fundamentals = FundamentalAnalyzer().latest_values(
            dict(financial) if financial is not None else {},
            latest_price["close"] if latest_price is not None else None,
            trailing_dividends,
        )
        return {
            "code": code,
            "master": dict(master) if master is not None else None,
            "latest_price": dict(latest_price) if latest_price is not None else None,
            "latest_financial": dict(financial) if financial is not None else None,
            "fundamentals": fundamentals,
            "relative_performance": self.relative_performance(code, benchmark_code),
        }

    def relative_performance(self, code: str, benchmark_code: str | None) -> list[dict[str, object]]:
        if not benchmark_code or code == benchmark_code:
            return []
        result = []
        for sessions in (20, 60, 120):
            rows = self.conn.execute(
                """SELECT stock.trade_date, stock.close AS stock_close, benchmark.close AS benchmark_close
                   FROM price_daily stock INNER JOIN price_daily benchmark ON benchmark.trade_date=stock.trade_date
                   WHERE stock.code=? AND benchmark.code=?
                   ORDER BY stock.trade_date DESC LIMIT ?""",
                [code, benchmark_code, sessions + 1],
            ).fetchall()
            if len(rows) < sessions + 1 or rows[-1]["stock_close"] in (None, 0) or rows[-1]["benchmark_close"] in (None, 0):
                continue
            latest, earliest = rows[0], rows[-1]
            stock_return = (latest["stock_close"] / earliest["stock_close"] - 1) * 100
            benchmark_return = (latest["benchmark_close"] / earliest["benchmark_close"] - 1) * 100
            result.append({
                "sessions": sessions, "start_date": earliest["trade_date"], "end_date": latest["trade_date"],
                "stock_return_percent": round(stock_return, 2), "benchmark_return_percent": round(benchmark_return, 2),
                "excess_return_percent": round(stock_return - benchmark_return, 2), "benchmark_code": benchmark_code,
            })
        return result

    def analysis_history(self, code: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT as_of_date, profile_name, analysis_type, result_json, created_at FROM analysis_snapshot WHERE code=? ORDER BY as_of_date DESC, created_at DESC LIMIT ?",
            [code, limit],
        ).fetchall()
        return [{**dict(row), "result": json.loads(row["result_json"])} for row in rows]

    def latest_backtest_result(self, code: str, profile_name: str) -> dict[str, object] | None:
        row = self.conn.execute(
            """SELECT result_json FROM analysis_snapshot
               WHERE code=? AND profile_name=? AND analysis_type='backtest'
               ORDER BY as_of_date DESC, created_at DESC LIMIT 1""",
            [code, profile_name],
        ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def latest_rankings(self, limit: int = 100) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT a.code, a.as_of_date, a.profile_name, a.result_json
               FROM analysis_snapshot a
               INNER JOIN (
                 SELECT code, profile_name, analysis_type, MAX(created_at) AS max_created
                 FROM analysis_snapshot WHERE analysis_type='backtest'
                 GROUP BY code, profile_name, analysis_type
               ) latest ON latest.code=a.code AND latest.profile_name=a.profile_name
                 AND latest.max_created=a.created_at
               WHERE a.analysis_type='backtest'
                 AND a.code NOT IN (SELECT DISTINCT market_code FROM market_regime)
               ORDER BY a.created_at DESC LIMIT ?""",
            [limit],
        ).fetchall()
        rankings = []
        for row in rows:
            result = json.loads(row["result_json"])
            rankings.append({
                "code": row["code"], "as_of_date": row["as_of_date"], "profile_name": row["profile_name"],
                "expectation_score": result.get("expectation", {}).get("score"),
                "grade": result.get("expectation", {}).get("grade"),
                "summary": result.get("summary", {}),
            })
        return sorted(rankings, key=lambda item: item["expectation_score"] or 0, reverse=True)

    def score_changes(self, limit: int = 100, minimum_delta: float = 0.0) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT code, as_of_date, profile_name, result_json
               FROM analysis_snapshot WHERE analysis_type='backtest'
                 AND code NOT IN (SELECT DISTINCT market_code FROM market_regime)
               ORDER BY code, profile_name, as_of_date DESC"""
        ).fetchall()
        latest_by_key: dict[tuple[str, str], tuple[object, float | None]] = {}
        changes = []
        for row in rows:
            key = (row["code"], row["profile_name"])
            score = json.loads(row["result_json"]).get("expectation", {}).get("score")
            score = float(score) if score is not None else None
            if key not in latest_by_key:
                latest_by_key[key] = (row, score)
                continue
            latest_row, latest_score = latest_by_key.pop(key)
            if latest_score is None or score is None:
                continue
            delta = latest_score - score
            if abs(delta) >= minimum_delta:
                changes.append({
                    "code": latest_row["code"], "profile_name": latest_row["profile_name"],
                    "latest_date": latest_row["as_of_date"], "previous_date": row["as_of_date"],
                    "latest_score": latest_score, "previous_score": score, "delta": round(delta, 1),
                })
        return sorted(changes, key=lambda item: (-abs(item["delta"]), item["code"]))[:limit]

    def recent_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT id, job_name, status, details_json, started_at, finished_at
               FROM job_run ORDER BY id DESC LIMIT ?""",
            [limit],
        ).fetchall()
        return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]

    def operations_status(self) -> dict[str, object]:
        """Return the latest evening/morning screening state for operator UIs."""
        pool = self.conn.execute(
            """SELECT pool_date, universe_count, evaluated_count, candidate_count,
                      failed_count, status, created_at
               FROM screening_pool_run ORDER BY pool_date DESC LIMIT 1"""
        ).fetchone()

        def latest_job(name: str) -> dict[str, object] | None:
            row = self.conn.execute(
                """SELECT status, details_json, started_at, finished_at
                   FROM job_run WHERE job_name=? ORDER BY id DESC LIMIT 1""",
                [name],
            ).fetchone()
            if row is None:
                return None
            return {
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "details": json.loads(row["details_json"]),
            }

        return {
            "ready": pool is not None and pool["status"] == "success",
            "pool": dict(pool) if pool is not None else None,
            "evening_update": latest_job("evening_universe"),
            "morning_update": latest_job("morning_candidates"),
            "morning_screening": latest_job("morning_screening"),
        }
