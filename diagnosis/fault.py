"""Deterministic workflow-fault assessment from rule + runtime + discrepancy.

Does not map incident ids to root causes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import SystemGraph
from diagnosis.ontology import EdgeType, NodeType
from diagnosis.rules import predicted_writes
from diagnosis.runtime import RuntimeState


@dataclass(frozen=True)
class FaultEvidence:
    node_id: str
    kind: str
    summary: str
    predicted: dict[str, Any]
    observed: dict[str, Any]


def _adjacent_fields(graph: SystemGraph, workflow_id: str, edge_type: str) -> list[str]:
    fields: list[str] = []
    for neighbor in graph.get_neighbors(workflow_id):
        if neighbor.edge_type == edge_type and neighbor.edge_direction == "outgoing":
            if neighbor.neighbor_id in CANONICAL_FIELDS:
                fields.append(neighbor.neighbor_id)
    return fields


def assess_workflow_fault(
    graph: SystemGraph,
    workflow_id: str,
    workflow: dict[str, Any],
    runtime: RuntimeState,
    discrepancy_observed: dict[str, Any],
    discrepancy_expected: dict[str, Any],
) -> FaultEvidence | None:
    node = graph.get_node(workflow_id)
    if node is None or node["type"] != NodeType.WORKFLOW.value:
        return None

    write_fields = _adjacent_fields(graph, workflow_id, EdgeType.WRITES.value)
    read_fields = _adjacent_fields(graph, workflow_id, EdgeType.READS.value)
    inputs_complete = all(runtime.get(field) is not None for field in read_fields) if read_fields else True

    if workflow.get("enabled") is False:
        enabled = dict(workflow)
        enabled["enabled"] = True
        would_write = predicted_writes(enabled, runtime)
        for field, value in would_write.items():
            if field in discrepancy_expected and runtime.get(field) != discrepancy_expected[field]:
                return FaultEvidence(
                    node_id=workflow_id,
                    kind="disabled",
                    summary=f"{workflow_id} is disabled; enabling it would write {field}={value}.",
                    predicted=would_write,
                    observed={field: runtime.get(field) for field in write_fields},
                )

    predicted = predicted_writes(workflow, runtime)

    for field in write_fields:
        if field not in predicted and runtime.get(field) is None:
            if any(runtime.get(src) is not None for src in read_fields):
                return FaultEvidence(
                    node_id=workflow_id,
                    kind="missing_write",
                    summary=f"{workflow_id} did not write {field} even though its inputs are populated.",
                    predicted=predicted,
                    observed={field: None},
                )

    if not inputs_complete:
        return None

    for field, value in predicted.items():
        if field in discrepancy_expected and value != discrepancy_expected[field]:
            if runtime.get(field) == value:
                return FaultEvidence(
                    node_id=workflow_id,
                    kind="incorrect_write",
                    summary=(
                        f"{workflow_id} wrote {field}={value} from complete inputs; "
                        f"expected {discrepancy_expected[field]}."
                    ),
                    predicted=predicted,
                    observed={field: runtime.get(field)},
                )
    return None
