"""Targeted long-history backfill for user-specific expectation backtests."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from modules.daily_job import DailyUpdateJob
from modules.data_loader import DataLoader
from modules.database import Database


class BacktestHistoryBackfill:
    def __init__(self, database: Database, settings: Mapping[str, object]) -> None:
        self.database = database
        self.settings = settings
        self.loader = DataLoader(database, settings)

    def run(self, codes: Sequence[str], holding_days: int) -> dict[str, object]:
        cloud = self.settings.get("cloud_screening", {})
        signal_sessions = int(
            cloud.get("backtest_minimum_signal_sessions", 252)
        )
        required_rows = int(holding_days) + signal_sessions + 2
        missing = self.codes_requiring_history(codes, required_rows)
        if not missing:
            return {
                "required_rows": required_rows,
                "requested_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "updated_codes": [],
                "failed": [],
            }

        provider = self.settings["providers"]["yfinance"]
        suffix = str(provider["suffix"])
        period = str(cloud.get("backtest_history_period", "10y"))
        chunk_size = max(
            1, int(cloud.get("backtest_history_chunk_size", 5))
        )
        updated_codes: list[str] = []
        failed: list[dict[str, str]] = []
        for start in range(0, len(missing), chunk_size):
            chunk = missing[start:start + chunk_size]
            pairs = [
                (DailyUpdateJob.ticker_for_code(code, suffix), code)
                for code in chunk
            ]
            outcome = self.loader.load_yfinance_batch(pairs, period)
            updated_codes.extend(str(item["code"]) for item in outcome["updated"])
            for item in outcome["failed"]:
                try:
                    self.loader.load_yfinance_prices(
                        str(item["ticker"]), str(item["code"]), period=period
                    )
                    updated_codes.append(str(item["code"]))
                except Exception as error:
                    failed.append({
                        "code": str(item["code"]),
                        "error": f"{type(error).__name__}: {error}",
                    })
        return {
            "required_rows": required_rows,
            "requested_count": len(missing),
            "updated_count": len(set(updated_codes)),
            "failed_count": len(failed),
            "updated_codes": list(dict.fromkeys(updated_codes)),
            "failed": failed,
        }

    def codes_requiring_history(
        self, codes: Sequence[str], required_rows: int
    ) -> list[str]:
        unique_codes = list(dict.fromkeys(str(code) for code in codes))
        if not unique_codes:
            return []
        placeholders = ",".join("?" for _ in unique_codes)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT code, COUNT(*) AS row_count
                    FROM price_daily
                    WHERE code IN ({placeholders})
                    GROUP BY code""",
                unique_codes,
            ).fetchall()
        counts = {str(row[0]): int(row[1]) for row in rows}
        return [
            code for code in unique_codes
            if counts.get(code, 0) < required_rows
        ]
