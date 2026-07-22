"""Local daily data-refresh job for watchlist symbols."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
import pandas as pd

from modules.data_loader import DataLoader
from modules.database import Database
from modules.regime import MarketRegimeAnalyzer


class DailyUpdateJob:
    def __init__(
        self, database: Database, settings: Mapping[str, object], regime_config: Mapping[str, object] | None = None,
    ) -> None:
        self.db, self.settings = database, settings
        self.loader = DataLoader(database, settings)
        self.regime_config = regime_config

    def run(self, period: str | None = None) -> dict[str, object]:
        with self.db.connect() as conn:
            watchlist = [dict(row) for row in conn.execute(
                """SELECT w.code, MAX(d.trade_date) AS latest_price_date
                   FROM watchlist w LEFT JOIN price_daily d ON d.code=w.code
                   GROUP BY w.code ORDER BY w.code"""
            )]
        result: dict[str, object] = {"updated": [], "failed": [], "financial_updated": [], "financial_failed": [], "market_regimes": []}
        config = self.settings["providers"]["yfinance"]
        initial_period = period or str(config.get("period", "10y"))
        suffix = config["suffix"]
        overlap_days = int(config.get("daily_update_overlap_days", 7))
        symbols = self._symbols(watchlist, suffix)
        for item in symbols:
            code = item["code"]
            ticker = item["ticker"]
            start = self.incremental_start(item["latest_price_date"], overlap_days)
            try:
                count = self.loader.load_yfinance_prices(ticker, code, period=initial_period, start=start)
                result["updated"].append({"code": code, "ticker": ticker, "daily_rows": count, "start": start})
                if item["is_market_index"] and self.regime_config is not None:
                    result["market_regimes"].append(self._update_market_regime(code))
                if not item["is_market_index"] and self._should_update_financials(code):
                    try:
                        financial_count = self.loader.load_jquants_financial(code)
                        result["financial_updated"].append({"code": code, "financial_rows": financial_count})
                    except Exception as error:
                        result["financial_failed"].append({"code": code, "error": str(error)})
            except Exception as error:  # One symbol must not stop the rest of the job.
                result["failed"].append({"code": code, "error": str(error)})
        result["watchlist_count"] = len(watchlist)
        result["market_index_count"] = sum(item["is_market_index"] for item in symbols)
        status = "success" if not result["failed"] and not result["financial_failed"] else "partial_failure"
        self.db.save_job_run("daily_update", status, result)
        return result

    def _symbols(self, watchlist: list[dict[str, object]], suffix: str) -> list[dict[str, object]]:
        latest_by_code = {str(item["code"]): item.get("latest_price_date") for item in watchlist}
        symbols = []
        configured_indices = self.settings.get("market_indices", [])
        for index in configured_indices if isinstance(configured_indices, list) else []:
            if not isinstance(index, Mapping) or not index.get("code") or not index.get("ticker"):
                continue
            code = str(index["code"])
            symbols.append({
                "code": code, "ticker": str(index["ticker"]), "is_market_index": True,
                "latest_price_date": latest_by_code.get(code) or self._latest_price_date(code),
            })
        configured_codes = {item["code"] for item in symbols}
        for item in watchlist:
            code = str(item["code"])
            if code not in configured_codes:
                symbols.append({
                    "code": code, "ticker": self.ticker_for_code(code, suffix), "is_market_index": False,
                    "latest_price_date": item.get("latest_price_date"),
                })
        return symbols

    def _latest_price_date(self, code: str) -> str | None:
        with self.db.connect() as connection:
            return connection.execute("SELECT MAX(trade_date) FROM price_daily WHERE code=?", [code]).fetchone()[0]

    def _should_update_financials(self, code: str) -> bool:
        providers = self.settings.get("providers", {})
        jquants = providers.get("jquants", {}) if isinstance(providers, Mapping) else {}
        return bool(jquants.get("daily_financial_update", False)) and code.isdigit() and len(code) in {4, 5}

    def _update_market_regime(self, code: str) -> dict[str, object]:
        with self.db.connect() as connection:
            prices = pd.read_sql_query(
                "SELECT trade_date, close FROM price_daily WHERE code=? ORDER BY trade_date",
                connection, params=[code], parse_dates=["trade_date"],
            )
        classified = MarketRegimeAnalyzer(self.regime_config).classify(prices)
        rows = [{
            "market_code": code, "trade_date": row["trade_date"].date().isoformat(),
            "regime": row["regime"], "close": row["close"], "sma_short": row["sma_short"], "sma_long": row["sma_long"],
        } for _, row in classified.iterrows()]
        self.db.upsert_rows("market_regime", rows, ["market_code", "trade_date"])
        return {"code": code, **MarketRegimeAnalyzer.summary(classified)}

    @staticmethod
    def ticker_for_code(code: str, suffix: str) -> str:
        """Translate only Japanese numeric security codes; preserve index/foreign symbols."""
        if code.endswith(suffix) or not code.isdigit() or len(code) not in {4, 5}:
            return code
        return f"{code[:4]}{suffix}"

    @staticmethod
    def incremental_start(latest_price_date: str | None, overlap_days: int) -> str | None:
        if not latest_price_date:
            return None
        try:
            return (date.fromisoformat(latest_price_date) - timedelta(days=max(overlap_days, 0))).isoformat()
        except ValueError:
            return None
