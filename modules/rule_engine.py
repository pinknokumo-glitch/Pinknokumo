"""Safe declarative rule evaluator. Rules never execute Python expressions."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

OPERATORS = {
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
}

@dataclass(frozen=True)
class RuleResult:
    matched: bool
    reason: str

class RuleEngine:
    def evaluate(self, rule: Mapping[str, object], values: Mapping[str, object]) -> RuleResult:
        if "all" in rule:
            results = [self.evaluate(child, values) for child in rule["all"]]
            failed = next((result for result in results if not result.matched), None)
            return RuleResult(failed is None, "all conditions matched" if failed is None else failed.reason)
        if "any" in rule:
            results = [self.evaluate(child, values) for child in rule["any"]]
            success = next((result for result in results if result.matched), None)
            return RuleResult(success is not None, success.reason if success else "no alternative matched")
        if "not" in rule:
            result = self.evaluate(rule["not"], values)
            return RuleResult(not result.matched, f"NOT ({result.reason})")
        return self._evaluate_condition(rule, values)

    def _evaluate_condition(self, condition: Mapping[str, object], values: Mapping[str, object]) -> RuleResult:
        field, operator = condition.get("field"), condition.get("operator")
        if not isinstance(field, str) or operator not in OPERATORS:
            raise ValueError("A condition requires a valid field and operator")
        left = values.get(field)
        if "value_from" in condition:
            right = values.get(condition["value_from"])
            right_name = str(condition["value_from"])
        else:
            right, right_name = condition.get("value"), repr(condition.get("value"))
        if left is None or right is None or any(isinstance(value, float) and math.isnan(value) for value in (left, right)):
            return RuleResult(False, f"{field} has insufficient data")
        matched = OPERATORS[operator](left, right)
        return RuleResult(matched, f"{field} ({left:.3f}) {operator} {right_name} ({right:.3f})")

