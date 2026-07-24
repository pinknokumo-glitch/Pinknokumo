"""Refresh all Prime/Standard/Growth stocks and save the morning candidate pool."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.data_loader import DataLoader  # noqa: E402
from modules.database import Database  # noqa: E402
from modules.evening_universe import EveningUniverseJob  # noqa: E402


def load_yaml(relative_path: str) -> dict:
    with (ROOT / relative_path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def main() -> int:
    settings = load_yaml("config/settings.yaml")
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    # Refresh listings nightly so new listings and delistings change the universe.
    DataLoader(database, settings).load_jquants()
    result = EveningUniverseJob(
        database, settings, load_yaml("config/indicators.yaml")
    ).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["usable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
