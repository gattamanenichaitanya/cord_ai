"""Bounded investigation loop. Claude chooses action_id; backend executes tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from diagnosis.actions import ActionType, CandidateAction, InvalidActionError
from diagnosis.anchors import retrieve_anchors
from diagnosis.changes import get_recent_changes
from diagnosis.expectations import ExpectationResult, evaluate_expectations, violations
from diagnosis.fault import FaultEvidence, assess_workflow_fault, _adjacent_fields
from diagnosis.graph import SystemGraph, load_graph
from diagnosis.incidents import get_incident
from diagnosis.neighborhood import build_candidate_actions
from diagnosis.ontology import EdgeType
from diagnosis.parser import TicketParse, parse_incident, parse_ticket
from diagnosis.planner import ClaudePlanner
from diagnosis.recommend import build_recommended_check
from diagnosis.roles import SemanticRole, derive_semantic_role
from diagnosis.rules import get_workflow_rule
from diagnosis.runtime import RuntimeState, get_runtime
from diagnosis.trace import action_result_event, expectation_event, planner_decision_event, stop_event

MAX_HOPS = 12
MAX_NODES_VISITED = 30
MAX_PLANNER_CALLS = 20


@dataclass
class DiagnosisResult:
    status: str
    root_cause_node: str | None
    confidence: float
    reason: str
    record_id: str | None
    incident_id: str | None
    discrepancy: dict[str, Any] | None
    visited_nodes: list[str]
    trace: list[dict[str, Any]] = field(default_factory=list)
    parsed: TicketParse | None = None
    recommendation: str | None = None


def _discrepancy_dict(result: ExpectationResult) -> dict[str, Any]:
    return {
        "policy_id": result.policy_id,
        "status": result.status.value,
        "subject_node": result.subject_node,
        "observed": result.observed,
        "expected": result.expected,
        "summary": result.summary,
    }


def select_primary_discrepancy(
    parsed: TicketParse,
    results: list[ExpectationResult],
) -> ExpectationResult | None:
    found = violations(results)
    if not found:
        return None
    unexpected = {claim.subject for claim in parsed.observed_claims if claim.qualifier == "unexpected"}
    for item in found:
        if item.subject_node in unexpected:
            return item
    return found[0]


def _validate_inspect(graph: SystemGraph, action: CandidateAction) -> None:
    if action.action_type != ActionType.INSPECT_CONNECTED_NODE.value:
        return
    if action.target_node_id is None or action.edge_type is None:
        raise InvalidActionError("INSPECT_CONNECTED_NODE missing target or edge_type")
    if graph.get_node(action.current_node_id) is None:
        raise InvalidActionError("current node does not exist")
    if graph.get_node(action.target_node_id) is None:
        raise InvalidActionError("target node does not exist")
    neighbor = graph.find_neighbor(action.current_node_id, action.target_node_id, action.edge_type)
    if neighbor is None:
        raise InvalidActionError("edge does not exist")
    if neighbor.edge_type != action.edge_type:
        raise InvalidActionError("edge_type mismatch")
    if neighbor.edge_direction != action.edge_direction:
        raise InvalidActionError("edge_direction mismatch")
    expected_role = derive_semantic_role(action.edge_type, action.edge_direction).value
    if action.semantic_role != expected_role or neighbor.semantic_role != expected_role:
        raise InvalidActionError("semantic_role mismatch")


def diagnose(
    incident_id: str,
    *,
    ticket_text: str | None = None,
    runtime: RuntimeState | None = None,
    rules_incident_id: str | None = None,
    graph: SystemGraph | None = None,
    planner: ClaudePlanner | None = None,
    max_hops: int = MAX_HOPS,
    max_nodes_visited: int = MAX_NODES_VISITED,
    max_planner_calls: int = MAX_PLANNER_CALLS,
) -> DiagnosisResult:
    incident = get_incident(incident_id)
    parsed = (
        parse_ticket(ticket_text, incident=incident)
        if ticket_text is not None
        else parse_incident(incident_id)
    )
    record_id = parsed.record_id or incident.deal_id
    state = runtime or get_runtime(record_id)
    overlay_id = rules_incident_id if rules_incident_id is not None else incident_id
    system = graph or load_graph()

    expectation_results = evaluate_expectations(state)
    trace: list[dict[str, Any]] = [
        expectation_event([item.as_dict() for item in expectation_results])
    ]
    primary = select_primary_discrepancy(parsed, expectation_results)
    if primary is None:
        trace.append(
            stop_event(
                status="no_anomaly",
                root_cause_node=None,
                reason="No validated policy/runtime discrepancy; causal traversal did not start.",
            )
        )
        return DiagnosisResult(
            status="no_anomaly",
            root_cause_node=None,
            confidence=1.0,
            reason="No validated anomaly.",
            record_id=record_id,
            incident_id=incident_id,
            discrepancy=None,
            visited_nodes=[],
            trace=trace,
            parsed=parsed,
        )

    discrepancy = _discrepancy_dict(primary)
    start = primary.subject_node
    if start is None or system.get_node(start) is None:
        anchors = retrieve_anchors(system, parsed, top_k=1)
        start = anchors[0].node_id if anchors else None
    if start is None:
        trace.append(stop_event(status="needs_human", root_cause_node=None, reason="No start node."))
        return DiagnosisResult(
            status="needs_human",
            root_cause_node=None,
            confidence=0.2,
            reason="No start node.",
            record_id=record_id,
            incident_id=incident_id,
            discrepancy=discrepancy,
            visited_nodes=[],
            trace=trace,
            parsed=parsed,
        )

    if max_hops <= 0 or max_planner_calls <= 0:
        reason = "No sufficiently supported causal explanation found within the investigation budget."
        trace.append(stop_event(status="needs_human", root_cause_node=None, reason=reason))
        return DiagnosisResult(
            status="needs_human",
            root_cause_node=None,
            confidence=0.35,
            reason=reason,
            record_id=record_id,
            incident_id=incident_id,
            discrepancy=discrepancy,
            visited_nodes=[start],
            trace=trace,
            parsed=parsed,
        )

    chooser = planner or ClaudePlanner()
    current = start
    visited: list[str] = [current]
    evidence: list[dict[str, Any]] = []
    faults: list[FaultEvidence] = []
    hop_count = 0
    planner_calls = 0
    inspected_workflows: set[str] = set()

    def _uninspected_producers() -> list[str]:
        fields = set(discrepancy.get("expected", {})) | set(discrepancy.get("observed", {}))
        remaining: list[str] = []
        for field_id in fields:
            if system.get_node(field_id) is None:
                continue
            for neighbor in system.get_neighbors(field_id):
                if (
                    neighbor.semantic_role == SemanticRole.UPSTREAM_PRODUCER.value
                    and neighbor.neighbor_id not in inspected_workflows
                    and neighbor.neighbor_id not in remaining
                ):
                    remaining.append(neighbor.neighbor_id)
        return remaining

    def current_payload() -> dict[str, Any]:
        node = system.get_node(current) or {"id": current, "type": None}
        runtime_value = state.get(current) if current in state.values else None
        null_fields = [field for field in state.values if state.values[field] is None]
        return {
            "id": current,
            "type": node.get("type"),
            "runtime_value": runtime_value,
            "runtime_null_fields": null_fields,
            "uninspected_producers_of_discrepancy_fields": _uninspected_producers(),
        }

    while hop_count < max_hops and planner_calls < max_planner_calls and len(visited) <= max_nodes_visited:
        candidates = build_candidate_actions(
            system,
            current,
            visited=visited,
            incident_id=overlay_id,
            allow_root_cause_stop=bool(faults),
        )
        planner_calls += 1
        try:
            action, choice = chooser.choose_validated(
                ticket_text=incident.text if ticket_text is None else ticket_text,
                discrepancy=discrepancy,
                current_node=current_payload(),
                evidence=evidence,
                faults=[fault.__dict__ for fault in faults],
                candidates=candidates,
            )
            _validate_inspect(system, action)
        except InvalidActionError as exc:
            trace.append(
                stop_event(
                    status="needs_human",
                    root_cause_node=None,
                    reason=f"Planner selection invalid after retry: {exc}",
                )
            )
            return DiagnosisResult(
                status="needs_human",
                root_cause_node=None,
                confidence=0.2,
                reason=str(exc),
                record_id=record_id,
                incident_id=incident_id,
                discrepancy=discrepancy,
                visited_nodes=visited,
                trace=trace,
                parsed=parsed,
            )

        trace.append(
            planner_decision_event(
                current_node=current,
                validated_anomaly=discrepancy,
                candidate_actions=[item.action_id for item in candidates],
                selected_action_id=action.action_id,
                selected_target=action.target_node_id,
                edge_type=action.edge_type,
                edge_direction=action.edge_direction,
                semantic_role=action.semantic_role,
                reason=choice.reason,
                confidence=choice.confidence,
            )
        )

        output, current, hop_count, new_fault = _execute(
            action=action,
            graph=system,
            runtime=state,
            overlay_id=overlay_id,
            current=current,
            visited=visited,
            hop_count=hop_count,
            discrepancy=primary,
            faults=faults,
        )
        if action.action_type == ActionType.INSPECT_RULE.value:
            inspected_workflows.add(action.target_node_id or action.current_node_id)
        if new_fault is not None and all(existing.node_id != new_fault.node_id for existing in faults):
            faults.append(new_fault)
        evidence.append({"action_type": action.action_type, "output": output})
        trace.append(action_result_event(action_type=action.action_type, output=output))

        if new_fault is not None:
            rca = new_fault.node_id
            recommendation = _recommended_check_for(
                new_fault,
                overlay_id,
                state,
                client=getattr(chooser, "client", None),
                discrepancy=discrepancy,
            )
            trace.append(
                stop_event(
                    status="diagnosed",
                    root_cause_node=rca,
                    reason=new_fault.summary,
                    recommendation=recommendation,
                )
            )
            return DiagnosisResult(
                status="diagnosed",
                root_cause_node=rca,
                confidence=choice.confidence,
                reason=new_fault.summary,
                record_id=record_id,
                incident_id=incident_id,
                discrepancy=discrepancy,
                visited_nodes=visited,
                trace=trace,
                parsed=parsed,
                recommendation=recommendation,
            )

        if action.action_type == ActionType.STOP_WITH_ROOT_CAUSE.value:
            rca = _root_cause_from_faults(faults, current)
            if rca is None:
                continue
            rca_fault = next((item for item in reversed(faults) if item.node_id == rca), faults[-1])
            reason = rca_fault.summary if rca_fault else choice.reason
            recommendation = _recommended_check_for(
                rca_fault,
                overlay_id,
                state,
                client=getattr(chooser, "client", None),
                discrepancy=discrepancy,
            )
            trace.append(
                stop_event(
                    status="diagnosed",
                    root_cause_node=rca,
                    reason=reason,
                    recommendation=recommendation,
                )
            )
            return DiagnosisResult(
                status="diagnosed",
                root_cause_node=rca,
                confidence=choice.confidence,
                reason=reason,
                record_id=record_id,
                incident_id=incident_id,
                discrepancy=discrepancy,
                visited_nodes=visited,
                trace=trace,
                parsed=parsed,
                recommendation=recommendation,
            )

        if action.action_type == ActionType.STOP_NEEDS_HUMAN.value:
            trace.append(
                stop_event(
                    status="needs_human",
                    root_cause_node=None,
                    reason=choice.reason,
                )
            )
            return DiagnosisResult(
                status="needs_human",
                root_cause_node=None,
                confidence=choice.confidence,
                reason=choice.reason,
                record_id=record_id,
                incident_id=incident_id,
                discrepancy=discrepancy,
                visited_nodes=visited,
                trace=trace,
                parsed=parsed,
            )

    reason = "No sufficiently supported causal explanation found within the investigation budget."
    trace.append(stop_event(status="needs_human", root_cause_node=None, reason=reason))
    return DiagnosisResult(
        status="needs_human",
        root_cause_node=None,
        confidence=0.35,
        reason=reason,
        record_id=record_id,
        incident_id=incident_id,
        discrepancy=discrepancy,
        visited_nodes=visited,
        trace=trace,
        parsed=parsed,
    )


def _root_cause_from_faults(faults: list[FaultEvidence], current: str) -> str | None:
    if not faults:
        return None
    for fault in reversed(faults):
        if fault.node_id == current:
            return fault.node_id
    return faults[-1].node_id


def _recommended_check_for(
    fault: FaultEvidence,
    overlay_id: str | None,
    runtime: RuntimeState,
    client: Any | None = None,
    discrepancy: dict[str, Any] | None = None,
) -> str:
    current_rule = get_workflow_rule(fault.node_id, overlay_id)
    try:
        healthy_rule = get_workflow_rule(fault.node_id, None)
    except KeyError:
        healthy_rule = None
    return build_recommended_check(
        fault,
        current_rule,
        healthy_rule,
        runtime,
        client=client,
        discrepancy=discrepancy,
    )


def _execute(
    *,
    action: CandidateAction,
    graph: SystemGraph,
    runtime: RuntimeState,
    overlay_id: str | None,
    current: str,
    visited: list[str],
    hop_count: int,
    discrepancy: ExpectationResult,
    faults: list[FaultEvidence],
) -> tuple[dict[str, Any], str, int, FaultEvidence | None]:
    kind = action.action_type
    new_fault: FaultEvidence | None = None

    if kind == ActionType.INSPECT_CONNECTED_NODE.value:
        target = action.target_node_id
        assert target is not None
        if target not in visited:
            visited.append(target)
        hop_count += 1
        node = graph.get_node(target) or {}
        return (
            {"moved_to": target, "node_type": node.get("type"), "label": node.get("label")},
            target,
            hop_count,
            None,
        )

    if kind == ActionType.RETURN_TO_CANDIDATE.value:
        target = action.target_node_id
        assert target is not None
        hop_count += 1
        return ({"returned_to": target}, target, hop_count, None)

    if kind == ActionType.READ_RUNTIME_VALUE.value:
        field_id = action.target_node_id or current
        value = runtime.get(field_id)
        return ({"field": field_id, "value": value}, current, hop_count, None)

    if kind == ActionType.INSPECT_RULE.value:
        workflow_id = action.target_node_id or current
        rule = get_workflow_rule(workflow_id, overlay_id)
        new_fault = assess_workflow_fault(
            graph,
            workflow_id,
            rule,
            runtime,
            discrepancy.observed,
            discrepancy.expected,
        )
        read_fields = _adjacent_fields(graph, workflow_id, EdgeType.READS.value)
        incomplete = [field for field in read_fields if runtime.get(field) is None]
        output: dict[str, Any] = {
            "workflow_id": workflow_id,
            "rule": rule,
            "incomplete_inputs": incomplete,
            "fault": None if new_fault is None else new_fault.__dict__,
        }
        return output, current, hop_count, new_fault

    if kind == ActionType.CHECK_RECENT_CHANGES.value:
        node_id = action.target_node_id or current
        return ({"changes": get_recent_changes(node_id)}, current, hop_count, None)

    if kind in {ActionType.STOP_WITH_ROOT_CAUSE.value, ActionType.STOP_NEEDS_HUMAN.value}:
        return ({"stop": kind}, current, hop_count, None)

    raise InvalidActionError(f"Unsupported action type {kind}")
