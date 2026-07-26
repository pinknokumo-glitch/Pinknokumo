"""Publish the latest evening candidate codes for authenticated app users."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
            self._send(Request(
                f"{self.url}/rest/v1/screening_candidates",
                method="DELETE",
                headers=headers,
            ), "candidate cleanup")
            rows = [{"pool_date": pool_date, "code": str(code)} for code in codes]
            if rows:
                self._send(Request(
                    f"{self.url}/rest/v1/screening_candidates",
                    data=json.dumps(rows).encode("utf-8"),
                    method="POST",
                    headers=headers,
                ), "candidate insert")
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
            # Delete then insert instead of relying on an older deployment having
            # the unique constraint required by PostgREST's on_conflict option.
            self._send(Request(
                f"{self.url}/rest/v1/screening_candidate_runs"
                f"?pool_date=eq.{quote(pool_date)}",
                method="DELETE",
                headers=headers,
            ), "candidate run cleanup")
            self._send(Request(
                f"{self.url}/rest/v1/screening_candidate_runs",
                data=json.dumps([run_row]).encode("utf-8"),
                method="POST",
                headers=headers,
            ), "candidate run insert")
        except RuntimeError:
            raise
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not publish screening candidates: {self._error_detail(error)}"
            ) from error
        return len(codes)

    @staticmethod
    def _send(request: Request, operation: str) -> None:
        try:
            with urlopen(request, timeout=20):
                pass
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not publish screening candidates during {operation}: "
                f"{CloudCandidatePublisher._error_detail(error)}"
            ) from error

    @staticmethod
    def _error_detail(error: HTTPError | URLError) -> str:
        if isinstance(error, HTTPError):
            try:
                body = error.read().decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""
            detail = f"HTTP {error.code}"
            if body:
                detail = f"{detail}: {body[:1000]}"
            return detail
        return f"{type(error).__name__}: {error.reason}"
