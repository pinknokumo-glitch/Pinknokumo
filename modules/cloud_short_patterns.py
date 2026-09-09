"""Atomic publication of global short-horizon pattern results."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CloudShortPatternPublisher:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key

    def publish(self, run_id: str, signal_date: str, source_run_id: str, results: Sequence[Mapping[str, object]]) -> int:
        if not run_id or not source_run_id:
            raise ValueError("pattern run identifiers are required")
        payload = {"p_run_id": run_id, "p_signal_date": signal_date, "p_source_run_id": source_run_id,
                   "p_results": [dict(item) for item in results]}
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        request = Request(self.url + "/rest/v1/rpc/publish_short_pattern_run",
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=60):
                pass
        except (HTTPError, URLError) as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000] if isinstance(error, HTTPError) else str(error.reason)
            raise RuntimeError(f"Could not publish short patterns: {detail}") from error
        return len(results)
