"""Friendly labels for Diagnose UI. Presentation only — graph ids stay canonical."""

from __future__ import annotations

import html

from diagnosis.graph import SystemGraph
from diagnosis.prose import plain_user_prose
from diagnosis.roles import SemanticRole

ROLE_LABELS = {
    SemanticRole.UPSTREAM_PRODUCER.value: "Producer",
    SemanticRole.DOWNSTREAM_CONSUMER.value: "Consumer",
    SemanticRole.UPSTREAM_DEPENDENCY.value: "Uses",
    SemanticRole.DOWNSTREAM_DEPENDENT.value: "Used by",
    SemanticRole.CONFIGURATION_PARENT.value: "Contains",
    SemanticRole.CONFIGURATION_CHILD.value: "Part of",
    SemanticRole.CHANGE_SOURCE.value: "Changed by",
    SemanticRole.RELATED_COMPONENT.value: "Related",
}


def node_label(graph: SystemGraph, node_id: str | None) -> str:
    if not node_id:
        return ""
    node = graph.get_node(node_id)
    if node and node.get("label"):
        return str(node["label"])
    return node_id.replace("_", " ").title()


def role_label(semantic_role: str | None) -> str:
    if not semantic_role:
        return ""
    return ROLE_LABELS.get(semantic_role, semantic_role.replace("_", " ").title())


def edge_verb(edge_type: str | None) -> str:
    if not edge_type:
        return "connected to"
    return edge_type.replace("_", " ").title()


def prose_alert_html(text: str) -> str:
    body = html.escape(plain_user_prose(text))
    return f'<div class="diagnose-prose-alert">{body}</div>'
