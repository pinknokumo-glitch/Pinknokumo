"""Contract checks for the read-only local API."""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api import app


class ApiContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_endpoints(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.get("/system/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("latest_price_date", response.json())

    def test_local_summary_endpoints(self) -> None:
        report = self.client.get("/reports/daily")
        self.assertEqual(report.status_code, 200)
        self.assertTrue({"health", "recent_jobs", "market_regimes", "portfolio"} <= report.json().keys())
        jobs = self.client.get("/jobs")
        self.assertEqual(jobs.status_code, 200)
        self.assertIn("jobs", jobs.json())
        operations = self.client.get("/operations/status")
        self.assertEqual(operations.status_code, 200)
        self.assertTrue(
            {"ready", "pool", "evening_update", "morning_update", "morning_screening"}
            <= operations.json().keys()
        )

    def test_read_models(self) -> None:
        for path, key in (
            ("/rankings", "rankings"),
            ("/rankings/changes", "changes"),
            ("/watchlist", "watchlist"),
            ("/portfolio", "positions"),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(key, response.json())

    def test_invalid_price_timeframe_is_rejected(self) -> None:
        response = self.client.get("/stocks/MISSING/prices?timeframe=invalid")
        self.assertEqual(response.status_code, 400)

    def test_missing_overview_is_not_found(self) -> None:
        response = self.client.get("/stocks/MISSING/overview")
        self.assertEqual(response.status_code, 404)

    def test_chart_endpoint_returns_svg_or_not_found(self) -> None:
        response = self.client.get("/stocks/72030/chart.svg")
        self.assertIn(response.status_code, {200, 404})
        if response.status_code == 200:
            self.assertEqual(response.headers["content-type"], "image/svg+xml")

    def test_screening_options_and_bounded_manual_preview(self) -> None:
        options = self.client.get("/screening-options")
        self.assertEqual(options.status_code, 200)
        self.assertIn("割安株", [item["label"] for item in options.json()["genres"]])
        self.assertEqual({mode["id"] for mode in options.json()["modes"]}, {"auto", "manual"})
        preview = self.client.post("/screening-preview", json={
            "logic": "all", "conditions": [
                {"field": "daily.rsi_14", "operator": "<=", "value": 60},
                {"field": "fundamental.per", "operator": "<=", "value": 15},
            ],
        })
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["persisted"])
        rejected = self.client.post("/screening-preview", json={
            "conditions": [{"field": "daily.rsi_14", "operator": "<=", "value": 999}],
        })
        self.assertEqual(rejected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
