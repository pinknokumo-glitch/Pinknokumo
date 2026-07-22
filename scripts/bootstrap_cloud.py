"""Initialize the cloud database and its default TOPIX Core30 universe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.data_loader import DataLoader  # noqa: E402
from modules.database import Database  # noqa: E402


def main() -> None:
    with (ROOT / "config" / "settings.yaml").open(encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()

    with database.connect() as connection:
        master_count = int(connection.execute("SELECT COUNT(*) FROM master_stock").fetchone()[0])
    if master_count == 0:
        master_count, _ = DataLoader(database, settings).load_jquants()

    added = database.import_watchlist_by_scale(["TOPIX Core30"], "TOPIX Core30")
    with database.connect() as connection:
        watchlist_count = int(connection.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0])
    print(json.dumps({
        "master_count": master_count,
        "watchlist_added": added,
        "watchlist_count": watchlist_count,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

