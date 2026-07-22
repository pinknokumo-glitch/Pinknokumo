"""Technical indicator calculations driven by config/indicators.yaml."""
from __future__ import annotations

from collections.abc import Mapping
import pandas as pd

class TechnicalAnalyzer:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config["indicators"]

    def calculate(self, prices: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(prices.columns.str.lower())
        if missing:
            raise ValueError(f"Missing price columns: {', '.join(sorted(missing))}")
        frame = prices.copy()
        frame.columns = [str(column).lower() for column in frame.columns]
        close, high, low = frame["close"], frame["high"], frame["low"]

        rsi_cfg = self.config["rsi"]
        if rsi_cfg["enabled"]:
            period = int(rsi_cfg["period"])
            delta = close.diff()
            gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            rsi = 100 - (100 / (1 + avg_gain / avg_loss.replace(0, pd.NA)))
            rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
            rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
            frame[f"rsi_{period}"] = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50.0)

        macd_cfg = self.config["macd"]
        if macd_cfg["enabled"]:
            fast, slow, signal = (int(macd_cfg[key]) for key in ("fast", "slow", "signal"))
            macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
            frame["macd"], frame["macd_signal"] = macd, macd.ewm(span=signal, adjust=False).mean()
            frame["macd_histogram"] = frame["macd"] - frame["macd_signal"]

        ma_cfg = self.config["moving_average"]
        if ma_cfg["enabled"]:
            for period in ma_cfg["periods"]:
                frame[f"sma_{int(period)}"] = close.rolling(int(period), min_periods=int(period)).mean()

        bb_cfg = self.config["bollinger_bands"]
        if bb_cfg["enabled"]:
            period, deviations = int(bb_cfg["period"]), float(bb_cfg["standard_deviations"])
            middle = close.rolling(period, min_periods=period).mean()
            std = close.rolling(period, min_periods=period).std()
            frame["bb_middle"], frame["bb_upper"], frame["bb_lower"] = middle, middle + deviations * std, middle - deviations * std

        atr_cfg = self.config["atr"]
        if atr_cfg["enabled"]:
            period = int(atr_cfg["period"])
            previous_close = close.shift()
            true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
            frame[f"atr_{period}"] = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

        adx_cfg = self.config["adx"]
        if adx_cfg["enabled"]:
            period = int(adx_cfg["period"])
            up_move, down_move = high.diff(), -low.diff()
            plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
            minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
            tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
            atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
            minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
            frame[f"adx_{period}"] = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

        stoch_cfg = self.config["stochastic"]
        if stoch_cfg["enabled"]:
            k_period, d_period = int(stoch_cfg["k_period"]), int(stoch_cfg["d_period"])
            lowest, highest = low.rolling(k_period).min(), high.rolling(k_period).max()
            frame["stoch_k"] = 100 * (close - lowest) / (highest - lowest)
            frame["stoch_d"] = frame["stoch_k"].rolling(d_period).mean()
        return frame

    @staticmethod
    def latest_values(frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty:
            return {}
        latest = frame.iloc[-1].to_dict()
        values = {name: value for name, value in latest.items() if pd.notna(value)}
        previous = frame.iloc[-2].to_dict() if len(frame) > 1 else {}
        for name, value in previous.items():
            if name.startswith(("rsi_", "macd", "sma_", "adx_", "atr_", "stoch_")) and pd.notna(value):
                values[f"{name}_previous"] = value
        return values
