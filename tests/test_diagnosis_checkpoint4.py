"""Checkpoint 4: graph-derived candidate actions (Acceptance Tests 7–8, 9 on actions)."""

from diagnosis.actions import ActionType, InvalidActionError, validate_selected_action
from diagnosis.graph import load_graph
from diagnosis.neighborhood import build_candidate_actions, get_local_neighborhood
from diagnosis.roles import (
    FORBIDDEN_AMBIGUOUS_DIRECTION_KEY,
    PLANNER_EDGE_DIRECTION_KEY,
    PLANNER_SEMANTIC_ROLE_KEY,
    derive_semantic_role,
)
import pytest


def _inspect_actions(current_node_id: str, **kwargs):
    graph = load_graph()
    actions = build_candidate_actions(graph, current_node_id, **kwargs)
    inspect = [a for a in actions if a.action_type == ActionType.INSPECT_CONNECTED_NODE.value]
    return graph, actions, inspect


def test_inspect_connected_actions_are_graph_derived():
    graph, _, inspect = _inspect_actions("deal_stage")
    assert inspect
    current = graph.get_node("deal_stage")
    assert current is not None
    for action in inspect:
        assert graph.get_node(action.current_node_id) is not None
        assert action.target_node_id is not None
        assert graph.get_node(action.target_node_id) is not None
        neighbor = graph.find_neighbor(
            action.current_node_id,
            action.target_node_id,
            edge_type=action.edge_type,
        )
        assert neighbor is not None
        assert neighbor.edge_type == action.edge_type
        assert neighbor.edge_direction == action.edge_direction
        assert neighbor.semantic_role == action.semantic_role
        assert action.semantic_role == derive_semantic_role(
            action.edge_type, action.edge_direction
        ).value


def test_deal_stage_inspect_targets_include_core_neighbors():
    _, _, inspect = _inspect_actions("deal_stage")
    targets = {a.target_node_id for a in inspect}
    assert "deal_stage_automation" in targets
    assert "fulfillment_workflow" in targets
    assert "reporting_workflow" in targets
    by_target = {a.target_node_id: a for a in inspect}
    automation = by_target["deal_stage_automation"]
    assert automation.edge_type == "WRITES"
    assert automation.edge_direction == "incoming"
    assert automation.semantic_role == "UPSTREAM_PRODUCER"
    fulfillment = by_target["fulfillment_workflow"]
    assert fulfillment.edge_type == "READS"
    assert fulfillment.edge_direction == "incoming"
    assert fulfillment.semantic_role == "DOWNSTREAM_CONSUMER"


def test_planner_cannot_invent_action_id():
    _, actions, _ = _inspect_actions("deal_stage")
    allowed = {a.action_id for a in actions}
    assert "A1" in allowed
    with pytest.raises(InvalidActionError):
        validate_selected_action(actions, "A999")
    with pytest.raises(InvalidActionError):
        validate_selected_action(actions, "invented_node")


def test_planner_cannot_select_unlisted_target():
    _, actions, inspect = _inspect_actions("deal_stage")
    targets = {a.target_node_id for a in inspect}
    assert "made_up_workflow" not in targets
    chosen = validate_selected_action(actions, inspect[0].action_id)
    assert chosen.target_node_id in targets
    assert chosen in actions


def test_candidate_actions_omit_ambiguous_direction():
    _, actions, inspect = _inspect_actions("deal_stage")
    assert inspect
    for action in actions:
        payload = action.as_planner_dict()
        assert FORBIDDEN_AMBIGUOUS_DIRECTION_KEY not in payload
        assert not hasattr(action, FORBIDDEN_AMBIGUOUS_DIRECTION_KEY)
        if action.action_type == ActionType.INSPECT_CONNECTED_NODE.value:
            assert PLANNER_EDGE_DIRECTION_KEY in payload
            assert PLANNER_SEMANTIC_ROLE_KEY in payload


def test_same_node_same_inspect_set_regardless_of_incident_overlay():
    _, _, inspect_a = _inspect_actions("deal_stage", incident_id="INC-1042")
    _, _, inspect_d = _inspect_actions("deal_stage", incident_id="INC-3310")
    keys_a = {(a.target_node_id, a.edge_type, a.edge_direction, a.semantic_role) for a in inspect_a}
    keys_d = {(a.target_node_id, a.edge_type, a.edge_direction, a.semantic_role) for a in inspect_d}
    assert keys_a == keys_d


def test_visited_neighbors_are_not_reoffered_as_inspect():
    graph = load_graph()
    neighbors = get_local_neighborhood(
        graph, "deal_stage", visited=["deal_stage_automation"]
    )
    assert all(n.neighbor_id != "deal_stage_automation" for n in neighbors)
    _, _, inspect = _inspect_actions("deal_stage", visited=["deal_stage_automation"])
    assert all(a.target_node_id != "deal_stage_automation" for a in inspect)


def test_property_offers_runtime_read_workflow_offers_rule_inspect():
    _, property_actions, _ = _inspect_actions("deal_stage")
    types = {a.action_type for a in property_actions}
    assert ActionType.READ_RUNTIME_VALUE.value in types
    _, workflow_actions, _ = _inspect_actions("derive_pricing_segment")
    types = {a.action_type for a in workflow_actions}
    assert ActionType.INSPECT_RULE.value in types
    assert ActionType.CHECK_RECENT_CHANGES.value in types
