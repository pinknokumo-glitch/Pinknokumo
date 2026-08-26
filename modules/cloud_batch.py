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
from modules.pooled_backtest import attach_scope_comparisons
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
        "rsi_method": preference.rsi_method,
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


def should_stop_relaxation(
    hit_count: int,
    minimum_hits: int,
    stage_index: int,
    stage_count: int,
) -> bool:
    """Stop after reaching the target, or always accept the final bounded stage."""
    return hit_count >= minimum_hits or stage_index >= stage_count - 1


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
            methods = (
                ("rakuten", "wilder")
                if members[0].rsi_method == "auto"
                else (members[0].rsi_method,)
            )
            candidates = [
                _compute_group(
                    database, f"{signature}_{method}", members[0], options,
                    screening_config, indicator_config, backtest_config,
                    scoring_config, snapshots, company_names, sector_names,
                    rule_engine, max_hits_per_group=max_hits_per_group,
                    settings=settings, rsi_method=method,
                )
                for method in methods
            ]
            outcome = max(candidates, key=_auto_rsi_rank)
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
                    evaluation_mode=outcome["effective_evaluation_mode"],
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
                    evaluation_mode=outcome["effective_evaluation_mode"],
                    target_return_percent=members[0].target_return_percent,
                    relaxation_label=outcome["relaxation_label"],
                    relaxation_counts=outcome["relaxation_counts"],
                    rsi_method=outcome["rsi_method"],
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
            "evaluation_mode": outcome["effective_evaluation_mode"],
            "target_return_percent": members[0].target_return_percent,
            "relaxation_label": outcome["relaxation_label"],
            "relaxation_counts": outcome["relaxation_counts"],
            "backtest_requested_count": outcome["backtest_requested_count"],
            "backtest_reused_count": outcome["backtest_reused_count"],
            "history_backfill": outcome["history_backfill"],
            "pooled_backtest": outcome["pooled_backtest"],
            "rsi_method": outcome["rsi_method"],
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
    sector_names: Mapping[str, object],
    rule_engine: RuleEngine,
    max_hits_per_group: int = 100,
    settings: Mapping[str, object] | None = None,
    rsi_method: str = "rakuten",
) -> dict[str, object]:
    resolved, base_profile = apply_preference(
        preference, options, screening_config
    )
    base_rule = _rule_for_rsi_method(resolved["profiles"][base_profile], rsi_method)
    expectation_config, expectation_profile = apply_expectation_preference(
        preference, options, screening_config
    )
    expectation_rule = _rule_for_rsi_method(
        expectation_config["profiles"][expectation_profile], rsi_method
    )
    configured_evaluation_mode = preference.expectation_evaluation_mode
    effective_evaluation_mode = configured_evaluation_mode
    if configured_evaluation_mode in {"condition_exit", "period_end"}:
        effective_evaluation_mode = (
            "condition_exit" if expectation_rule else "period_end"
        )
    hits: list[dict[str, object]] = []
    effective_rule = base_rule
    effective_profile = f"cloud_{signature}"
    relaxation_label = "基準条件"
    relaxation_counts: list[dict[str, object]] = []
    relaxation_stages = staged_rules(
        base_profile, base_rule, resolved.get("auto_relaxation")
    )
    minimum_hits = max(
        1,
        int(
            ((settings or {}).get("cloud_screening") or {}).get(
                "minimum_hits_before_relaxation", 5
            )
        ),
    )
    for stage_index, (_, stage_label, stage_rule) in enumerate(relaxation_stages):
        stage_profile = f"cloud_{signature}_{stage_index}"
        hits = []
        for source_snapshot in snapshots:
            snapshot = _snapshot_for_rsi_method(source_snapshot, rsi_method)
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
        if should_stop_relaxation(
            len(hits), minimum_hits, stage_index, len(relaxation_stages)
        ):
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
                evaluation_mode=effective_evaluation_mode,
                target_return_percent=preference.target_return_percent,
            )
        universe_codes = list(dict.fromkeys(
            str(snapshot["code"]) for snapshot in snapshots
        ))
        pooled_limit = max(
            len(hit_codes),
            int(
                ((settings or {}).get("cloud_screening") or {}).get(
                    "pooled_backtest_max_codes", 5000
                )
            ),
        )
        pooled_codes = list(dict.fromkeys([
            *hit_codes,
            *sorted(universe_codes),
        ]))[:pooled_limit]
        pooled_missing = _codes_without_current_summary(
            database, pooled_codes, effective_profile
        )
        # Matched stocks were refreshed above. The remaining per-stock results
        # are reusable for this stable condition profile and make the first full
        # market calculation the only expensive run.
        pooled_missing = [
            code for code in pooled_missing if code not in missing_codes
        ]
        if pooled_missing:
            BatchBacktester(
                database, indicator_config, backtest_config, scoring_config
            ).run(
                effective_profile,
                effective_rule,
                preference.holding_days,
                codes=pooled_missing,
                exit_rule=expectation_rule,
                position_side=preference.trade_direction,
                evaluation_mode=effective_evaluation_mode,
                target_return_percent=preference.target_return_percent,
            )
        with database.connect() as connection:
            repository = StockRepository(connection)
            pooled_summaries: dict[str, Mapping[str, object]] = {}
            for code in pooled_codes:
                pooled_result = repository.latest_backtest_result(
                    code, effective_profile
                )
                if isinstance(pooled_result, Mapping):
                    pooled_summary = pooled_result.get("summary")
                    if isinstance(pooled_summary, Mapping):
                        pooled_summaries[code] = pooled_summary
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
                    hit["profit_10_probability_percent"] = summary.get(
                        "profit_10_probability_percent"
                    )
                    hit["profit_20_probability_percent"] = summary.get(
                        "profit_20_probability_percent"
                    )
                    hit.update(_estimated_price_fields(
                        hit.get("daily.close"),
                        summary,
                        preference.trade_direction,
                        effective_evaluation_mode,
                    ))
                backtest_comment = None
                if result:
                    summary = result.get("summary")
                    expectation = result.get("expectation")
                    if isinstance(summary, Mapping) and isinstance(
                        expectation, Mapping
                    ):
                        backtest_comment = AnalysisCommentary().backtest_comment(
                            summary,
                            expectation,
                            holding_days=preference.holding_days,
                            position_side=preference.trade_direction,
                            evaluation_mode=effective_evaluation_mode,
                            target_return_percent=preference.target_return_percent,
                        )
                comments[code] = AnalysisCommentary.integrated_comment(
                    hit, backtest_comment
                )
        pooled_backtest = attach_scope_comparisons(
            hits,
            pooled_summaries,
            sector_names,
            len(universe_codes),
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
        "effective_evaluation_mode": effective_evaluation_mode,
        "relaxation_label": relaxation_label,
        "relaxation_counts": relaxation_counts,
        "backtest_requested_count": backtest_requested_count,
        "backtest_reused_count": backtest_reused_count,
        "history_backfill": history_backfill,
        "pooled_backtest": pooled_backtest if hits else {
            "universe_count": len(snapshots),
            "tested_stock_count": 0,
            "coverage_ratio": 0.0,
        },
        "rsi_method": rsi_method,
    }


def _rule_for_rsi_method(value: object, method: str) -> object:
    if isinstance(value, list):
        return [_rule_for_rsi_method(item, method) for item in value]
    if not isinstance(value, Mapping):
        return value
    output = {
        key: _rule_for_rsi_method(item, method)
        for key, item in value.items()
    }
    for key in ("field", "value_from"):
        field = output.get(key)
        if isinstance(field, str):
            prefix, separator, name = field.partition(".")
            if separator and name.startswith("rsi_") and not name.endswith(
                ("_rakuten", "_wilder")
            ):
                if name.endswith("_previous"):
                    name = f"{name[:-len('_previous')]}_{method}_previous"
                else:
                    name = f"{name}_{method}"
                output[key] = f"{prefix}.{name}"
    return output


def _snapshot_for_rsi_method(
    source: Mapping[str, object], method: str,
) -> dict[str, object]:
    snapshot = dict(source)
    suffix = f"_{method}"
    for key, value in source.items():
        prefix, separator, name = str(key).partition(".")
        if separator and name.startswith("rsi_") and name.endswith(suffix):
            snapshot[f"{prefix}.{name[:-len(suffix)]}"] = value
    return snapshot


def _auto_rsi_rank(outcome: Mapping[str, object]) -> tuple[float, float, float, int, int]:
    pooled = outcome.get("pooled_backtest")
    market = pooled.get("market") if isinstance(pooled, Mapping) else None
    market = market if isinstance(market, Mapping) else {}
    def number(name: str) -> float:
        value = market.get(name)
        try:
            result = float(value)
        except (TypeError, ValueError):
            return float("-inf")
        return result if math.isfinite(result) else float("-inf")
    return (
        number("out_of_sample_outcome_probability_percent"),
        number("out_of_sample_average_return_percent"),
        number("out_of_sample_win_rate_percent"),
        int(market.get("out_of_sample_trade_count") or 0),
        1 if outcome.get("rsi_method") == "rakuten" else 0,
    )


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
        if (
            "conditional_median_return_percent" in summary
            and "profit_20_probability_percent" in summary
        ):
            cached.add(str(row[0]))
    return [str(code) for code in codes if str(code) not in cached]


def _codes_without_current_summary(
    database: Database,
    codes: Sequence[str],
    profile_name: str,
) -> list[str]:
    """Find profile results missing the new chronological holdout metrics."""
    if not codes:
        return []
    cached: set[str] = set()
    # Keep below SQLite's commonly configured parameter limit.
    for start in range(0, len(codes), 500):
        chunk = [str(code) for code in codes[start:start + 500]]
        placeholders = ",".join("?" for _ in chunk)
        with database.connect() as connection:
            rows = connection.execute(
                f"""SELECT code, result_json FROM analysis_snapshot
                    WHERE analysis_type='backtest' AND profile_name=?
                      AND code IN ({placeholders})
                    ORDER BY as_of_date DESC, created_at DESC""",
                [profile_name, *chunk],
            ).fetchall()
        for row in rows:
            if str(row["code"]) in cached:
                continue
            summary = json.loads(row["result_json"]).get("summary", {})
            if (
                "out_of_sample_trade_count" in summary
                and "profit_20_probability_percent" in summary
            ):
                cached.add(str(row["code"]))
    return [str(code) for code in codes if str(code) not in cached]


def _estimated_price_fields(
    reference_price: object,
    summary: Mapping[str, object],
    position_side: str,
    evaluation_mode: str = "condition_exit",
) -> dict[str, float | int | None]:
    """Convert the applicable return distribution into a reference price range."""
    try:
        reference = float(reference_price)
    except (TypeError, ValueError):
        reference = math.nan
    if not math.isfinite(reference) or reference <= 0:
        reference = None

    if evaluation_mode == "period_end":
        sample_count = int(summary.get("trade_count") or 0)
        median_days = _finite_float(summary.get("median_sessions_held"))
        returns = [
            _finite_float(summary.get("median_return_percent")),
            _finite_float(summary.get("return_p25_percent")),
            _finite_float(summary.get("return_p75_percent")),
        ]
    else:
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
