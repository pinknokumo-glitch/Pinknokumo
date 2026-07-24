"""Generate app-visible screening results for every saved Supabase preference."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.cloud_batch import run_cloud_batch  # noqa: E402
from modules.cloud_preferences import CloudPreferenceClient  # noqa: E402
from modules.database import Database  # noqa: E402
from modules.screening_options import ScreeningOptions  # noqa: E402


def load_yaml(path: str) -> dict:
    with (ROOT / path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Cloud user screening: skipped (Supabase server settings unavailable)")
        return 0
    settings = load_yaml("config/settings.yaml")
    screening = load_yaml("config/screening.yaml")
    options = ScreeningOptions(load_yaml("config/screening_options.yaml"), screening)
    preferences = CloudPreferenceClient(url, key).fetch_all(options)
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    result = run_cloud_batch(
        database=database,
        preferences=preferences,
        options=options,
        screening_config=screening,
        indicator_config=load_yaml("config/indicators.yaml"),
        backtest_config=load_yaml("config/backtest.yaml"),
        scoring_config=load_yaml("config/scoring.yaml"),
        supabase_url=url,
        service_role_key=key,
        # Use the full Prime/Standard/Growth universe refreshed by the evening job.
        # The RSI-only morning prefilter would incorrectly exclude value/dividend users.
        candidate_codes=None,
    )
    database.save_job_run("cloud_user_screening", "success", result)
    print(json.dumps({"cloud_user_screening": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
