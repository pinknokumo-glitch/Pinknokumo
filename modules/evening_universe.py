"""Evening full-market refresh and next-morning candidate-pool construction."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import sqlite3

import pandas as pd

from modules.daily_job import DailyUpdateJob
from modules.data_loader import DataLoader
from modules.database import Database
from modules.technical import TechnicalAnalyzer


class EveningUniverseJob:
    def __init__(
        self,
        database: Database,
        settings: Mapping[str, object],
        indicator_config: Mapping[str, object],
    ) -> None:
        self.database = database
        self.settings = settings
        self.loader = DataLoader(database, settings)
        self.analyzer = TechnicalAnalyzer(indicator_config)

    def run(self) -> dict[str, object]:
        universe_config = self.settings["screening_universe"]
        markets = list(universe_config["markets"])
        universe_count = self.database.sync_screening_universe(markets)
        codes = self.database.screening_universe_codes()
        refresh = self._refresh_prices(codes)
        pool = self._build_pool(
            codes, universe_config["prefilter"], int(refresh["failed_count"])
        )
        result = {
            "run_date": date.today().isoformat(),
            "markets": markets,
            "universe_count": universe_count,
            **refresh,
            **pool,
        }
        status = "success" if not refresh["failed"] else "partial_failure"
        self.database.save_job_run("evening_universe", status, result)
        return result

    def _refresh_prices(self, codes: list[str]) -> dict[str, object]:
        config = self.settings["providers"]["yfinance"]
        suffix = str(config["suffix"])
        initial_period = str(config.get("bulk_initial_period", "2y"))
        incremental_period = str(config.get("bulk_incremental_period", "10d"))
        chunk_size = int(config.get("bulk_chunk_size", 100))
        with self.database.connect() as connection:
            existing = {
                str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT code FROM price_daily"
                )
            }
        groups = [
            (initial_period, [code for code in codes if code not in existing]),
            (incremental_period, [code for code in codes if code in existing]),
        ]
        updated: list[dict[str, object]] = []
        failed: list[dict[str, object]] = []
        for period, group_codes in groups:
            for start in range(0, len(group_codes), chunk_size):
                chunk = group_codes[start:start + chunk_size]
                pairs = [
                    (DailyUpdateJob.ticker_for_code(code, suffix), code)
                    for code in chunk
                ]
                outcome = self.loader.load_yfinance_batch(pairs, period)
                updated.extend(outcome["updated"])
                for item in outcome["failed"]:
                    try:
                        count = self.loader.load_yfinance_prices(
                            str(item["ticker"]), str(item["code"]), period=period
                        )
                        updated.append({
                            "code": item["code"], "ticker": item["ticker"],
                            "daily_rows": count, "retried": True,
                        })
                    except Exception as error:
                        failed.append({
                            "code": item["code"], "ticker": item["ticker"],
                            "error": str(error),
                        })
        return {
            "updated_count": len(updated),
            "failed_count": len(failed),
            "failed": failed,
        }

    def _build_pool(
        self,
        codes: list[str],
        prefilter: Mapping[str, object],
        failed_count: int,
    ) -> dict[str, object]:
        weekly_max = float(prefilter["weekly_rsi_max"])
        monthly_max = float(prefilter["monthly_rsi_max"])
        candidates, evaluated = [], 0
        latest_date = None
        with self.database.connect() as connection:
            for code in codes:
                weekly = self._latest_rsi(connection, code, "price_weekly")
                monthly = self._latest_rsi(connection, code, "price_monthly")
                if weekly is None or monthly is None:
                    continue
                evaluated += 1
                if weekly <= weekly_max and monthly <= monthly_max:
                    candidates.append({
                        "code": code,
                        "weekly_rsi": weekly,
                        "monthly_rsi": monthly,
                    })
            row = connection.execute(
                """SELECT MAX(d.trade_date)
                   FROM price_daily d
                   INNER JOIN screening_universe u ON u.code=d.code
                   WHERE u.enabled=1"""
            ).fetchone()
            latest_date = str(row[0]) if row and row[0] else None
        if latest_date is None:
            raise RuntimeError("No current price date is available for the screening universe")
        self.database.replace_candidate_pool(
            latest_date,
            candidates,
            universe_count=len(codes),
            evaluated_count=evaluated,
            failed_count=failed_count,
            minimum_coverage_ratio=float(
                self.settings["screening_universe"].get(
                    "minimum_coverage_ratio", 0.95
                )
            ),
        )
        return {
            "pool_date": latest_date,
            "evaluated_count": evaluated,
            "candidate_count": len(candidates),
            "weekly_rsi_max": weekly_max,
            "monthly_rsi_max": monthly_max,
        }

    def _latest_rsi(
        self, connection: sqlite3.Connection, code: str, table: str
    ) -> float | None:
        frame = pd.read_sql_query(
            f"""SELECT trade_date, open, high, low, close, adjusted_close,
                       volume, dividends
                FROM {table} WHERE code=? ORDER BY trade_date""",
            connection,
            params=[code],
            parse_dates=["trade_date"],
        )
        if frame.empty:
            return None
        value = self.analyzer.latest_values(
            self.analyzer.calculate(frame)
        ).get("rsi_14")
        return float(value) if value is not None and not pd.isna(value) else None
