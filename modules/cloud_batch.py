"""Compute user-specific cloud results once per unique screening configuration."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence

from modules.ai_comment import AnalysisCommentary
from modules.batch_backtest import BatchBacktester
from modules.cloud_preferences import ScreeningPreference, apply_preference
from modules.cloud_results import CloudResultPublisher
from modules.database import Database
from modules.repository import StockRepository
from modules.rule_engine import RuleEngine
from modules.screener import Screener
from modules.screening_options import ScreeningOptions
from modules.screening_relaxation import staged_rules


def preference_signature(preference: ScreeningPreference) -> str:
    payload = {
        "mode": preference.mode,
        "genre_id": preference.genre_id,
        "manual_logic": preference.manual_logic,
        "manual_conditions": preference.manual_conditions,
        "holding_days": preference.holding_days,
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
) -> dict[str, object]:
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
        company_names = {
            str(row["code"]): row["company_name"]
            for row in connection.execute(
                "SELECT code, company_name FROM master_stock"
            )
        }
    rule_engine = RuleEngine()
    for signature, members in groups.items():
        try:
            outcome = _compute_group(
                database, signature, members[0], options, screening_config,
                indicator_config, backtest_config, scoring_config,
                snapshots, company_names, rule_engine,
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
                    condition_summary=outcome["condition_summary"],
                )
                publisher.publish_run(
                    outcome["screening_date"], outcome["profile"],
                    members[0].holding_days, outcome["condition_summary"],
                    len(outcome["hits"]),
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
        })
    return {
        "preference_count": len(preferences),
        "group_count": len(groups),
        "published_user_count": published_users,
        "failed_group_count": len(failed_groups),
        "failed_user_count": len(failed_users),
        "failed_groups": failed_groups,
        "failed_users": failed_users,
        "groups": processed_groups,
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
) -> dict[str, object]:
    resolved, base_profile = apply_preference(
        preference, options, screening_config
    )
    base_rule = resolved["profiles"][base_profile]
    hits: list[dict[str, object]] = []
    effective_rule = base_rule
    effective_profile = f"cloud_{signature}"
    for stage_index, (_, _, stage_rule) in enumerate(
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
        effective_profile = stage_profile
        effective_rule = stage_rule
        if hits:
            break

    comments: dict[str, str] = {}
    if hits:
        BatchBacktester(
            database, indicator_config, backtest_config, scoring_config
        ).run(
            effective_profile,
            effective_rule,
            preference.holding_days,
            codes=[str(hit["code"]) for hit in hits],
        )
        with database.connect() as connection:
            screener = Screener(
                connection, indicator_config, resolved,
                candidate_codes=[str(hit["code"]) for hit in hits],
            )
            hits = screener.run(effective_profile, effective_rule)
            repository = StockRepository(connection)
            for hit in hits:
                code = str(hit["code"])
                result = repository.latest_backtest_result(code, effective_profile)
                backtest_comment = (
                    str(result["comment"])
                    if result and result.get("comment")
                    else None
                )
                comments[code] = AnalysisCommentary.integrated_comment(
                    hit, backtest_comment
                )
    with database.connect() as connection:
        screening_date = connection.execute(
            "SELECT MAX(trade_date) FROM price_daily"
        ).fetchone()[0]
    return {
        "screening_date": str(screening_date),
        "profile": effective_profile,
        "hits": hits,
        "comments": comments,
        "condition_summary": json.dumps(
            effective_rule, ensure_ascii=False, sort_keys=True
        ),
    }
