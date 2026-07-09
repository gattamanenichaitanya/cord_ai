import os
import json
import asyncio
from pathlib import Path
import pytest
import requests
from planning.models import PlanAction
from execution.executors.api_executor import APIExecutor
from execution.models import ExecutionStatus, ExecutionMethodUsed


def test_api_executor_can_execute():
    executor = APIExecutor()
    
    valid_op = {
        "operation_id": "hubspot.create_custom_property",
        "execution_methods": [
            {
                "method": "api",
                "preference_rank": 1
            }
        ]
    }
    
    invalid_op_1 = {
        "operation_id": "hubspot.create_custom_property",
        "execution_methods": [
            {
                "method": "ui",
                "preference_rank": 2
            }
        ]
    }

    assert asyncio.run(executor.can_execute(valid_op)) is True
    assert asyncio.run(executor.can_execute(invalid_op_1)) is False


@pytest.mark.integration
def test_api_executor_live_create_and_delete_property(tmp_path):
    # 1. Load the operation entry from graph
    project_root = Path(__file__).resolve().parent.parent
    op_file = project_root / "graph" / "hubspot" / "operations" / "create_custom_property.json"
    
    with open(op_file, "r", encoding="utf-8") as f:
        operation_entry = json.load(f)

    executor = APIExecutor()

    # Define a unique test property name (all lowercase for HubSpot compatibility)
    test_prop_name = "test_acs_delete_me"

    # Ensure it's deleted before we start (in case of previous dirty run)
    cleanup_url = f"{executor.base_url}/crm/v3/properties/contacts/{test_prop_name}"
    requests.delete(cleanup_url, headers=executor.headers)

    # 2. Create a PlanAction to create "test_acs_delete_me"
    action = PlanAction(
        action_id="ACT-TEST-CREATE",
        operation_id="hubspot.create_custom_property",
        description="Create temporary integration test property",
        parameters={
            "property_label": "Test ACS Delete Me",
            "internal_name": test_prop_name,
            "field_type": "text",
            "group_name": "contactinformation",
            "description": "Temporary property created by automated integration tests."
        },
        depends_on=[],
        estimated_duration_seconds=60
    )

    # 3. Run APIExecutor.execute()
    result = asyncio.run(executor.execute(
        action=action,
        operation_entry=operation_entry,
        run_dir=tmp_path
    ))

    # Assertions for successful creation & verification
    trace_file = tmp_path / "actions" / "ACT-TEST-CREATE_api_trace.json"
    if result.status == ExecutionStatus.FAILED:
        print(f"\n[Test Fail Info] Error message: {result.error_message}")
        if trace_file.exists():
            with open(trace_file, "r", encoding="utf-8") as f:
                print(f"[Test Fail Info] Trace Data: {f.read()}")
        
    assert result.status == ExecutionStatus.SUCCESS
    assert result.error_message is None
    assert result.verification_result is not None
    assert result.verification_result.get("success") is True
    
    # 4. Verify the property exists via HubSpot API
    check_resp = requests.get(cleanup_url, headers=executor.headers)
    assert check_resp.status_code == 200
    prop_data = check_resp.json()
    assert prop_data.get("name") == test_prop_name
    assert prop_data.get("label") == "Test ACS Delete Me"
    assert prop_data.get("type") == "string"
    assert prop_data.get("fieldType") == "text"

    # Cleanup: Delete the property
    delete_resp = requests.delete(cleanup_url, headers=executor.headers)
    assert delete_resp.status_code in (204, 200)
    
    # Verify it is deleted
    post_delete_resp = requests.get(cleanup_url, headers=executor.headers)
    assert post_delete_resp.status_code == 404
    print("Live property creation, verification, and cleanup succeeded!")
