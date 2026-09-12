"""Run all-day precision research for complete bottom/top conditions."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.complete_condition_precision import validate_complete_conditions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        codes = [str(row[0]) for row in connection.execute("SELECT code FROM evening_analysis_codes ORDER BY code")]
        frames = {code: pd.read_sql_query("SELECT trade_date,open,high,low,close,adjusted_close,volume FROM price_daily WHERE code=? ORDER BY trade_date", connection, params=[code]) for code in codes}
    config = yaml.safe_load((ROOT / "config/indicators.yaml").read_text(encoding="utf-8"))
    result = validate_complete_conditions(frames, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"universe_stock_count": result["universe_stock_count"],
                      "usable_stock_count": result["usable_stock_count"],
                      "summary_rows": len(result["summary"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
