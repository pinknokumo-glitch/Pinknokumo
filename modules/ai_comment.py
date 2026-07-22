"""Generate a factual Japanese commentary from stored backtest statistics.

This module explains calculated data only; it does not predict prices or issue trade instructions.
"""
from __future__ import annotations

from collections.abc import Mapping


class AnalysisCommentary:
    def backtest_comment(self, summary: Mapping[str, object], expectation: Mapping[str, object]) -> str:
        count = int(summary["trade_count"])
        if count == 0:
            return "条件に一致した過去シグナルがないため、統計的な評価はできません。条件を緩めるか、対象期間を長くしてください。"
        average = float(summary["average_return_percent"])
        win_rate = float(summary["win_rate_percent"])
        drawdown = float(summary["max_drawdown_percent"])
        score, grade = float(expectation["score"]), str(expectation["grade"])
        direction = "プラス" if average > 0 else "マイナス"
        reliability = "サンプル数が限られる" if count < 30 else "一定数のサンプルがある"
        risk = "下振れ幅も比較的抑えられています" if drawdown >= -15 else "大きな含み損が発生した局面があります"
        return (
            f"過去シグナルは{count}件で、指定保有期間の平均リターンは{average:.1f}%（{direction}）、"
            f"勝率は{win_rate:.1f}%でした。最大含み損は{drawdown:.1f}%で、{risk}。"
            f"期待値スコアは{score:.1f}/100（{grade}）です。{reliability}ため、将来の結果を保証するものではありません。"
        )
