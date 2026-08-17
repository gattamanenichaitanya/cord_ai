"""Checkpoint 2: locked chat evidence packs. No Claude."""

from __future__ import annotations

import json

from diagnosis.chat_context import FORBIDDEN_CHAT_KEYS, build_chat_evidence
from diagnosis.graph import load_graph
from diagnosis.incidents import get_incident
from diagnosis.loop import DiagnosisResult


def _walk_keys(payload) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        keys.update(payload)
        for value in payload.values():
            keys |= _walk_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            keys |= _walk_keys(item)
    return keys


def _inc1042_result() -> DiagnosisResult:
    return DiagnosisResult(
        status="diagnosed",
        root_cause_node="derive_pricing_segment",
        confidence=0.9,
        reason="derive_pricing_segment did not write pricing_segment even though its inputs are populated.",
        record_id="DEAL-4821",
        incident_id="INC-1042",
        discrepancy={"summary": "approval required is false"},
        visited_nodes=["deal_stage", "deal_stage_automation", "derive_pricing_segment"],
        recommendation="Add an Enterprise case to derive pricing segment.",
        trace=[
            {
                "event": "PLANNER_DECISION",
                "current_node": "deal_stage",
                "selected_target": "deal_stage_automation",
                "reason": "It writes deal stage.",
                "semantic_role": "UPSTREAM_PRODUCER",
                "selected_action_id": "A1",
            },
            {
                "event": "STOP",
                "status": "diagnosed",
                "root_cause_node": "derive_pricing_segment",
                "reason": "missing write",
            },
        ],
    )


def test_no_ticket_pack_has_no_root_cause():
    pack = build_chat_evidence("What workflows write deal stage?", incident_id=None, result=None)
    blob = json.dumps(pack)
    assert "root_cause" not in pack
    assert pack["diagnosis_run"] is False
    assert pack.get("diagnosis") is None
    assert "root_cause" not in blob


def test_diagnosed_inc1042_fixture_includes_rca():
    pack = build_chat_evidence(
        "What should we fix?",
        incident_id="INC-1042",
        result=_inc1042_result(),
    )
    assert pack["diagnosis_run"] is True
    assert pack["diagnosis"]["root_cause"]["id"] == "derive_pricing_segment"
    ids = json.dumps(pack)
    assert "derive_pricing_segment" in ids
    assert "made_up_workflow" not in ids


def test_unknown_component_is_omitted():
    pack = build_chat_evidence("what about made_up_workflow", incident_id=None, result=None)
    blob = json.dumps(pack)
    assert "made_up_workflow" not in blob
    matched_ids = [item["id"] for item in pack["matched_components"]]
    assert "made_up_workflow" not in matched_ids


def test_named_graph_component_is_matched():
    pack = build_chat_evidence("What does deal stage automation do?", incident_id=None, result=None)
    matched_ids = [item["id"] for item in pack["matched_components"]]
    assert "deal_stage_automation" in matched_ids
    automation = next(item for item in pack["matched_components"] if item["id"] == "deal_stage_automation")
    assert automation["neighbors"]
    assert all("semantic_role" not in neighbor for neighbor in automation["neighbors"])


def test_pack_omits_planner_keys():
    pack = build_chat_evidence(
        "Why inspect deal stage automation?",
        incident_id="INC-1042",
        result=_inc1042_result(),
    )
    keys = _walk_keys(pack)
    assert keys.isdisjoint(FORBIDDEN_CHAT_KEYS)
    assert "semantic_role" not in keys
    assert "selected_action_id" not in keys
    assert "action_id" not in keys


def test_ticket_without_result():
    incident = get_incident("INC-1042")
    pack = build_chat_evidence("What is this ticket about?", incident_id="INC-1042", result=None)
    assert pack["diagnosis_run"] is False
    assert pack["incident"]["id"] == "INC-1042"
    assert pack["incident"]["text"] == incident.text
    assert pack["incident"]["deal_id"] == incident.deal_id
    assert "root_cause" not in pack
    assert pack.get("diagnosis") is None


def test_graph_load_used_for_neighbors():
    graph = load_graph()
    pack = build_chat_evidence("deal stage automation", graph=graph)
    matched = pack["matched_components"][0]
    neighbor_ids = {row["id"] for row in matched["neighbors"]}
    real = {n.neighbor_id for n in graph.get_neighbors("deal_stage_automation")}
    assert neighbor_ids <= real
    assert neighbor_ids
