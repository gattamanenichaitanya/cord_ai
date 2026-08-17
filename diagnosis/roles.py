"""Deterministic semantic_role from stored edge type + current-node perspective.

edge_direction is graph topology (incoming/outgoing).
semantic_role is causal/config meaning. They must not be collapsed into `direction`.
"""

from __future__ import annotations

from enum import Enum

from diagnosis.ontology import EdgeType

PLANNER_EDGE_DIRECTION_KEY = "edge_direction"
PLANNER_SEMANTIC_ROLE_KEY = "semantic_role"
FORBIDDEN_AMBIGUOUS_DIRECTION_KEY = "direction"


class SemanticRole(str, Enum):
    UPSTREAM_PRODUCER = "UPSTREAM_PRODUCER"
    DOWNSTREAM_CONSUMER = "DOWNSTREAM_CONSUMER"
    UPSTREAM_DEPENDENCY = "UPSTREAM_DEPENDENCY"
    DOWNSTREAM_DEPENDENT = "DOWNSTREAM_DEPENDENT"
    CONFIGURATION_PARENT = "CONFIGURATION_PARENT"
    CONFIGURATION_CHILD = "CONFIGURATION_CHILD"
    CHANGE_SOURCE = "CHANGE_SOURCE"
    RELATED_COMPONENT = "RELATED_COMPONENT"


class EdgeDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


def derive_semantic_role(edge_type: str | EdgeType, edge_direction: str | EdgeDirection) -> SemanticRole:
    """Role from (edge_type, perspective). Must not ignore edge_type."""
    et = EdgeType(edge_type) if not isinstance(edge_type, EdgeType) else edge_type
    direction = (
        EdgeDirection(edge_direction) if not isinstance(edge_direction, EdgeDirection) else edge_direction
    )

    if et is EdgeType.WRITES:
        if direction is EdgeDirection.INCOMING:
            return SemanticRole.UPSTREAM_PRODUCER
        return SemanticRole.DOWNSTREAM_DEPENDENT

    if et is EdgeType.READS:
        if direction is EdgeDirection.INCOMING:
            return SemanticRole.DOWNSTREAM_CONSUMER
        return SemanticRole.UPSTREAM_DEPENDENCY

    if et is EdgeType.DEPENDS_ON:
        if direction is EdgeDirection.OUTGOING:
            return SemanticRole.UPSTREAM_DEPENDENCY
        return SemanticRole.DOWNSTREAM_DEPENDENT

    if et is EdgeType.CONTAINS:
        if direction is EdgeDirection.OUTGOING:
            return SemanticRole.CONFIGURATION_CHILD
        return SemanticRole.CONFIGURATION_PARENT

    if et is EdgeType.MODIFIED:
        if direction is EdgeDirection.INCOMING:
            return SemanticRole.CHANGE_SOURCE
        return SemanticRole.RELATED_COMPONENT

    return SemanticRole.RELATED_COMPONENT


USER_ROLE_LABELS = {
    SemanticRole.UPSTREAM_PRODUCER.value: "producer",
    SemanticRole.DOWNSTREAM_CONSUMER.value: "consumer",
    SemanticRole.UPSTREAM_DEPENDENCY.value: "dependency",
    SemanticRole.DOWNSTREAM_DEPENDENT.value: "dependent",
    SemanticRole.CONFIGURATION_PARENT.value: "parent",
    SemanticRole.CONFIGURATION_CHILD.value: "child",
    SemanticRole.CHANGE_SOURCE.value: "recent change",
    SemanticRole.RELATED_COMPONENT.value: "related component",
}


def user_role_label(semantic_role: str | None) -> str:
    if not semantic_role:
        return ""
    return USER_ROLE_LABELS.get(semantic_role, semantic_role.replace("_", " ").lower())
