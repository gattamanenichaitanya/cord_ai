"""Bounded local neighborhood and graph-derived candidate actions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from diagnosis.actions import ActionType, CandidateAction, assign_action_ids
from diagnosis.changes import get_recent_changes
from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import SystemGraph
from diagnosis.ontology import NodeType
from diagnosis.rules import rules_for_incident

if TYPE_CHECKING:
    from diagnosis.graph import Neighbor


def get_local_neighborhood(
    graph: SystemGraph,
    current_node_id: str,
    visited: Iterable[str] = (),
) -> list[Neighbor]:
    """One-hop neighbors from stored edges. Already-visited nodes are omitted."""
    seen = set(visited)
    return [neighbor for neighbor in graph.get_neighbors(current_node_id) if neighbor.neighbor_id not in seen]


def _inspect_connected_actions(
    current_node_id: str,
    neighbors: list[Neighbor],
) -> list[CandidateAction]:
    ordered = sorted(neighbors, key=lambda item: (item.neighbor_id, item.edge_type))
    return [
        CandidateAction(
            action_id="",
            action_type=ActionType.INSPECT_CONNECTED_NODE.value,
            current_node_id=current_node_id,
            target_node_id=neighbor.neighbor_id,
            target_node_name=neighbor.neighbor_name,
            edge_type=neighbor.edge_type,
            edge_direction=neighbor.edge_direction,
            semantic_role=neighbor.semantic_role,
        )
        for neighbor in ordered
    ]


def _tool_actions(
    graph: SystemGraph,
    current_node_id: str,
    *,
    incident_id: str | None,
) -> list[CandidateAction]:
    node = graph.get_node(current_node_id)
    if node is None:
        raise KeyError(f"Unknown node: {current_node_id}")
    actions: list[CandidateAction] = []
    node_type = node["type"]
    label = node.get("label") or current_node_id

    if node_type == NodeType.PROPERTY.value and current_node_id in CANONICAL_FIELDS:
        actions.append(
            CandidateAction(
                action_id="",
                action_type=ActionType.READ_RUNTIME_VALUE.value,
                current_node_id=current_node_id,
                target_node_id=current_node_id,
                target_node_name=label,
            )
        )

    if node_type == NodeType.WORKFLOW.value and current_node_id in rules_for_incident(incident_id):
        actions.append(
            CandidateAction(
                action_id="",
                action_type=ActionType.INSPECT_RULE.value,
                current_node_id=current_node_id,
                target_node_id=current_node_id,
                target_node_name=label,
            )
        )

    if get_recent_changes(current_node_id):
        actions.append(
            CandidateAction(
                action_id="",
                action_type=ActionType.CHECK_RECENT_CHANGES.value,
                current_node_id=current_node_id,
                target_node_id=current_node_id,
                target_node_name=label,
            )
        )
    return actions


def _return_actions(graph: SystemGraph, current_node_id: str, visited: Iterable[str]) -> list[CandidateAction]:
    actions: list[CandidateAction] = []
    for node_id in visited:
        if node_id == current_node_id:
            continue
        node = graph.get_node(node_id)
        if node is None:
            continue
        actions.append(
            CandidateAction(
                action_id="",
                action_type=ActionType.RETURN_TO_CANDIDATE.value,
                current_node_id=current_node_id,
                target_node_id=node_id,
                target_node_name=node.get("label") or node_id,
            )
        )
    return actions


def _stop_actions(current_node_id: str, *, allow_root_cause: bool) -> list[CandidateAction]:
    actions: list[CandidateAction] = []
    if allow_root_cause:
        actions.append(
            CandidateAction(
                action_id="",
                action_type=ActionType.STOP_WITH_ROOT_CAUSE.value,
                current_node_id=current_node_id,
                target_node_id=current_node_id,
                target_node_name=None,
            )
        )
    actions.append(
        CandidateAction(
            action_id="",
            action_type=ActionType.STOP_NEEDS_HUMAN.value,
            current_node_id=current_node_id,
            target_node_id=None,
            target_node_name=None,
        )
    )
    return actions


def build_candidate_actions(
    graph: SystemGraph,
    current_node_id: str,
    *,
    visited: Iterable[str] = (),
    incident_id: str | None = None,
    include_stop_actions: bool = True,
    allow_root_cause_stop: bool = False,
) -> list[CandidateAction]:
    """Finite action set from real neighbors and tools. The planner may only pick an action_id."""
    if graph.get_node(current_node_id) is None:
        raise KeyError(f"Unknown node: {current_node_id}")
    visited_list = list(visited)
    neighbors = get_local_neighborhood(graph, current_node_id, visited_list)
    actions: list[CandidateAction] = []
    actions.extend(_inspect_connected_actions(current_node_id, neighbors))
    actions.extend(_tool_actions(graph, current_node_id, incident_id=incident_id))
    actions.extend(_return_actions(graph, current_node_id, visited_list))
    if include_stop_actions:
        actions.extend(_stop_actions(current_node_id, allow_root_cause=allow_root_cause_stop))
    return assign_action_ids(actions)
