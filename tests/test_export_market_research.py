import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from scripts.export_market_research import export


class MarketExportTests(unittest.TestCase):
    def test_only_allowed_market_tables_and_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            with closing(sqlite3.connect(source)) as c, c:
                c.executescript("""CREATE TABLE evening_analysis_codes(code TEXT);
                INSERT INTO evening_analysis_codes VALUES ('1234');
                CREATE TABLE private_settings(secret TEXT);
                INSERT INTO private_settings VALUES ('not for export');
                CREATE TABLE price_daily(code TEXT,trade_date TEXT,open REAL,high REAL,
                low REAL,close REAL,adjusted_close REAL,volume REAL,dividends REAL,stock_splits REAL);
                INSERT INTO price_daily VALUES ('1234','2026-01-01',1,2,1,2,2,100,0,0);
                INSERT INTO price_daily VALUES ('OTHER','2026-01-01',1,2,1,2,2,100,0,0);""")
            original = source.read_bytes()
            result = export(source, output)
            self.assertEqual(result['row_count'], 1)
            self.assertEqual(source.read_bytes(), original)
            with closing(sqlite3.connect(output)) as c:
                self.assertEqual({r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                                 {'price_daily','evening_analysis_codes'})
            with self.assertRaises(FileExistsError):
                export(source, output)

    def test_empty_universe_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            with closing(sqlite3.connect(source)) as c, c:
                c.execute('CREATE TABLE evening_analysis_codes(code TEXT)')
            with self.assertRaises(ValueError):
                export(source, output)
            self.assertFalse(output.exists())
