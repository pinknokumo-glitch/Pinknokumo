"""Convert a backtest summary into an explainable 0-100 expectation score."""
from __future__ import annotations

from collections.abc import Mapping

class ExpectationScorer:
    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config["expectation_score"]

    def score(self, summary: Mapping[str, float | int | None]) -> dict[str, float | str]:
        if not summary["trade_count"]:
            return {"score": 0.0, "grade": "N/A", "comment": "バックテスト対象の取引がありません。"}
        targets, weights = self.config["targets"], self.config["weights"]
        components = {
            "average_return": self._cap(float(summary["average_return_percent"]) / float(targets["average_return_percent"]) * 100),
            "win_rate": self._cap(float(summary["win_rate_percent"]) / float(targets["win_rate_percent"]) * 100),
            "max_drawdown": self._cap(abs(float(targets["max_drawdown_percent"])) / abs(float(summary["max_drawdown_percent"])) * 100) if summary["max_drawdown_percent"] else 100.0,
            "sample_size": self._cap(float(summary["trade_count"]) / float(targets["sample_size"]) * 100),
        }
        score = sum(components[name] * float(weights[name]) for name in components)
        grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
        return {"score": round(score, 1), "grade": grade, **{f"{name}_component": round(value, 1) for name, value in components.items()}}

    @staticmethod
    def _cap(value: float) -> float:
        return max(0.0, min(100.0, value))

