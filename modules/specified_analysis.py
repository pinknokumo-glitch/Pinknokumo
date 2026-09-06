"""Independent close-based historical windows; never reads user screening rules."""
import math

import pandas as pd

from modules.expectation import ExpectationScorer


def analyze(prices, days, up, down, scoring):
    if type(days) is not int or not 1 <= days <= 1000:
        raise ValueError("検証期間は1～1000営業日です")
    for target in (up, down):
        if target is not None and (not math.isfinite(float(target)) or not 0 < target <= 100):
            raise ValueError("目標率は0より大きく100以下です")
    frame = prices.sort_values("trade_date").reset_index(drop=True)
    samples, up_days, down_days = [], [], []
    for i in range(len(frame) - days):
        window = frame.iloc[i:i + days + 1]
        numbers = window[["close", "high", "low"]].apply(pd.to_numeric, errors="coerce")
        if not numbers.map(lambda x: pd.notna(x) and math.isfinite(x) and x > 0).all().all():
            continue
        base = float(numbers.iloc[0].close)
        future = numbers.iloc[1:]
        samples.append(((float(future.iloc[-1].close) / base - 1) * 100,
                        min(0.0, (float(future.low.min()) / base - 1) * 100)))
        for target, field, sign, bucket in ((up, "high", 1, up_days), (down, "low", -1, down_days)):
            hit = None
            if target is not None:
                for day, value in enumerate(future[field], 1):
                    if (float(value) / base - 1) * 100 * sign >= target - 1e-9:
                        hit = day
                        break
            bucket.append(hit)
    n = len(samples)
    summary = {"trade_count": n,
               "average_return_percent": sum(x[0] for x in samples) / n if n else None,
               "win_rate_percent": sum(x[0] > 0 for x in samples) * 100 / n if n else None,
               "max_drawdown_percent": min(x[1] for x in samples) if n else None}
    targets = {"up_target_percent": up, "down_target_percent": down}
    for name, target, bucket in (("up", up, up_days), ("down", down, down_days)):
        hits = [d for d in bucket if d is not None]
        targets[f"{name}_target_probability_percent"] = len(hits) * 100 / n if n and target is not None else None
        targets[f"median_sessions_to_{name}_target"] = float(pd.Series(hits).median()) if hits else None
    latest = frame.iloc[-1] if not frame.empty else None
    reference = float(latest.close) if latest is not None and pd.notna(latest.close) and math.isfinite(float(latest.close)) and latest.close > 0 else None
    method = (f"過去の各営業日終値を基準に、翌営業日から{days}営業日内の高値・安値で上下の到達率を集計。"
              f"平均リターン・勝率は{days}営業日後の終値、最大含み損は期間内安値で算出します。"
              "上下到達は独立集計のため、両方に到達する場合があります。期間が重複する事例を含み、独立した取引数ではありません。"
              "手数料・税金・配当は含みません。過去の統計であり将来の確率を保証しません。")
    return {"holding_days": days, "summary": summary,
            "expectation": ExpectationScorer(scoring).score(summary) if n else {"score": None},
            "specified_targets": targets, "reference_price": reference,
            "reference_date": str(latest.trade_date) if latest is not None else None,
            "up_target_price": reference * (1 + up / 100) if reference and up is not None else None,
            "down_target_price": reference * (1 - down / 100) if reference and down is not None else None,
            "comment": ("検証期間を満たす有効な価格履歴が不足しています。" if not n else "") + method,
            "prices": [{"date": str(row.trade_date), "close": float(row.close)} for row in frame.tail(180).itertuples()
                       if pd.notna(row.close) and math.isfinite(float(row.close))]}
