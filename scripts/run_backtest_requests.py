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
    apply_preference,
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


def optional_target_percent(item: dict, field: str) -> float | None:
    value = item.get(field)
    if value is None or value == "":
        return None
    target = float(value)
    if not 0 < target <= 100:
        raise ValueError(f"{field} must be greater than 0 and at most 100")
    return target


def main(request_id: str | None = None, dataset_run_id: str | None = None) -> int:
    on_demand = request_id is not None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Requested backtests: skipped (Supabase unavailable)")
        return 0
    screening = load_yaml("screening.yaml")
    options = ScreeningOptions(load_yaml("screening_options.yaml"), screening)
    if request_id is not None and (not request_id.isdigit() or not (dataset_run_id or "").isdigit()):
        raise ValueError("Invalid analysis request or dataset id")
    preferences = {} if request_id else {
        item.user_id: item
        for item in CloudPreferenceClient(url, key).fetch_all(options)
    }
    pending = request(
        url, key, "GET",
        (f"/rest/v1/backtest_requests?id=eq.{request_id}&status=eq.pending&limit=1"
         if request_id else
         "/rest/v1/backtest_requests?status=eq.pending&input_snapshot=is.null&order=created_at.asc&limit=10"),
    )
    settings = load_yaml("settings.yaml")
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    processed = 0
    failed = 0
    for item in pending:
        request_id = item["id"]
        user_id = str(item["user_id"])
        code = str(item["code"]).strip().upper()
        path = f"/rest/v1/backtest_requests?id=eq.{quote(str(request_id))}"
        try:
            up_target_percent = optional_target_percent(item, "up_target_percent")
            down_target_percent = optional_target_percent(item, "down_target_percent")
            if on_demand:
                if item.get("dataset_run_id") != dataset_run_id:
                    raise ValueError("Evening dataset does not match request")
                preference = CloudPreferenceClient.validate(item["input_snapshot"], options)
                with database.connect() as connection:
                    if not connection.execute(
                        "SELECT 1 FROM evening_analysis_codes WHERE code=?", (code,)
                    ).fetchone():
                        raise ValueError("銘柄が夕方取得データにありません")
            else:
                preference = preferences[user_id]
            # Claim atomically so a workflow retry cannot compute the same request twice.
            claimed = request(url, key, "PATCH", path + "&status=eq.pending", {"status": "processing"})
            if not claimed:
                continue
            entry_config, entry_profile = apply_preference(
                preference, options, screening
            )
            exit_config, expectation_profile = apply_expectation_preference(
                preference, options, screening
            )
            entry_rule = entry_config["profiles"][entry_profile]
            exit_rule = exit_config["profiles"][expectation_profile]
            # Keep every request isolated so a rapid second request for the same
            # code cannot replace the snapshot read by the first one.
            profile = f"requested_{request_id}_{preference_signature(preference)}"
            BatchBacktester(
                database,
                load_yaml("indicators.yaml"),
                load_yaml("backtest.yaml"),
                load_yaml("scoring.yaml"),
            ).run(
                profile,
                entry_rule,
                preference.holding_days,
                codes=[code],
                exit_rule=exit_rule,
                position_side=preference.trade_direction,
                evaluation_mode=preference.expectation_evaluation_mode,
                target_return_percent=preference.target_return_percent,
                up_target_percent=up_target_percent,
                down_target_percent=down_target_percent,
            )
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
                    "entry_condition_summary": entry_rule,
                    "exit_condition_summary": exit_rule,
                    "trade_direction": preference.trade_direction,
                    "expectation_evaluation_mode":
                        preference.expectation_evaluation_mode,
                    "target_return_percent": preference.target_return_percent,
                    "request_id": request_id,
                    "dataset_run_id": item.get("dataset_run_id"),
                    "reference_price": (
                        float(prices.iloc[-1]["close"]) if not prices.empty else None
                    ),
                },
                "error_message": None,
            }
            request(url, key, "PATCH", path, payload)
            processed += 1
        except Exception as error:
            failed += 1
            request(url, key, "PATCH", path, {
                "status": "failed",
                "error_message": f"{type(error).__name__}: {error}",
            })
    print(json.dumps({"requested_backtests": {"processed_count": processed}}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(os.getenv("ANALYSIS_REQUEST_ID"), os.getenv("EVENING_DATASET_RUN_ID")))

