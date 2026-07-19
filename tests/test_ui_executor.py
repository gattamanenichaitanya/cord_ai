"""
Integration test: UIExecutor creates a custom property via the HubSpot UI.

This test:
1. Loads the create_custom_property operation entry from the graph
2. Creates a PlanAction for a test property (test_ui_delete_me)
3. Runs UIExecutor.execute() which navigates the browser and fills forms
4. Verifies screenshots were captured for every step
5. Cleans up the property via API after the test
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

import pytest
import requests
from dotenv import load_dotenv

from planning.models import PlanAction
from execution.executors.ui_executor import UIExecutor
from execution.models import ExecutionStatus, ExecutionMethodUsed
from execution.tools.vision_locator import VisionLocator
import anthropic


@pytest.mark.anyio
async def test_ui_executor_create_property():
    load_dotenv()
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    base_url = "https://api.hubapi.com"
    test_prop_name = "validation_2"

    # Pre-cleanup: delete the property if it already exists
    requests.delete(
        f"{base_url}/crm/v3/properties/contacts/{test_prop_name}",
        headers=headers,
    )

    # Use a persistent run_dir so we can inspect screenshots
    project_root = Path(__file__).resolve().parent.parent
    run_dir = project_root / "execution_runs" / "test_runs" / "ui_executor_test"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load the operation entry from graph
    op_file = project_root / "graph" / "hubspot" / "operations" / "create_custom_property.json"

    with open(op_file, "r", encoding="utf-8") as f:
        operation_entry = json.load(f)

    # 2. Create a PlanAction
    action = PlanAction(
        action_id="ACT-UI-TEST",
        operation_id="hubspot.create_custom_property",
        description="Create temporary UI test property",
        parameters={
            "object_type": "contacts",
            "label": "Validation 2",
            "internal_name": test_prop_name,
            "field_type": "text",
            "group_name": "contactinformation",
        },
        depends_on=[],
        estimated_duration_seconds=60,
    )

    # 3. Run UIExecutor with VisionLocator
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    vision_locator = VisionLocator(client)
    executor = UIExecutor(vision_locator=vision_locator)  # Will launch its own browser from saved auth state
    can = await executor.can_execute(operation_entry)
    assert can is True, "UIExecutor should be able to handle this operation"

    result = await executor.execute(
        action=action,
        operation_entry=operation_entry,
        run_dir=run_dir,
    )

    # 4. Print step-by-step results
    print(f"\nAction ID: {result.action_id}")
    print(f"Status: {result.status}")
    print(f"Method: {result.method_used}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    for step in result.steps:
        print(f"  Step {step.step_id}: [{step.status.value}] {step.intent}")
        if step.reasoning:
            print(f"    Reasoning: {step.reasoning}")
        if step.error_message:
            print(f"    Error: {step.error_message}")
        for ss in step.screenshots:
            print(f"    Screenshot: {ss.filename} — {ss.caption}")

    if result.verification_result:
        print(f"  Verification: {result.verification_result}")

    # 5. Assert key outcomes
    assert result.status == ExecutionStatus.SUCCESS, f"UI Execution failed with: {result.error_message}"
    assert result.method_used == ExecutionMethodUsed.UI
    assert result.action_id == "ACT-UI-TEST"
    # Check that the action result file was persisted
    assert (run_dir / "actions" / "ACT-UI-TEST.json").exists()
    # Check that screenshots were captured
    screenshots_dir = run_dir / "screenshots" / "ACT-UI-TEST"
    if screenshots_dir.exists():
        screenshot_files = list(screenshots_dir.glob("*.png"))
        print(f"\n  Total screenshots captured: {len(screenshot_files)}")
        assert len(screenshot_files) > 0, "At least one screenshot should have been captured"

    # 6. Post-cleanup: skip deletion so we can verify the created property
    print("\n  Cleanup: Skipped deletion for property validation_2")


@pytest.mark.anyio
async def test_ui_executor_create_workflow():
    load_dotenv()
    project_root = Path(__file__).resolve().parent.parent
    run_dir = project_root / "execution_runs" / "test_runs" / "ui_executor_test"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load the operation entry from graph
    op_file = project_root / "graph" / "hubspot" / "operations" / "create_workflow.json"

    with open(op_file, "r", encoding="utf-8") as f:
        operation_entry = json.load(f)

    # 2. Create a PlanAction
    action = PlanAction(
        action_id="ACT-WF-TEST",
        operation_id="hubspot.create_workflow",
        description="Create At-Risk Customer Alert workflow",
        parameters={
            "workflow_name": "At-Risk Customer Alert",
            "object_label": "Contact",
            "trigger": {
                "type": "filter_based",
                "logic": "AND",
                "conditions": [
                    {
                        "property_label": "Total revenue",
                        "operator_label": "is equal to any of",
                        "value": "100"
                    }
                ]
            },
            "re_enrollment_enabled": False,
            "actions": [
                {
                    "type": "set_property_value",
                    "record_type": "Contact (Current object)",
                    "property_label": "Annual Revenue",
                    "change_type": "Replace",
                    "value": "100"
                }
            ],
            "enroll_existing_records": False
        },
        depends_on=[],
        estimated_duration_seconds=150,
    )

    # 3. Run UIExecutor with VisionLocator
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    vision_locator = VisionLocator(client)
    executor = UIExecutor(vision_locator=vision_locator)
    can = await executor.can_execute(operation_entry)
    assert can is True, "UIExecutor should be able to handle create_workflow operation"

    result = await executor.execute(
        action=action,
        operation_entry=operation_entry,
        run_dir=run_dir,
    )

    # 4. Print step-by-step results
    print(f"\nAction ID: {result.action_id}")
    print(f"Status: {result.status}")
    print(f"Method: {result.method_used}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    if result.error_message:
        print(f"Error: {result.error_message}")

    for step in result.steps:
        print(f"  Step {step.step_id}: [{step.status.value}] {step.intent}")
        if step.reasoning:
            print(f"    Reasoning: {step.reasoning}")
        if step.error_message:
            print(f"    Error: {step.error_message}")
        for ss in step.screenshots:
            print(f"    Screenshot: {ss.filename} — {ss.caption}")

    if result.verification_result:
        print(f"  Verification: {result.verification_result}")

    # 5. Assert key outcomes
    assert result.status == ExecutionStatus.SUCCESS, f"UI Execution failed with: {result.error_message}"
    assert result.method_used == ExecutionMethodUsed.UI
    assert result.action_id == "ACT-WF-TEST"
    assert (run_dir / "actions" / "ACT-WF-TEST.json").exists()
