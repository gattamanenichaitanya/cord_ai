"""Checkpoint 3: neighbors + semantic_role (Acceptance Tests 6 and 9)."""

from diagnosis.graph import load_graph
from diagnosis.ontology import EdgeType
from diagnosis.roles import (
    FORBIDDEN_AMBIGUOUS_DIRECTION_KEY,
    PLANNER_EDGE_DIRECTION_KEY,
    PLANNER_SEMANTIC_ROLE_KEY,
    EdgeDirection,
    SemanticRole,
    derive_semantic_role,
)
import pytest


def test_incoming_writes_is_upstream_producer():
    graph = load_graph()
    neighbor = graph.find_neighbor("deal_stage", "deal_stage_automation", edge_type="WRITES")
    assert neighbor is not None
    assert neighbor.edge_direction == "incoming"
    assert neighbor.semantic_role == SemanticRole.UPSTREAM_PRODUCER.value


def test_incoming_reads_is_downstream_consumer():
    graph = load_graph()
    neighbor = graph.find_neighbor("deal_stage", "fulfillment_workflow", edge_type="READS")
    assert neighbor is not None
    assert neighbor.edge_direction == "incoming"
    assert neighbor.semantic_role == SemanticRole.DOWNSTREAM_CONSUMER.value


def test_semantic_role_is_not_derived_from_direction_alone():
    graph = load_graph()
    neighbors = graph.get_neighbors("deal_stage")
    incoming = [n for n in neighbors if n.edge_direction == "incoming"]
    writes = [n for n in incoming if n.edge_type == "WRITES"]
    reads = [n for n in incoming if n.edge_type == "READS"]
    assert writes and reads
    write_roles = {n.semantic_role for n in writes}
    read_roles = {n.semantic_role for n in reads}
    assert write_roles == {SemanticRole.UPSTREAM_PRODUCER.value}
    assert read_roles == {SemanticRole.DOWNSTREAM_CONSUMER.value}
    assert write_roles != read_roles


def test_same_edge_type_flips_role_with_perspective():
    incoming_writes = derive_semantic_role(EdgeType.WRITES, EdgeDirection.INCOMING)
    outgoing_writes = derive_semantic_role(EdgeType.WRITES, EdgeDirection.OUTGOING)
    incoming_reads = derive_semantic_role(EdgeType.READS, EdgeDirection.INCOMING)
    outgoing_reads = derive_semantic_role(EdgeType.READS, EdgeDirection.OUTGOING)
    assert incoming_writes is SemanticRole.UPSTREAM_PRODUCER
    assert outgoing_writes is SemanticRole.DOWNSTREAM_DEPENDENT
    assert incoming_reads is SemanticRole.DOWNSTREAM_CONSUMER
    assert outgoing_reads is SemanticRole.UPSTREAM_DEPENDENCY


def test_from_workflow_outgoing_writes_is_not_upstream_producer():
    graph = load_graph()
    neighbor = graph.find_neighbor("deal_stage_automation", "deal_stage", edge_type="WRITES")
    assert neighbor is not None
    assert neighbor.edge_direction == "outgoing"
    assert neighbor.semantic_role != SemanticRole.UPSTREAM_PRODUCER.value
    assert neighbor.semantic_role == SemanticRole.DOWNSTREAM_DEPENDENT.value


def test_deal_stage_neighborhood_includes_core_consumers():
    graph = load_graph()
    neighbors = graph.get_neighbors("deal_stage")
    by_id = {n.neighbor_id: n for n in neighbors}
    for nid in ("deal_stage_automation", "fulfillment_workflow", "reporting_workflow"):
        assert nid in by_id
        assert by_id[nid].edge_direction == "incoming"


def test_unknown_node_has_no_neighbors():
    graph = load_graph()
    with pytest.raises(KeyError):
        graph.get_neighbors("not_a_real_node")


def test_planner_facing_neighbors_use_edge_direction_and_semantic_role():
    graph = load_graph()
    for neighbor in graph.get_neighbors("deal_stage"):
        payload = neighbor.as_planner_dict()
        assert PLANNER_EDGE_DIRECTION_KEY in payload
        assert PLANNER_SEMANTIC_ROLE_KEY in payload
        assert FORBIDDEN_AMBIGUOUS_DIRECTION_KEY not in payload
        assert FORBIDDEN_AMBIGUOUS_DIRECTION_KEY not in payload.values()
        assert not hasattr(neighbor, FORBIDDEN_AMBIGUOUS_DIRECTION_KEY)
