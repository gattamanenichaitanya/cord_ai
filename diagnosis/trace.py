"""Investigation trace events. Planner-facing records never use ambiguous `direction`."""

from __future__ import annotations

from typing import Any

from diagnosis.roles import FORBIDDEN_AMBIGUOUS_DIRECTION_KEY


def _reject_ambiguous_direction(event: dict[str, Any]) -> dict[str, Any]:
    if FORBIDDEN_AMBIGUOUS_DIRECTION_KEY in event:
        raise RuntimeError("Trace must not use ambiguous direction")
    return event


def expectation_event(results: list[dict[str, Any]]) -> dict[str, Any]:
    return _reject_ambiguous_direction({"event": "EXPECTATION_VALIDATION", "results": results})


def planner_decision_event(
    *,
    current_node: str,
    validated_anomaly: dict[str, Any],
    candidate_actions: list[str],
    selected_action_id: str,
    selected_target: str | None,
    edge_type: str | None,
    edge_direction: str | None,
    semantic_role: str | None,
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    return _reject_ambiguous_direction(
        {
            "event": "PLANNER_DECISION",
            "current_node": current_node,
            "validated_anomaly": validated_anomaly,
            "candidate_actions": candidate_actions,
            "selected_action_id": selected_action_id,
            "selected_target": selected_target,
            "edge_type": edge_type,
            "edge_direction": edge_direction,
            "semantic_role": semantic_role,
            "reason": reason,
            "confidence": confidence,
        }
    )


def action_result_event(*, action_type: str, output: dict[str, Any]) -> dict[str, Any]:
    return _reject_ambiguous_direction(
        {"event": "ACTION_RESULT", "action_type": action_type, "output": output}
    )


def stop_event(
    *,
    status: str,
    root_cause_node: str | None,
    reason: str,
    recommendation: str | None = None,
) -> dict[str, Any]:
    payload = {
        "event": "STOP",
        "status": status,
        "root_cause_node": root_cause_node,
        "reason": reason,
    }
    if recommendation:
        payload["recommendation"] = recommendation
    return _reject_ambiguous_direction(payload)
