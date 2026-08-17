"""Replay investigation UI state from a backend trace. No ticket → path maps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from diagnosis.graph import SystemGraph

from dashboard.diagnose.labels import edge_verb, node_label, role_label


@dataclass
class ReplayFrame:
    step: int
    current_node: str | None
    selected_target: str | None
    decision_label: str
    why: str
    connected: list[dict[str, str]]
    log_lines: list[str]
    node_states: dict[str, str]
    rca: str | None = None
    status: str = "diagnosing"


def highlight_sequence(trace: list[dict[str, Any]]) -> list[tuple[str | None, str | None]]:
    """Ordered (current_node, selected_target) from planner events. Trace-driven."""
    sequence: list[tuple[str | None, str | None]] = []
    for event in trace:
        if event.get("event") != "PLANNER_DECISION":
            continue
        sequence.append((event.get("current_node"), event.get("selected_target")))
    return sequence


def _connected(graph: SystemGraph, node_id: str | None) -> list[dict[str, str]]:
    if not node_id or graph.get_node(node_id) is None:
        return []
    rows: list[dict[str, str]] = []
    for neighbor in graph.get_neighbors(node_id):
        rows.append(
            {
                "id": neighbor.neighbor_id,
                "name": neighbor.neighbor_name,
                "edge": edge_verb(neighbor.edge_type),
                "role": role_label(neighbor.semantic_role),
            }
        )
    return rows


def _node_states(
    *,
    visited: list[str],
    current: str | None,
    candidates: list[str],
    rca: str | None,
    complete: bool,
) -> dict[str, str]:
    states: dict[str, str] = {}
    for node_id in visited:
        states[node_id] = "VISITED"
    for node_id in candidates:
        if node_id not in states:
            states[node_id] = "CANDIDATE"
    if current:
        states[current] = "CURRENT"
    if complete and rca:
        states[rca] = "ROOT_CAUSE"
        for node_id in visited:
            if node_id != rca and states.get(node_id) != "ROOT_CAUSE":
                states[node_id] = "CAUSAL_PATH"
        if current and current != rca:
            states[current] = "CAUSAL_PATH"
    return states


def replay_frames(graph: SystemGraph, result: Any) -> list[ReplayFrame]:
    frames: list[ReplayFrame] = []
    log: list[str] = []
    visited: list[str] = []
    rca = result.root_cause_node if result.status == "diagnosed" else None

    for event in result.trace:
        kind = event.get("event")
        if kind == "EXPECTATION_VALIDATION":
            log.append(f"Loaded record {result.record_id or 'unknown'}.")
            violated = [
                item for item in event.get("results", []) if item.get("status") == "VIOLATED"
            ]
            if not violated:
                log.append("No policy violation confirmed. Diagnosis did not start a graph walk.")
            else:
                summary = violated[0].get("summary") or "Policy violation confirmed."
                log.append(f"Policy violation confirmed. {summary}")
            continue

        if kind == "PLANNER_DECISION":
            current = event.get("current_node")
            if current and current not in visited:
                visited.append(current)
            target = event.get("selected_target")
            connected = _connected(graph, current)
            candidates = [row["id"] for row in connected]
            why = event.get("reason") or ""
            decision = node_label(graph, target) if target else "Paused"
            log.append(f"Current: {node_label(graph, current)}")
            if connected:
                names = ", ".join(f"{row['name']} ({row['role']})" for row in connected[:6])
                log.append(f"Connected: {names}")
            log.append(f"Cord chose: {decision}")
            if why:
                log.append(f"Why: {why}")
            frames.append(
                ReplayFrame(
                    step=len(frames) + 1,
                    current_node=current,
                    selected_target=target,
                    decision_label=decision,
                    why=why,
                    connected=connected,
                    log_lines=list(log),
                    node_states=_node_states(
                        visited=visited,
                        current=current,
                        candidates=candidates,
                        rca=None,
                        complete=False,
                    ),
                    status="diagnosing",
                )
            )
            continue

        if kind == "ACTION_RESULT":
            moved = (event.get("output") or {}).get("moved_to")
            if moved and moved not in visited:
                visited.append(moved)
            action_type = event.get("action_type")
            if action_type == "INSPECT_RULE":
                output = event.get("output") or {}
                workflow = node_label(graph, output.get("workflow_id"))
                fault = output.get("fault")
                if fault:
                    log.append(f"Rule issue on {workflow}: {fault.get('summary', '')}")
                else:
                    log.append(f"{workflow} behaved as configured for its current inputs.")
            continue

        if kind == "STOP":
            status = event.get("status") or result.status
            if status == "diagnosed" and event.get("root_cause_node"):
                log.append(f"Root cause found: {node_label(graph, event.get('root_cause_node'))}")
            elif status == "no_anomaly":
                log.append("No validated anomaly.")
            else:
                log.append("Needs a human. Evidence was not sufficient.")
            current = visited[-1] if visited else None
            connected = _connected(graph, current)
            frames.append(
                ReplayFrame(
                    step=len(frames) + 1,
                    current_node=current,
                    selected_target=event.get("root_cause_node"),
                    decision_label=node_label(graph, event.get("root_cause_node")),
                    why=event.get("reason") or "",
                    connected=connected,
                    log_lines=list(log),
                    node_states=_node_states(
                        visited=visited,
                        current=current,
                        candidates=[row["id"] for row in connected],
                        rca=event.get("root_cause_node"),
                        complete=status == "diagnosed",
                    ),
                    rca=event.get("root_cause_node"),
                    status=status,
                )
            )
    if not frames:
        frames.append(
            ReplayFrame(
                step=1,
                current_node=None,
                selected_target=None,
                decision_label="",
                why="",
                connected=[],
                log_lines=log or ["No investigation steps."],
                node_states={},
                rca=rca,
                status=result.status,
            )
        )
    return frames
