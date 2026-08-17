"""Recommended check is derived from fault + rule diffs, not incident maps."""

from pathlib import Path

from diagnosis.fault import assess_workflow_fault
from diagnosis.graph import load_graph
from diagnosis.recommend import build_recommended_check, recommendation_evidence
from diagnosis.rules import get_workflow_rule
from diagnosis.runtime import get_runtime


def _check(workflow_id: str, overlay_id: str, deal_id: str, observed: dict, expected: dict) -> str:
    graph = load_graph()
    runtime = get_runtime(deal_id)
    current = get_workflow_rule(workflow_id, overlay_id)
    healthy = get_workflow_rule(workflow_id)
    fault = assess_workflow_fault(graph, workflow_id, current, runtime, observed, expected)
    assert fault is not None
    return build_recommended_check(fault, current, healthy, runtime)


def test_4920_recommendation_explains_amount_threshold():
    text = _check(
        "discount_governance",
        "INC-1188",
        "DEAL-4920",
        {"approval_required": False, "deal_stage": "Contract Sent"},
        {"approval_required": True},
    )
    assert "$500,000" in text
    assert "$100,000" in text
    assert "deal amount" in text
    assert "discount governance" in text
    assert "Cord will not change the CRM" not in text
    assert "INC-1188" not in text
    assert "inspect" not in text.lower()


def test_4821_recommendation_explains_missing_enterprise_case():
    text = _check(
        "derive_pricing_segment",
        "INC-1042",
        "DEAL-4821",
        {"deal_stage": "Contract Sent", "approval_required": False},
        {"approval_required": True},
    )
    assert "Enterprise" in text
    assert "pricing segment" in text
    assert "derive pricing segment" in text
    assert "customer tier" in text
    assert "Cord will not change the CRM" not in text
    assert "Missing branch" not in text
    assert "inspect" not in text.lower()


def test_5101_recommendation_says_turn_workflow_on():
    text = _check(
        "fulfillment_workflow",
        "INC-3310",
        "DEAL-5101",
        {"fulfillment_started": False},
        {"fulfillment_started": True},
    )
    assert "turned off" in text
    assert "fulfillment workflow" in text
    assert "Cord will not change the CRM" not in text


def test_5033_recommendation_explains_discount_threshold():
    text = _check(
        "legacy_discount_override",
        "INC-2201",
        "DEAL-5033",
        {"approval_required": True},
        {"approval_required": False},
    )
    assert "0%" in text
    assert "40%" in text
    assert "discount %" in text
    assert "Cord will not change the CRM" not in text


def test_recommend_module_has_no_incident_maps():
    source = Path("diagnosis/recommend.py").read_text(encoding="utf-8")
    assert "INC-1042" not in source
    assert "INC-1188" not in source
    assert "if incident_id" not in source
    assert "Cord will not change the CRM" not in source


def _evidence(workflow_id: str, overlay_id: str, deal_id: str, observed: dict, expected: dict) -> dict:
    graph = load_graph()
    runtime = get_runtime(deal_id)
    current = get_workflow_rule(workflow_id, overlay_id)
    healthy = get_workflow_rule(workflow_id)
    fault = assess_workflow_fault(graph, workflow_id, current, runtime, observed, expected)
    assert fault is not None
    return recommendation_evidence(
        fault,
        current,
        healthy,
        runtime,
        {"observed": observed, "expected": expected},
    )


def test_1042_evidence_json_has_missing_enterprise_case_not_incident_id():
    payload = _evidence(
        "derive_pricing_segment",
        "INC-1042",
        "DEAL-4821",
        {"deal_stage": "Contract Sent", "approval_required": False},
        {"approval_required": True},
    )
    assert payload["restrictions"]["fix_only_this_component"] is True
    assert "INC-1042" not in str(payload)
    assert "approval_required" not in payload.get("this_deal", {})
    assert "deal_stage" not in payload.get("this_deal", {})
    assert "Contract Sent" not in str(payload)
    cases = payload["rule_diff"]["missing_cases"]
    assert cases
    assert cases[0]["should_write"]["display_value"] == "Enterprise"
    assert payload["this_deal"]["customer_tier"]["display_value"] == "Enterprise"
    assert payload["this_component"]["how_to_refer"] == "derive pricing segment"


def test_claude_recommendation_uses_only_client_output():
    class _Fake:
        def call_with_structured_output(self, **kwargs):
            from diagnosis.recommend import RecommendationCopy

            assert "restrictions" in kwargs["prompt"]
            assert "INC-1042" not in kwargs["prompt"]
            return RecommendationCopy(recommendation="Restore the Enterprise case on Derive Pricing Segment."), {}

    graph = load_graph()
    runtime = get_runtime("DEAL-4821")
    current = get_workflow_rule("derive_pricing_segment", "INC-1042")
    healthy = get_workflow_rule("derive_pricing_segment")
    fault = assess_workflow_fault(
        graph,
        "derive_pricing_segment",
        current,
        runtime,
        {"deal_stage": "Contract Sent", "approval_required": False},
        {"approval_required": True},
    )
    text = build_recommended_check(fault, current, healthy, runtime, client=_Fake())
    assert text == "Restore the Enterprise case on Derive Pricing Segment."
