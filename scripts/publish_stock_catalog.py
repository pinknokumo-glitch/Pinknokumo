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
        rows = connection.execute(
            "SELECT code, company_name FROM master_stock ORDER BY code"
        ).fetchall()
    count = CloudStockCatalogPublisher(url, key).publish(rows)
    print(json.dumps({"stock_search_catalog": {"published_count": count}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

