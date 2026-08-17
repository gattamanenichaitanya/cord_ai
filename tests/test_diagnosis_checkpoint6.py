"""Checkpoint 6 helpers that do not call Claude."""

from diagnosis.fault import assess_workflow_fault
from diagnosis.graph import load_graph
from diagnosis.loop import select_primary_discrepancy
from diagnosis.parser import parse_incident
from diagnosis.rules import get_workflow_rule
from diagnosis.runtime import get_runtime
from diagnosis.expectations import evaluate_expectations


def test_primary_discrepancy_prefers_unexpected_claim_subject():
    parsed = parse_incident("INC-1042")
    results = evaluate_expectations(get_runtime("DEAL-4821"))
    primary = select_primary_discrepancy(parsed, results)
    assert primary is not None
    assert primary.policy_id == "enterprise_finance_approval_policy"
    assert primary.subject_node == "deal_stage"


def test_5101_primary_discrepancy_is_fulfillment():
    parsed = parse_incident("INC-3310")
    results = evaluate_expectations(get_runtime("DEAL-5101"))
    primary = select_primary_discrepancy(parsed, results)
    assert primary is not None
    assert primary.subject_node == "fulfillment_started"


def test_fault_missing_write_on_broken_derive():
    graph = load_graph()
    runtime = get_runtime("DEAL-4821")
    rule = get_workflow_rule("derive_pricing_segment", "INC-1042")
    fault = assess_workflow_fault(
        graph,
        "derive_pricing_segment",
        rule,
        runtime,
        {"deal_stage": "Contract Sent", "approval_required": False},
        {"approval_required": True},
    )
    assert fault is not None
    assert fault.kind == "missing_write"


def test_healthy_derive_is_not_a_fault_when_segment_populated():
    graph = load_graph()
    runtime = get_runtime("DEAL-4920")
    rule = get_workflow_rule("derive_pricing_segment")
    fault = assess_workflow_fault(
        graph,
        "derive_pricing_segment",
        rule,
        runtime,
        {"approval_required": False},
        {"approval_required": True},
    )
    assert fault is None


def test_broken_discount_governance_is_incorrect_write():
    graph = load_graph()
    runtime = get_runtime("DEAL-4920")
    rule = get_workflow_rule("discount_governance", "INC-1188")
    fault = assess_workflow_fault(
        graph,
        "discount_governance",
        rule,
        runtime,
        {"approval_required": False, "deal_stage": "Contract Sent"},
        {"approval_required": True},
    )
    assert fault is not None
    assert fault.kind == "incorrect_write"
