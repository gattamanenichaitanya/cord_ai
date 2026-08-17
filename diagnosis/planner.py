"""Claude planner: choose exactly one allowed action_id."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from diagnosis.actions import CandidateAction, InvalidActionError, validate_selected_action
from diagnosis.recommend import friendly_name
from diagnosis.roles import user_role_label
from planning.claude_client import ClaudeClient

SYSTEM_PROMPT = """You are Cord's investigation planner.

You MUST select exactly one action_id from candidate_actions.
You MUST NOT invent nodes, edges, action ids, or runtime values.
Use semantic_role for causal reasoning. edge_direction is stored graph topology only.
Do not use a field named direction.

If the discrepancy is an unexpected property value, prefer UPSTREAM_PRODUCER neighbors
of that property (components that write it), then continue upstream while inputs look incomplete.
If the discrepancy is missing downstream behavior while the current property looks healthy,
prefer DOWNSTREAM_CONSUMER neighbors.

INSPECT_RULE on a workflow before declaring it the root cause.
If a visited workflow reads a property whose runtime value is null, inspect that
property next and then its UPSTREAM_PRODUCER. Null inputs mean the writer is not
yet explained; do not stop on a downstream workflow that is behaving correctly
given missing inputs.
If uninspected_producers_of_discrepancy_fields is non-empty, inspect those workflows
next (return to the discrepancy subject node if needed). Do not follow change-history
or unrelated branches until every producer of the violating field has been inspected.
Only choose STOP_WITH_ROOT_CAUSE when fault_evidence names that workflow.
Only choose STOP_NEEDS_HUMAN when evidence is insufficient.
Prefer investigating unvisited producers over returning or stopping early.
"""

WHY_SYSTEM_PROMPT = """You explain one already-chosen investigation step to an operations user.

The action is already decided. Do not suggest a different component.
Write 2 to 4 short sentences: what looks wrong, why this component is next, and what inspecting it should show.
Use ordinary English names from the evidence (deal stage, deal stage automation).
Never mention action ids (A1), JSON keys, or tokens like UPSTREAM_PRODUCER, semantic_role, or INSPECT_RULE.
Do not Title Case workflow names.
"""


class PlannerChoice(BaseModel):
    selected_action_id: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class UserWhy(BaseModel):
    reason: str = Field(min_length=1)


def sanitize_planner_reason(reason: str) -> str:
    """Strip planner internals that leaked into the user-facing why."""
    text = reason
    replacements = (
        (r"\bA\d+\b", ""),
        (r"UPSTREAM_PRODUCER", "producer"),
        (r"DOWNSTREAM_CONSUMER", "consumer"),
        (r"UPSTREAM_DEPENDENCY", "dependency"),
        (r"DOWNSTREAM_DEPENDENT", "dependent"),
        (r"uninspected_producers_of_discrepancy_fields", "other writers of this field"),
        (r"semantic_role", ""),
        (r"INSPECT_RULE", "the workflow rule"),
        (r"INSPECT_CONNECTED_NODE", "this connected component"),
        (r"STOP_WITH_ROOT_CAUSE", "stop with a root cause"),
        (r"`+", ""),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


def _planner_payload(
    *,
    ticket_text: str,
    discrepancy: dict[str, Any],
    current_node: dict[str, Any],
    evidence: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    candidates: list[CandidateAction],
) -> dict[str, Any]:
    return {
        "incident": {"text": ticket_text},
        "validated_discrepancy": discrepancy,
        "current_node": current_node,
        "important_prior_evidence": evidence,
        "fault_evidence": faults,
        "runtime_null_fields": current_node.get("runtime_null_fields", []),
        "uninspected_producers_of_discrepancy_fields": current_node.get(
            "uninspected_producers_of_discrepancy_fields", []
        ),
        "candidate_actions": [action.as_planner_dict() for action in candidates],
    }


def _user_why_evidence(
    action: CandidateAction,
    discrepancy: dict[str, Any],
    current_node: dict[str, Any],
) -> dict[str, Any]:
    target = action.target_node_name or action.target_node_id
    current_id = current_node.get("id")
    return {
        "current": friendly_name(current_id) if current_id else "",
        "chosen_component": (target or "").replace("_", " ").lower(),
        "role": user_role_label(action.semantic_role),
        "relationship": (action.edge_type or "").lower(),
        "discrepancy_summary": discrepancy.get("summary"),
        "expected": discrepancy.get("expected"),
        "observed": discrepancy.get("observed"),
        "runtime_value_here": current_node.get("runtime_value"),
    }


def write_user_why(
    client: ClaudeClient,
    *,
    action: CandidateAction,
    discrepancy: dict[str, Any],
    current_node: dict[str, Any],
    fallback: str,
) -> str:
    prompt = (
        "Explain this locked investigation step.\n\n"
        + json.dumps(_user_why_evidence(action, discrepancy, current_node), indent=2, default=str)
    )
    try:
        copy, _meta = client.call_with_structured_output(
            prompt=prompt,
            output_model=UserWhy,
            system_prompt=WHY_SYSTEM_PROMPT,
            max_tokens=512,
        )
        text = copy.reason.strip()
        if text:
            return sanitize_planner_reason(text)
    except Exception:
        pass
    return sanitize_planner_reason(fallback)


class ClaudePlanner:
    def __init__(self, client: ClaudeClient | None = None):
        self.client = client or ClaudeClient()

    def choose(
        self,
        *,
        ticket_text: str,
        discrepancy: dict[str, Any],
        current_node: dict[str, Any],
        evidence: list[dict[str, Any]],
        faults: list[dict[str, Any]],
        candidates: list[CandidateAction],
        validation_error: str | None = None,
    ) -> PlannerChoice:
        payload = _planner_payload(
            ticket_text=ticket_text,
            discrepancy=discrepancy,
            current_node=current_node,
            evidence=evidence,
            faults=faults,
            candidates=candidates,
        )
        prompt = (
            "Investigate this grounded situation and submit one allowed action.\n\n"
            + json.dumps(payload, indent=2, default=str)
        )
        if validation_error:
            prompt += (
                "\n\nYour previous selected_action_id was invalid: "
                + validation_error
                + "\nSelect a different action_id from candidate_actions."
            )
        choice, _meta = self.client.call_with_structured_output(
            prompt=prompt,
            output_model=PlannerChoice,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=1024,
        )
        return choice

    def choose_validated(
        self,
        *,
        ticket_text: str,
        discrepancy: dict[str, Any],
        current_node: dict[str, Any],
        evidence: list[dict[str, Any]],
        faults: list[dict[str, Any]],
        candidates: list[CandidateAction],
    ) -> tuple[CandidateAction, PlannerChoice]:
        choice = self.choose(
            ticket_text=ticket_text,
            discrepancy=discrepancy,
            current_node=current_node,
            evidence=evidence,
            faults=faults,
            candidates=candidates,
        )
        try:
            action = validate_selected_action(candidates, choice.selected_action_id)
        except InvalidActionError as exc:
            retry = self.choose(
                ticket_text=ticket_text,
                discrepancy=discrepancy,
                current_node=current_node,
                evidence=evidence,
                faults=faults,
                candidates=candidates,
                validation_error=str(exc),
            )
            action = validate_selected_action(candidates, retry.selected_action_id)
            choice = retry
        user_why = write_user_why(
            self.client,
            action=action,
            discrepancy=discrepancy,
            current_node=current_node,
            fallback=choice.reason,
        )
        return action, PlannerChoice(
            selected_action_id=choice.selected_action_id,
            reason=user_why,
            confidence=choice.confidence,
        )
