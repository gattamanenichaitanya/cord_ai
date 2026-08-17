"""Locked evidence JSON for Diagnose chat. No LLM. No invented nodes."""

from __future__ import annotations

from typing import Any

from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import SystemGraph, load_graph
from diagnosis.incidents import get_incident
from diagnosis.loop import DiagnosisResult
from diagnosis.recommend import format_field_value, friendly_name
from diagnosis.runtime import get_runtime

FORBIDDEN_CHAT_KEYS = frozenset(
    {
        "semantic_role",
        "selected_action_id",
        "action_id",
        "edge_direction",
    }
)


def _component(node_id: str, graph: SystemGraph) -> dict[str, Any]:
    node = graph.get_node(node_id) or {}
    return {
        "id": node_id,
        "type": node.get("type"),
        "how_to_refer": friendly_name(node_id),
    }


def _match_phrases(node_id: str, graph: SystemGraph) -> list[str]:
    node = graph.get_node(node_id) or {}
    phrases = {node_id.lower(), node_id.replace("_", " ").lower()}
    label = node.get("label")
    if label:
        phrases.add(str(label).lower())
    return sorted(phrases, key=len, reverse=True)


def match_mentioned_nodes(question: str, graph: SystemGraph) -> list[str]:
    """Return graph node ids whose id or label appears in the question. Longest phrase wins."""
    text = question.lower()
    scored: list[tuple[int, str, str]] = []
    for node_id in graph.nodes:
        best = ""
        for phrase in _match_phrases(node_id, graph):
            if len(phrase) < 4:
                continue
            if phrase in text and len(phrase) > len(best):
                best = phrase
        if best:
            scored.append((len(best), node_id, best))
    scored.sort(key=lambda row: (-row[0], row[1]))
    chosen: list[str] = []
    accepted_phrases: list[str] = []
    for _length, node_id, phrase in scored:
        if any(phrase != other and phrase in other for other in accepted_phrases):
            continue
        chosen.append(node_id)
        accepted_phrases.append(phrase)
    return chosen


def _neighbors_payload(node_id: str, graph: SystemGraph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for neighbor in graph.get_neighbors(node_id):
        key = (neighbor.neighbor_id, neighbor.edge_type)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "id": neighbor.neighbor_id,
                "type": neighbor.neighbor_type,
                "how_to_refer": friendly_name(neighbor.neighbor_id),
                "relationship": neighbor.edge_type,
            }
        )
    return rows


def _matched_components(question: str, graph: SystemGraph) -> list[dict[str, Any]]:
    matched = []
    for node_id in match_mentioned_nodes(question, graph):
        item = _component(node_id, graph)
        item["neighbors"] = _neighbors_payload(node_id, graph)
        matched.append(item)
    return matched


def _hop_summaries(result: DiagnosisResult, graph: SystemGraph) -> list[dict[str, Any]]:
    hops: list[dict[str, Any]] = []
    for event in result.trace:
        if event.get("event") != "PLANNER_DECISION":
            continue
        target = event.get("selected_target") or event.get("current_node")
        if not target:
            continue
        hops.append(
            {
                "component": _component(str(target), graph),
                "why": event.get("reason") or "",
            }
        )
    return hops


def _deal_runtime(record_id: str | None) -> list[dict[str, Any]]:
    if not record_id:
        return []
    try:
        runtime = get_runtime(record_id)
    except KeyError:
        return []
    rows = []
    for field in CANONICAL_FIELDS:
        if field not in runtime.values:
            continue
        value = runtime.get(field)
        rows.append(
            {
                "id": field,
                "how_to_refer": friendly_name(field),
                "display_value": format_field_value(field, value),
            }
        )
    return rows


def _assert_pack_is_clean(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_CHAT_KEYS:
                raise RuntimeError(f"Chat evidence must not include {key}")
            _assert_pack_is_clean(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_pack_is_clean(item)


def build_chat_evidence(
    question: str,
    *,
    incident_id: str | None = None,
    result: DiagnosisResult | None = None,
    graph: SystemGraph | None = None,
) -> dict[str, Any]:
    system = graph or load_graph()
    pack: dict[str, Any] = {
        "canonical_fields": [{"id": field, "how_to_refer": friendly_name(field)} for field in CANONICAL_FIELDS],
        "diagnosis_run": False,
        "matched_components": _matched_components(question, system),
    }

    if incident_id:
        incident = get_incident(incident_id)
        pack["incident"] = {
            "id": incident.id,
            "deal_id": incident.deal_id,
            "text": incident.text,
        }

    if result is not None:
        pack["diagnosis_run"] = True
        diagnosis: dict[str, Any] = {
            "status": result.status,
            "reason": result.reason,
            "recommendation": result.recommendation,
            "visited": [_component(node_id, system) for node_id in result.visited_nodes],
            "hops": _hop_summaries(result, system),
            "this_deal": _deal_runtime(result.record_id),
        }
        if result.root_cause_node:
            diagnosis["root_cause"] = _component(result.root_cause_node, system)
        pack["diagnosis"] = diagnosis
        if result.record_id and not pack.get("incident"):
            pack["this_deal"] = diagnosis["this_deal"]

    _assert_pack_is_clean(pack)
    return pack
