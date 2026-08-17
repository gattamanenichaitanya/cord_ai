"""Deterministic workflow-rule evaluation against canonical runtime."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from diagnosis.fields import assert_canonical_field
from diagnosis.graph import DATA_DIR
from diagnosis.runtime import RuntimeState

RULES_PATH = DATA_DIR / "rules.json"

OPS = {
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    ">": lambda left, right: left is not None and left > right,
    ">=": lambda left, right: left is not None and left >= right,
    "<": lambda left, right: left is not None and left < right,
    "<=": lambda left, right: left is not None and left <= right,
}


def _eval_condition(runtime: RuntimeState, condition: dict[str, Any]) -> bool:
    field_id = condition["field"]
    assert_canonical_field(field_id)
    op = condition["op"]
    if op not in OPS:
        raise ValueError(f"Unsupported op: {op}")
    return bool(OPS[op](runtime.get(field_id), condition["value"]))


def conditions_hold(runtime: RuntimeState, conditions: list[dict[str, Any]]) -> bool:
    return all(_eval_condition(runtime, cond) for cond in conditions)


def _assignment(clause: dict[str, Any]) -> dict[str, Any]:
    field_id = clause["field"]
    assert_canonical_field(field_id)
    return {field_id: clause["value"]}


def predicted_writes(workflow: dict[str, Any], runtime: RuntimeState) -> dict[str, Any]:
    """Return field assignments this workflow would write, if it fires."""
    if workflow.get("enabled") is False:
        return {}
    rule = workflow["rule"]
    if "cases" in rule:
        for case in rule["cases"]:
            if conditions_hold(runtime, case["when"]):
                return _assignment(case["then"])
        return {}
    if "all" in rule:
        if conditions_hold(runtime, rule["all"]):
            return _assignment(rule["then"])
        if "else" in rule:
            return _assignment(rule["else"])
        return {}
    raise ValueError(f"Unsupported rule shape for {workflow.get('id')}")


def load_rules_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or RULES_PATH
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def rules_for_incident(incident_id: str | None = None, path: Path | None = None) -> dict[str, Any]:
    catalog = load_rules_catalog(path)
    merged = copy.deepcopy(catalog["healthy"])
    if incident_id:
        overlay = catalog.get("overlays", {}).get(incident_id, {})
        merged.update(copy.deepcopy(overlay))
    return merged


def get_workflow_rule(workflow_id: str, incident_id: str | None = None) -> dict[str, Any]:
    rules = rules_for_incident(incident_id)
    if workflow_id not in rules:
        raise KeyError(f"Unknown workflow rule: {workflow_id}")
    return copy.deepcopy(rules[workflow_id])
