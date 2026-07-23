"""Market-data loaders for StockAI."""
from __future__ import annotations

import os
import time
from datetime import date, datetime
from collections.abc import Mapping
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from modules.database import Database

def clean(value: object) -> object:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.date().isoformat() if isinstance(value, (pd.Timestamp, datetime)) else value.isoformat()
    return None if pd.isna(value) else value

def first(row: Mapping[str, object], *names: str) -> object:
    return next((row[name] for name in names if row.get(name) not in (None, "")), None)

class DataLoader:
    def __init__(self, database: Database, settings: Mapping[str, object]) -> None:
        self.db, self.settings = database, settings

    def load_yfinance_prices(
        self, ticker: str, code: str, period: str | None = None, start: str | None = None,
    ) -> int:
        cfg = self.settings["providers"]["yfinance"]
        frame, last_error = None, None
        request = {
            "interval": cfg["interval"], "auto_adjust": cfg["auto_adjust"],
            "repair": cfg["repair"], "actions": True,
        }
        if start:
            request["start"] = start
        else:
            request["period"] = period or cfg["period"]
        for attempt in range(int(cfg.get("retries", 1))):
            try:
                frame = yf.Ticker(ticker).history(**request)
                if not frame.empty:
                    break
            except Exception as error:
                last_error = error
            if attempt + 1 < int(cfg.get("retries", 1)):
                time.sleep(float(cfg.get("retry_delay_seconds", 0)))
        if frame is None:
            if last_error is not None:
                raise RuntimeError(f"Could not download {ticker} after {cfg.get('retries', 1)} attempts") from last_error
            raise RuntimeError(f"No price data returned for {ticker}")
        if frame.empty:
            raise RuntimeError(f"No price data returned for {ticker}")
        return self._save_yfinance_frame(code, frame)

    def load_yfinance_batch(
        self,
        ticker_codes: list[tuple[str, str]],
        period: str,
    ) -> dict[str, object]:
        """Download a bounded ticker batch and persist every returned security."""
        if not ticker_codes:
            return {"updated": [], "failed": []}
        cfg = self.settings["providers"]["yfinance"]
        tickers = [ticker for ticker, _ in ticker_codes]
        try:
            frame = yf.download(
                tickers=tickers,
                period=period,
                interval=cfg["interval"],
                auto_adjust=cfg["auto_adjust"],
                repair=cfg["repair"],
                actions=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as error:
            return {
                "updated": [],
                "failed": [{"code": code, "ticker": ticker, "error": str(error)}
                           for ticker, code in ticker_codes],
            }
        updated, failed = [], []
        for ticker, code in ticker_codes:
            try:
                ticker_frame = self._ticker_frame(frame, ticker, len(ticker_codes))
                count = self._save_yfinance_frame(code, ticker_frame)
                updated.append({"code": code, "ticker": ticker, "daily_rows": count})
            except Exception as error:
                failed.append({"code": code, "ticker": ticker, "error": str(error)})
        return {"updated": updated, "failed": failed}

    @staticmethod
    def _ticker_frame(frame: pd.DataFrame, ticker: str, ticker_count: int) -> pd.DataFrame:
        if frame.empty:
            raise RuntimeError("No batch price data returned")
        if isinstance(frame.columns, pd.MultiIndex):
            level0 = frame.columns.get_level_values(0)
            level1 = frame.columns.get_level_values(1)
            if ticker in level0:
                return frame[ticker].dropna(how="all")
            if ticker in level1:
                return frame.xs(ticker, axis=1, level=1).dropna(how="all")
        if ticker_count == 1:
            return frame.dropna(how="all")
        raise RuntimeError(f"No price data returned for {ticker}")

    def _save_yfinance_frame(self, code: str, frame: pd.DataFrame) -> int:
        if frame is None or frame.empty:
            raise RuntimeError(f"No price data returned for {code}")
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        frame.index.name = "trade_date"
        frame = frame.reset_index()
        frame["trade_date"] = frame["trade_date"].dt.date.astype(str)
        rows = [self._price_row(code, item) for item in frame.to_dict("records")]
        saved = self.db.upsert_rows("price_daily", rows, ["code", "trade_date"])
        self._save_resampled(code, frame, "price_weekly", self.settings["resampling"]["weekly_rule"])
        self._save_resampled(code, frame, "price_monthly", self.settings["resampling"]["monthly_rule"])
        return saved

    def _price_row(self, code: str, item: Mapping[str, object]) -> dict[str, object]:
        return {
            "code": code, "trade_date": str(item["trade_date"]),
            "open": clean(item.get("Open")), "high": clean(item.get("High")),
            "low": clean(item.get("Low")), "close": clean(item.get("Close")),
            "adjusted_close": clean(item.get("Adj Close", item.get("Close"))),
            "volume": clean(item.get("Volume")), "dividends": clean(item.get("Dividends", 0)),
            "stock_splits": clean(item.get("Stock Splits", 0)),
        }

    def _save_resampled(self, code: str, frame: pd.DataFrame, table: str, rule: str) -> None:
        indexed = frame.set_index(pd.to_datetime(frame["trade_date"]))
        aggregation = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        for column, func in (("Adj Close", "last"), ("Dividends", "sum"), ("Stock Splits", "sum")):
            if column in indexed: aggregation[column] = func
        sampled = indexed.resample(rule).agg(aggregation).dropna(subset=["Close"]).reset_index()
        sampled["trade_date"] = sampled["trade_date"].dt.date.astype(str)
        self.db.upsert_rows(table, [self._price_row(code, item) for item in sampled.to_dict("records")], ["code", "trade_date"])

    def load_jquants(self, financial_code: str | None = None) -> tuple[int, int]:
        client = self._jquants_client()
        masters = self._as_records(client.get_eq_master())
        master_rows = [{
            "code": str(first(row, "Code", "code") or ""),
            "company_name": first(row, "CompanyName", "CoName", "company_name", "Name"),
            "company_name_en": first(row, "CompanyNameEnglish", "CoNameEn", "company_name_en"),
            "market_code": first(row, "MarketCode", "Mkt", "market_code"),
            "market_name": first(row, "MarketCodeName", "MktNm", "market_name"),
            "sector_17_code": first(row, "Sector17Code", "S17", "sector_17_code"),
            "sector_17_name": first(row, "Sector17CodeName", "S17Nm", "sector_17_name"),
            "sector_33_code": first(row, "Sector33Code", "S33", "sector_33_code"),
            "sector_33_name": first(row, "Sector33CodeName", "S33Nm", "sector_33_name"),
            "scale_category": first(row, "ScaleCategory", "ScaleCat", "scale_category"),
            "listed_date": first(row, "ListedDate", "Date", "listed_date"),
            "delisted_date": first(row, "DelistedDate", "delisted_date"),
        } for row in masters if first(row, "Code", "code")]
        master_rows = [{key: clean(value) for key, value in row.items()} for row in master_rows]
        master_count = self.db.upsert_rows("master_stock", master_rows, ["code"])
        financial_count = self._save_financial(client.get_fin_summary(code=financial_code)) if financial_code else 0
        return master_count, financial_count

    def load_jquants_financial(self, financial_code: str) -> int:
        """Refresh one security's financial disclosures without reloading the full master."""
        return self._save_financial(self._jquants_client().get_fin_summary(code=financial_code))

    def _jquants_client(self):
        load_dotenv()
        api_key = os.getenv(self.settings["providers"]["jquants"]["api_key_env"])
        if not api_key:
            raise RuntimeError("J-Quants API key is missing. Set it in .env.")
        import jquantsapi
        return jquantsapi.ClientV2(api_key=api_key)

    def _save_financial(self, response: object) -> int:
        rows = self._as_records(response)
        normalized = [{
            "code": str(first(row, "Code", "code") or ""),
            "disclosed_date": str(clean(first(row, "DisclosedDate", "DiscDate", "disclosed_date")) or ""),
            "document_type": str(first(row, "TypeOfDocument", "DocType", "document_type") or ""),
            "fiscal_year": first(row, "FiscalYear", "CurFYEn", "fiscal_year"),
            "fiscal_quarter": first(row, "FiscalQuarter", "CurPerType", "fiscal_quarter"),
            "net_sales": first(row, "NetSales", "Sales", "net_sales"),
            "operating_profit": first(row, "OperatingProfit", "OP", "operating_profit"),
            "ordinary_profit": first(row, "OrdinaryProfit", "OdP", "ordinary_profit"),
            "profit": first(row, "Profit", "NP", "profit"),
            "earnings_per_share": first(row, "EarningsPerShare", "EPS", "earnings_per_share"),
            "book_value_per_share": first(row, "BookValuePerShare", "BPS", "book_value_per_share"),
            "total_assets": first(row, "TotalAssets", "TA", "total_assets"),
            "equity": first(row, "Equity", "Eq", "equity"),
            "equity_ratio": first(row, "EquityToAssetRatio", "EqAR", "equity_ratio"),
            "cash_flows_from_operating_activities": first(row, "CashFlowsFromOperatingActivities", "CFO", "cash_flows_from_operating_activities"),
            "cash_flows_from_investing_activities": first(row, "CashFlowsFromInvestingActivities", "CFI", "cash_flows_from_investing_activities"),
            "cash_flows_from_financing_activities": first(row, "CashFlowsFromFinancingActivities", "CFF", "cash_flows_from_financing_activities"),
            "raw_json": row,
        } for row in rows if first(row, "Code", "code") and first(row, "DisclosedDate", "DiscDate", "disclosed_date")]
        normalized = [
            {key: value if key == "raw_json" else clean(value) for key, value in row.items()}
            for row in normalized
        ]
        return self.db.save_financial_rows(normalized)

    @staticmethod
    def _as_records(response: object) -> list[dict[str, object]]:
        if isinstance(response, pd.DataFrame): return response.to_dict("records")
        if isinstance(response, list): return [dict(row) for row in response]
        if isinstance(response, dict):
            for value in response.values():
                if isinstance(value, list): return [dict(row) for row in value]
        raise TypeError(f"Unexpected J-Quants response type: {type(response).__name__}")
