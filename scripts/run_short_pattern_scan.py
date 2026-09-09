"""Build and publish the independent evening short-horizon pattern dataset."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.cloud_short_patterns import CloudShortPatternPublisher  # noqa: E402
from modules.database import Database  # noqa: E402
from modules.short_horizon_patterns import ShortHorizonPatternScanner  # noqa: E402


def load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def main() -> int:
    settings = load_yaml("config/settings.yaml")
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    source_run_id = os.getenv("EVENING_DATASET_RUN_ID", "").strip()
    if not source_run_id.isdigit():
        raise ValueError("EVENING_DATASET_RUN_ID is required")
    with database.connect() as connection:
        codes = [str(row[0]) for row in connection.execute("SELECT code FROM evening_analysis_codes ORDER BY code")]
        names = {str(row[0]): str(row[1] or "") for row in connection.execute(
            "SELECT code, company_name FROM master_stock WHERE code IN (SELECT code FROM evening_analysis_codes)"
        )}
        frames = {
            code: pd.read_sql_query(
                "SELECT trade_date, open, high, low, close, volume FROM price_daily WHERE code=? ORDER BY trade_date",
                connection, params=[code],
            ) for code in codes
        }
    results = ShortHorizonPatternScanner(load_yaml("config/indicators.yaml"), settings).scan(frames, names)
    signal_date = max((str(row["signal_date"]) for row in results), default="")
    if not signal_date:
        with database.connect() as connection:
            row = connection.execute("SELECT MAX(trade_date) FROM price_daily WHERE code IN (SELECT code FROM evening_analysis_codes)").fetchone()
        signal_date = str(row[0] or "")
    if not signal_date:
        raise RuntimeError("Evening snapshot has no usable price date")
    run_id = f"{source_run_id}-short-patterns"
    database.replace_short_patterns(run_id, signal_date, source_run_id, results)
    url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    published = CloudShortPatternPublisher(url, key).publish(run_id, signal_date, source_run_id, results) if url and key else 0
    print(json.dumps({"short_patterns": {"run_id": run_id, "signal_date": signal_date,
          "candidate_count": len(results), "published_count": published}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
