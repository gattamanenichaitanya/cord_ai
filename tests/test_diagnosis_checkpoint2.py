"""Checkpoint 2: runtime, rules, policies, expectation evaluation."""

from diagnosis.changes import get_recent_changes
from diagnosis.expectations import (
    ExpectationStatus,
    evaluate_expectations,
    violations,
)
from diagnosis.fields import CANONICAL_FIELDS, FORBIDDEN_ALIASES
from diagnosis.rules import get_workflow_rule, predicted_writes, rules_for_incident
from diagnosis.runtime import get_runtime, load_runtime
import pytest


def test_runtime_records_use_canonical_fields_only():
    records = load_runtime()
    assert set(records) >= {"DEAL-4821", "DEAL-4920", "DEAL-5033", "DEAL-5101", "DEAL-OK"}
    for state in records.values():
        assert set(state.values) == CANONICAL_FIELDS
        for alias in FORBIDDEN_ALIASES:
            assert alias not in state.as_dict()


def test_unknown_deal_raises():
    with pytest.raises(KeyError):
        get_runtime("DEAL-MISSING")


def test_enterprise_policy_violated_on_deal_4821():
    runtime = get_runtime("DEAL-4821")
    results = evaluate_expectations(runtime)
    finance = next(r for r in results if r.policy_id == "enterprise_finance_approval_policy")
    assert finance.status is ExpectationStatus.VIOLATED
    assert finance.subject_node == "deal_stage"
    assert finance.observed == {"deal_stage": "Contract Sent", "approval_required": False}
    assert finance.expected == {"approval_required": True}
    assert "Finance approval" in finance.summary


def test_same_policy_violated_on_deal_4920():
    runtime = get_runtime("DEAL-4920")
    finance = next(
        r
        for r in evaluate_expectations(runtime)
        if r.policy_id == "enterprise_finance_approval_policy"
    )
    assert finance.status is ExpectationStatus.VIOLATED


def test_policy_does_not_apply_to_smb_deals():
    for deal_id in ("DEAL-5033", "DEAL-5101", "DEAL-OK"):
        finance = next(
            r
            for r in evaluate_expectations(get_runtime(deal_id))
            if r.policy_id == "enterprise_finance_approval_policy"
        )
        assert finance.status is ExpectationStatus.NOT_APPLICABLE, deal_id


def test_fulfillment_expectation_violated_on_deal_5101():
    runtime = get_runtime("DEAL-5101")
    fulfillment = next(
        r
        for r in evaluate_expectations(runtime)
        if r.policy_id == "fulfillment_after_contract_sent"
    )
    assert fulfillment.status is ExpectationStatus.VIOLATED
    assert fulfillment.observed["fulfillment_started"] is False
    assert fulfillment.expected == {"fulfillment_started": True}


def test_healthy_deal_has_no_violations():
    results = evaluate_expectations(get_runtime("DEAL-OK"))
    assert violations(results) == []
    statuses = {r.policy_id: r.status for r in results}
    assert statuses["enterprise_finance_approval_policy"] is ExpectationStatus.NOT_APPLICABLE
    assert statuses["fulfillment_after_contract_sent"] is ExpectationStatus.SATISFIED
    assert statuses["smb_no_finance_approval"] is ExpectationStatus.SATISFIED


def test_healthy_derive_rule_writes_enterprise_for_4821():
    runtime = get_runtime("DEAL-4821")
    healthy = get_workflow_rule("derive_pricing_segment")
    assert predicted_writes(healthy, runtime) == {"pricing_segment": "Enterprise"}


def test_broken_derive_overlay_does_not_write_enterprise():
    runtime = get_runtime("DEAL-4821")
    broken = get_workflow_rule("derive_pricing_segment", incident_id="INC-1042")
    assert predicted_writes(broken, runtime) == {}
    assert runtime.get("pricing_segment") is None


def test_healthy_vs_broken_discount_governance_on_4920():
    runtime = get_runtime("DEAL-4920")
    healthy = get_workflow_rule("discount_governance")
    broken = get_workflow_rule("discount_governance", incident_id="INC-1188")
    assert predicted_writes(healthy, runtime) == {"approval_required": True}
    assert predicted_writes(broken, runtime) == {"approval_required": False}
    assert runtime.get("approval_required") is False


def test_legacy_override_overlay_writes_approval_on_5033():
    runtime = get_runtime("DEAL-5033")
    healthy = get_workflow_rule("legacy_discount_override")
    broken = get_workflow_rule("legacy_discount_override", incident_id="INC-2201")
    assert predicted_writes(healthy, runtime) == {}
    assert predicted_writes(broken, runtime) == {"approval_required": True}


def test_disabled_fulfillment_overlay_writes_nothing():
    runtime = get_runtime("DEAL-5101")
    healthy = get_workflow_rule("fulfillment_workflow")
    broken = get_workflow_rule("fulfillment_workflow", incident_id="INC-3310")
    assert predicted_writes(healthy, runtime) == {"fulfillment_started": True}
    assert predicted_writes(broken, runtime) == {}
    assert broken["enabled"] is False


def test_incident_overlay_does_not_replace_unrelated_rules():
    merged = rules_for_incident("INC-1042")
    assert merged["discount_governance"]["rule"]["all"][0]["value"] == 100000
    assert "SMB" in str(merged["derive_pricing_segment"])
    assert "Enterprise" not in str(merged["derive_pricing_segment"]["rule"]["cases"])


def test_change_history_for_derive_pricing_segment():
    changes = get_recent_changes("derive_pricing_segment")
    assert len(changes) == 1
    assert changes[0]["id"] == "CHANGE-1007"
    assert changes[0]["modified_node_id"] == "derive_pricing_segment"
    assert get_recent_changes("discount_governance") == []
