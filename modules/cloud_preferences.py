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
    user_id: str | None
    mode: str
    genre_id: str | None
    manual_logic: str
    manual_conditions: list[dict[str, object]]
    holding_days: int = 60
    expectation_mode: str | None = None
    expectation_genre_id: str | None = None
    expectation_manual_logic: str = "all"
    expectation_manual_conditions: list[dict[str, object]] | None = None
    trade_direction: str = "long"
    expectation_evaluation_mode: str = "condition_exit"
    target_return_percent: float = 5.0


class CloudPreferenceClient:
    def __init__(self, url: str, service_role_key: str, user_id: str | None = None) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key
        self.user_id = user_id
        self.validation_errors: list[dict[str, str]] = []

    @classmethod
    def from_environment(cls) -> "CloudPreferenceClient | None":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        user_id = os.getenv("STOCKAI_USER_ID", "").strip() or None
        return cls(url, key, user_id) if url and key else None

    def fetch(self, options: ScreeningOptions) -> ScreeningPreference | None:
        filters = (
            f"user_id=eq.{quote(self.user_id)}&"
            if self.user_id
            else "order=updated_at.desc&"
        )
        endpoint = (
            f"{self.url}/rest/v1/screening_preferences?{filters}"
            "select=user_id,mode,genre_id,manual_logic,manual_conditions,holding_days,"
            "expectation_mode,expectation_genre_id,expectation_manual_logic,"
            "expectation_manual_conditions,trade_direction,"
            "expectation_evaluation_mode,target_return_percent&limit=1"
        )
        request = Request(endpoint, headers=self.headers())
        try:
            with urlopen(request, timeout=15) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not load cloud screening preference: {type(error).__name__}") from error
        if not rows:
            return None
        return self.validate(rows[0], options)

    def headers(self) -> dict[str, str]:
        """Support both current sb_secret keys and legacy JWT service-role keys."""
        headers = {"apikey": self.key, "Accept": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

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
        user_id = str(raw.get("user_id") or "") or None
        holding_days = int(raw.get("holding_days") or 60)
        if holding_days < 1 or holding_days > 250:
            raise ValueError("cloud holding_days must be between 1 and 250")
        expectation_mode = str(raw.get("expectation_mode") or mode)
        expectation_genre_id = str(
            raw.get("expectation_genre_id") or genre_id or ""
        ) or None
        expectation_logic = str(raw.get("expectation_manual_logic") or logic)
        expectation_conditions = raw.get("expectation_manual_conditions")
        if expectation_conditions is None:
            expectation_conditions = conditions
        if not isinstance(expectation_conditions, list):
            raise ValueError("cloud expectation_manual_conditions must be a list")
        if expectation_mode == "auto":
            genres = {
                str(item["id"]): item
                for item in options.catalog()["genres"] if item["available"]
            }
            if expectation_genre_id not in genres:
                raise ValueError("cloud expectation_genre_id is unavailable")
            expectation_conditions = []
        elif expectation_mode == "manual":
            options.manual_rule(expectation_conditions, expectation_logic)
            expectation_genre_id = None
        else:
            raise ValueError("cloud expectation_mode is invalid")
        trade_direction = str(raw.get("trade_direction") or "long")
        if trade_direction not in {"long", "short"}:
            raise ValueError("cloud trade_direction must be long or short")
        evaluation_mode = str(
            raw.get("expectation_evaluation_mode") or "condition_exit"
        )
        if evaluation_mode not in {
            "condition_exit", "period_end", "within_period_up", "target_return"
        }:
            raise ValueError("cloud expectation_evaluation_mode is invalid")
        target_return_percent = float(raw.get("target_return_percent") or 5.0)
        if target_return_percent <= 0 or target_return_percent > 100:
            raise ValueError(
                "cloud target_return_percent must be greater than 0 and at most 100"
            )
        return ScreeningPreference(
            user_id=user_id,
            mode=mode,
            genre_id=genre_id,
            manual_logic=logic,
            manual_conditions=[dict(item) for item in conditions],
            holding_days=holding_days,
            expectation_mode=expectation_mode,
            expectation_genre_id=expectation_genre_id,
            expectation_manual_logic=expectation_logic,
            expectation_manual_conditions=[
                dict(item) for item in expectation_conditions
            ],
            trade_direction=trade_direction,
            expectation_evaluation_mode=evaluation_mode,
            target_return_percent=target_return_percent,
        )

    def fetch_all(self, options: ScreeningOptions) -> list[ScreeningPreference]:
        endpoint = (
            f"{self.url}/rest/v1/screening_preferences?"
            "select=user_id,mode,genre_id,manual_logic,manual_conditions,holding_days,"
            "expectation_mode,expectation_genre_id,expectation_manual_logic,"
            "expectation_manual_conditions,trade_direction,"
            "expectation_evaluation_mode,target_return_percent"
            "&order=updated_at.asc"
        )
        request = Request(endpoint, headers=self.headers())
        try:
            with urlopen(request, timeout=20) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not load cloud screening preferences: {type(error).__name__}"
            ) from error
        self.validation_errors = []
        valid = []
        for row in rows:
            try:
                valid.append(self.validate(row, options))
            except (TypeError, ValueError) as error:
                self.validation_errors.append({
                    "user_id": str(row.get("user_id") or ""),
                    "error": f"{type(error).__name__}: {error}",
                })
        return valid


def apply_preference(
    preference: ScreeningPreference,
    options: ScreeningOptions,
    screening_config: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    """Build an in-memory screening config without changing repository files."""
    config = dict(screening_config)
    profiles = dict(config.get("profiles") or {})
    if preference.mode == "auto":
        genres = {str(item["id"]): item for item in options.catalog()["genres"] if item["available"]}
        genre = genres.get(preference.genre_id or "")
        if genre is None:
            raise ValueError("cloud genre_id is unavailable")
        profile = str(genre["profile"])
    else:
        profile = "cloud_manual"
        profiles[profile] = options.manual_rule(preference.manual_conditions, preference.manual_logic)
    config["profiles"] = profiles
    config["active_profile"] = profile
    return config, profile


def apply_expectation_preference(
    preference: ScreeningPreference,
    options: ScreeningOptions,
    screening_config: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    expectation = ScreeningPreference(
        user_id=preference.user_id,
        mode=preference.expectation_mode or preference.mode,
        genre_id=preference.expectation_genre_id or preference.genre_id,
        manual_logic=preference.expectation_manual_logic,
        manual_conditions=(
            preference.expectation_manual_conditions
            if preference.expectation_manual_conditions is not None
            else preference.manual_conditions
        ),
        holding_days=preference.holding_days,
        trade_direction=preference.trade_direction,
        expectation_evaluation_mode=preference.expectation_evaluation_mode,
        target_return_percent=preference.target_return_percent,
    )
    return apply_preference(expectation, options, screening_config)
