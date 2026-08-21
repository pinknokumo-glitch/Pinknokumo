"""Build ordered screening rules without relaxing the monthly timeframe."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy

BOUNDED_OSCILLATOR_PREFIXES = ("rsi_", "stoch_k", "stoch_d")
ZERO_CENTERED_OSCILLATOR_PREFIXES = ("macd",)


def staged_rules(
    profile_name: str,
    base_rule: Mapping[str, object],
    relaxation_config: Mapping[str, object] | None,
) -> list[tuple[str, str, dict[str, object]]]:
    """Return the base rule followed by configured cumulative relaxation stages."""
    stages = [(profile_name, "基準条件", deepcopy(dict(base_rule)))]
    config = relaxation_config or {}
    enabled_profiles = config.get("enabled_profiles") or []
    if profile_name not in enabled_profiles and profile_name != "cloud_manual":
        return stages

    for stage in config.get("stages") or []:
        if not isinstance(stage, Mapping):
            continue
        stage_id = str(stage.get("id") or len(stages))
        label = str(stage.get("label") or stage_id)
        rule = _replace_thresholds(base_rule, stage.get("thresholds") or {})
        _relax_timeframes(rule, stage.get("timeframe_relaxation") or {})
        stages.append((f"{profile_name}_{stage_id}_relaxed", label, rule))
    return stages


def _replace_thresholds(
    rule: Mapping[str, object], thresholds: Mapping[str, object]
) -> dict[str, object]:
    result = deepcopy(dict(rule))
    _replace_in_node(result, thresholds)
    return result


def _replace_in_node(node: object, thresholds: Mapping[str, object]) -> None:
    if not isinstance(node, dict):
        return
    field = node.get("field")
    if field in thresholds and "value" in node:
        node["value"] = float(thresholds[str(field)])
    for key in ("all", "any"):
        children = node.get(key)
        if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
            for child in children:
                _replace_in_node(child, thresholds)


def _relax_timeframes(
    rule: dict[str, object], policies: Mapping[str, object]
) -> None:
    _relax_in_node(rule, policies)


def _relax_in_node(node: object, policies: Mapping[str, object]) -> None:
    if not isinstance(node, dict):
        return
    field = str(node.get("field") or "")
    operator = str(node.get("operator") or "")
    if "." in field and operator in {"<=", ">="} and "value" in node:
        timeframe, indicator = field.split(".", 1)
        policy = policies.get(timeframe)
        if isinstance(policy, Mapping):
            node["value"] = _relaxed_value(
                indicator, operator, float(node["value"]), policy
            )
    for key in ("all", "any"):
        children = node.get(key)
        if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
            for child in children:
                _relax_in_node(child, policies)


def _relaxed_value(
    indicator: str,
    operator: str,
    value: float,
    policy: Mapping[str, object],
) -> float:
    if indicator.startswith(BOUNDED_OSCILLATOR_PREFIXES):
        if operator == "<=" and policy.get("oscillator_le") is not None:
            return max(value, float(policy["oscillator_le"]))
        if operator == ">=" and policy.get("oscillator_ge") is not None:
            return min(value, float(policy["oscillator_ge"]))
    if (
        indicator.startswith(ZERO_CENTERED_OSCILLATOR_PREFIXES)
        and bool(policy.get("zero_centered"))
    ):
        if operator == "<=" and value < 0:
            return 0.0
        if operator == ">=" and value > 0:
            return 0.0
    return value
