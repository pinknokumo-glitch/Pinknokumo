"""Publish the read-only stock search catalog used by the Android app."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CloudStockCatalogPublisher:
    """Upsert the local stock master into the authenticated Supabase catalog."""

    def __init__(self, url: str, service_role_key: str) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key

    def publish(self, rows: Sequence[Mapping[str, object]]) -> int:
        normalized = [
            {
                "code": str(row["code"]).strip().upper(),
                "company_name": str(row["company_name"] or "").strip(),
            }
            for row in rows
            if str(row["code"] or "").strip()
        ]
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json; charset=utf-8",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        try:
            for offset in range(0, len(normalized), 500):
                payload = normalized[offset : offset + 500]
                request = Request(
                    f"{self.url}/rest/v1/stock_search_catalog?on_conflict=code",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    method="POST",
                    headers=headers,
                )
                with urlopen(request, timeout=30):
                    pass
        except (HTTPError, URLError) as error:
            detail = self._error_detail(error)
            raise RuntimeError(f"Could not publish stock search catalog: {detail}") from error
        return len(normalized)

    def publish_snapshot(self, rows: Sequence[Mapping[str, object]], run_id: str) -> int:
        if not run_id.isdigit() or not rows:
            raise ValueError("Evening snapshot must have a run id and fetched stocks")
        payload = {"p_run_id": run_id, "p_stocks": [
            {"code": str(row["code"]), "company_name": str(row["company_name"] or "")}
            for row in rows
        ]}
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        req = Request(self.url + "/rest/v1/rpc/publish_evening_catalog",
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers=headers, method="POST")
        with urlopen(req, timeout=60):
            pass
        return len(rows)

    @staticmethod
    def _error_detail(error: HTTPError | URLError) -> str:
        if isinstance(error, HTTPError):
            try:
                body = error.read().decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""
            return f"HTTP {error.code}" + (f": {body[:1000]}" if body else "")
        return f"{type(error).__name__}: {error.reason}"

