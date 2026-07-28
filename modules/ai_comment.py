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
        lines: list[str] = []
        timeframes = (
            ("daily", "日足", "日"),
            ("weekly", "週足", "週"),
            ("monthly", "月足", "か月"),
        )

        rsi_items = []
        for prefix, label, _ in timeframes:
            value = cls._number(values, f"{prefix}.rsi_14")
            if value is None:
                continue
            previous = cls._number(values, f"{prefix}.rsi_14_previous")
            change = cls._change_label(value, previous)
            rsi_items.append(
                f"{label}{value:.1f}（{cls._rsi_label(value)}"
                + (f"、前回比{change}" if change else "")
                + "）"
            )
        if rsi_items:
            lines.append("・RSI: " + " / ".join(rsi_items))

        for prefix, label, unit in timeframes:
            close = cls._number(values, f"{prefix}.close")
            averages = []
            for period in (5, 25, 75, 200):
                average = cls._number(values, f"{prefix}.sma_{period}")
                if close is None or average is None:
                    continue
                distance = cls._number(
                    values, f"{prefix}.price_vs_sma_{period}_percent"
                )
                if distance is None and average:
                    distance = (close / average - 1) * 100
                averages.append(
                    f"{period}{unit}線{average:,.1f}"
                    f"（乖離{distance:+.1f}%、{'上側' if close >= average else '下側'}）"
                )
            if averages:
                lines.append(
                    f"・{label}トレンド: 終値{close:,.1f} / " + " / ".join(averages)
                )

        for prefix, label, _ in timeframes:
            macd = cls._number(values, f"{prefix}.macd")
            signal = cls._number(values, f"{prefix}.macd_signal")
            histogram = cls._number(values, f"{prefix}.macd_histogram")
            if macd is None or signal is None:
                continue
            previous_histogram = cls._number(
                values, f"{prefix}.macd_histogram_previous"
            )
            momentum = "上向き" if macd >= signal else "下向き"
            histogram_change = cls._change_label(histogram, previous_histogram)
            histogram_text = f"{histogram:.2f}" if histogram is not None else "-"
            lines.append(
                f"・{label}MACD: {macd:.2f}、シグナル{signal:.2f}"
                f"（{momentum}、ヒストグラム"
                f"{histogram_text}"
                + (f"・前回比{histogram_change}" if histogram_change else "")
                + "）"
            )

        for prefix, label, _ in timeframes:
            k = cls._number(values, f"{prefix}.stoch_k")
            d = cls._number(values, f"{prefix}.stoch_d")
            if k is None or d is None:
                continue
            zone = (
                "売られ過ぎ圏"
                if max(k, d) <= 20
                else "買われ過ぎ圏"
                if min(k, d) >= 80
                else "中立圏"
            )
            cross = "%Kが%Dを上回る" if k >= d else "%Kが%Dを下回る"
            lines.append(
                f"・{label}ストキャスティクス: %K {k:.1f} / %D {d:.1f}"
                f"（{zone}、{cross}）"
            )

        for prefix, label, _ in timeframes:
            percent_b = cls._number(values, f"{prefix}.bb_percent_b")
            adx = cls._number(values, f"{prefix}.adx_14")
            atr = cls._number(values, f"{prefix}.atr_14_percent")
            components = []
            if percent_b is not None:
                components.append(
                    f"ボリンジャー%B {percent_b:.1f}（{cls._bollinger_label(percent_b)}）"
                )
            if adx is not None:
                components.append(
                    f"ADX {adx:.1f}（{cls._adx_label(adx)}。方向は他指標で確認）"
                )
            if atr is not None:
                components.append(
                    f"ATR比率 {atr:.1f}%（{cls._atr_label(atr)}）"
                )
            if components:
                lines.append(f"・{label}変動・トレンド強度: " + " / ".join(components))

        momentum_items = []
        for sessions, label in ((5, "5日"), (20, "20日"), (60, "60日")):
            value = cls._number(values, f"daily.return_{sessions}_percent")
            if value is not None:
                momentum_items.append(f"{label}{value:+.1f}%")
        volume = cls._number(values, "daily.volume_ratio_20")
        if momentum_items or volume is not None:
            suffix = ""
            if volume is not None:
                suffix = (
                    f" / 出来高は20日平均比{volume:.0f}%"
                    f"（{cls._volume_label(volume)}）"
                )
            lines.append("・短中期モメンタム: " + " / ".join(momentum_items) + suffix)

        return "\n".join(lines) or "テクニカル指標を十分に取得できていません。"

    @staticmethod
    def _change_label(value: float | None, previous: float | None) -> str | None:
        if value is None or previous is None:
            return None
        change = value - previous
        if abs(change) < 0.1:
            return "横ばい"
        return f"{change:+.1f}（{'上昇' if change > 0 else '低下'}）"

    @staticmethod
    def _rsi_label(value: float) -> str:
        if value <= 30:
            return "売られ過ぎ圏"
        if value >= 70:
            return "買われ過ぎ圏"
        return "中立圏"

    @staticmethod
    def _bollinger_label(value: float) -> str:
        if value < 0:
            return "下限バンド割れ"
        if value <= 20:
            return "下限バンド付近"
        if value < 80:
            return "バンド中央域"
        if value <= 100:
            return "上限バンド付近"
        return "上限バンド超え"

    @staticmethod
    def _adx_label(value: float) -> str:
        if value < 20:
            return "明確なトレンドは弱い"
        if value < 25:
            return "トレンド形成の兆候"
        return "トレンドが強い"

    @staticmethod
    def _atr_label(value: float) -> str:
        if value < 1.5:
            return "値動きは比較的小さい"
        if value < 4:
            return "値動きは中程度"
        return "値動きが大きくリスク管理に注意"

    @staticmethod
    def _volume_label(value: float) -> str:
        if value >= 150:
            return "商いが活発"
        if value < 70:
            return "商いが低調"
        return "通常水準"

    @classmethod
    def _fundamental_comment(cls, values: Mapping[str, object]) -> str:
        if not any(
            cls._number(values, f"fundamental.{metric}") is not None
            for metric in (
                "per", "pbr", "roe", "roa", "operating_margin",
                "equity_ratio", "dividend_yield",
            )
        ):
            return "最新の財務指標を取得できていないため、ファンダメンタル評価は未実施です。"
        disclosed = values.get("fundamental.disclosed_date")
        sector = str(values.get("fundamental.sector_name") or "業種未分類")
        sample_count = int(cls._number(values, "industry.sample_count") or 0)
        lines = [
            (
                f"開示日{disclosed}、業種「{sector}」の参考平均"
                f"（比較可能{sample_count}銘柄）との比較です。"
                if disclosed
                else f"業種「{sector}」の参考平均（比較可能{sample_count}銘柄）との比較です。"
            )
        ]
        cls._append_industry_line(
            lines, values, "PER", "per", "倍", lower_is_better=True,
            low_label="業界比で割安", high_label="業界比で割高",
        )
        cls._append_industry_line(
            lines, values, "PBR", "pbr", "倍", lower_is_better=True,
            low_label="業界比で割安", high_label="業界比で割高",
        )
        cls._append_industry_line(
            lines, values, "ROE", "roe", "%", lower_is_better=False,
            low_label="収益性は業界平均を下回る", high_label="収益性は業界平均を上回る",
        )
        cls._append_industry_line(
            lines, values, "ROA", "roa", "%", lower_is_better=False,
            low_label="資産効率は業界平均を下回る", high_label="資産効率は業界平均を上回る",
        )
        cls._append_industry_line(
            lines, values, "営業利益率", "operating_margin", "%",
            lower_is_better=False,
            low_label="本業の収益性は業界平均を下回る",
            high_label="本業の収益性は業界平均を上回る",
        )
        cls._append_industry_line(
            lines, values, "自己資本比率", "equity_ratio", "%",
            lower_is_better=False,
            low_label="財務余力は業界平均を下回る",
            high_label="財務余力は業界平均を上回る",
        )
        cash_flow = cls._number(values, "fundamental.operating_cash_flow")
        if cash_flow is not None:
            lines.append(
                f"・営業キャッシュフロー {cash_flow:,.0f}："
                + ("プラスで資金創出は良好" if cash_flow > 0 else "マイナスで資金繰りに注意")
            )
        cls._append_industry_line(
            lines, values, "配当利回り", "dividend_yield", "%",
            lower_is_better=False,
            low_label="配当水準は業界平均より低い",
            high_label="配当水準は業界平均より高い",
        )
        for label, metric in (
            ("売上成長率", "sales_growth"),
            ("営業利益成長率", "operating_profit_growth"),
            ("純利益成長率", "profit_growth"),
            ("EPS成長率", "eps_growth"),
        ):
            cls._append_industry_line(
                lines, values, label, metric, "%", lower_is_better=False,
                low_label="成長性は業界平均を下回る",
                high_label="成長性は業界平均を上回る",
            )
        lines.append("業界平均は取得対象銘柄から算出した参考値で、決算期や一時要因の違いを含みます。")
        return "\n".join(lines)

    @classmethod
    def _append_industry_line(
        cls,
        lines: list[str],
        values: Mapping[str, object],
        label: str,
        metric: str,
        unit: str,
        *,
        lower_is_better: bool,
        low_label: str,
        high_label: str,
    ) -> None:
        value = cls._number(values, f"fundamental.{metric}")
        if value is None:
            return
        average = cls._number(values, f"industry.{metric}")
        if average is None:
            judgment = cls._standalone_judgment(metric, value)
            lines.append(f"・{label} {value:.1f}{unit}：{judgment}")
            return
        ratio = value / average if average not in (0, None) else 1.0
        if 0.85 <= ratio <= 1.15:
            judgment = "業界平均と同程度"
        else:
            value_is_low = ratio < 0.85
            favorable = value_is_low if lower_is_better else not value_is_low
            judgment = low_label if value_is_low else high_label
            if not favorable and metric in {"roe", "roa", "operating_margin", "equity_ratio"}:
                judgment += "ため注意"
        lines.append(
            f"・{label} {value:.1f}{unit}（業界平均{average:.1f}{unit}）：{judgment}"
        )

    @staticmethod
    def _standalone_judgment(metric: str, value: float) -> str:
        if metric == "per":
            return "15倍以下で割安寄り" if 0 < value <= 15 else "業界比較データ不足"
        if metric == "pbr":
            return "1倍以下で割安寄り" if 0 < value <= 1 else "業界比較データ不足"
        if metric == "roe":
            return "10%以上で良好" if value >= 10 else "10%未満で注意"
        if metric == "equity_ratio":
            return "40%以上で比較的良好" if value >= 40 else "40%未満で注意"
        if metric == "dividend_yield":
            return "3.5%以上で高配当寄り" if value >= 3.5 else "業界比較データ不足"
        if metric.endswith("growth"):
            return "増加" if value > 0 else "減少しており注意"
        return "業界比較データ不足"

    @classmethod
    def _overall_assessment(cls, values: Mapping[str, object]) -> str:
        technical = cls._technical_assessment(values)
        valuation = cls._valuation_assessment(values)
        profitability = cls._profitability_assessment(values)
        finances = cls._financial_assessment(values)
        growth = cls._growth_assessment(values)
        dividend = cls._dividend_assessment(values)
        if all(
            item == "判断材料不足"
            for item in (technical, valuation, profitability, finances, growth, dividend)
        ):
            return "評価材料が不足しています。追加の決算情報と価格推移を確認してください。"
        contrast = ""
        if technical in {"売られ過ぎ寄り", "上昇基調"} and growth == "成長性に注意":
            contrast = (
                "テクニカル面には反発・上昇の余地が見られますが、"
                "ファンダメンタル面では成長性が弱く、将来性は慎重な評価が必要です。"
            )
        elif growth == "成長性に注意":
            contrast = (
                "ファンダメンタル面では成長性が弱く、"
                "将来性は慎重な評価が必要です。"
            )
        elif technical == "売られ過ぎ寄り" and valuation == "割安寄り":
            contrast = "テクニカルと相対バリュエーションの両面で割安寄りです。"
        return (
            f"{contrast}"
            f"テクニカル: {technical}。"
            f"バリュエーション: {valuation}。"
            f"収益性: {profitability}。財務健全性: {finances}。"
            f"成長性: {growth}。配当: {dividend}。"
            "これは候補選定の参考情報であり、将来の業績や株価を保証するものではありません。"
        )

    @classmethod
    def _technical_assessment(cls, values: Mapping[str, object]) -> str:
        rsi = cls._number(values, "daily.rsi_14")
        close = cls._number(values, "daily.close")
        sma25 = cls._number(values, "daily.sma_25")
        sma75 = cls._number(values, "daily.sma_75")
        if rsi is not None and rsi <= 35:
            return "売られ過ぎ寄り"
        if rsi is not None and rsi >= 70:
            return "過熱気味"
        if close is not None and sma25 is not None and sma75 is not None:
            return "上昇基調" if close > sma25 and close > sma75 else "弱含み"
        return "判断材料不足"

    @classmethod
    def _valuation_assessment(cls, values: Mapping[str, object]) -> str:
        comparisons = []
        for metric in ("per", "pbr"):
            value = cls._number(values, f"fundamental.{metric}")
            average = cls._number(values, f"industry.{metric}")
            if value is not None and average not in (None, 0):
                comparisons.append(value / average)
        if not comparisons:
            return "判断材料不足"
        average_ratio = sum(comparisons) / len(comparisons)
        return "割安寄り" if average_ratio < 0.85 else "割高寄り" if average_ratio > 1.15 else "業界並み"

    @classmethod
    def _profitability_assessment(cls, values: Mapping[str, object]) -> str:
        roe = cls._number(values, "fundamental.roe")
        margin = cls._number(values, "fundamental.operating_margin")
        industry_roe = cls._number(values, "industry.roe")
        positives = int(roe is not None and roe >= 10)
        positives += int(
            roe is not None and industry_roe is not None and roe >= industry_roe
        )
        positives += int(margin is not None and margin > 0)
        return "良好" if positives >= 2 else "注意" if roe is not None or margin is not None else "判断材料不足"

    @classmethod
    def _financial_assessment(cls, values: Mapping[str, object]) -> str:
        equity = cls._number(values, "fundamental.equity_ratio")
        cash_flow = cls._number(values, "fundamental.operating_cash_flow")
        if equity is None and cash_flow is None:
            return "判断材料不足"
        if (equity is None or equity >= 40) and (cash_flow is None or cash_flow > 0):
            return "良好"
        return "注意"

    @classmethod
    def _growth_assessment(cls, values: Mapping[str, object]) -> str:
        growth = [
            cls._number(values, f"fundamental.{metric}")
            for metric in (
                "sales_growth", "operating_profit_growth",
                "profit_growth", "eps_growth",
            )
        ]
        growth = [value for value in growth if value is not None]
        if not growth:
            return "判断材料不足"
        positive_count = sum(value > 0 for value in growth)
        return "良好" if positive_count >= (len(growth) + 1) // 2 else "成長性に注意"

    @classmethod
    def _dividend_assessment(cls, values: Mapping[str, object]) -> str:
        value = cls._number(values, "fundamental.dividend_yield")
        average = cls._number(values, "industry.dividend_yield")
        if value is None:
            return "判断材料不足"
        if average not in (None, 0):
            return "業界平均より高い" if value > average * 1.15 else "業界平均より低い" if value < average * 0.85 else "業界並み"
        return "高配当寄り" if value >= 3.5 else "比較材料不足"
