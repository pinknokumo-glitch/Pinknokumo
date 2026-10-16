import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from scripts.export_market_research import export, load_include_codes


class MarketExportTests(unittest.TestCase):
    def make_history(self, path):
        with closing(sqlite3.connect(path)) as c, c:
            c.executescript("""CREATE TABLE evening_analysis_codes(code TEXT);
            INSERT INTO evening_analysis_codes VALUES ('12340');
            CREATE TABLE master_stock(code TEXT PRIMARY KEY,sector_17_name TEXT,
                sector_33_name TEXT,market_name TEXT,scale_category TEXT,secret TEXT);
            INSERT INTO master_stock VALUES ('12340','a','b','Prime','s','private');
            INSERT INTO master_stock VALUES ('19480','a','b','Standard','s','private');
            INSERT INTO master_stock VALUES ('OTHER','a','b','Standard','s','private');
            CREATE TABLE private_settings(secret TEXT);
            INSERT INTO private_settings VALUES ('never export');
            CREATE TABLE price_daily(code TEXT,trade_date TEXT,open REAL,high REAL,
                low REAL,close REAL,adjusted_close REAL,volume REAL,dividends REAL,
                stock_splits REAL,private_note TEXT);
            INSERT INTO price_daily VALUES ('12340','2026-10-15',10,12,9,11,10.5,100,0,0,'private');
            INSERT INTO price_daily VALUES ('19480','2026-09-30',20,21,19,20,19.5,200,0,0,'private');
            INSERT INTO price_daily VALUES ('19480','2026-09-29',40,42,38,40,39,400,1,2,'private');
            INSERT INTO price_daily VALUES ('OTHER','2026-10-15',1,2,1,2,2,100,0,0,'private');""")

    def test_only_allowed_market_tables_and_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            with closing(sqlite3.connect(source)) as c, c:
                c.executescript("""CREATE TABLE evening_analysis_codes(code TEXT);
                INSERT INTO evening_analysis_codes VALUES ('1234');
                CREATE TABLE master_stock(code TEXT PRIMARY KEY,sector_17_name TEXT,
                sector_33_name TEXT,market_name TEXT,scale_category TEXT);
                INSERT INTO master_stock VALUES ('1234','製造業','電気機器','Prime','TOPIX Mid400');
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
                                 {'price_daily','evening_analysis_codes','master_stock'})
                self.assertEqual(c.execute("SELECT sector_33_name FROM master_stock WHERE code='1234'").fetchone()[0],
                                 '電気機器')
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

    def test_fixed_history_survives_removal_without_mutating_universe_or_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            self.make_history(source)
            original = source.read_bytes()
            result = export(source, output, ('19480', '12340'))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(result['universe_count'], 1)
            self.assertEqual(result['export_code_count'], 2)
            self.assertEqual(result['required_not_in_evening'], ['19480'])
            self.assertEqual(result['required_last_dates']['19480'], '2026-09-30')
            self.assertEqual(result['row_count'], 3)
            with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(output)) as dst:
                self.assertEqual(dst.execute('SELECT code FROM evening_analysis_codes').fetchall(), [('12340',)])
                self.assertEqual(dst.execute('SELECT code FROM master_stock ORDER BY code').fetchall(),
                                 [('12340',), ('19480',)])
                columns = 'code,trade_date,open,high,low,close,adjusted_close,volume,dividends,stock_splits'
                expected = src.execute(f'SELECT {columns} FROM price_daily WHERE code != ? ORDER BY code,trade_date',
                                       ('OTHER',)).fetchall()
                self.assertEqual(dst.execute(f'SELECT {columns} FROM price_daily ORDER BY code,trade_date').fetchall(), expected)
                self.assertEqual({r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                                 {'evening_analysis_codes', 'master_stock', 'price_daily'})
                self.assertNotIn('secret', {r[1] for r in dst.execute('PRAGMA table_info(master_stock)')})
                self.assertNotIn('private_note', {r[1] for r in dst.execute('PRAGMA table_info(price_daily)')})

    def test_absent_fixed_history_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            self.make_history(source)
            original = source.read_bytes()
            with self.assertRaisesRegex(ValueError, '38560'):
                export(source, output, ('19480', '38560'))
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_fixed_code_does_not_require_current_master_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            self.make_history(source)
            with closing(sqlite3.connect(source)) as c, c:
                c.execute("DELETE FROM master_stock WHERE code='19480'")
            self.assertEqual(export(source, output, ('19480',))['price_stock_count'], 2)

    def test_include_selection_uses_parameters_not_sql_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.db', Path(tmp)/'export.db'
            self.make_history(source)
            with self.assertRaisesRegex(ValueError, 'no source price history'):
                export(source, output, ("19480') OR 1=1 --",))
            self.assertFalse(output.exists())

    def test_manifest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'codes.json'
            valid = dict(schema_version=1, code_count=2, codes=['19480', '147A0'])
            path.write_text(json.dumps(valid), encoding='utf-8')
            self.assertEqual(load_include_codes(path), ('147A0', '19480'))
            invalid = [[], {}, {**valid, 'schema_version': 2}, {**valid, 'code_count': 1},
                       {**valid, 'codes': ['19480', '19480']},
                       {**valid, 'codes': ['19480', 147]},
                       {**valid, 'codes': ['19480', 'unsafe']},
                       {**valid, 'codes': []}, {**valid, 'codes': '19480'}]
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_include_codes(path)

    def test_committed_manifest_matches_fixed_research_count(self):
        path = Path(__file__).resolve().parents[1]/'config/research_frozen_codes_2026-09-18.json'
        codes = load_include_codes(path)
        self.assertEqual(len(codes), 442)
        self.assertIn('19480', codes)
        self.assertIn('38560', codes)
