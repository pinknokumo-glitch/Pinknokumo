"""Refresh only prior-evening short-pattern candidates with a morning quote."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.cloud_short_patterns import CloudShortPatternPublisher  # noqa: E402
from modules.data_loader import DataLoader  # noqa: E402
from modules.daily_job import DailyUpdateJob  # noqa: E402
from modules.database import Database  # noqa: E402


def load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def confirmation(row: dict[str, object], quote: dict[str, object]) -> dict[str, object]:
    price, direction = float(quote["price"]), str(row["direction"])
    target_percent = float(row["target_percent"])
    row["morning_price"] = round(price, 4)
    row["morning_price_at"] = str(quote["observed_at"])
    row["morning_target_price"] = round(price * (1 + target_percent / 100 if direction == "long" else 1 - target_percent / 100), 4)
    barrier = row.get("resistance_price") if direction == "long" else row.get("support_price")
    if barrier is not None and ((direction == "long" and price >= float(barrier)) or (direction == "short" and price <= float(barrier))):
        row["confirmation_status"] = "節目に到達済み：追随は注意"
    elif barrier is not None and ((direction == "long" and row["morning_target_price"] > float(barrier)) or (direction == "short" and row["morning_target_price"] < float(barrier))):
        row["confirmation_status"] = "目標までに節目の突破が必要"
    else:
        row["confirmation_status"] = "朝の価格を確認済み"
    return row


def main() -> int:
    settings = load_yaml("config/settings.yaml")
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    metadata, results = database.latest_short_patterns()
    if metadata is None:
        print(json.dumps({"short_pattern_confirmation": {"skipped": "no evening snapshot"}}, ensure_ascii=False))
        return 0
    loader = DataLoader(database, settings)
    suffix = str(settings["providers"]["yfinance"]["suffix"])
    confirmed, failed = 0, []
    for row in results:
        try:
            quote = loader.load_yfinance_quote(DailyUpdateJob.ticker_for_code(str(row["code"]), suffix), str(row["code"]))
            confirmation(row, quote)
            confirmed += 1
        except Exception as error:
            row["confirmation_status"] = "朝の価格を取得できませんでした。前日終値の参考情報です"
            failed.append({"code": row["code"], "error": str(error)})
    database.replace_short_patterns(str(metadata["run_id"]), str(metadata["signal_date"]), str(metadata["source_run_id"]), results)
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if url and key:
        CloudShortPatternPublisher(url, key).publish(str(metadata["run_id"]), str(metadata["signal_date"]), str(metadata["source_run_id"]), results)
    print(json.dumps({"short_pattern_confirmation": {"confirmed_count": confirmed, "failed": failed}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
