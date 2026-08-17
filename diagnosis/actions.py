"""Planner-facing candidate action types. No ambiguous `direction` field."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from diagnosis.roles import (
    FORBIDDEN_AMBIGUOUS_DIRECTION_KEY,
    PLANNER_EDGE_DIRECTION_KEY,
    PLANNER_SEMANTIC_ROLE_KEY,
)


class ActionType(str, Enum):
    INSPECT_CONNECTED_NODE = "INSPECT_CONNECTED_NODE"
    READ_RUNTIME_VALUE = "READ_RUNTIME_VALUE"
    INSPECT_RULE = "INSPECT_RULE"
    CHECK_RECENT_CHANGES = "CHECK_RECENT_CHANGES"
    RETURN_TO_CANDIDATE = "RETURN_TO_CANDIDATE"
    STOP_WITH_ROOT_CAUSE = "STOP_WITH_ROOT_CAUSE"
    STOP_NEEDS_HUMAN = "STOP_NEEDS_HUMAN"


class InvalidActionError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    action_type: str
    current_node_id: str
    target_node_id: str | None = None
    target_node_name: str | None = None
    edge_type: str | None = None
    edge_direction: str | None = None
    semantic_role: str | None = None

    def as_planner_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target_node_id": self.target_node_id,
            "target_node_name": self.target_node_name,
        }
        if self.edge_type is not None:
            payload["edge_type"] = self.edge_type
        if self.edge_direction is not None:
            payload[PLANNER_EDGE_DIRECTION_KEY] = self.edge_direction
        if self.semantic_role is not None:
            payload[PLANNER_SEMANTIC_ROLE_KEY] = self.semantic_role
        if FORBIDDEN_AMBIGUOUS_DIRECTION_KEY in payload:
            raise RuntimeError("Candidate actions must not expose ambiguous direction")
        return payload


def assign_action_ids(actions: list[CandidateAction]) -> list[CandidateAction]:
    numbered: list[CandidateAction] = []
    for index, action in enumerate(actions, start=1):
        numbered.append(
            CandidateAction(
                action_id=f"A{index}",
                action_type=action.action_type,
                current_node_id=action.current_node_id,
                target_node_id=action.target_node_id,
                target_node_name=action.target_node_name,
                edge_type=action.edge_type,
                edge_direction=action.edge_direction,
                semantic_role=action.semantic_role,
            )
        )
    return numbered


def validate_selected_action(
    candidates: list[CandidateAction],
    selected_action_id: str,
) -> CandidateAction:
    by_id = {action.action_id: action for action in candidates}
    if selected_action_id not in by_id:
        raise InvalidActionError(
            f"Selected action_id {selected_action_id!r} is not in the allowed candidate set"
        )
    return by_id[selected_action_id]
