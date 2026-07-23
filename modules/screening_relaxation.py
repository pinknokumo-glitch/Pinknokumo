"""Build ordered screening rules without relaxing the monthly timeframe."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy


def staged_rules(
    profile_name: str,
    base_rule: Mapping[str, object],
    relaxation_config: Mapping[str, object] | None,
) -> list[tuple[str, str, dict[str, object]]]:
    """Return the base rule followed by configured cumulative relaxation stages."""
    stages = [(profile_name, "基準条件", deepcopy(dict(base_rule)))]
    config = relaxation_config or {}
    if profile_name not in (config.get("enabled_profiles") or []):
        return stages

    for stage in config.get("stages") or []:
        if not isinstance(stage, Mapping):
            continue
        stage_id = str(stage.get("id") or len(stages))
        label = str(stage.get("label") or stage_id)
        rule = _replace_thresholds(base_rule, stage.get("thresholds") or {})
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
