"""Publish the local stock master as a read-only Supabase search catalog."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.cloud_stock_catalog import CloudStockCatalogPublisher  # noqa: E402
from modules.database import Database  # noqa: E402


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Stock search catalog: skipped (Supabase unavailable)")
        return 0
    with (ROOT / "config" / "settings.yaml").open(encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    with database.connect() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='evening_analysis_codes'").fetchone():
            print("Stock search catalog: awaiting evening snapshot")
            return 0
        rows = connection.execute(
            "SELECT m.code, m.company_name FROM master_stock m "
            "JOIN evening_analysis_codes e ON e.code=m.code ORDER BY m.code"
        ).fetchall()
    run_id = os.getenv("EVENING_DATASET_RUN_ID", "").strip()
    if not run_id:
        print("Stock search catalog: preserved (only evening publishes snapshots)")
        return 0
    count = CloudStockCatalogPublisher(url, key).publish_snapshot(rows, run_id)
    print(json.dumps({"stock_search_catalog": {"published_count": count}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

