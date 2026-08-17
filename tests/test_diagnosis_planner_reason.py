"""User-facing planner reasons must not leak action ids or role tokens."""

from diagnosis.actions import ActionType
from diagnosis.graph import load_graph
from diagnosis.neighborhood import build_candidate_actions
from diagnosis.planner import (
    ClaudePlanner,
    PlannerChoice,
    SYSTEM_PROMPT,
    UserWhy,
    WHY_SYSTEM_PROMPT,
    _planner_payload,
    sanitize_planner_reason,
    write_user_why,
)


def test_sanitize_strips_action_ids_and_role_tokens():
    raw = (
        "deal_stage_automation (A1) is a direct UPSTREAM_PRODUCER (semantic_role) "
        "that WRITES deal_stage. The uninspected_producers_of_discrepancy_fields list "
        "includes discount_governance."
    )
    cleaned = sanitize_planner_reason(raw)
    assert "A1" not in cleaned
    assert "UPSTREAM_PRODUCER" not in cleaned
    assert "semantic_role" not in cleaned
    assert "uninspected_producers_of_discrepancy_fields" not in cleaned
    assert "producer" in cleaned
    assert "discount_governance" in cleaned


def test_planner_payload_matches_original_selection_keys():
    graph = load_graph()
    candidates = build_candidate_actions(graph, "deal_stage")
    payload = _planner_payload(
        ticket_text="demo",
        discrepancy={"expected": {"approval_required": True}, "observed": {"approval_required": False}},
        current_node={
            "id": "deal_stage",
            "type": "PROPERTY",
            "runtime_value": "Contract Sent",
            "runtime_null_fields": ["pricing_segment"],
            "uninspected_producers_of_discrepancy_fields": ["discount_governance", "legacy_discount_override"],
        },
        evidence=[
            {
                "action_type": ActionType.INSPECT_RULE.value,
                "output": {"workflow_id": "deal_stage_automation", "incomplete_inputs": []},
            }
        ],
        faults=[],
        candidates=candidates,
    )
    assert set(payload) == {
        "incident",
        "validated_discrepancy",
        "current_node",
        "important_prior_evidence",
        "fault_evidence",
        "runtime_null_fields",
        "uninspected_producers_of_discrepancy_fields",
        "candidate_actions",
    }
    assert payload["current_node"]["id"] == "deal_stage"
    assert payload["uninspected_producers_of_discrepancy_fields"] == [
        "discount_governance",
        "legacy_discount_override",
    ]
    assert payload["important_prior_evidence"][0]["output"]["workflow_id"] == "deal_stage_automation"
    assert "how_to_refer" not in payload["candidate_actions"][0]
    assert "how_to_refer" not in SYSTEM_PROMPT
    assert "user-facing" not in SYSTEM_PROMPT.lower()
    assert "ordinary English" in WHY_SYSTEM_PROMPT


def test_write_user_why_falls_back_when_claude_fails():
    class Broken:
        def call_with_structured_output(self, **kwargs):
            raise RuntimeError("no api")

    graph = load_graph()
    action = build_candidate_actions(graph, "deal_stage")[0]
    text = write_user_why(
        Broken(),
        action=action,
        discrepancy={"summary": "approval required is false"},
        current_node={"id": "deal_stage"},
        fallback="Inspect deal_stage_automation (A1) as UPSTREAM_PRODUCER.",
    )
    assert "A1" not in text
    assert "UPSTREAM_PRODUCER" not in text


def test_choose_validated_rewrites_why_after_action_is_locked():
    graph = load_graph()
    candidates = build_candidate_actions(graph, "deal_stage")
    selected = candidates[0]

    class Stub:
        def __init__(self):
            self.prompts = []

        def call_with_structured_output(self, **kwargs):
            self.prompts.append(kwargs["system_prompt"])
            if kwargs["output_model"] is PlannerChoice:
                return (
                    PlannerChoice(
                        selected_action_id=selected.action_id,
                        reason="internal A1 UPSTREAM_PRODUCER",
                        confidence=0.9,
                    ),
                    {},
                )
            return (UserWhy(reason="Checking the workflow that writes deal stage."), {})

    planner = ClaudePlanner(client=Stub())
    action, choice = planner.choose_validated(
        ticket_text="demo",
        discrepancy={"summary": "approval required is false"},
        current_node={"id": "deal_stage"},
        evidence=[],
        faults=[],
        candidates=candidates,
    )
    assert action.action_id == selected.action_id
    assert choice.reason == "Checking the workflow that writes deal stage."
    assert planner.client.prompts[0] == SYSTEM_PROMPT
    assert planner.client.prompts[1] == WHY_SYSTEM_PROMPT
