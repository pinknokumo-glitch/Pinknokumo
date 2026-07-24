"""Publish latest screened candidates for authenticated Android clients."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CloudResultPublisher:
    def __init__(self, url: str, service_role_key: str, user_id: str) -> None:
        self.url, self.key, self.user_id = url.rstrip("/"), service_role_key, user_id

    @classmethod
    def from_environment(cls) -> "CloudResultPublisher | None":
        values = [os.getenv(name, "").strip() for name in (
            "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "STOCKAI_USER_ID",
        )]
        return cls(*values) if all(values) else None

    def publish(
        self, screening_date: str, profile: str,
        hits: Sequence[Mapping[str, object]], comments: Mapping[str, str],
        chart_urls: Sequence[str],
    ) -> int:
        rows = []
        for position, hit in enumerate(hits, start=1):
            code = str(hit["code"])
            rows.append({
                "user_id": self.user_id, "screening_date": screening_date,
                "profile_name": profile, "position": position, "code": code,
                "company_name": hit.get("company_name"),
                "expectation_score": hit.get("expectation_score"),
                "reason": hit.get("reason"), "comment": comments.get(code),
                "chart_url": chart_urls[position - 1] if position <= len(chart_urls) else None,
            })
        request = Request(
            f"{self.url}/rest/v1/screening_results"
            "?on_conflict=user_id,screening_date,profile_name,code",
            data=json.dumps(rows, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={
                **self.headers(), "Content-Type": "application/json; charset=utf-8",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=20):
                return len(rows)
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not publish cloud screening results: {type(error).__name__}"
            ) from error

    def headers(self) -> dict[str, str]:
        headers = {"apikey": self.key, "Accept": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

