"""Export only market history from an evening snapshot; never copy user tables."""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from contextlib import closing


def export(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("Research output already exists; refusing overwrite")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        codes = [row[0] for row in src.execute("SELECT DISTINCT code FROM evening_analysis_codes ORDER BY code")]
        if not codes:
            raise ValueError("Evening universe is empty")
        # Deliberate column allow-list. No preferences, tokens, requests or user IDs.
        # Sector metadata is market reference data and is needed only for aggregate
        # research breakdowns; it does not identify an app user.
        sectors = list(src.execute("""SELECT code, sector_17_name, sector_33_name,
            market_name, scale_category FROM master_stock
            WHERE code IN (SELECT code FROM evening_analysis_codes) ORDER BY code"""))
        cursor = src.execute("""SELECT code, trade_date, open, high, low, close,
            adjusted_close, volume, dividends, stock_splits FROM price_daily
            WHERE code IN (SELECT code FROM evening_analysis_codes)
            ORDER BY code, trade_date""")
        output.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(output)) as dst, dst:
            dst.execute("CREATE TABLE evening_analysis_codes (code TEXT PRIMARY KEY)")
            dst.executemany("INSERT INTO evening_analysis_codes VALUES (?)", [(code,) for code in codes])
            dst.execute("""CREATE TABLE master_stock (code TEXT PRIMARY KEY,
                sector_17_name TEXT, sector_33_name TEXT, market_name TEXT,
                scale_category TEXT)""")
            dst.executemany("INSERT INTO master_stock VALUES (?,?,?,?,?)", sectors)
            dst.execute("""CREATE TABLE price_daily (code TEXT, trade_date TEXT,
                open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
                volume REAL, dividends REAL, stock_splits REAL,
                PRIMARY KEY(code,trade_date))""")
            while rows := cursor.fetchmany(10000):
                dst.executemany("INSERT INTO price_daily VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            count, stocks, start, end = dst.execute(
                "SELECT COUNT(*),COUNT(DISTINCT code),MIN(trade_date),MAX(trade_date) FROM price_daily").fetchone()
            if not count:
                raise ValueError("Evening universe has no price history")
    return dict(universe_count=len(codes), price_stock_count=stocks, row_count=count,
                first_date=start, last_date=end)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.output), ensure_ascii=False))
