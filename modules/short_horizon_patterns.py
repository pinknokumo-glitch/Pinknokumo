"""Point-in-time short-horizon chart-pattern screening.

The scanner intentionally uses only the signal day's completed OHLCV data and
enters its historical examples at the *next* session's open.  It is separate
from user screening preferences and from requested single-stock analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping

import pandas as pd

from modules.technical import TechnicalAnalyzer


@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    direction: str
    label: str
    summary: str


PATTERNS = (
    PatternSpec("long_pullback_reversal", "long", "上昇・押し目反発", "上昇基調の押し目で、陽線とRSI反転を確認"),
    PatternSpec("long_volume_breakout", "long", "上昇・出来高上放れ", "上昇基調で直近高値を出来高増加とともに更新"),
    PatternSpec("short_rally_failure", "short", "下落警戒・戻り売り", "下降基調の戻りで、陰線とRSI失速を確認"),
    PatternSpec("short_volume_breakdown", "short", "下落警戒・出来高下放れ", "下降基調で直近安値を出来高増加とともに更新"),
)


class ShortHorizonPatternScanner:
    def __init__(self, indicator_config: Mapping[str, object], config: Mapping[str, object]) -> None:
        self.analyzer = TechnicalAnalyzer(indicator_config)
        self.config = config["short_horizon_patterns"]
        self.horizons = tuple(sorted({int(value) for value in self.config["horizons"]}))
        self.display_horizon = int(self.config["display_horizon"])
        self.target_percent = float(self.config["target_percent"])
        self.primary_thresholds = self._thresholds("primary")
        self.watch_thresholds = self._thresholds("watch")
        if not self.horizons or self.display_horizon not in self.horizons:
            raise ValueError("display_horizon must be included in horizons")

    def scan(self, frames: Mapping[str, pd.DataFrame], names: Mapping[str, str] | None = None) -> list[dict[str, object]]:
        """Return currently active signals with pooled, chronological statistics."""
        prepared: dict[str, pd.DataFrame] = {}
        pooled: dict[tuple[str, int], list[dict[str, float | str]]] = {
            (spec.pattern_id, horizon): [] for spec in PATTERNS for horizon in self.horizons
        }
        for code, source in frames.items():
            frame = self._prepare(source)
            if frame.empty:
                continue
            prepared[code] = frame
            for spec in PATTERNS:
                for index in self._signal_indexes(frame, spec):
                    for horizon in self.horizons:
                        sample = self._outcome(frame, index, horizon, spec.direction)
                        if sample is not None:
                            pooled[(spec.pattern_id, horizon)].append(sample)

        summaries = {
            key: self._summary(samples)
            for key, samples in pooled.items()
        }
        active: list[dict[str, object]] = []
        names = names or {}
        for code, frame in prepared.items():
            current_index = len(frame) - 1
            for spec in PATTERNS:
                if not self._matches(frame, current_index, spec):
                    continue
                stats = summaries[(spec.pattern_id, self.display_horizon)]
                tier = self._tier(stats)
                if tier is None:
                    continue
                latest = frame.iloc[current_index]
                close = float(latest["close"])
                resistance, support = self._levels(frame, current_index, close)
                target = close * (1 + self.target_percent / 100) if spec.direction == "long" else close * (1 - self.target_percent / 100)
                active.append({
                    "code": str(code),
                    "company_name": str(names.get(code, "")),
                    "pattern_id": spec.pattern_id,
                    "pattern_label": spec.label,
                    "direction": spec.direction,
                    "tier": tier,
                    "pattern_summary": spec.summary,
                    "signal_date": str(pd.Timestamp(latest["trade_date"]).date()),
                    "signal_close": round(close, 4),
                    "target_percent": self.target_percent,
                    "target_price": round(target, 4),
                    "resistance_price": resistance,
                    "support_price": support,
                    "holding_days": self.display_horizon,
                    "target_probability_percent": stats["target_probability_percent"],
                    "trade_count": stats["trade_count"],
                    "average_return_percent": stats["average_return_percent"],
                    "median_return_percent": stats["median_return_percent"],
                    "max_adverse_percent": stats["max_adverse_percent"],
                    "out_of_sample_trade_count": stats["out_of_sample_trade_count"],
                    "out_of_sample_target_probability_percent": stats["out_of_sample_target_probability_percent"],
                    "horizon_statistics": {
                        str(horizon): summaries[(spec.pattern_id, horizon)] for horizon in self.horizons
                    },
                    "morning_price": None,
                    "morning_price_at": None,
                    "morning_target_price": None,
                    "confirmation_status": "前日終値で抽出。朝の確認待ち",
                })
        return self._select(active)

    def _select(self, active: list[dict[str, object]]) -> list[dict[str, object]]:
        active.sort(key=lambda item: (
            0 if item["direction"] == "long" else 1,
            0 if item["tier"] == "primary" else 1,
            -float(item["target_probability_percent"]),
            -int(item["trade_count"]),
            str(item["code"]),
        ))
        selected = []
        for direction in ("long", "short"):
            for tier, thresholds in (("primary", self.primary_thresholds), ("watch", self.watch_thresholds)):
                rows = [row for row in active if row["direction"] == direction and row["tier"] == tier]
                selected.extend(rows[:int(thresholds["maximum_candidates_per_side"])])
        return [{**item, "position": position + 1} for position, item in enumerate(selected)]

    def _thresholds(self, tier: str) -> dict[str, float | int]:
        values = self.config.get(tier)
        if not isinstance(values, Mapping):
            # Backward-compatible for a local configuration created before tiers.
            values = self.config
        return {
            "minimum_trade_count": int(values["minimum_trade_count"]),
            "minimum_oos_trade_count": int(values["minimum_oos_trade_count"]),
            "minimum_probability_percent": float(values["minimum_probability_percent"]),
            "maximum_candidates_per_side": int(values.get("maximum_candidates_per_side", 20)),
        }

    def _prepare(self, source: pd.DataFrame) -> pd.DataFrame:
        required = {"trade_date", "open", "high", "low", "close", "volume"}
        if not required.issubset(source.columns):
            return pd.DataFrame()
        frame = source.copy().sort_values("trade_date").reset_index(drop=True)
        for column in required - {"trade_date"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=list(required)).reset_index(drop=True)
        frame = frame[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)].reset_index(drop=True)
        if len(frame) < 90:
            return pd.DataFrame()
        return self.analyzer.calculate(frame).reset_index(drop=True)

    def _signal_indexes(self, frame: pd.DataFrame, spec: PatternSpec) -> list[int]:
        # The last usable index must leave one entry session and the full horizon.
        maximum = len(frame) - self.display_horizon - 1
        return [index for index in range(75, max(75, maximum + 1)) if self._matches(frame, index, spec)]

    @staticmethod
    def _finite(*values: object) -> bool:
        try:
            return all(pd.notna(value) and math.isfinite(float(value)) for value in values)
        except (TypeError, ValueError):
            return False

    def _matches(self, frame: pd.DataFrame, index: int, spec: PatternSpec) -> bool:
        if index < 75 or index >= len(frame):
            return False
        row, previous = frame.iloc[index], frame.iloc[index - 1]
        needed = (row["open"], row["high"], row["low"], row["close"], row.get("sma_25"), row.get("sma_75"),
                  row.get("rsi_9"), previous.get("rsi_9"), row.get("volume_ratio_20"))
        if not self._finite(*needed):
            return False
        open_price, high, low, close = (float(row[key]) for key in ("open", "high", "low", "close"))
        body, span = abs(close - open_price), high - low
        if span <= 0:
            return False
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        uptrend = float(row["sma_25"]) >= float(row["sma_75"])
        downtrend = float(row["sma_25"]) <= float(row["sma_75"])
        rsi, previous_rsi = float(row["rsi_9"]), float(previous["rsi_9"])
        previous_twenty = frame.iloc[index - 20:index]
        if previous_twenty.empty:
            return False
        if spec.pattern_id == "long_pullback_reversal":
            return uptrend and close > open_price and rsi > previous_rsi and previous_rsi <= 50 and lower_shadow >= max(body, span * 0.25)
        if spec.pattern_id == "long_volume_breakout":
            return uptrend and close > float(previous_twenty["high"].max()) and float(row["volume_ratio_20"]) >= 130
        if spec.pattern_id == "short_rally_failure":
            return downtrend and close < open_price and rsi < previous_rsi and previous_rsi >= 50 and upper_shadow >= max(body, span * 0.25)
        if spec.pattern_id == "short_volume_breakdown":
            return downtrend and close < float(previous_twenty["low"].min()) and float(row["volume_ratio_20"]) >= 130
        return False

    def _outcome(self, frame: pd.DataFrame, signal_index: int, horizon: int, direction: str) -> dict[str, float | str] | None:
        entry_index = signal_index + 1
        end_index = entry_index + horizon - 1
        if end_index >= len(frame):
            return None
        entry = float(frame.iloc[entry_index]["open"])
        path = frame.iloc[entry_index:end_index + 1]
        if not self._finite(entry, *path[["high", "low", "close"]].to_numpy().ravel()) or entry <= 0:
            return None
        end_close = float(path.iloc[-1]["close"])
        if direction == "long":
            target_hit = float(path["high"].max()) >= entry * (1 + self.target_percent / 100)
            terminal_return = (end_close / entry - 1) * 100
            adverse = (float(path["low"].min()) / entry - 1) * 100
        else:
            target_hit = float(path["low"].min()) <= entry * (1 - self.target_percent / 100)
            terminal_return = (entry / end_close - 1) * 100
            adverse = (entry / float(path["high"].max()) - 1) * 100
        return {
            "signal_date": str(pd.Timestamp(frame.iloc[signal_index]["trade_date"]).date()),
            "target_hit": float(target_hit),
            "terminal_return": terminal_return,
            "adverse": adverse,
        }

    def _summary(self, samples: list[dict[str, float | str]]) -> dict[str, float | int | None]:
        if not samples:
            return {"trade_count": 0, "target_probability_percent": None, "average_return_percent": None,
                    "median_return_percent": None, "max_adverse_percent": None, "out_of_sample_trade_count": 0,
                    "out_of_sample_target_probability_percent": None}
        frame = pd.DataFrame(samples).sort_values("signal_date")
        oos_count = max(1, math.ceil(len(frame) * 0.2))
        oos = frame.tail(oos_count)
        return {
            "trade_count": int(len(frame)),
            "target_probability_percent": round(float(frame["target_hit"].mean() * 100), 2),
            "average_return_percent": round(float(frame["terminal_return"].mean()), 2),
            "median_return_percent": round(float(frame["terminal_return"].median()), 2),
            "max_adverse_percent": round(float(frame["adverse"].min()), 2),
            "out_of_sample_trade_count": int(len(oos)),
            "out_of_sample_target_probability_percent": round(float(oos["target_hit"].mean() * 100), 2),
        }

    @staticmethod
    def _eligible(stats: Mapping[str, object], thresholds: Mapping[str, float | int]) -> bool:
        probability = stats.get("target_probability_percent")
        out_of_sample_probability = stats.get("out_of_sample_target_probability_percent")
        return (
            int(stats.get("trade_count") or 0) >= int(thresholds["minimum_trade_count"])
            and int(stats.get("out_of_sample_trade_count") or 0) >= int(thresholds["minimum_oos_trade_count"])
            and probability is not None
            and float(probability) >= float(thresholds["minimum_probability_percent"])
            and out_of_sample_probability is not None
            and float(out_of_sample_probability) >= float(thresholds["minimum_probability_percent"])
        )

    def _tier(self, stats: Mapping[str, object]) -> str | None:
        if self._eligible(stats, self.primary_thresholds):
            return "primary"
        if self._eligible(stats, self.watch_thresholds):
            return "watch"
        return None

    @staticmethod
    def _levels(frame: pd.DataFrame, index: int, close: float) -> tuple[float | None, float | None]:
        history = frame.iloc[max(0, index - 60):index]
        if history.empty:
            return None, None
        above = history.loc[history["high"] > close, "high"]
        below = history.loc[history["low"] < close, "low"]
        resistance = round(float(above.min()), 4) if not above.empty else None
        support = round(float(below.max()), 4) if not below.empty else None
        return resistance, support
