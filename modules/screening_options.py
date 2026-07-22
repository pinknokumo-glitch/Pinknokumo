"""Safe auto-genre catalog and bounded manual screening rule builder."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from modules.config_validation import ConfigValidator

MANUAL_OPERATORS = {"<=", ">="}


class ScreeningOptions:
    def __init__(self, options_config: Mapping[str, object], screening_config: Mapping[str, object]) -> None:
        self.options = options_config["screening_options"]
        self.screening = screening_config

    def catalog(self) -> dict[str, object]:
        profiles = self.screening["profiles"]
        genres = []
        for raw in self.options["genres"]:
            item = dict(raw)
            item["available"] = item.get("profile") in profiles
            item.setdefault("evidence_status", "baseline")
            genres.append(item)
        return {
            "modes": [
                {"id": "auto", "label": "オート", "description": "ジャンルを選んで自動判定します。"},
                {"id": "manual", "label": "マニュアル", "description": "指標と基準値を自分で設定します。"},
            ],
            "genres": genres,
            "manual_fields": [dict(item) for item in self.options["manual_fields"]],
        }

    def manual_rule(self, conditions: Sequence[Mapping[str, object]], logic: str = "all") -> dict[str, object]:
        if logic not in {"all", "any"}:
            raise ValueError("logic must be all or any")
        if not conditions or len(conditions) > 8:
            raise ValueError("manual conditions must contain 1 to 8 items")
        allowed = {str(item["field"]): item for item in self.options["manual_fields"]}
        rules = []
        for condition in conditions:
            field = str(condition.get("field") or "")
            operator = str(condition.get("operator") or "")
            spec = allowed.get(field)
            if spec is None:
                raise ValueError(f"manual field is not allowed: {field}")
            if operator not in MANUAL_OPERATORS:
                raise ValueError(f"manual operator is not allowed: {operator}")
            try:
                value = float(condition["value"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"manual value must be numeric: {field}") from error
            if not float(spec["min"]) <= value <= float(spec["max"]):
                raise ValueError(f"manual value is outside the allowed range: {field}")
            rules.append({"field": field, "operator": operator, "value": value})
        rule = {logic: rules}
        errors = ConfigValidator()._validate_rule(rule, "manual")
        if errors:
            raise ValueError("; ".join(errors))
        return rule
