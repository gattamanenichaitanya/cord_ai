"""Load and query the configuration system graph."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diagnosis.fields import CANONICAL_FIELDS, FORBIDDEN_ALIASES
from diagnosis.ontology import EdgeType, NodeType
from diagnosis.roles import (
    PLANNER_EDGE_DIRECTION_KEY,
    PLANNER_SEMANTIC_ROLE_KEY,
    EdgeDirection,
    derive_semantic_role,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
GRAPH_PATH = DATA_DIR / "system_graph.json"


@dataclass(frozen=True)
class Neighbor:
    neighbor_id: str
    neighbor_type: str
    neighbor_name: str
    edge_type: str
    edge_direction: str
    semantic_role: str

    def as_planner_dict(self) -> dict[str, str]:
        """Planner-facing fields. Never includes ambiguous `direction`."""
        return {
            "neighbor_id": self.neighbor_id,
            "neighbor_type": self.neighbor_type,
            "neighbor_name": self.neighbor_name,
            "edge_type": self.edge_type,
            PLANNER_EDGE_DIRECTION_KEY: self.edge_direction,
            PLANNER_SEMANTIC_ROLE_KEY: self.semantic_role,
        }


class SystemGraph:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.nodes: dict[str, dict[str, Any]] = {n["id"]: dict(n) for n in payload["nodes"]}
        self.edges: list[dict[str, str]] = [dict(e) for e in payload["edges"]]
        self._validate()

    def _validate(self) -> None:
        for node_id, node in self.nodes.items():
            try:
                NodeType(node["type"])
            except ValueError as exc:
                allowed = ", ".join(t.value for t in NodeType)
                raise ValueError(
                    f"Unknown node type {node['type']!r} on {node_id}; expected one of: {allowed}"
                ) from exc
            if node_id in FORBIDDEN_ALIASES:
                raise ValueError(f"Forbidden alias used as node id: {node_id}")
        for field_id in CANONICAL_FIELDS:
            node = self.nodes.get(field_id)
            if node is None:
                raise ValueError(f"Canonical PROPERTY node missing: {field_id}")
            if node["type"] != NodeType.PROPERTY.value:
                raise ValueError(f"Canonical field {field_id} must be type PROPERTY")
        for edge in self.edges:
            if edge["from"] not in self.nodes:
                raise ValueError(f"Edge from unknown node: {edge['from']}")
            if edge["to"] not in self.nodes:
                raise ValueError(f"Edge to unknown node: {edge['to']}")
            EdgeType(edge["type"])

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        node = self.nodes.get(node_id)
        return dict(node) if node else None

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def property_node_ids(self) -> set[str]:
        return {nid for nid, n in self.nodes.items() if n["type"] == NodeType.PROPERTY.value}

    def get_neighbors(self, node_id: str) -> list[Neighbor]:
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node: {node_id}")
        neighbors: list[Neighbor] = []
        for edge in self.edges:
            if edge["to"] == node_id:
                direction = EdgeDirection.INCOMING
                other_id = edge["from"]
            elif edge["from"] == node_id:
                direction = EdgeDirection.OUTGOING
                other_id = edge["to"]
            else:
                continue
            other = self.nodes[other_id]
            role = derive_semantic_role(edge["type"], direction)
            neighbors.append(
                Neighbor(
                    neighbor_id=other_id,
                    neighbor_type=other["type"],
                    neighbor_name=other.get("label") or other_id,
                    edge_type=edge["type"],
                    edge_direction=direction.value,
                    semantic_role=role.value,
                )
            )
        return neighbors

    def find_neighbor(
        self,
        node_id: str,
        neighbor_id: str,
        edge_type: str | None = None,
    ) -> Neighbor | None:
        matches = [
            n
            for n in self.get_neighbors(node_id)
            if n.neighbor_id == neighbor_id and (edge_type is None or n.edge_type == edge_type)
        ]
        return matches[0] if matches else None


def load_graph(path: Path | None = None) -> SystemGraph:
    target = path or GRAPH_PATH
    with open(target, encoding="utf-8") as f:
        return SystemGraph(json.load(f))
