from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from modules.cloud_stock_catalog import CloudStockCatalogPublisher


class CloudStockCatalogPublisherTests(unittest.TestCase):
    def test_snapshot_publishes_atomic_replacement_and_run_id(self):
        response = MagicMock()
        with patch("modules.cloud_stock_catalog.urlopen", return_value=response) as send:
            count = CloudStockCatalogPublisher('https://test', 'test').publish_snapshot(
                [{'code': '7203', 'company_name': 'トヨタ'}], '123')
        self.assertEqual(count, 1)
        self.assertTrue(send.call_args.args[0].full_url.endswith('/rpc/publish_evening_catalog'))
        self.assertEqual(json.loads(send.call_args.args[0].data)['p_run_id'], '123')

    def test_empty_snapshot_does_not_remove_existing_catalog(self):
        with patch("modules.cloud_stock_catalog.urlopen") as send:
            with self.assertRaises(ValueError):
                CloudStockCatalogPublisher('https://test', 'test').publish_snapshot([], '123')
        send.assert_not_called()

    def test_publish_normalizes_codes_and_uses_catalog_upsert(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        publisher = CloudStockCatalogPublisher(
            "https://example.supabase.co", "sb_secret_test"
        )
        with patch("modules.cloud_stock_catalog.urlopen", return_value=response) as send:
            count = publisher.publish([
                {"code": "7203", "company_name": "トヨタ自動車"},
                {"code": " 6758 ", "company_name": "ソニー"},
            ])
        self.assertEqual(count, 2)
        request = send.call_args.args[0]
        self.assertIn("stock_search_catalog?on_conflict=code", request.full_url)
        self.assertEqual(json.loads(request.data.decode("utf-8"))[1]["code"], "6758")
        self.assertIn("resolution=merge-duplicates", request.headers["Prefer"])

    def test_publish_accepts_sqlite_rows_from_the_existing_stock_master(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("create table master_stock (code text, company_name text)")
        connection.execute("insert into master_stock values ('7203', 'トヨタ自動車')")
        rows = connection.execute("select code, company_name from master_stock").fetchall()
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("modules.cloud_stock_catalog.urlopen", return_value=response):
            count = CloudStockCatalogPublisher(
                "https://example.supabase.co", "sb_secret_test"
            ).publish(rows)
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

