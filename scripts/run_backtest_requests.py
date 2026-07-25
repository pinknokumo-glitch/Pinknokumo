"""Process pending user-requested backtests using saved expectation conditions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.batch_backtest import BatchBacktester  # noqa: E402
from modules.cloud_batch import preference_signature  # noqa: E402
from modules.cloud_preferences import (  # noqa: E402
    CloudPreferenceClient,
    apply_expectation_preference,
)
from modules.database import Database  # noqa: E402
from modules.repository import StockRepository  # noqa: E402
from modules.screening_options import ScreeningOptions  # noqa: E402


def load_yaml(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def request(url: str, key: str, method: str, path: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    req = Request(
        url.rstrip("/") + path,
        data=data,
        method=method,
        headers=headers,
    )
    with urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else []


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Requested backtests: skipped (Supabase unavailable)")
        return 0
    screening = load_yaml("screening.yaml")
    options = ScreeningOptions(load_yaml("screening_options.yaml"), screening)
    preferences = {
        item.user_id: item
        for item in CloudPreferenceClient(url, key).fetch_all(options)
    }
    pending = request(
        url, key, "GET",
        "/rest/v1/backtest_requests?status=eq.pending&order=created_at.asc&limit=10",
    )
    settings = load_yaml("settings.yaml")
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    processed = 0
    for item in pending:
        request_id = item["id"]
        user_id = str(item["user_id"])
        code = str(item["code"]).strip().upper()
        path = f"/rest/v1/backtest_requests?id=eq.{quote(str(request_id))}"
        try:
            preference = preferences[user_id]
            resolved, expectation_profile = apply_expectation_preference(
                preference, options, screening
            )
            rule = resolved["profiles"][expectation_profile]
            profile = f"requested_{preference_signature(preference)}"
            request(url, key, "PATCH", path, {"status": "processing"})
            BatchBacktester(
                database,
                load_yaml("indicators.yaml"),
                load_yaml("backtest.yaml"),
                load_yaml("scoring.yaml"),
            ).run(profile, rule, preference.holding_days, codes=[code])
            with database.connect() as connection:
                result = StockRepository(connection).latest_backtest_result(code, profile)
                prices = pd.read_sql_query(
                    """SELECT trade_date, close FROM price_daily
                       WHERE code=? ORDER BY trade_date DESC LIMIT 180""",
                    connection, params=[code],
                ).iloc[::-1]
            if result is None:
                raise RuntimeError("バックテスト結果を作成できませんでした")
            payload = {
                "status": "complete",
                "result_json": {
                    **result,
                    "prices": [
                        {"date": str(row.trade_date), "close": float(row.close)}
                        for row in prices.itertuples()
                    ],
                    "condition_summary": rule,
                },
                "error_message": None,
            }
            request(url, key, "PATCH", path, payload)
            processed += 1
        except Exception as error:
            request(url, key, "PATCH", path, {
                "status": "failed",
                "error_message": f"{type(error).__name__}: {error}",
            })
    print(json.dumps({"requested_backtests": {"processed_count": processed}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
