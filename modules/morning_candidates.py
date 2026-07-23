"""Refresh only the candidate pool immediately before morning screening."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from modules.daily_job import DailyUpdateJob
from modules.data_loader import DataLoader
from modules.database import Database


class MorningCandidateJob:
    def __init__(self, database: Database, settings: Mapping[str, object]) -> None:
        self.database = database
        self.settings = settings
        self.loader = DataLoader(database, settings)

    def load_valid_pool(self) -> tuple[dict[str, object], list[str]]:
        metadata, codes = self.database.latest_candidate_pool()
        if metadata is None:
            raise RuntimeError("前夜の候補プールがありません。17時処理を先に実行してください。")
        pool_date = date.fromisoformat(str(metadata["pool_date"]))
        maximum_age = int(
            self.settings["screening_universe"].get("maximum_pool_age_days", 4)
        )
        if (date.today() - pool_date).days > maximum_age:
            raise RuntimeError(
                f"候補プールが古いため配信を停止しました: {pool_date.isoformat()}"
            )
        if str(metadata["status"]) != "success":
            raise RuntimeError(
                f"前夜の全銘柄更新が未完了です: failed={metadata['failed_count']}"
            )
        return metadata, codes

    def run(self, codes: list[str]) -> dict[str, object]:
        config = self.settings["providers"]["yfinance"]
        suffix = str(config["suffix"])
        period = str(config.get("bulk_incremental_period", "10d"))
        chunk_size = int(config.get("bulk_chunk_size", 100))
        updated, failed = [], []
        for start in range(0, len(codes), chunk_size):
            chunk = codes[start:start + chunk_size]
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
        financial_updated, financial_failed = [], []
        for code in codes:
            try:
                count = self.loader.load_jquants_financial(code)
                financial_updated.append({"code": code, "financial_rows": count})
            except Exception as error:
                financial_failed.append({"code": code, "error": str(error)})
        result = {
            "candidate_count": len(codes),
            "updated": updated,
            "failed": failed,
            "financial_updated": financial_updated,
            "financial_failed": financial_failed,
            "watchlist_count": len(codes),
            "market_index_count": 0,
        }
        status = "success" if not failed else "partial_failure"
        self.database.save_job_run("morning_candidates", status, result)
        return result
