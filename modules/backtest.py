"""Historical rule backtesting with next-session entries to prevent look-ahead bias."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import pandas as pd

from modules.rule_engine import RuleEngine
from modules.technical import TechnicalAnalyzer
from modules.fundamentals import FundamentalAnalyzer

@dataclass(frozen=True)
class Trade:
    signal_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_percent: float
    max_favorable_excursion_percent: float
    max_drawdown_percent: float

class Backtester:
    def __init__(self, indicator_config: Mapping[str, object], backtest_config: Mapping[str, object]) -> None:
        self.analyzer = TechnicalAnalyzer(indicator_config)
        self.config = backtest_config["backtest"]
        self.rules = RuleEngine()
        self.fundamentals = FundamentalAnalyzer()

    def run(
        self, prices: pd.DataFrame, rule: Mapping[str, object], holding_days: int,
        timeframe_prices: Mapping[str, pd.DataFrame] | None = None, financials: pd.DataFrame | None = None,
    ) -> list[Trade]:
        self._ensure_supported_rule(rule)
        computed = self.analyzer.calculate(prices).reset_index(drop=True)
        signal_frame = self._add_timeframe_values(computed, timeframe_prices or {})
        signal_frame = self._add_fundamental_values(signal_frame, financials)
        required_rows = holding_days + 2
        trades: list[Trade] = []
        for signal_index in range(len(computed) - required_rows + 1):
            values = self._values_at(signal_frame, signal_index)
            if not self.rules.evaluate(rule, values).matched:
                continue
            entry_index, exit_index = signal_index + 1, signal_index + 1 + holding_days
            entry, exit_row = computed.iloc[entry_index], computed.iloc[exit_index]
            entry_price = float(entry["open"])
            if entry_price <= 0:
                continue
            path = computed.iloc[entry_index : exit_index + 1]
            trades.append(Trade(
                signal_date=self._date(computed.iloc[signal_index]["trade_date"]),
                entry_date=self._date(entry["trade_date"]),
                exit_date=self._date(exit_row["trade_date"]),
                entry_price=entry_price,
                exit_price=float(exit_row["close"]),
                return_percent=(float(exit_row["close"]) / entry_price - 1) * 100,
                max_favorable_excursion_percent=(float(path["high"].max()) / entry_price - 1) * 100,
                max_drawdown_percent=(float(path["low"].min()) / entry_price - 1) * 100,
            ))
        return trades

    @classmethod
    def _ensure_supported_rule(cls, rule: Mapping[str, object]) -> None:
        for key in ("all", "any"):
            if key in rule:
                for child in rule[key]:
                    cls._ensure_supported_rule(child)
                return
        if "not" in rule:
            cls._ensure_supported_rule(rule["not"])
            return
        for key in ("field", "value_from"):
            value = rule.get(key)
            if isinstance(value, str) and not value.startswith(("daily.", "weekly.", "monthly.", "fundamental.")):
                raise ValueError("Backtesting supports daily.*, weekly.*, monthly.*, and fundamental.* conditions only")

    def _add_timeframe_values(self, daily: pd.DataFrame, timeframe_prices: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        signal_frame = daily.copy().sort_values("trade_date").reset_index(drop=True)
        signal_frame["trade_date"] = pd.to_datetime(signal_frame["trade_date"])
        for timeframe in ("weekly", "monthly"):
            prices = timeframe_prices.get(timeframe)
            if prices is None or prices.empty:
                continue
            computed = self.analyzer.calculate(prices).sort_values("trade_date")
            computed["trade_date"] = pd.to_datetime(computed["trade_date"])
            renamed = computed.rename(columns={column: f"{timeframe}__{column}" for column in computed.columns if column != "trade_date"})
            signal_frame = pd.merge_asof(signal_frame, renamed, on="trade_date", direction="backward")
        return signal_frame

    def _add_fundamental_values(self, signal_frame: pd.DataFrame, financials: pd.DataFrame | None) -> pd.DataFrame:
        if financials is None or financials.empty:
            return signal_frame
        required = {"disclosed_date", "earnings_per_share", "book_value_per_share"}
        if not required.issubset(financials.columns):
            return signal_frame
        financial = financials.copy()
        financial["disclosed_date"] = pd.to_datetime(financial["disclosed_date"])
        financial = financial.sort_values("disclosed_date").drop_duplicates("disclosed_date", keep="last")
        base = signal_frame.sort_values("trade_date").copy()
        joined = pd.merge_asof(base, financial, left_on="trade_date", right_on="disclosed_date", direction="backward")
        dividends = base["dividends"] if "dividends" in base else pd.Series(0.0, index=base.index)
        trailing_dividends = pd.Series(dividends.to_list(), index=pd.to_datetime(base["trade_date"])).rolling("365D").sum().to_list()
        values = [
            self.fundamentals.latest_values(row, row.get("close"), dividend)
            for (_, row), dividend in zip(joined.iterrows(), trailing_dividends)
        ]
        for name in {key for item in values for key in item}:
            base[f"fundamental__{name}"] = [item.get(name) for item in values]
        return base

    def summarize(self, trades: list[Trade]) -> dict[str, float | int | None]:
        if not trades:
            return {"trade_count": 0, "average_return_percent": None, "win_rate_percent": None, "median_return_percent": None, "max_drawdown_percent": None, "average_mfe_percent": None}
        frame = pd.DataFrame(asdict(trade) for trade in trades)
        return {
            "trade_count": len(frame),
            "average_return_percent": float(frame["return_percent"].mean()),
            "median_return_percent": float(frame["return_percent"].median()),
            "win_rate_percent": float((frame["return_percent"] > 0).mean() * 100),
            "max_drawdown_percent": float(frame["max_drawdown_percent"].min()),
            "average_mfe_percent": float(frame["max_favorable_excursion_percent"].mean()),
        }

    def run_horizons(
        self, prices: pd.DataFrame, rule: Mapping[str, object], holding_days: Iterable[int],
        timeframe_prices: Mapping[str, pd.DataFrame] | None = None, financials: pd.DataFrame | None = None,
    ) -> dict[str, dict[str, float | int | None]]:
        return {
            str(days): self.summarize(self.run(prices, rule, int(days), timeframe_prices, financials))
            for days in holding_days
        }

    @staticmethod
    def _date(value: object) -> str:
        return pd.Timestamp(value).date().isoformat()

    @staticmethod
    def _values_at(frame: pd.DataFrame, index: int) -> dict[str, object]:
        current = frame.iloc[index].to_dict()
        previous = frame.iloc[index - 1].to_dict() if index else {}
        values = {}
        for name, value in current.items():
            if not pd.notna(value):
                continue
            if "__" in name:
                timeframe, indicator = name.split("__", 1)
                values[f"{timeframe}.{indicator}"] = value
            else:
                values[f"daily.{name}"] = value
        for name, value in previous.items():
            if not pd.notna(value):
                continue
            prefix, indicator = (name.split("__", 1) if "__" in name else ("daily", name))
            if indicator.startswith(("rsi_", "macd", "sma_", "adx_", "atr_", "stoch_")):
                values[f"{prefix}.{indicator}_previous"] = value
        return values
