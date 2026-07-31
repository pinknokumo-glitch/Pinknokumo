"""Publish latest screened candidates for authenticated Android clients."""
from __future__ import annotations

import json
import math
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
        expectation_condition_summary: str | None = None,
        trade_direction: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
    ) -> int:
        rows = []
        for position, hit in enumerate(hits, start=1):
            code = str(hit["code"])
            rows.append({
                "user_id": self.user_id, "screening_date": screening_date,
                "profile_name": profile, "position": position, "code": code,
                "company_name": hit.get("company_name"),
                "expectation_score": self._finite_number(
                    hit.get("expectation_score")
                ),
                "reason": hit.get("reason"), "comment": comments.get(code),
                "chart_url": chart_urls[position - 1] if position <= len(chart_urls) else None,
                "holding_days": holding_days,
                "condition_summary": condition_summary,
                "expectation_condition_summary": expectation_condition_summary,
                "trade_direction": trade_direction,
                "expectation_evaluation_mode": evaluation_mode,
                "target_return_percent": target_return_percent,
                "outcome_probability_percent": self._finite_number(
                    hit.get("outcome_probability_percent")
                ),
                "profit_10_probability_percent": self._finite_number(
                    hit.get("profit_10_probability_percent")
                ),
                "profit_20_probability_percent": self._finite_number(
                    hit.get("profit_20_probability_percent")
                ),
                "average_return_percent": self._finite_number(
                    hit.get("average_return_percent")
                ),
                "win_rate_percent": self._finite_number(
                    hit.get("win_rate_percent")
                ),
                "max_drawdown_percent": self._finite_number(
                    hit.get("max_drawdown_percent")
                ),
                "reference_price": self._finite_number(hit.get("reference_price")),
                "estimated_price_median": self._finite_number(
                    hit.get("estimated_price_median")
                ),
                "estimated_price_low": self._finite_number(
                    hit.get("estimated_price_low")
                ),
                "estimated_price_high": self._finite_number(
                    hit.get("estimated_price_high")
                ),
                "estimate_sample_count": int(hit.get("estimate_sample_count") or 0),
                "median_days_to_outcome": self._finite_number(
                    hit.get("median_days_to_outcome")
                ),
                "individual_trade_count": int(
                    hit.get("individual_trade_count") or 0
                ),
                "individual_out_of_sample_trade_count": int(
                    hit.get("individual_out_of_sample_trade_count") or 0
                ),
                "individual_out_of_sample_average_return_percent":
                    self._finite_number(
                        hit.get(
                            "individual_out_of_sample_average_return_percent"
                        )
                    ),
                "individual_out_of_sample_win_rate_percent":
                    self._finite_number(
                        hit.get(
                            "individual_out_of_sample_win_rate_percent"
                        )
                    ),
                "sector_name": hit.get("sector_name"),
                "sector_backtest": self._finite_mapping(
                    hit.get("sector_backtest")
                ),
                "market_backtest": self._finite_mapping(
                    hit.get("market_backtest")
                ),
                "backtest_coverage_ratio": self._finite_number(
                    hit.get("backtest_coverage_ratio")
                ),
                "backtest_confidence": hit.get("backtest_confidence"),
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
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                "Could not publish cloud screening results: "
                f"HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Could not publish cloud screening results: {type(error).__name__}"
            ) from error

    def replace(
        self, screening_date: str, profile: str,
        hits: Sequence[Mapping[str, object]], comments: Mapping[str, str],
        chart_urls: Sequence[str] = (),
        holding_days: int | None = None,
        condition_summary: str | None = None,
        expectation_condition_summary: str | None = None,
        trade_direction: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
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
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                "Could not replace cloud screening results: "
                f"HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Could not replace cloud screening results: {type(error).__name__}"
            ) from error
        if not hits:
            return 0
        return self.publish(
            screening_date, profile, hits, comments, chart_urls,
            holding_days, condition_summary, expectation_condition_summary,
            trade_direction, evaluation_mode, target_return_percent,
        )

    def publish_run(
        self,
        screening_date: str,
        profile: str,
        holding_days: int,
        condition_summary: str,
        hit_count: int,
        expectation_condition_summary: str | None = None,
        trade_direction: str = "long",
        evaluation_mode: str = "condition_exit",
        target_return_percent: float = 5.0,
        relaxation_label: str | None = None,
        relaxation_counts: Sequence[Mapping[str, object]] = (),
    ) -> None:
        payload = [{
            "user_id": self.user_id,
            "screening_date": screening_date,
            "profile_name": profile,
            "holding_days": holding_days,
            "condition_summary": condition_summary,
            "expectation_condition_summary": expectation_condition_summary,
            "trade_direction": trade_direction,
            "expectation_evaluation_mode": evaluation_mode,
            "target_return_percent": target_return_percent,
            "relaxation_label": relaxation_label,
            "relaxation_counts": list(relaxation_counts),
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
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                f"Could not publish cloud screening run: HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Could not publish cloud screening run: {type(error).__name__}"
            ) from error

    def headers(self) -> dict[str, str]:
        headers = {"apikey": self.key, "Accept": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    @staticmethod
    def _finite_number(value: object) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _finite_mapping(cls, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            return {}
        return {
            str(key): (
                cls._finite_number(item)
                if isinstance(item, float)
                else item
            )
            for key, item in value.items()
        }

