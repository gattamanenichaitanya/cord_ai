"""Checkpoint 6 + acceptance Tests 1–5, 10–16. Planner is Claude."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from diagnosis.actions import ActionType, InvalidActionError, validate_selected_action
from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import load_graph
from diagnosis.loop import diagnose
from diagnosis.neighborhood import build_candidate_actions
from diagnosis.planner import ClaudePlanner
from diagnosis.roles import FORBIDDEN_AMBIGUOUS_DIRECTION_KEY
from diagnosis.runtime import get_runtime

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def claude_planner():
    return ClaudePlanner()


@pytest.fixture(scope="module")
def result_4821(claude_planner):
    return diagnose("INC-1042", planner=claude_planner)


def test_0_canonical_fields():
    assert CANONICAL_FIELDS == {
        "deal_amount",
        "discount_pct",
        "customer_tier",
        "pricing_segment",
        "approval_required",
        "deal_stage",
        "fulfillment_started",
        "sales_process_complete",
    }


@pytest.mark.integration
def test_1_primary_rca(result_4821):
    result = result_4821
    assert result.status == "diagnosed"
    assert result.root_cause_node == "derive_pricing_segment"


@pytest.mark.integration
def test_2_runtime_mutation_invalidates_derive_rca(claude_planner):
    original = get_runtime("DEAL-4821")
    mutated = replace(original, values={**original.values, "pricing_segment": "Enterprise"})
    result = diagnose(
        "INC-1042",
        runtime=mutated,
        rules_incident_id="",
        planner=claude_planner,
    )
    assert result.root_cause_node != "derive_pricing_segment"


@pytest.mark.integration
def test_3_same_symptom_discount_governance(claude_planner):
    result = diagnose("INC-1188", planner=claude_planner)
    assert result.status == "diagnosed"
    assert result.root_cause_node == "discount_governance"


@pytest.mark.integration
def test_4_legacy_override(claude_planner):
    result = diagnose("INC-2201", planner=claude_planner)
    assert result.status == "diagnosed"
    assert result.root_cause_node == "legacy_discount_override"


@pytest.mark.integration
def test_5_and_10_same_neighborhood_different_planner_choice(claude_planner):
    graph = load_graph()
    runtime_a = get_runtime("DEAL-4821")
    runtime_d = get_runtime("DEAL-5101")
    candidates = build_candidate_actions(graph, "deal_stage", include_stop_actions=False)
    inspect = [a for a in candidates if a.action_type == ActionType.INSPECT_CONNECTED_NODE.value]
    by_target = {a.target_node_id: a for a in inspect}
    assert by_target["deal_stage_automation"].edge_direction == "incoming"
    assert by_target["deal_stage_automation"].semantic_role == "UPSTREAM_PRODUCER"
    assert by_target["fulfillment_workflow"].edge_direction == "incoming"
    assert by_target["fulfillment_workflow"].semantic_role == "DOWNSTREAM_CONSUMER"

    action_a, _choice_a = claude_planner.choose_validated(
        ticket_text=get_incident_text("INC-1042"),
        discrepancy={
            "subject_node": "deal_stage",
            "summary": "Contract Sent occurred before required Finance approval.",
            "observed": {"deal_stage": "Contract Sent", "approval_required": False},
            "expected": {"approval_required": True},
        },
        current_node={"id": "deal_stage", "type": "PROPERTY", "runtime_value": runtime_a.get("deal_stage")},
        evidence=[],
        faults=[],
        candidates=inspect,
    )
    action_d, _choice_d = claude_planner.choose_validated(
        ticket_text=get_incident_text("INC-3310"),
        discrepancy={
            "subject_node": "fulfillment_started",
            "summary": "Deal reached Contract Sent but fulfillment never started.",
            "observed": {"fulfillment_started": False},
            "expected": {"fulfillment_started": True},
        },
        current_node={"id": "deal_stage", "type": "PROPERTY", "runtime_value": runtime_d.get("deal_stage")},
        evidence=[],
        faults=[],
        candidates=inspect,
    )
    assert action_a.target_node_id == "deal_stage_automation"
    assert action_d.target_node_id == "fulfillment_workflow"
    assert action_a.target_node_id != action_d.target_node_id


def get_incident_text(incident_id: str) -> str:
    from diagnosis.incidents import get_incident

    return get_incident(incident_id).text


@pytest.mark.integration
def test_7_planner_cannot_invent_action(result_4821):
    graph = load_graph()
    candidates = build_candidate_actions(graph, "deal_stage", include_stop_actions=False)
    with pytest.raises(InvalidActionError):
        validate_selected_action(candidates, "not_a_real_action")
    for event in result_4821.trace:
        if event.get("event") != "PLANNER_DECISION":
            continue
        assert event["selected_action_id"] in event["candidate_actions"]


@pytest.mark.integration
def test_8_inspect_actions_in_trace_are_graph_derived(result_4821):
    graph = load_graph()
    result = result_4821
    decisions = [e for e in result.trace if e.get("event") == "PLANNER_DECISION"]
    assert decisions
    for event in decisions:
        if not event.get("edge_type"):
            continue
        neighbor = graph.find_neighbor(
            event["current_node"],
            event["selected_target"],
            event["edge_type"],
        )
        if neighbor is None:
            continue
        assert neighbor.edge_direction == event["edge_direction"]
        assert neighbor.semantic_role == event["semantic_role"]


def test_9_trace_and_actions_omit_direction():
    graph = load_graph()
    for action in build_candidate_actions(graph, "deal_stage"):
        assert FORBIDDEN_AMBIGUOUS_DIRECTION_KEY not in action.as_planner_dict()


@pytest.mark.integration
def test_11_visited_budget_and_same_rca(result_4821):
    result = result_4821
    assert result.root_cause_node == "derive_pricing_segment"
    assert len(result.visited_nodes) <= 30


@pytest.mark.integration
def test_12_paraphrase_preserves_rca(claude_planner):
    text = "The $250,000 Enterprise opportunity went to Contract Sent with no Finance approval at 22 percent discount."
    result = diagnose("INC-1042", ticket_text=text, planner=claude_planner)
    assert result.root_cause_node == "derive_pricing_segment"


def test_13_no_anomaly_does_not_traverse():
    result = diagnose("INC-4401", max_planner_calls=0)
    assert result.status == "no_anomaly"
    assert result.root_cause_node is None
    assert result.visited_nodes == []
    assert not any(e.get("event") == "PLANNER_DECISION" for e in result.trace)


def test_14_insufficient_evidence_needs_human():
    result = diagnose("INC-1042", max_hops=0, max_planner_calls=0)
    assert result.status == "needs_human"
    assert result.root_cause_node is None


@pytest.mark.integration
def test_15_trace_integrity(result_4821):
    result = result_4821
    decisions = [e for e in result.trace if e.get("event") == "PLANNER_DECISION"]
    results = [e for e in result.trace if e.get("event") == "ACTION_RESULT"]
    assert decisions
    assert len(results) == len(decisions)
    for event in decisions:
        assert event["current_node"]
        assert event["validated_anomaly"]
        assert event["candidate_actions"]
        assert event["selected_action_id"]
        assert "reason" in event
        assert FORBIDDEN_AMBIGUOUS_DIRECTION_KEY not in event
        if event.get("edge_type"):
            assert "edge_direction" in event
            assert "semantic_role" in event


def test_16_no_forbidden_diagnosis_maps():
    banned_snippets = (
        'if incident_id == "INC-1042"',
        "incident_id -> root_cause",
        'EDGE_ORDER = ["WRITES"',
        'if current_node == "deal_stage":\n    next_node',
    )
    for path in list((REPO / "diagnosis").rglob("*.py")) + list((REPO / "dashboard" / "diagnose").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for snippet in banned_snippets:
            assert snippet not in text, f"{path} contains {snippet!r}"
    loop_src = (REPO / "diagnosis" / "loop.py").read_text(encoding="utf-8")
    assert 'root_cause_node == "derive_pricing_segment"' not in loop_src
    assert '"INC-1042": "derive_pricing_segment"' not in loop_src
