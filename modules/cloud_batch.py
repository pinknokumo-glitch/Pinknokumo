"""Compute user-specific cloud results once per unique screening configuration."""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence

from modules.ai_comment import AnalysisCommentary
from modules.batch_backtest import BatchBacktester
from modules.backtest_history import BacktestHistoryBackfill
from modules.cloud_preferences import (
    ScreeningPreference,
    apply_expectation_preference,
    apply_preference,
)
from modules.cloud_results import CloudResultPublisher
from modules.database import Database
from modules.repository import StockRepository
from modules.rule_engine import RuleEngine
from modules.screener import Screener
from modules.screening_options import ScreeningOptions
from modules.screening_relaxation import staged_rules

INDUSTRY_METRICS = (
    "per",
    "pbr",
    "roe",
    "roa",
    "operating_margin",
    "equity_ratio",
    "dividend_yield",
    "sales_growth",
    "operating_profit_growth",
    "profit_growth",
    "eps_growth",
)


def preference_signature(preference: ScreeningPreference) -> str:
    payload = {
        "mode": preference.mode,
        "genre_id": preference.genre_id,
        "manual_logic": preference.manual_logic,
        "manual_conditions": preference.manual_conditions,
        "holding_days": preference.holding_days,
        "expectation_mode": preference.expectation_mode,
        "expectation_genre_id": preference.expectation_genre_id,
        "expectation_manual_logic": preference.expectation_manual_logic,
        "expectation_manual_conditions": preference.expectation_manual_conditions,
        "trade_direction": preference.trade_direction,
        "expectation_evaluation_mode": preference.expectation_evaluation_mode,
        "target_return_percent": preference.target_return_percent,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def group_preferences(
    preferences: Sequence[ScreeningPreference],
) -> dict[str, list[ScreeningPreference]]:
    groups: dict[str, list[ScreeningPreference]] = defaultdict(list)
    for preference in preferences:
        if preference.user_id:
            groups[preference_signature(preference)].append(preference)
    return dict(groups)


def verified_expectation_score(
    result: Mapping[str, object] | None,
) -> float | None:
    if not result:
        return None
    summary = result.get("summary")
    expectation = result.get("expectation")
    if not isinstance(summary, Mapping) or not isinstance(expectation, Mapping):
        return None
    if int(summary.get("trade_count") or 0) <= 0:
        return None
    score = expectation.get("score")
    return float(score) if score is not None else None


def add_industry_benchmarks(
    snapshots: Sequence[Mapping[str, object]],
    sector_names: Mapping[str, object],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    prepared: list[dict[str, object]] = []
    for source in snapshots:
        item = dict(source)
        sector = str(sector_names.get(str(item["code"])) or "業種未分類")
        item["fundamental.sector_name"] = sector
        prepared.append(item)
        for metric in INDUSTRY_METRICS:
            value = _finite_float(item.get(f"fundamental.{metric}"))
            if value is not None and _reasonable_industry_value(metric, value):
                grouped[sector][metric].append(value)
    for item in prepared:
        sector = str(item["fundamental.sector_name"])
        peer_counts = []
        for metric in INDUSTRY_METRICS:
            values = grouped[sector].get(metric, [])
            if len(values) >= 2:
                item[f"industry.{metric}"] = sum(values) / len(values)
                peer_counts.append(len(values))
        item["industry.sample_count"] = max(peer_counts, default=0)
    return prepared


def _reasonable_industry_value(metric: str, value: float) -> bool:
    limits = {
        "per": (0.0, 300.0),
        "pbr": (0.0, 30.0),
        "dividend_yield": (0.0, 20.0),
        "equity_ratio": (0.0, 100.0),
    }
    low, high = limits.get(metric, (-200.0, 500.0))
    return low < value <= high


def run_cloud_batch(
    database: Database,
    preferences: Sequence[ScreeningPreference],
    options: ScreeningOptions,
    screening_config: Mapping[str, object],
    indicator_config: Mapping[str, object],
    backtest_config: Mapping[str, object],
    scoring_config: Mapping[str, object],
    supabase_url: str,
    service_role_key: str,
    candidate_codes: list[str] | None = None,
    max_groups: int = 50,
    max_hits_per_group: int = 100,
    settings: Mapping[str, object] | None = None,
) -> dict[str, object]:
    started_at = time.monotonic()
    groups = group_preferences(preferences)
    published_users = 0
    processed_groups: list[dict[str, object]] = []
    failed_groups: list[dict[str, object]] = []
    failed_users: list[dict[str, object]] = []
    with database.connect() as connection:
        snapshot_reader = Screener(
            connection, indicator_config, screening_config,
            candidate_codes=candidate_codes,
        )
        snapshots = snapshot_reader.snapshots()
        master_rows = connection.execute(
            "SELECT code, company_name, sector_33_name FROM master_stock"
        ).fetchall()
        company_names = {
            str(row["code"]): row["company_name"] for row in master_rows
        }
        sector_names = {
            str(row["code"]): row["sector_33_name"] for row in master_rows
        }
    snapshots = add_industry_benchmarks(snapshots, sector_names)
    rule_engine = RuleEngine()
    queued_groups = list(groups.items())
    overflow_groups = queued_groups[max_groups:]
    queued_groups = queued_groups[:max_groups]
    for signature, members in overflow_groups:
        failed_groups.append({
            "signature": signature,
            "user_count": len(members),
            "error": f"SafetyLimit: maximum {max_groups} unique configurations per run",
        })
    for signature, members in queued_groups:
        try:
            outcome = _compute_group(
                database, signature, members[0], options, screening_config,
                indicator_config, backtest_config, scoring_config,
                snapshots, company_names, rule_engine,
                max_hits_per_group=max_hits_per_group,
                settings=settings,
            )
        except Exception as error:
            failed_groups.append({
                "signature": signature,
                "user_count": len(members),
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        for member in members:
            try:
                publisher = CloudResultPublisher(
                    supabase_url, service_role_key, str(member.user_id)
                )
                publisher.replace(
                    outcome["screening_date"], outcome["profile"],
                    outcome["hits"], outcome["comments"],
                    holding_days=members[0].holding_days,
                    condition_summary=outcome["screening_condition_summary"],
                    expectation_condition_summary=outcome[
                        "expectation_condition_summary"
                    ],
                    trade_direction=members[0].trade_direction,
                    evaluation_mode=members[0].expectation_evaluation_mode,
                    target_return_percent=members[0].target_return_percent,
                )
                publisher.publish_run(
                    outcome["screening_date"],
                    outcome["profile"],
                    members[0].holding_days,
                    outcome["screening_condition_summary"],
                    len(outcome["hits"]),
                    expectation_condition_summary=outcome[
                        "expectation_condition_summary"
                    ],
                    trade_direction=members[0].trade_direction,
                    evaluation_mode=members[0].expectation_evaluation_mode,
                    target_return_percent=members[0].target_return_percent,
                    relaxation_label=outcome["relaxation_label"],
                    relaxation_counts=outcome["relaxation_counts"],
                )
                published_users += 1
            except Exception as error:
                failed_users.append({
                    "user_id": str(member.user_id),
                    "signature": signature,
                    "error": f"{type(error).__name__}: {error}",
                })
        processed_groups.append({
            "signature": signature,
            "user_count": len(members),
            "holding_days": members[0].holding_days,
            "hit_count": len(outcome["hits"]),
            "profile": outcome["profile"],
            "trade_direction": members[0].trade_direction,
            "evaluation_mode": members[0].expectation_evaluation_mode,
            "target_return_percent": members[0].target_return_percent,
            "relaxation_label": outcome["relaxation_label"],
            "relaxation_counts": outcome["relaxation_counts"],
            "backtest_requested_count": outcome["backtest_requested_count"],
            "backtest_reused_count": outcome["backtest_reused_count"],
            "history_backfill": outcome["history_backfill"],
        })
    return {
        "preference_count": len(preferences),
        "group_count": len(groups),
        "published_user_count": published_users,
        "failed_group_count": len(failed_groups),
        "failed_user_count": len(failed_users),
        "history_backfill_failed_count": sum(
            int(group["history_backfill"].get("failed_count", 0))
            for group in processed_groups
        ),
        "failed_groups": failed_groups,
        "failed_users": failed_users,
        "groups": processed_groups,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "limits": {
            "max_groups": max_groups,
            "max_hits_per_group": max_hits_per_group,
        },
    }


def _compute_group(
    database: Database,
    signature: str,
    preference: ScreeningPreference,
    options: ScreeningOptions,
    screening_config: Mapping[str, object],
    indicator_config: Mapping[str, object],
    backtest_config: Mapping[str, object],
    scoring_config: Mapping[str, object],
    snapshots: Sequence[Mapping[str, object]],
    company_names: Mapping[str, object],
    rule_engine: RuleEngine,
    max_hits_per_group: int = 100,
    settings: Mapping[str, object] | None = None,
) -> dict[str, object]:
    resolved, base_profile = apply_preference(
        preference, options, screening_config
    )
    base_rule = resolved["profiles"][base_profile]
    expectation_config, expectation_profile = apply_expectation_preference(
        preference, options, screening_config
    )
    expectation_rule = expectation_config["profiles"][expectation_profile]
    hits: list[dict[str, object]] = []
    effective_rule = base_rule
    effective_profile = f"cloud_{signature}"
    relaxation_label = "基準条件"
    relaxation_counts: list[dict[str, object]] = []
    for stage_index, (_, stage_label, stage_rule) in enumerate(
        staged_rules(base_profile, base_rule, resolved.get("auto_relaxation"))
    ):
        stage_profile = f"cloud_{signature}_{stage_index}"
        hits = []
        for snapshot in snapshots:
            evaluation = rule_engine.evaluate(stage_rule, snapshot)
            if evaluation.matched:
                code = str(snapshot["code"])
                hits.append({
                    **snapshot,
                    "profile": stage_profile,
                    "reason": evaluation.reason,
                    "company_name": company_names.get(code),
                    "expectation_score": None,
                })
        relaxation_counts.append({
            "stage": stage_label,
            "hit_count": len(hits),
        })
        effective_profile = stage_profile
        effective_rule = stage_rule
        relaxation_label = stage_label
        if hits:
            break
    hits = hits[:max_hits_per_group]

    comments: dict[str, str] = {}
    backtest_requested_count = 0
    backtest_reused_count = 0
    history_backfill: dict[str, object] = {
        "requested_count": 0,
        "updated_count": 0,
        "failed_count": 0,
        "updated_codes": [],
        "failed": [],
    }
    if hits:
        hit_codes = [str(hit["code"]) for hit in hits]
        if settings is not None:
            history_backfill = BacktestHistoryBackfill(
                database, settings
            ).run(hit_codes, preference.holding_days)
        current_date = _latest_trade_date(database)
        missing_codes = _codes_requiring_backtest(
            database, hit_codes, effective_profile, current_date
        )
        missing_codes = list(dict.fromkeys([
            *history_backfill.get("updated_codes", []),
            *missing_codes,
        ]))
        backtest_requested_count = len(missing_codes)
        backtest_reused_count = len(hit_codes) - len(missing_codes)
        if missing_codes:
            BatchBacktester(
                database, indicator_config, backtest_config, scoring_config
            ).run(
                effective_profile,
                effective_rule,
                preference.holding_days,
                codes=missing_codes,
                exit_rule=expectation_rule,
                position_side=preference.trade_direction,
                evaluation_mode=preference.expectation_evaluation_mode,
                target_return_percent=preference.target_return_percent,
            )
        with database.connect() as connection:
            repository = StockRepository(connection)
            for hit in hits:
                code = str(hit["code"])
                result = repository.latest_backtest_result(code, effective_profile)
                if result:
                    summary = result.get("summary", {})
                    hit["expectation_score"] = verified_expectation_score(result)
                    hit["outcome_probability_percent"] = summary.get(
                        "outcome_probability_percent"
                    )
                    hit["average_return_percent"] = summary.get(
                        "average_return_percent"
                    )
                    hit["win_rate_percent"] = summary.get(
                        "win_rate_percent"
                    )
                    hit["max_drawdown_percent"] = summary.get(
                        "max_drawdown_percent"
                    )
                    hit.update(_estimated_price_fields(
                        hit.get("daily.close"),
                        summary,
                        preference.trade_direction,
                    ))
                backtest_comment = (
                    str(result["comment"])
                    if result and result.get("comment")
                    else None
                )
                comments[code] = AnalysisCommentary.integrated_comment(
                    hit, backtest_comment
                )
        # The entry decision is made from the common pre-backfill snapshot.
        # Historical rows downloaded for expectation analysis must not silently
        # remove an already selected stock by screening it a second time.
        hits = sorted(
            hits,
            key=lambda item: (
                item["expectation_score"]
                if item.get("expectation_score") is not None
                else float("-inf")
            ),
            reverse=True,
        )
    screening_date = _latest_trade_date(database)
    return {
        "screening_date": str(screening_date),
        "profile": effective_profile,
        "hits": hits,
        "comments": comments,
        "screening_condition_summary": json.dumps(
            effective_rule, ensure_ascii=False, sort_keys=True
        ),
        "expectation_condition_summary": json.dumps(
            expectation_rule, ensure_ascii=False, sort_keys=True
        ),
        "relaxation_label": relaxation_label,
        "relaxation_counts": relaxation_counts,
        "backtest_requested_count": backtest_requested_count,
        "backtest_reused_count": backtest_reused_count,
        "history_backfill": history_backfill,
    }


def _latest_trade_date(database: Database) -> str:
    with database.connect() as connection:
        value = connection.execute(
            "SELECT MAX(trade_date) FROM price_daily"
        ).fetchone()[0]
    return str(value)


def _codes_requiring_backtest(
    database: Database,
    codes: Sequence[str],
    profile_name: str,
    as_of_date: str,
) -> list[str]:
    if not codes:
        return []
    placeholders = ",".join("?" for _ in codes)
    with database.connect() as connection:
        rows = connection.execute(
            f"""SELECT code, result_json FROM analysis_snapshot
                WHERE analysis_type='backtest' AND profile_name=?
                  AND as_of_date=? AND code IN ({placeholders})""",
            [profile_name, as_of_date, *codes],
        ).fetchall()
    cached = set()
    for row in rows:
        result = json.loads(row[1])
        summary = result.get("summary", {})
        if "conditional_median_return_percent" in summary:
            cached.add(str(row[0]))
    return [str(code) for code in codes if str(code) not in cached]


def _estimated_price_fields(
    reference_price: object,
    summary: Mapping[str, object],
    position_side: str,
) -> dict[str, float | int | None]:
    """Convert reached-outcome return distribution into a reference price range."""
    try:
        reference = float(reference_price)
    except (TypeError, ValueError):
        reference = math.nan
    if not math.isfinite(reference) or reference <= 0:
        reference = None

    sample_count = int(summary.get("target_reached_count") or 0)
    median_days = _finite_float(summary.get("median_sessions_to_outcome"))
    returns = [
        _finite_float(summary.get("conditional_median_return_percent")),
        _finite_float(summary.get("conditional_return_p25_percent")),
        _finite_float(summary.get("conditional_return_p75_percent")),
    ]
    if reference is None or sample_count <= 0 or any(value is None for value in returns):
        return {
            "reference_price": reference,
            "estimated_price_median": None,
            "estimated_price_low": None,
            "estimated_price_high": None,
            "estimate_sample_count": sample_count,
            "median_days_to_outcome": median_days,
        }

    def price_for(return_percent: float) -> float:
        direction = -1 if position_side == "short" else 1
        return reference * (1 + direction * return_percent / 100)

    median_price = price_for(returns[0])
    range_prices = sorted((price_for(returns[1]), price_for(returns[2])))
    return {
        "reference_price": round(reference, 2),
        "estimated_price_median": round(median_price, 2),
        "estimated_price_low": round(range_prices[0], 2),
        "estimated_price_high": round(range_prices[1], 2),
        "estimate_sample_count": sample_count,
        "median_days_to_outcome": median_days,
    }


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
