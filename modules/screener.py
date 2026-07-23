"""Read stored prices, calculate indicators and evaluate a named screening profile."""
from __future__ import annotations

from collections.abc import Mapping
import json
import sqlite3
import pandas as pd

from modules.technical import TechnicalAnalyzer
from modules.rule_engine import RuleEngine
from modules.fundamentals import FundamentalAnalyzer

TABLES = {"daily": "price_daily", "weekly": "price_weekly", "monthly": "price_monthly"}

class Screener:
    def __init__(
        self,
        conn: sqlite3.Connection,
        indicator_config: Mapping[str, object],
        screening_config: Mapping[str, object],
        candidate_codes: list[str] | None = None,
    ) -> None:
        self.conn, self.analyzer = conn, TechnicalAnalyzer(indicator_config)
        self.screening_config, self.rules = screening_config, RuleEngine()
        self.fundamentals = FundamentalAnalyzer()
        self.restricted_codes = candidate_codes

    def run(
        self, profile_name: str | None = None, rule: Mapping[str, object] | None = None
    ) -> list[dict[str, object]]:
        profile_name = profile_name or self.screening_config["active_profile"]
        profile = rule or self.screening_config["profiles"].get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")
        codes = self._candidate_codes()
        hits = []
        for code in codes:
            values = self._values_for_code(code)
            result = self.rules.evaluate(profile, values)
            if result.matched:
                master = self.conn.execute(
                    "SELECT company_name FROM master_stock WHERE code=?", [code]
                ).fetchone()
                hits.append({
                    "code": code, "profile": profile_name, "reason": result.reason,
                    "company_name": master["company_name"] if master else None,
                    "expectation_score": self._latest_expectation_score(code, profile_name), **values,
                })
        return sorted(hits, key=lambda item: item["expectation_score"] if item["expectation_score"] is not None else float("-inf"), reverse=True)

    def snapshots(self) -> list[dict[str, object]]:
        codes = self._candidate_codes()
        return [{"code": code, **self._values_for_code(code)} for code in codes]

    def candidate_count(self) -> int:
        return len(self._candidate_codes())

    def _candidate_codes(self) -> list[str]:
        if self.restricted_codes is not None:
            return list(dict.fromkeys(self.restricted_codes))
        return [row[0] for row in self.conn.execute(
            """SELECT DISTINCT code FROM price_daily
               WHERE code NOT IN (SELECT DISTINCT market_code FROM market_regime)
               ORDER BY code"""
        )]

    def _values_for_code(self, code: str) -> dict[str, object]:
        values: dict[str, object] = {}
        daily_frame = None
        for timeframe, table in TABLES.items():
            frame = pd.read_sql_query(
                f"SELECT trade_date, open, high, low, close, adjusted_close, volume, dividends FROM {table} WHERE code=? ORDER BY trade_date",
                self.conn, params=[code], parse_dates=["trade_date"],
            )
            if frame.empty:
                continue
            computed = self.analyzer.calculate(frame)
            values.update({f"{timeframe}.{name}": value for name, value in self.analyzer.latest_values(computed).items()})
            if timeframe == "daily":
                daily_frame = frame
        financial = self.conn.execute(
            "SELECT * FROM financial WHERE code=? ORDER BY disclosed_date DESC LIMIT 1", [code]
        ).fetchone()
        if financial and values.get("daily.close") is not None:
            values["fundamental.disclosed_date"] = financial["disclosed_date"]
            trailing_dividends = None
            if daily_frame is not None and not daily_frame.empty:
                cutoff = daily_frame["trade_date"].max() - pd.Timedelta(days=365)
                trailing_dividends = daily_frame.loc[daily_frame["trade_date"] > cutoff, "dividends"].fillna(0).sum()
            values.update({f"fundamental.{name}": value for name, value in self.fundamentals.latest_values(dict(financial), values["daily.close"], trailing_dividends).items()})
        return values

    def _latest_expectation_score(self, code: str, profile_name: str) -> float | None:
        row = self.conn.execute(
            """SELECT result_json FROM analysis_snapshot
               WHERE code=? AND profile_name=? AND analysis_type='backtest'
               ORDER BY as_of_date DESC, created_at DESC LIMIT 1""",
            [code, profile_name],
        ).fetchone()
        if not row:
            return None
        score = json.loads(row["result_json"]).get("expectation", {}).get("score")
        return float(score) if score is not None else None
