"""Business-policy / expectation evaluation against canonical runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from diagnosis.fields import assert_canonical_field
from diagnosis.graph import DATA_DIR
from diagnosis.rules import conditions_hold
from diagnosis.runtime import RuntimeState

POLICIES_PATH = DATA_DIR / "policies.json"


class ExpectationStatus(str, Enum):
    VIOLATED = "VIOLATED"
    SATISFIED = "SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ExpectationResult:
    policy_id: str
    status: ExpectationStatus
    subject_node: str | None
    observed: dict[str, Any]
    expected: dict[str, Any]
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "status": self.status.value,
            "subject_node": self.subject_node,
            "observed": dict(self.observed),
            "expected": dict(self.expected),
            "summary": self.summary,
        }


def load_policies(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or POLICIES_PATH
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    return list(payload["policies"])


def _required_state(constraint: dict[str, Any]) -> tuple[str, Any]:
    required = constraint["required_state"]
    field_id = required["field"]
    assert_canonical_field(field_id)
    return field_id, required["value"]


def evaluate_policy(policy: dict[str, Any], runtime: RuntimeState) -> ExpectationResult:
    policy_id = policy["id"]
    if not conditions_hold(runtime, policy["applies_when"]):
        return ExpectationResult(
            policy_id=policy_id,
            status=ExpectationStatus.NOT_APPLICABLE,
            subject_node=None,
            observed={},
            expected={},
            summary=f"Policy {policy_id} does not apply.",
        )

    constraint = policy["constraint"]
    required_field, required_value = _required_state(constraint)
    observed_required = runtime.get(required_field)

    before_stage = constraint.get("before_stage")
    if before_stage:
        stage_field = before_stage["field"]
        assert_canonical_field(stage_field)
        stage_value = before_stage["value"]
        observed_stage = runtime.get(stage_field)
        if observed_stage != stage_value:
            return ExpectationResult(
                policy_id=policy_id,
                status=ExpectationStatus.SATISFIED,
                subject_node=stage_field,
                observed={stage_field: observed_stage, required_field: observed_required},
                expected={required_field: required_value},
                summary=f"Policy {policy_id} applies but {stage_field} is not {stage_value}.",
            )
        subject_node = stage_field
        observed = {stage_field: observed_stage, required_field: observed_required}
    else:
        subject_node = required_field
        observed = {required_field: observed_required}

    expected = {required_field: required_value}
    if observed_required == required_value:
        return ExpectationResult(
            policy_id=policy_id,
            status=ExpectationStatus.SATISFIED,
            subject_node=subject_node,
            observed=observed,
            expected=expected,
            summary=f"Policy {policy_id} is satisfied.",
        )

    return ExpectationResult(
        policy_id=policy_id,
        status=ExpectationStatus.VIOLATED,
        subject_node=subject_node,
        observed=observed,
        expected=expected,
        summary=policy.get("violation_summary", f"Policy {policy_id} is violated."),
    )


def evaluate_expectations(
    runtime: RuntimeState,
    policies: list[dict[str, Any]] | None = None,
) -> list[ExpectationResult]:
    loaded = policies if policies is not None else load_policies()
    return [evaluate_policy(policy, runtime) for policy in loaded]


def violations(results: list[ExpectationResult]) -> list[ExpectationResult]:
    return [result for result in results if result.status is ExpectationStatus.VIOLATED]
