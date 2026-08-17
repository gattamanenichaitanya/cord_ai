"""Checkpoint 1: canonical fields and graph load (Acceptance Test 0)."""

from diagnosis.fields import CANONICAL_FIELDS, FORBIDDEN_ALIASES, assert_canonical_field, is_canonical_field
from diagnosis.graph import load_graph
from diagnosis.ontology import NodeType
import pytest


def test_canonical_field_set():
    expected = {
        "deal_amount",
        "discount_pct",
        "customer_tier",
        "pricing_segment",
        "approval_required",
        "deal_stage",
        "fulfillment_started",
        "sales_process_complete",
    }
    assert CANONICAL_FIELDS == expected


def test_aliases_are_not_canonical():
    for alias in ("company.tier", "company_tier", "deal.amount", "amount", "deal.stage"):
        assert not is_canonical_field(alias)
        assert alias in FORBIDDEN_ALIASES or not is_canonical_field(alias)
        with pytest.raises(ValueError):
            assert_canonical_field(alias)


def test_graph_loads_and_size():
    graph = load_graph()
    assert 40 <= graph.node_count() <= 80
    assert graph.edge_count() >= 1


def test_graph_has_all_canonical_property_nodes():
    graph = load_graph()
    for field_id in CANONICAL_FIELDS:
        node = graph.get_node(field_id)
        assert node is not None, field_id
        assert node["type"] == NodeType.PROPERTY.value


def test_graph_has_no_forbidden_alias_ids():
    graph = load_graph()
    for alias in FORBIDDEN_ALIASES:
        assert graph.get_node(alias) is None


def test_core_workflow_nodes_exist():
    graph = load_graph()
    for nid in (
        "derive_pricing_segment",
        "discount_governance",
        "deal_stage_automation",
        "legacy_discount_override",
        "fulfillment_workflow",
        "reporting_workflow",
    ):
        node = graph.get_node(nid)
        assert node is not None, nid
        assert node["type"] == NodeType.WORKFLOW.value
