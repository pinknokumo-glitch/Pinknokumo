"""Validation for declarative screening profiles before they are used."""
from __future__ import annotations

from collections.abc import Mapping

from modules.rule_engine import OPERATORS

ALLOWED_PREFIXES = ("daily.", "weekly.", "monthly.", "fundamental.")


class ConfigValidator:
    def validate_screening(self, config: Mapping[str, object]) -> list[str]:
        errors: list[str] = []
        profiles = config.get("profiles")
        if not isinstance(profiles, Mapping) or not profiles:
            return ["profiles must be a non-empty mapping"]
        active = config.get("active_profile")
        if active not in profiles:
            errors.append("active_profile does not match a profile")
        for name, rule in profiles.items():
            if not isinstance(rule, Mapping):
                errors.append(f"profiles.{name} must be a mapping")
                continue
            errors.extend(self._validate_rule(rule, f"profiles.{name}"))
        return errors

    def _validate_rule(self, rule: Mapping[str, object], path: str) -> list[str]:
        if "all" in rule or "any" in rule:
            key = "all" if "all" in rule else "any"
            children = rule[key]
            if not isinstance(children, list) or not children:
                return [f"{path}.{key} must be a non-empty list"]
            errors: list[str] = []
            for index, child in enumerate(children):
                if not isinstance(child, Mapping):
                    errors.append(f"{path}.{key}[{index}] must be a mapping")
                else:
                    errors.extend(self._validate_rule(child, f"{path}.{key}[{index}]"))
            return errors
        if "not" in rule:
            child = rule["not"]
            return self._validate_rule(child, f"{path}.not") if isinstance(child, Mapping) else [f"{path}.not must be a mapping"]
        field, operator = rule.get("field"), rule.get("operator")
        errors = []
        if not isinstance(field, str) or not field.startswith(ALLOWED_PREFIXES):
            errors.append(f"{path}.field has an unsupported prefix")
        if operator not in OPERATORS:
            errors.append(f"{path}.operator is invalid")
        has_value, has_value_from = "value" in rule, "value_from" in rule
        if has_value == has_value_from:
            errors.append(f"{path} requires exactly one of value or value_from")
        if has_value_from and (not isinstance(rule["value_from"], str) or not rule["value_from"].startswith(ALLOWED_PREFIXES)):
            errors.append(f"{path}.value_from has an unsupported prefix")
        return errors
