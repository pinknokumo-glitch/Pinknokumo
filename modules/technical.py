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
            delta = close.diff()
            gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
            for period in self._periods(rsi_cfg):
                avg_gain = gain.ewm(
                    alpha=1 / period, adjust=False, min_periods=period,
                ).mean()
                avg_loss = loss.ewm(
                    alpha=1 / period, adjust=False, min_periods=period,
                ).mean()
                rsi = 100 - (100 / (1 + avg_gain / avg_loss.replace(0, pd.NA)))
                rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
                rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
                frame[f"rsi_{period}"] = rsi.mask(
                    (avg_gain == 0) & (avg_loss == 0), 50.0,
                )

        macd_cfg = self.config["macd"]
        if macd_cfg["enabled"]:
            default_macd = tuple(
                int(macd_cfg[key]) for key in ("fast", "slow", "signal")
            )
            for fast, slow, signal in self._macd_presets(macd_cfg):
                macd = (
                    close.ewm(span=fast, adjust=False).mean()
                    - close.ewm(span=slow, adjust=False).mean()
                )
                signal_line = macd.ewm(span=signal, adjust=False).mean()
                suffix = f"{fast}_{slow}_{signal}"
                frame[f"macd_{suffix}"] = macd
                frame[f"macd_signal_{suffix}"] = signal_line
                frame[f"macd_histogram_{suffix}"] = macd - signal_line
                if (fast, slow, signal) == default_macd:
                    # Preserve every saved profile that uses the original field names.
                    frame["macd"] = macd
                    frame["macd_signal"] = signal_line
                    frame["macd_histogram"] = macd - signal_line

        ma_cfg = self.config["moving_average"]
        if ma_cfg["enabled"]:
            for period in ma_cfg["periods"]:
                period = int(period)
                average = close.rolling(period, min_periods=period).mean()
                frame[f"sma_{period}"] = average
                frame[f"price_vs_sma_{period}_percent"] = (close / average - 1) * 100

        bb_cfg = self.config["bollinger_bands"]
        if bb_cfg["enabled"]:
            period, deviations = int(bb_cfg["period"]), float(bb_cfg["standard_deviations"])
            middle = close.rolling(period, min_periods=period).mean()
            std = close.rolling(period, min_periods=period).std()
            frame["bb_middle"], frame["bb_upper"], frame["bb_lower"] = middle, middle + deviations * std, middle - deviations * std
            width = (frame["bb_upper"] - frame["bb_lower"]).replace(0, pd.NA)
            frame["bb_percent_b"] = (close - frame["bb_lower"]) / width * 100

        atr_cfg = self.config["atr"]
        if atr_cfg["enabled"]:
            period = int(atr_cfg["period"])
            previous_close = close.shift()
            true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
            frame[f"atr_{period}"] = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
            frame[f"atr_{period}_percent"] = frame[f"atr_{period}"] / close * 100

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
            default_stochastic = (
                int(stoch_cfg["k_period"]), int(stoch_cfg["d_period"]),
            )
            for k_period, d_period in self._stochastic_presets(stoch_cfg):
                lowest = low.rolling(k_period).min()
                highest = high.rolling(k_period).max()
                stochastic_k = 100 * (close - lowest) / (highest - lowest)
                stochastic_d = stochastic_k.rolling(d_period).mean()
                suffix = f"{k_period}_{d_period}"
                frame[f"stoch_k_{suffix}"] = stochastic_k
                frame[f"stoch_d_{suffix}"] = stochastic_d
                if (k_period, d_period) == default_stochastic:
                    frame["stoch_k"] = stochastic_k
                    frame["stoch_d"] = stochastic_d
        for sessions in (5, 20, 60):
            frame[f"return_{sessions}_percent"] = close.pct_change(sessions) * 100
        volume_average = frame["volume"].rolling(20, min_periods=20).mean()
        frame["volume_ratio_20"] = frame["volume"] / volume_average * 100
        return frame

    @staticmethod
    def _periods(config: Mapping[str, object]) -> list[int]:
        raw_periods = config.get("periods") or [config["period"]]
        periods = list(dict.fromkeys(int(value) for value in raw_periods))
        if not periods or any(period <= 0 for period in periods):
            raise ValueError("indicator periods must contain positive integers")
        return periods

    @staticmethod
    def _macd_presets(config: Mapping[str, object]) -> list[tuple[int, int, int]]:
        raw_presets = config.get("presets") or [{
            "fast": config["fast"], "slow": config["slow"],
            "signal": config["signal"],
        }]
        presets = list(dict.fromkeys(
            (int(item["fast"]), int(item["slow"]), int(item["signal"]))
            for item in raw_presets
        ))
        if not presets or any(
            fast <= 0 or slow <= fast or signal <= 0
            for fast, slow, signal in presets
        ):
            raise ValueError("MACD presets require 0 < fast < slow and signal > 0")
        return presets

    @staticmethod
    def _stochastic_presets(config: Mapping[str, object]) -> list[tuple[int, int]]:
        raw_presets = config.get("presets") or [{
            "k_period": config["k_period"], "d_period": config["d_period"],
        }]
        presets = list(dict.fromkeys(
            (int(item["k_period"]), int(item["d_period"]))
            for item in raw_presets
        ))
        if not presets or any(k_period <= 0 or d_period <= 0 for k_period, d_period in presets):
            raise ValueError("stochastic presets require positive periods")
        return presets

    @staticmethod
    def latest_values(frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty:
            return {}
        latest = frame.iloc[-1].to_dict()
        values = {name: value for name, value in latest.items() if pd.notna(value)}
        previous = frame.iloc[-2].to_dict() if len(frame) > 1 else {}
        for name, value in previous.items():
            if name.startswith((
                "rsi_", "macd", "sma_", "adx_", "atr_", "stoch_",
                "price_vs_sma_", "bb_", "return_", "volume_ratio_",
            )) and pd.notna(value):
                values[f"{name}_previous"] = value
        return values
