from datetime import datetime
import pytest
from planning.models import (
    RequirementType,
    ExtractedRequirement,
    Stage1Output,
    CandidateGraphEntry,
    Stage2Output,
    ArchitectureDecision,
    StateInspectionItem,
    Stage4Output,
    Severity,
    Gap,
    Stage5Output,
    PlanAction,
    Stage6Output,
    ImplementationPlan,
)


def test_stage_1_models():
    req = ExtractedRequirement(
        id="REQ-001",
        title="Custom Property",
        description="Create custom property for customer tier",
        requirement_type=RequirementType.PROPERTY_CONFIGURATION,
        source_section="Section 3.1",
        source_excerpt="Add customer tier property",
        dependencies=[],
    )
    s1 = Stage1Output(
        document_summary="Summary of requirements document",
        requirements=[req],
        extraction_metadata={"tokens": 150},
    )

    json_str = s1.model_dump_json()
    s1_restored = Stage1Output.model_validate_json(json_str)

    assert s1_restored.document_summary == s1.document_summary
    assert len(s1_restored.requirements) == 1
    assert s1_restored.requirements[0].id == "REQ-001"


def test_stage_2_models():
    candidate = CandidateGraphEntry(
        entry_id="notes_last_contacted",
        entry_type="standard_property",
        file_path="graph/hubspot/properties/notes_last_contacted.json",
        relevance_score=0.95,
        reasoning="Matches last contact timestamp",
    )
    s2 = Stage2Output(
        requirement_id="REQ-001",
        candidates=[candidate],
        interpretation="Need to track last contact date",
        ambiguities=["Which channel counts?"],
    )

    json_str = s2.model_dump_json()
    s2_restored = Stage2Output.model_validate_json(json_str)

    assert s2_restored.requirement_id == "REQ-001"
    assert s2_restored.candidates[0].relevance_score == 0.95


def test_stage_3_models():
    decision = ArchitectureDecision(
        requirement_id="REQ-001",
        chosen_approach="Use standard property notes_last_contacted",
        rationale="Property already exists natively",
        selected_capabilities=["custom_property"],
        selected_operations=["hubspot.create_custom_property"],
        parameters={"property_name": "customer_tier"},
        rejected_alternatives=[{"approach": "custom text field", "reason": "redundant"}],
    )

    json_str = decision.model_dump_json()
    decision_restored = ArchitectureDecision.model_validate_json(json_str)

    assert decision_restored.chosen_approach == decision.chosen_approach
    assert decision_restored.parameters["property_name"] == "customer_tier"


def test_stage_4_models():
    item = StateInspectionItem(
        item_type="property",
        item_id="customer_tier",
        exists=False,
        details=None,
    )
    s4 = Stage4Output(
        requirement_id="REQ-001",
        inspected_items=[item],
        inspection_summary="Property customer_tier does not exist yet",
    )

    json_str = s4.model_dump_json()
    s4_restored = Stage4Output.model_validate_json(json_str)

    assert s4_restored.inspected_items[0].exists is False


def test_stage_5_models():
    gap = Gap(
        gap_id="GAP-001",
        severity=Severity.HIGH,
        title="Missing property",
        description="Property must be created prior to workflow setup",
        referenced_gotcha="property_internal_name_immutable",
        suggested_resolution="Create property first",
        blocks_execution=True,
    )
    s5 = Stage5Output(
        requirement_id="REQ-001",
        gaps=[gap],
        summary="Found 1 high-severity gap",
    )

    json_str = s5.model_dump_json()
    s5_restored = Stage5Output.model_validate_json(json_str)

    assert s5_restored.gaps[0].severity == Severity.HIGH
    assert s5_restored.gaps[0].blocks_execution is True


def test_stage_6_models():
    action = PlanAction(
        action_id="ACT-001",
        operation_id="hubspot.create_custom_property",
        description="Create customer_tier property",
        parameters={"name": "customer_tier", "label": "Customer Tier"},
        depends_on=[],
        estimated_duration_seconds=15,
    )
    s6 = Stage6Output(
        requirement_id="REQ-001",
        actions=[action],
        execution_order_rationale="Property must be created first",
    )

    json_str = s6.model_dump_json()
    s6_restored = Stage6Output.model_validate_json(json_str)

    assert len(s6_restored.actions) == 1
    assert s6_restored.actions[0].action_id == "ACT-001"


def test_stage_7_models():
    action = PlanAction(
        action_id="ACT-001",
        operation_id="hubspot.create_custom_property",
        description="Create customer_tier property",
        parameters={"name": "customer_tier", "label": "Customer Tier"},
        depends_on=[],
        estimated_duration_seconds=15,
    )
    gap = Gap(
        gap_id="GAP-001",
        severity=Severity.MEDIUM,
        title="Unconfirmed naming",
        description="Internal name needs signoff",
        suggested_resolution="Confirm with consultant",
        blocks_execution=False,
    )
    plan = ImplementationPlan(
        plan_id="PLAN-20260628-001",
        requirement_id="REQ-001",
        requirement_title="Customer Tier Property Setup",
        document_source="docs/requirements.docx",
        actions=[action],
        chosen_approach="Create custom dropdown property",
        rationale="Best fits reporting requirements",
        identified_gaps=[gap],
        created_at=datetime.now(),
        pipeline_metadata={"stages_completed": 7},
        approved=False,
        approval_notes=None,
    )

    json_str = plan.model_dump_json()
    plan_restored = ImplementationPlan.model_validate_json(json_str)

    assert plan_restored.plan_id == plan.plan_id
    assert plan_restored.actions[0].operation_id == "hubspot.create_custom_property"
    assert plan_restored.approved is False
