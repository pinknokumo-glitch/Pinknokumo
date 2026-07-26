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
    position_side: str = "long"
    exit_reason: str = "holding_period"
    target_reached: bool = False

class Backtester:
    def __init__(self, indicator_config: Mapping[str, object], backtest_config: Mapping[str, object]) -> None:
        self.analyzer = TechnicalAnalyzer(indicator_config)
        self.config = backtest_config["backtest"]
        self.rules = RuleEngine()
        self.fundamentals = FundamentalAnalyzer()

    def run(
        self, prices: pd.DataFrame, rule: Mapping[str, object], holding_days: int,
        timeframe_prices: Mapping[str, pd.DataFrame] | None = None, financials: pd.DataFrame | None = None,
        exit_rule: Mapping[str, object] | None = None,
        position_side: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
    ) -> list[Trade]:
        self._ensure_supported_rule(rule)
        if exit_rule is not None:
            self._ensure_supported_rule(exit_rule)
        if position_side not in {"long", "short"}:
            raise ValueError("position_side must be long or short")
        if evaluation_mode not in {
            "condition_exit", "period_end", "within_period_up", "target_return"
        }:
            raise ValueError("evaluation_mode is invalid")
        if evaluation_mode == "condition_exit" and exit_rule is None:
            evaluation_mode = "period_end"
        if target_return_percent <= 0 or target_return_percent > 100:
            raise ValueError(
                "target_return_percent must be greater than 0 and at most 100"
            )
        computed = self.analyzer.calculate(prices).reset_index(drop=True)
        signal_frame = self._add_timeframe_values(computed, timeframe_prices or {})
        signal_frame = self._add_fundamental_values(signal_frame, financials)
        required_rows = holding_days + 2
        trades: list[Trade] = []
        for signal_index in range(len(computed) - required_rows + 1):
            values = self._values_at(signal_frame, signal_index)
            if not self.rules.evaluate(rule, values).matched:
                continue
            entry_index = signal_index + 1
            exit_index = entry_index + holding_days
            exit_price_field = "close"
            exit_reason = "holding_period"
            target_reached = False
            if evaluation_mode == "condition_exit" and exit_rule is not None:
                last_exit_signal_index = min(exit_index - 1, len(computed) - 2)
                for exit_signal_index in range(entry_index, last_exit_signal_index + 1):
                    exit_values = self._values_at(signal_frame, exit_signal_index)
                    if self.rules.evaluate(exit_rule, exit_values).matched:
                        exit_index = exit_signal_index + 1
                        exit_price_field = "open"
                        exit_reason = "condition"
                        target_reached = True
                        break
            entry = computed.iloc[entry_index]
            entry_price = float(entry["open"])
            if entry_price <= 0:
                continue
            if evaluation_mode == "within_period_up":
                for candidate_index in range(entry_index, exit_index + 1):
                    candidate_close = float(computed.iloc[candidate_index]["close"])
                    favorable = (
                        candidate_close > entry_price
                        if position_side == "long"
                        else candidate_close < entry_price
                    )
                    if favorable:
                        exit_index = candidate_index
                        exit_reason = "price_improvement"
                        target_reached = True
                        break
            target_exit_price: float | None = None
            if evaluation_mode == "target_return":
                target_fraction = target_return_percent / 100
                target_price = entry_price * (
                    1 + target_fraction if position_side == "long"
                    else 1 - target_fraction
                )
                for candidate_index in range(entry_index, exit_index + 1):
                    candidate = computed.iloc[candidate_index]
                    reached = (
                        float(candidate["high"]) >= target_price
                        if position_side == "long"
                        else float(candidate["low"]) <= target_price
                    )
                    if reached:
                        exit_index = candidate_index
                        target_exit_price = target_price
                        exit_reason = "target_return"
                        target_reached = True
                        break
            exit_row = computed.iloc[exit_index]
            exit_price = (
                target_exit_price
                if target_exit_price is not None
                else float(exit_row[exit_price_field])
            )
            if entry_price <= 0 or exit_price <= 0:
                continue
            path = computed.iloc[entry_index : exit_index + 1]
            if position_side == "long":
                return_percent = (exit_price / entry_price - 1) * 100
                favorable = (float(path["high"].max()) / entry_price - 1) * 100
                drawdown = (float(path["low"].min()) / entry_price - 1) * 100
            else:
                return_percent = (entry_price - exit_price) / entry_price * 100
                favorable = (entry_price - float(path["low"].min())) / entry_price * 100
                drawdown = (entry_price - float(path["high"].max())) / entry_price * 100
            if evaluation_mode == "period_end":
                target_reached = return_percent > 0
            trades.append(Trade(
                signal_date=self._date(computed.iloc[signal_index]["trade_date"]),
                entry_date=self._date(entry["trade_date"]),
                exit_date=self._date(exit_row["trade_date"]),
                entry_price=entry_price,
                exit_price=exit_price,
                return_percent=return_percent,
                max_favorable_excursion_percent=favorable,
                max_drawdown_percent=drawdown,
                position_side=position_side,
                exit_reason=exit_reason,
                target_reached=target_reached,
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
            return {
                "trade_count": 0, "average_return_percent": None,
                "win_rate_percent": None, "outcome_probability_percent": None,
                "median_return_percent": None, "max_drawdown_percent": None,
                "average_mfe_percent": None,
            }
        frame = pd.DataFrame(asdict(trade) for trade in trades)
        return {
            "trade_count": len(frame),
            "average_return_percent": float(frame["return_percent"].mean()),
            "median_return_percent": float(frame["return_percent"].median()),
            "win_rate_percent": float((frame["return_percent"] > 0).mean() * 100),
            "outcome_probability_percent": float(frame["target_reached"].mean() * 100),
            "max_drawdown_percent": float(frame["max_drawdown_percent"].min()),
            "average_mfe_percent": float(frame["max_favorable_excursion_percent"].mean()),
        }

    def run_horizons(
        self, prices: pd.DataFrame, rule: Mapping[str, object], holding_days: Iterable[int],
        timeframe_prices: Mapping[str, pd.DataFrame] | None = None, financials: pd.DataFrame | None = None,
        exit_rule: Mapping[str, object] | None = None,
        position_side: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
    ) -> dict[str, dict[str, float | int | None]]:
        return {
            str(days): self.summarize(
                self.run(
                    prices, rule, int(days), timeframe_prices, financials,
                    exit_rule=exit_rule, position_side=position_side,
                    evaluation_mode=evaluation_mode,
                    target_return_percent=target_return_percent,
                )
            )
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
