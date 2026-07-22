"""Read validated screening preferences from Supabase without exposing server credentials to Android."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from modules.screening_options import ScreeningOptions


@dataclass(frozen=True)
class ScreeningPreference:
    mode: str
    genre_id: str | None
    manual_logic: str
    manual_conditions: list[dict[str, object]]


class CloudPreferenceClient:
    def __init__(self, url: str, service_role_key: str, user_id: str) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key
        self.user_id = user_id

    @classmethod
    def from_environment(cls) -> "CloudPreferenceClient | None":
        values = [os.getenv(name, "").strip() for name in (
            "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "STOCKAI_USER_ID",
        )]
        return cls(*values) if all(values) else None

    def fetch(self, options: ScreeningOptions) -> ScreeningPreference | None:
        endpoint = (
            f"{self.url}/rest/v1/screening_preferences?user_id=eq.{quote(self.user_id)}"
            "&select=mode,genre_id,manual_logic,manual_conditions&limit=1"
        )
        request = Request(endpoint, headers={
            "apikey": self.key, "Authorization": f"Bearer {self.key}", "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=15) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not load cloud screening preference: {type(error).__name__}") from error
        if not rows:
            return None
        return self.validate(rows[0], options)

    @staticmethod
    def validate(raw: Mapping[str, object], options: ScreeningOptions) -> ScreeningPreference:
        mode = str(raw.get("mode") or "")
        if mode not in {"auto", "manual"}:
            raise ValueError("cloud preference mode is invalid")
        logic = str(raw.get("manual_logic") or "all")
        conditions = raw.get("manual_conditions") or []
        if not isinstance(conditions, list):
            raise ValueError("cloud manual_conditions must be a list")
        genre_id = str(raw.get("genre_id") or "") or None
        if mode == "auto":
            genres = {str(item["id"]): item for item in options.catalog()["genres"] if item["available"]}
            if genre_id not in genres:
                raise ValueError("cloud genre_id is unavailable")
            conditions = []
        else:
            options.manual_rule(conditions, logic)
            genre_id = None
        return ScreeningPreference(mode, genre_id, logic, [dict(item) for item in conditions])
