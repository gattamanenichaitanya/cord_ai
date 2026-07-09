from datetime import datetime
import pytest
from execution.models import (
    ExecutionStatus,
    ExecutionMethodUsed,
    ScreenshotRecord,
    ExecutionStep,
    ActionResult,
    ExecutionReport,
)


def test_execution_models_serialization():
    # 1. ScreenshotRecord
    screenshot = ScreenshotRecord(
        step_id=1,
        filename="runs/run_01/screenshots/after_click.png",
        caption="After clicking Save button",
        timestamp=datetime.now()
    )
    
    # 2. ExecutionStep
    step = ExecutionStep(
        step_id=1,
        intent="Click Save button",
        status=ExecutionStatus.SUCCESS,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        reasoning="Located button using fallback text selector and clicked.",
        healing_attempts=0,
        screenshots=[screenshot]
    )
    
    # 3. ActionResult
    action_result = ActionResult(
        action_id="ACT-001",
        operation_id="hubspot.create_custom_property",
        method_used=ExecutionMethodUsed.API,
        status=ExecutionStatus.SUCCESS,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        duration_seconds=1.5,
        steps=[step],
        output_data={"created_property_id": "acs_risk_score"},
        verification_result={"property_exists": True}
    )
    
    # 4. ExecutionReport
    report = ExecutionReport(
        plan_id="plan_REQ-009_20260704_151651",
        plan_source_path="plans/plan_REQ-009_20260704_151651.json",
        run_dir="runs/run_01",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        overall_status=ExecutionStatus.SUCCESS,
        action_results=[action_result],
        total_duration_seconds=1.5,
        api_cost_estimate=0.015,
        summary="Plan executed successfully with 1 action completed via API."
    )

    # Verify serialization
    json_str = report.model_dump_json()
    restored = ExecutionReport.model_validate_json(json_str)

    assert restored.plan_id == report.plan_id
    assert restored.overall_status == ExecutionStatus.SUCCESS
    assert len(restored.action_results) == 1
    assert restored.action_results[0].action_id == "ACT-001"
    assert restored.action_results[0].steps[0].intent == "Click Save button"
    assert restored.action_results[0].steps[0].screenshots[0].caption == "After clicking Save button"
    print("Serialization test passed successfully!")
