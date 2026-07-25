"""Publish latest screened candidates for authenticated Android clients."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class CloudResultPublisher:
    def __init__(self, url: str, service_role_key: str, user_id: str) -> None:
        self.url, self.key, self.user_id = url.rstrip("/"), service_role_key, user_id

    @classmethod
    def from_environment(cls, user_id: str | None = None) -> "CloudResultPublisher | None":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        resolved_user_id = user_id or os.getenv("STOCKAI_USER_ID", "").strip()
        return cls(url, key, resolved_user_id) if url and key and resolved_user_id else None

    def publish(
        self, screening_date: str, profile: str,
        hits: Sequence[Mapping[str, object]], comments: Mapping[str, str],
        chart_urls: Sequence[str],
        holding_days: int | None = None,
        condition_summary: str | None = None,
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
                "holding_days": holding_days,
                "condition_summary": condition_summary,
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

    def replace(
        self, screening_date: str, profile: str,
        hits: Sequence[Mapping[str, object]], comments: Mapping[str, str],
        chart_urls: Sequence[str] = (),
        holding_days: int | None = None,
        condition_summary: str | None = None,
    ) -> int:
        """Replace one user's visible result set, including a valid zero-hit result."""
        delete = Request(
            f"{self.url}/rest/v1/screening_results?user_id=eq.{quote(self.user_id)}",
            method="DELETE",
            headers={**self.headers(), "Prefer": "return=minimal"},
        )
        try:
            with urlopen(delete, timeout=20):
                pass
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not replace cloud screening results: {type(error).__name__}"
            ) from error
        if not hits:
            return 0
        return self.publish(
            screening_date, profile, hits, comments, chart_urls,
            holding_days, condition_summary,
        )

    def publish_run(
        self,
        screening_date: str,
        profile: str,
        holding_days: int,
        condition_summary: str,
        hit_count: int,
    ) -> None:
        payload = [{
            "user_id": self.user_id,
            "screening_date": screening_date,
            "profile_name": profile,
            "holding_days": holding_days,
            "condition_summary": condition_summary,
            "hit_count": hit_count,
        }]
        request = Request(
            f"{self.url}/rest/v1/screening_runs?on_conflict=user_id",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                **self.headers(),
                "Content-Type": "application/json; charset=utf-8",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urlopen(request, timeout=20):
                pass
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not publish cloud screening run: {type(error).__name__}"
            ) from error

    def headers(self) -> dict[str, str]:
        headers = {"apikey": self.key, "Accept": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

