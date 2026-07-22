"""Market-regime classification from a broad-market index price series."""
from __future__ import annotations

from collections.abc import Mapping
import pandas as pd


class MarketRegimeAnalyzer:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config["market_regime"]

    def classify(self, prices: pd.DataFrame) -> pd.DataFrame:
        if not {"trade_date", "close"}.issubset(prices.columns):
            raise ValueError("prices must contain trade_date and close")
        frame = prices.copy().sort_values("trade_date")
        short_period = int(self.config["short_moving_average"])
        long_period = int(self.config["long_moving_average"])
        frame["sma_short"] = frame["close"].rolling(short_period, min_periods=short_period).mean()
        frame["sma_long"] = frame["close"].rolling(long_period, min_periods=long_period).mean()
        labels = self.config["labels"]
        frame["regime"] = labels["neutral"]
        valid = frame["sma_long"].notna()
        bullish = valid & (frame["close"] > frame["sma_long"]) & (frame["sma_short"] > frame["sma_long"])
        bearish = valid & (frame["close"] < frame["sma_long"]) & (frame["sma_short"] < frame["sma_long"])
        frame.loc[bullish, "regime"] = labels["bullish"]
        frame.loc[bearish, "regime"] = labels["bearish"]
        return frame

    @staticmethod
    def summary(classified: pd.DataFrame) -> dict[str, object]:
        if classified.empty:
            return {"current_regime": None, "counts": {}}
        return {
            "current_regime": str(classified.iloc[-1]["regime"]),
            "counts": {str(key): int(value) for key, value in classified["regime"].value_counts().items()},
        }
