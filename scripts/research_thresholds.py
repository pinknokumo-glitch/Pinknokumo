"""Backtest configured RSI threshold candidates and write a JSON comparison report."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.backtest import Backtester  # noqa: E402
from modules.database import Database  # noqa: E402
from modules.expectation import ExpectationScorer  # noqa: E402
from modules.screener import Screener  # noqa: E402
from modules.threshold_research import oversold_rule, rank_threshold_results  # noqa: E402


def load_yaml(path: str) -> dict:
    with (ROOT / path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def main() -> int:
    indicators = load_yaml("config/indicators.yaml")
    backtest_config = load_yaml("config/backtest.yaml")
    scoring = load_yaml("config/scoring.yaml")
    settings = load_yaml("config/settings.yaml")
    research = load_yaml("config/threshold_research.yaml")["threshold_research"]
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    backtester = Backtester(indicators, backtest_config)
    scorer = ExpectationScorer(scoring)

    with database.connect() as connection:
        codes = [row[0] for row in connection.execute(
            """SELECT DISTINCT code FROM price_daily
               WHERE code NOT IN (SELECT DISTINCT market_code FROM market_regime) ORDER BY code"""
        )]
        frames = {}
        for code in codes:
            frames[code] = {
                timeframe: pd.read_sql_query(
                    f"SELECT trade_date, open, high, low, close, volume, dividends FROM {table} "
                    "WHERE code=? ORDER BY trade_date",
                    connection, params=[code], parse_dates=["trade_date"],
                )
                for timeframe, table in (
                    ("daily", "price_daily"), ("weekly", "price_weekly"), ("monthly", "price_monthly")
                )
            }

        raw_results = []
        for thresholds in research["candidates"]:
            rule = oversold_rule(thresholds)
            trades = []
            for code in codes:
                daily = frames[code]["daily"]
                if not daily.empty:
                    trades.extend(backtester.run(daily, rule, int(research["holding_days"]), frames[code]))
            summary = backtester.summarize(trades)
            screening_config = {"active_profile": "candidate", "profiles": {"candidate": rule}}
            current_hits = Screener(connection, indicators, screening_config).run("candidate")
            raw_results.append({
                "thresholds": dict(thresholds), "current_hit_count": len(current_hits),
                "current_hit_codes": [str(hit["code"]) for hit in current_hits],
                "summary": summary, "expectation": scorer.score(summary),
            })

    target = research["target_current_hits"]
    ranked = rank_threshold_results(
        raw_results, int(research["minimum_trades"]), int(target["min"]), int(target["max"]),
    )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "holding_days": int(research["holding_days"]), "security_count": len(codes),
        "selection_note": "本番設定は変更していません。過去成績は将来を保証しません。",
        "recommended_candidate": ranked[0] if ranked and ranked[0]["eligible"] else None,
        "results": ranked,
    }
    output = ROOT / "reports" / "threshold_research.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Threshold research written: {output}")
    for index, item in enumerate(ranked, start=1):
        summary = item["summary"]
        print(
            f"{index}. {item['thresholds']} hits={item['current_hit_count']} trades={summary['trade_count']} "
            f"avg={summary['average_return_percent']} win={summary['win_rate_percent']} "
            f"dd={summary['max_drawdown_percent']} score={item['expectation']['score']} eligible={item['eligible']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
