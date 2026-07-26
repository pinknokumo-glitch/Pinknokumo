"""Publish the latest evening candidate codes for authenticated app users."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CloudCandidatePublisher:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key

    def replace(
        self,
        pool_date: str,
        codes: Sequence[str],
        metadata: Mapping[str, object] | None = None,
    ) -> int:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json; charset=utf-8",
            "Prefer": "return=minimal",
        }
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        try:
            with urlopen(Request(
                f"{self.url}/rest/v1/screening_candidates",
                method="DELETE",
                headers=headers,
            ), timeout=20):
                pass
            rows = [{"pool_date": pool_date, "code": str(code)} for code in codes]
            if rows:
                with urlopen(Request(
                    f"{self.url}/rest/v1/screening_candidates",
                    data=json.dumps(rows).encode("utf-8"),
                    method="POST",
                    headers=headers,
                ), timeout=20):
                    pass
            details = dict(metadata or {})
            run_row = {
                "pool_date": pool_date,
                "universe_count": int(details.get("universe_count", 0)),
                "evaluated_count": int(details.get("evaluated_count", 0)),
                "candidate_count": len(codes),
                "failed_count": int(details.get("failed_count", 0)),
                "coverage_ratio": float(details.get("coverage_ratio", 0.0)),
                "status": str(details.get("status", "success")),
                "usable": bool(details.get("usable", False)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            run_headers = {
                **headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }
            with urlopen(Request(
                f"{self.url}/rest/v1/screening_candidate_runs?on_conflict=pool_date",
                data=json.dumps([run_row]).encode("utf-8"),
                method="POST",
                headers=run_headers,
            ), timeout=20):
                pass
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not publish screening candidates: {type(error).__name__}"
            ) from error
        return len(codes)
