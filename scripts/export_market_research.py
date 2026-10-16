"""Export only market history from an evening snapshot; never copy user tables."""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
from pathlib import Path
from contextlib import closing


def load_include_codes(path: Path) -> tuple[str, ...]:
    """Read the versioned, code-only frozen research universe; never trade data."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    codes = manifest.get("codes") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(codes, list)
            or not codes or manifest.get("code_count") != len(codes)
            or any(not isinstance(code, str) or not re.fullmatch(r"[0-9A-Z]{5}", code)
                   for code in codes) or len(codes) != len(set(codes))):
        raise ValueError("Invalid frozen research code manifest")
    return tuple(sorted(codes))


def export(source: Path, output: Path, include_codes: tuple[str, ...] = ()) -> dict:
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("Research output already exists; refusing overwrite")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        codes = [row[0] for row in src.execute("SELECT DISTINCT code FROM evening_analysis_codes ORDER BY code")]
        if not codes:
            raise ValueError("Evening universe is empty")
        # Preserve today's universe as-is. Add fixed research history only to
        # the market-table selection, not to evening_analysis_codes.
        export_codes = sorted(set(codes) | set(include_codes))
        src.execute("CREATE TEMP TABLE research_export_codes(code TEXT PRIMARY KEY)")
        src.executemany("INSERT INTO research_export_codes VALUES (?)",
                        [(code,) for code in export_codes])
        history_ends = dict(src.execute("""SELECT code, MAX(trade_date) FROM price_daily
            WHERE code IN (SELECT code FROM research_export_codes) GROUP BY code"""))
        missing = sorted(set(include_codes) - history_ends.keys())
        if missing:
            # Missing history must remain a visible failure, never an omitted
            # origin, fabricated price, or synthetic expiry.
            raise ValueError(f"Frozen research codes have no source price history: {missing}")
        # Deliberate column allow-list. No preferences, tokens, requests or user IDs.
        # Sector metadata is market reference data and is needed only for aggregate
        # research breakdowns; it does not identify an app user.
        sectors = list(src.execute("""SELECT code, sector_17_name, sector_33_name,
            market_name, scale_category FROM master_stock
            WHERE code IN (SELECT code FROM research_export_codes) ORDER BY code"""))
        cursor = src.execute("""SELECT code, trade_date, open, high, low, close,
            adjusted_close, volume, dividends, stock_splits FROM price_daily
            WHERE code IN (SELECT code FROM research_export_codes)
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
                first_date=start, last_date=end, export_code_count=len(export_codes),
                required_code_count=len(set(include_codes)),
                required_not_in_evening=sorted(set(include_codes) - set(codes)),
                required_last_dates={code: history_ends[code] for code in sorted(set(include_codes))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-codes", type=Path,
                        help="Versioned JSON manifest of frozen research codes to retain")
    args = parser.parse_args()
    included = load_include_codes(args.include_codes) if args.include_codes else ()
    print(json.dumps(export(args.source, args.output, included), ensure_ascii=False))
