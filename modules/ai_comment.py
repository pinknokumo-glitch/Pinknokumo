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

    @staticmethod
    def integrated_comment(values: Mapping[str, object], backtest_comment: str | None = None) -> str:
        """Explain technical, fundamental, and backtest facts without inventing missing data."""
        technical = AnalysisCommentary._technical_comment(values)
        fundamental = AnalysisCommentary._fundamental_comment(values)
        backtest = backtest_comment or "バックテスト結果は未算出です。"
        assessment = AnalysisCommentary._overall_assessment(values)
        return (
            f"【テクニカル】\n{technical}\n\n"
            f"【ファンダメンタル】\n{fundamental}\n\n"
            f"【バックテスト】\n{backtest}\n\n"
            f"【総合所見】\n{assessment}"
        )

    @staticmethod
    def _number(values: Mapping[str, object], key: str) -> float | None:
        value = values.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _technical_comment(cls, values: Mapping[str, object]) -> str:
        rsi_values = [(label, cls._number(values, key)) for label, key in (
            ("日足", "daily.rsi_14"), ("週足", "weekly.rsi_14"), ("月足", "monthly.rsi_14"),
        )]
        available_rsi = [(label, value) for label, value in rsi_values if value is not None]
        parts = []
        if available_rsi:
            parts.append("RSIは" + "、".join(f"{label}{value:.1f}" for label, value in available_rsi) + "です。")
        close = cls._number(values, "daily.close")
        sma25 = cls._number(values, "daily.sma_25")
        sma75 = cls._number(values, "daily.sma_75")
        if close is not None and sma25 is not None:
            parts.append(f"終値は25日移動平均を{'上回って' if close > sma25 else '下回って'}います。")
        if close is not None and sma75 is not None:
            parts.append(f"75日移動平均との位置関係は{'上側' if close > sma75 else '下側'}です。")
        macd = cls._number(values, "daily.macd")
        signal = cls._number(values, "daily.macd_signal")
        if macd is not None and signal is not None:
            parts.append(f"MACDはシグナルを{'上回って' if macd > signal else '下回って'}います。")
        return "".join(parts) or "テクニカル指標を十分に取得できていません。"

    @classmethod
    def _fundamental_comment(cls, values: Mapping[str, object]) -> str:
        metrics = {
            "PER": ("fundamental.per", "倍"), "PBR": ("fundamental.pbr", "倍"),
            "ROE": ("fundamental.roe", "%"), "ROA": ("fundamental.roa", "%"),
            "営業利益率": ("fundamental.operating_margin", "%"),
            "自己資本比率": ("fundamental.equity_ratio", "%"),
            "配当利回り": ("fundamental.dividend_yield", "%"),
        }
        available = [(label, cls._number(values, key), unit) for label, (key, unit) in metrics.items()]
        available = [(label, value, unit) for label, value, unit in available if value is not None]
        if not available:
            return "最新の財務指標を取得できていないため、ファンダメンタル評価は未実施です。"
        disclosed = values.get("fundamental.disclosed_date")
        prefix = f"開示日{disclosed}の財務データを基準に、" if disclosed else "最新の取得済み財務データを基準に、"
        text = prefix + "、".join(f"{label}{value:.1f}{unit}" for label, value, unit in available) + "です。"
        notes = []
        per = cls._number(values, "fundamental.per")
        pbr = cls._number(values, "fundamental.pbr")
        roe = cls._number(values, "fundamental.roe")
        equity_ratio = cls._number(values, "fundamental.equity_ratio")
        cash_flow = cls._number(values, "fundamental.operating_cash_flow")
        if per is not None:
            notes.append("PERは一般的な目安で割安寄り" if 0 < per <= 15 else "PERは割安水準とは断定できない")
        if pbr is not None and 0 < pbr <= 1:
            notes.append("PBRは1倍以下")
        if roe is not None:
            notes.append("ROEは10%以上" if roe >= 10 else "ROEは10%未満")
        if equity_ratio is not None:
            notes.append("自己資本比率は40%以上" if equity_ratio >= 40 else "自己資本比率は40%未満")
        if cash_flow is not None:
            notes.append("営業キャッシュフローはプラス" if cash_flow > 0 else "営業キャッシュフローはプラスではない")
        if notes:
            text += "確認点として、" + "、".join(notes) + "です。業種差や一時要因を含むため、単独指標での判断はできません。"
        return text

    @classmethod
    def _overall_assessment(cls, values: Mapping[str, object]) -> str:
        score = cls._number(values, "expectation_score")
        roe = cls._number(values, "fundamental.roe")
        equity_ratio = cls._number(values, "fundamental.equity_ratio")
        positives = []
        cautions = []
        if roe is not None:
            (positives if roe >= 10 else cautions).append("収益性")
        if equity_ratio is not None:
            (positives if equity_ratio >= 40 else cautions).append("財務健全性")
        if score is not None:
            (positives if score >= 60 else cautions).append("過去シグナルの期待値")
        if not positives and not cautions:
            return "評価材料が不足しています。追加の決算情報と価格推移を確認してください。"
        positive_text = "、".join(positives) + "は相対的な確認材料です。" if positives else ""
        caution_text = "、".join(cautions) + "は注意が必要です。" if cautions else ""
        return positive_text + caution_text + "テクニカルと財務の両面を確認し、売買判断ではなく候補選定情報として利用してください。"
