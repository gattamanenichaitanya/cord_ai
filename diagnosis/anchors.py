"""Rank graph nodes as a starting region from ticket clues. Not an RCA guess."""

from __future__ import annotations

from dataclasses import dataclass

from diagnosis.graph import SystemGraph
from diagnosis.ontology import NodeType
from diagnosis.parser import TicketParse
from diagnosis.roles import SemanticRole

_TYPE_WEIGHT = {
    NodeType.PROPERTY.value: 0.45,
    NodeType.PIPELINE_STAGE.value: 0.3,
    NodeType.WORKFLOW.value: 0.22,
    NodeType.TEAM.value: 0.18,
    NodeType.WORKFLOW_BRANCH.value: 0.12,
    NodeType.CHANGE.value: 0.1,
}


@dataclass(frozen=True)
class Anchor:
    node_id: str
    score: float

    def as_dict(self) -> dict[str, float | str]:
        return {"node_id": self.node_id, "score": round(self.score, 2)}


def _node_text(node: dict) -> str:
    return " ".join(
        str(part)
        for part in (node.get("id"), node.get("label"), node.get("description"))
        if part
    ).lower()


def retrieve_anchors(
    graph: SystemGraph,
    parsed: TicketParse,
    *,
    top_k: int = 8,
) -> list[Anchor]:
    scores: dict[str, float] = {}

    def bump(node_id: str, amount: float) -> None:
        if graph.get_node(node_id) is None:
            return
        scores[node_id] = scores.get(node_id, 0.0) + amount

    for claim in parsed.observed_claims:
        bump(claim.subject, 1.0)
    for field_id in parsed.mentioned_values:
        bump(field_id, 0.85)

    for concept in parsed.mentioned_concepts:
        concept_l = concept.lower()
        tokens = [token for token in concept_l.replace("_", " ").split() if len(token) > 2]
        for node_id, node in graph.nodes.items():
            text = _node_text(node)
            if concept_l in text or (tokens and all(token in text for token in tokens)):
                bump(node_id, _TYPE_WEIGHT.get(node["type"], 0.1))

    property_anchors = [
        node_id
        for node_id, score in scores.items()
        if score >= 0.8 and (graph.get_node(node_id) or {}).get("type") == NodeType.PROPERTY.value
    ]
    for property_id in property_anchors:
        for neighbor in graph.get_neighbors(property_id):
            if neighbor.semantic_role == SemanticRole.UPSTREAM_PRODUCER.value:
                bump(neighbor.neighbor_id, min(0.85, scores[property_id] * 0.85))

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [Anchor(node_id=node_id, score=min(score, 1.0)) for node_id, score in ranked[:top_k]]
