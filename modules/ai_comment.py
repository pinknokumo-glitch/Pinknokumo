"""Generate a factual Japanese commentary from stored backtest statistics.

This module explains calculated data only; it does not predict prices or issue trade instructions.
"""
from __future__ import annotations

from collections.abc import Mapping


class AnalysisCommentary:
    def backtest_comment(
        self,
        summary: Mapping[str, object],
        expectation: Mapping[str, object],
        *,
        holding_days: int | None = None,
        position_side: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
    ) -> str:
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
        calculation = self._average_return_method(
            holding_days, position_side, evaluation_mode, target_return_percent
        )
        return (
            f"過去シグナルは{count}件で、指定保有期間の平均リターンは{average:.1f}%（{direction}）、"
            f"勝率は{win_rate:.1f}%でした。最大含み損は{drawdown:.1f}%で、{risk}。"
            f"期待値スコアは{score:.1f}/100（{grade}）です。{reliability}ため、将来の結果を保証するものではありません。"
            f"\n算出方法: {calculation}"
        )

    @staticmethod
    def _average_return_method(
        holding_days: int | None,
        position_side: str,
        evaluation_mode: str,
        target_return_percent: float,
    ) -> str:
        entry = "ソート条件に一致した日の翌営業日始値で買い" if position_side != "short" else (
            "ソート条件に一致した日の翌営業日始値で売り"
        )
        period = f"{holding_days}営業日" if holding_days else "設定保有期間"
        exits = {
            "condition_exit": (
                "期待値条件が成立した翌営業日始値で決済し、成立しなければ"
                f"{period}終了時の終値で決済"
            ),
            "period_end": f"{period}終了時の終値で決済",
            "within_period_up": (
                f"{period}内で最初に有利な終値となった日に決済し、"
                "到達しなければ期間終了時に決済"
            ),
            "target_return": (
                f"{period}内に目標{target_return_percent:.1f}%へ到達した価格で決済し、"
                "未到達なら期間終了時に決済"
            ),
        }
        exit_method = exits.get(evaluation_mode, f"{period}終了時に決済")
        formula = (
            "（売値－買値）÷買値×100"
            if position_side != "short"
            else "（売建価格－買戻価格）÷売建価格×100"
        )
        return (
            f"{entry}、{exit_method}した各取引のリターン率"
            f"［{formula}］を、利益・損失を含めて単純平均しています。"
            "条件が連続日に成立した場合も、各日を独立した過去シグナルとして数えます。"
            "複利・年率換算ではなく、手数料・税金・スリッページは含みません。"
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
            ("monthly", "月足", "か月"),
            ("weekly", "週足", "週"),
            ("daily", "日足", "日"),
        )

        rsi_items = []
        rsi_states: dict[str, str] = {}
        rsi_falling: dict[str, bool] = {}
        for prefix, label, _ in timeframes:
            value = cls._number(values, f"{prefix}.rsi_14")
            if value is None:
                continue
            previous = cls._number(values, f"{prefix}.rsi_14_previous")
            change = cls._change_label(value, previous)
            state = cls._rsi_label(value)
            rsi_states[prefix] = state
            rsi_falling[prefix] = previous is not None and value < previous - 0.1
            rsi_items.append(
                f"{label}{value:.1f}（{state}"
                + (f"、前回比{change}" if change else "")
                + "）"
            )
        if rsi_items:
            lines.append(
                "・RSI: " + " / ".join(rsi_items) + "。"
                + cls._rsi_outlook(rsi_states, rsi_falling)
            )

        trend_items = []
        trend_states: dict[str, str] = {}
        trend_specs = (
            ("daily", "短期", "日足", (5, 25)),
            ("weekly", "中期", "週足", (25,)),
            ("monthly", "長期", "月足", (25,)),
        )
        for prefix, horizon, label, periods in trend_specs:
            state, distances = cls._moving_average_state(values, prefix, periods)
            if state is None:
                continue
            trend_states[horizon] = state
            detail = "、".join(
                f"{period}{'日' if prefix == 'daily' else '週' if prefix == 'weekly' else 'か月'}線比{distance:+.1f}%"
                for period, distance in distances
            )
            trend_items.append(
                f"{horizon}（{label}）は{state}" + (f"［{detail}］" if detail else "")
            )
        if trend_items:
            lines.append(
                "・移動平均線: " + " / ".join(trend_items) + "。"
                + cls._trend_outlook(trend_states)
            )

        macd_items = []
        macd_states = []
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
            macd_states.append(momentum)
            histogram_change = cls._change_label(histogram, previous_histogram)
            histogram_text = f"{histogram:.2f}" if histogram is not None else "-"
            macd_items.append(
                f"{label}{momentum}（MACD {macd:.2f}、ヒストグラム{histogram_text}"
                + (f"・前回比{histogram_change}" if histogram_change else "")
                + "）"
            )
        if macd_items:
            overall = (
                "全時間軸で上向き"
                if macd_states and all(state == "上向き" for state in macd_states)
                else "全時間軸で下向き"
                if macd_states and all(state == "下向き" for state in macd_states)
                else "時間軸で方向が分かれています"
            )
            lines.append("・MACD: " + " / ".join(macd_items) + f"。{overall}。")

        heat_items = []
        for prefix, label, _ in timeframes:
            k = cls._number(values, f"{prefix}.stoch_k")
            d = cls._number(values, f"{prefix}.stoch_d")
            percent_b = cls._number(values, f"{prefix}.bb_percent_b")
            components = []
            if k is not None and d is not None:
                zone = (
                    "売られ過ぎ"
                    if max(k, d) <= 20
                    else "買われ過ぎ"
                    if min(k, d) >= 80
                    else "中立"
                )
                components.append(
                    f"ストキャスティクス{zone}（%K {k:.1f}/%D {d:.1f}）"
                )
            if percent_b is not None:
                components.append(
                    f"ボリンジャー{cls._bollinger_label(percent_b)}（%B {percent_b:.1f}）"
                )
            if components:
                heat_items.append(f"{label}: " + "、".join(components))
        if heat_items:
            lines.append("・過熱感・価格位置: " + " / ".join(heat_items) + "。")

        strength_items = []
        for prefix, label, _ in timeframes:
            adx = cls._number(values, f"{prefix}.adx_14")
            atr = cls._number(values, f"{prefix}.atr_14_percent")
            components = []
            if adx is not None:
                components.append(f"ADX {adx:.1f}（{cls._adx_label(adx)}）")
            if atr is not None:
                components.append(f"ATR {atr:.1f}%（{cls._atr_label(atr)}）")
            if components:
                strength_items.append(f"{label}: " + "、".join(components))

        momentum_items = []
        for sessions, label in ((5, "5日"), (20, "20日"), (60, "60日")):
            value = cls._number(values, f"daily.return_{sessions}_percent")
            if value is not None:
                momentum_items.append(f"{label}{value:+.1f}%")
        volume = cls._number(values, "daily.volume_ratio_20")
        if strength_items or momentum_items or volume is not None:
            details = list(strength_items)
            if momentum_items:
                details.append("騰落率 " + " / ".join(momentum_items))
            if volume is not None:
                details.append(
                    f"出来高20日平均比{volume:.0f}%（{cls._volume_label(volume)}）"
                )
            lines.append("・強さ・変動リスク: " + " / ".join(details) + "。")

        return "\n".join(lines) or "テクニカル指標を十分に取得できていません。"

    @classmethod
    def _moving_average_state(
        cls,
        values: Mapping[str, object],
        prefix: str,
        periods: tuple[int, ...],
    ) -> tuple[str | None, list[tuple[int, float]]]:
        close = cls._number(values, f"{prefix}.close")
        if close is None:
            return None, []
        distances = []
        for period in periods:
            average = cls._number(values, f"{prefix}.sma_{period}")
            if average in (None, 0):
                continue
            distance = cls._number(
                values, f"{prefix}.price_vs_sma_{period}_percent"
            )
            if distance is None:
                distance = (close / average - 1) * 100
            distances.append((period, distance))
        if not distances:
            return None, []
        if all(distance >= 0 for _, distance in distances):
            state = "上昇基調"
        elif all(distance < 0 for _, distance in distances):
            state = "下落基調"
        else:
            state = "方向感が混在"
        return state, distances

    @staticmethod
    def _trend_outlook(states: Mapping[str, str]) -> str:
        short = states.get("短期")
        long = states.get("長期")
        if short == "上昇基調" and long == "下落基調":
            return "長期的には下落トレンドですが、短期的には反発・上昇しています"
        if short == "下落基調" and long == "上昇基調":
            return "長期上昇トレンド内の短期調整と見られます"
        if states and all(value == "上昇基調" for value in states.values()):
            return "短期から長期まで上昇方向がそろっています"
        if states and all(value == "下落基調" for value in states.values()):
            return "短期から長期まで下落方向がそろっています"
        return "時間軸によって方向が異なるため、転換確認が必要です"

    @staticmethod
    def _rsi_outlook(
        states: Mapping[str, str],
        falling: Mapping[str, bool],
    ) -> str:
        monthly = states.get("monthly")
        daily = states.get("daily")
        weekly = states.get("weekly")
        if monthly == "売られ過ぎ圏" and daily == weekly == "中立圏":
            if falling.get("daily") or falling.get("weekly"):
                return (
                    "月足は売られ過ぎですが、週足・日足は中立圏で低下中のため、"
                    "短中期にはさらに下げる可能性も残ります"
                )
            return (
                "月足は売られ過ぎですが、週足・日足は中立圏で、"
                "短中期の反転はまだ確認できません"
            )
        if states and all(value == "売られ過ぎ圏" for value in states.values()):
            return "全時間軸で売られ過ぎですが、反発開始の確認が必要です"
        if states and all(value == "買われ過ぎ圏" for value in states.values()):
            return "全時間軸で買われ過ぎとなり、反落リスクに注意が必要です"
        return "時間軸ごとの過熱感が異なるため、短期の方向変化を確認してください"

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
