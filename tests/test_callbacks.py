import pytest
import asyncio
from datetime import datetime
from pathlib import Path
from planning.models import ImplementationPlan, PlanAction
from execution.orchestrator import execute_plan
from execution.models import ExecutionStatus, ExecutionReport

class DummyProgressCallback:
    def __init__(self):
        self.events = []
    
    def on_action_start(self, action_id, description, method):
        self.events.append(("action_start", action_id, description, method))
        
    def on_step_start(self, action_id, step_id, intent):
        self.events.append(("step_start", action_id, step_id, intent))
        
    def on_step_complete(self, action_id, step_id, intent, status):
        self.events.append(("step_complete", action_id, step_id, intent, status))
        
    def on_healing(self, action_id, step_id, message):
        self.events.append(("healing", action_id, step_id, message))
        
    def on_action_complete(self, action_id, status, duration):
        self.events.append(("action_complete", action_id, status, duration))
        
    def on_plan_complete(self, report):
        self.events.append(("plan_complete", report.plan_id))

@pytest.mark.anyio
async def test_callbacks_firing():
    # Construct a simple dummy plan
    plan = ImplementationPlan(
        plan_id="test_plan_callbacks",
        requirement_id="REQ-TEST",
        requirement_title="Test Callbacks",
        document_source="test.md",
        approach_summary="Test approach",
        created_at=datetime.now(),
        rationale="Test rationale",
        identified_gaps=[],
        actions=[
            PlanAction(
                action_id="ACT-1",
                operation_id="hubspot.create_custom_property", # will try to load this operation JSON
                description="Test Action 1",
                depends_on=[],
                estimated_duration_seconds=60,
                parameters={
                    "object_type": "contacts",
                    "name": "test_prop",
                    "label": "Test Prop",
                    "type": "string",
                    "field_type": "text",
                    "group_name": "contactinformation"
                }
            )
        ]
    )
    
    callback = DummyProgressCallback()
    
    # We execute with dry_run = True to avoid hitting real HubSpot/Playwright
    report = await execute_plan(
        plan,
        progress_callback=callback,
        dry_run=True,
        demo_mode=True
    )
    
    # Verify the callback events
    assert len(callback.events) >= 3
    assert callback.events[0][0] == "action_start"
    assert callback.events[0][1] == "ACT-1"
    
    assert callback.events[-2][0] == "action_complete"
    assert callback.events[-2][1] == "ACT-1"
    assert callback.events[-2][2] == ExecutionStatus.SKIPPED # dry run skips
    
    assert callback.events[-1][0] == "plan_complete"
    assert callback.events[-1][1] == "test_plan_callbacks"
    
    print("Callback test passed successfully!")

from unittest.mock import AsyncMock, MagicMock
from execution.executors.ui_executor import UIExecutor

@pytest.mark.anyio
async def test_ui_executor_step_callbacks():
    # Mock playwright page
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.screenshot = AsyncMock()
    
    # We will pass a mocked page to UIExecutor
    callback = DummyProgressCallback()
    executor = UIExecutor(page=mock_page, progress_callback=callback)
    
    action = PlanAction(
        action_id="ACT-2",
        operation_id="hubspot.create_custom_property",
        description="Test Action 2",
        depends_on=[],
        estimated_duration_seconds=60,
        parameters={
            "object_type": "contacts",
            "name": "test_prop",
            "label": "Test Prop",
            "type": "string",
            "field_type": "text",
            "group_name": "contactinformation"
        }
    )
    
    # Mock _take_screenshot
    from execution.models import ScreenshotRecord
    executor._take_screenshot = AsyncMock(return_value=ScreenshotRecord(
        filename="dummy.png",
        caption="Dummy caption",
        timestamp=datetime.now(),
        step_id=0
    ))
    
    # We mock _run_verification and _execute_step so we don't need real selectors
    executor._run_verification = AsyncMock(return_value={"success": True})
    
    from execution.models import ExecutionStep
    executor._execute_step = AsyncMock(return_value=ExecutionStep(
        step_id=1,
        intent="Click create property button",
        status=ExecutionStatus.SUCCESS,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        screenshots=[]
    ))
    
    operation_entry = {
        "execution_methods": [
            {
                "method": "ui",
                "navigation": {
                    "url_pattern": "https://app.hubspot.com/property-settings/{portal_id}"
                },
                "steps": [
                    {
                        "step_id": 1,
                        "intent": "Click create property button",
                        "action": "click",
                        "element_to_find": {
                            "primary_role": "button",
                            "primary_label": "Create property"
                        }
                    }
                ]
            }
        ]
    }
    
    # Run the UI executor
    result = await executor.execute(
        action=action,
        operation_entry=operation_entry,
        run_dir=Path("scratch")
    )
    
    # Verify step callbacks
    # Steps are: navigate (step 0), then click (step 1)
    step_starts = [e for e in callback.events if e[0] == "step_start"]
    step_completes = [e for e in callback.events if e[0] == "step_complete"]
    
    assert len(step_starts) == 2
    assert step_starts[0] == ("step_start", "ACT-2", 0, "Navigate to target URL")
    assert step_starts[1] == ("step_start", "ACT-2", 1, "Click create property button")
    
    assert len(step_completes) == 2
    assert step_completes[0][0] == "step_complete"
    assert step_completes[0][1] == "ACT-2"
    assert step_completes[0][2] == 0
    assert step_completes[0][4] == ExecutionStatus.SUCCESS

if __name__ == "__main__":
    asyncio.run(test_callbacks_firing())
    asyncio.run(test_ui_executor_step_callbacks())
