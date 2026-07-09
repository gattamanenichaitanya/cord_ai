import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv

from planning.models import PlanAction
from execution.models import ActionResult, ExecutionStatus, ExecutionMethodUsed, ExecutionStep
from execution.executors.base import ExecutorBase


class APIExecutor(ExecutorBase):
    def __init__(self):
        load_dotenv()
        self.token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
        if not self.token:
            raise ValueError("HUBSPOT_PRIVATE_APP_TOKEN environment variable not set in .env")
        
        self.portal_id = os.environ.get("HUBSPOT_PORTAL_ID")
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def can_execute(self, operation_entry: dict) -> bool:
        """
        Check if this executor can handle the given operation.
        Returns True if operation_entry has an 'execution_methods' entry with method == 'api'
        and preference_rank >= 1.
        """
        methods = operation_entry.get("execution_methods", [])
        for m in methods:
            if m.get("method") == "api" and m.get("preference_rank", 0) >= 1:
                return True
        return False

    async def execute(
        self,
        action: PlanAction,
        operation_entry: dict,
        run_dir: Path
    ) -> ActionResult:
        """
        Execute one action. Returns the result with audit trail.
        """
        started_at = datetime.now()
        
        # 1. Find the API execution method
        api_method = None
        for m in operation_entry.get("execution_methods", []):
            if m.get("method") == "api":
                api_method = m
                break
                
        if not api_method:
            return ActionResult(
                action_id=action.action_id,
                operation_id=action.operation_id,
                method_used=ExecutionMethodUsed.API,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=0.0,
                error_message="No API method configuration found in operation schema."
            )

        # 2. Extract HTTP details
        endpoint = api_method.get("endpoint", "")
        if not endpoint or " " not in endpoint:
            return ActionResult(
                action_id=action.action_id,
                operation_id=action.operation_id,
                method_used=ExecutionMethodUsed.API,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=0.0,
                error_message=f"Invalid endpoint definition: '{endpoint}'"
            )
            
        http_method, path_template = endpoint.split(" ", 1)

        # 3. Path Parameter Substitution
        # Resolve common params
        object_type = action.parameters.get("object_type") or action.parameters.get("objectType") or "contacts"
        name = action.parameters.get("internal_name") or action.parameters.get("name") or ""

        url_path = (
            path_template.replace("{objectType}", object_type)
            .replace("{object_type}", object_type)
            .replace("{name}", name)
            .replace("{portalId}", self.portal_id or "")
            .replace("{portal_id}", self.portal_id or "")
        )
        url = f"{self.base_url}{url_path}"

        # 4. Payload Mapping for hubspot.create_custom_property
        payload = {}
        if action.operation_id == "hubspot.create_custom_property":
            params = action.parameters
            field_type = params.get("field_type") or params.get("type") or "text"

            type_map = {
                "number": ("number", "number"),
                "text": ("string", "text"),
                "textarea": ("string", "textarea"),
                "dropdown": ("enumeration", "select"),
                "date": ("date", "date"),
                "datetime": ("datetime", "date"),
                "booleancheckbox": ("bool", "booleancheckbox")
            }

            t_val, ft_val = type_map.get(field_type, ("string", "text"))

            payload = {
                "name": name,
                "label": params.get("property_label") or params.get("label") or name,
                "type": params.get("type") or t_val,
                "fieldType": params.get("fieldType") or ft_val,
                "groupName": params.get("group_name") or params.get("groupName") or "contactinformation"
            }

            if "description" in params:
                payload["description"] = params["description"]

            if (ft_val == "select" or payload["type"] == "enumeration") and "options" in params:
                raw_options = params.get("options", [])
                formatted_options = []
                for idx, opt in enumerate(raw_options):
                    if isinstance(opt, dict):
                        formatted_options.append({
                            "label": opt.get("label"),
                            "value": opt.get("value"),
                            "displayOrder": opt.get("displayOrder", idx),
                            "hidden": opt.get("hidden", False)
                        })
                    elif isinstance(opt, str):
                        formatted_options.append({
                            "label": opt,
                            "value": opt,
                            "displayOrder": idx,
                            "hidden": False
                        })
                payload["options"] = formatted_options
        else:
            # Default fallback: pass action parameters directly as payload
            payload = action.parameters

        # 5. Make the HTTP call with retries for 5xx
        status_code = None
        response_body = {}
        trace_data = {}
        
        step_start = datetime.now()
        step_status = ExecutionStatus.IN_PROGRESS

        for attempt in range(2):
            try:
                response = await asyncio.to_thread(
                    requests.request,
                    method=http_method,
                    url=url,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                status_code = response.status_code
                try:
                    response_body = response.json()
                except ValueError:
                    response_body = {"text": response.text}

                trace_data = {
                    "request": {
                        "method": http_method,
                        "url": url,
                        "headers": {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
                        "payload": payload
                    },
                    "response": {
                        "status_code": status_code,
                        "body": response_body
                    }
                }

                if status_code >= 500:
                    if attempt == 0:
                        print(f"[Warning] 5xx Server Error ({status_code}) on {action.action_id}. Retrying in 2 seconds...")
                        await asyncio.sleep(2)
                        continue
                break
            except Exception as e:
                status_code = 500
                response_body = {"error": str(e)}
                trace_data = {
                    "request": {"method": http_method, "url": url, "payload": payload},
                    "response": {"error": str(e)}
                }
                if attempt == 0:
                    print(f"[Warning] Network error ({e}) on {action.action_id}. Retrying in 2 seconds...")
                    await asyncio.sleep(2)
                    continue
                break

        step_end = datetime.now()

        # 6. Conflict Resolution (409) or Missing Scope (401)
        error_msg = None
        
        if status_code == 409:
            print(f"[Info] Conflict (409) detected for {name}. Checking schema match for conflict resolution...")
            try:
                check_url = f"{self.base_url}/crm/v3/properties/{object_type}/{name}"
                check_resp = await asyncio.to_thread(
                    requests.get,
                    url=check_url,
                    headers=self.headers,
                    timeout=30
                )
                if check_resp.status_code == 200:
                    existing_prop = check_resp.json()
                    
                    # Verify fields
                    expected_type = payload.get("type")
                    expected_field_type = payload.get("fieldType")
                    
                    actual_type = existing_prop.get("type")
                    actual_field_type = existing_prop.get("fieldType")
                    
                    type_matches = (actual_type == expected_type) and (actual_field_type == expected_field_type)
                    
                    options_match = True
                    if expected_field_type == "select" and "options" in payload:
                        existing_options = {opt.get("value") for opt in existing_prop.get("options", [])}
                        for expected_opt in payload["options"]:
                            if expected_opt["value"] not in existing_options:
                                options_match = False
                                break
                                
                    if type_matches and options_match:
                        print(f"[Info] Conflict resolved: Existing property '{name}' matches the expected schema.")
                        status_code = 200
                        response_body = existing_prop
                    else:
                        mismatch_reasons = []
                        if not type_matches:
                            mismatch_reasons.append(f"type mismatch (expected {expected_type}/{expected_field_type}, got {actual_type}/{actual_field_type})")
                        if not options_match:
                            mismatch_reasons.append("dropdown options mismatch")
                        error_msg = f"Conflict: Property '{name}' already exists but does not match expected schema: {', '.join(mismatch_reasons)}"
                else:
                    error_msg = f"Conflict: Property '{name}' already exists but fetch failed with status {check_resp.status_code}."
            except Exception as check_err:
                error_msg = f"Conflict: Property '{name}' already exists but verification check failed: {check_err}"
        
        elif status_code == 401:
            error_msg = "Authentication Error (401): Lacking required OAuth scope or Private App token is invalid. Please check and update your Private App scopes in HubSpot Settings."

        # Map to known failures if not handled and status is 4xx
        if status_code and 400 <= status_code < 500 and not error_msg:
            known_failures = api_method.get("known_failures", [])
            for kf in known_failures:
                if kf.get("status_code") == status_code:
                    error_msg = f"API Error {status_code}: {response_body.get('message', '')}. Recovery hint: {kf.get('recovery', '')}"
                    break
            if not error_msg:
                error_msg = f"API Error {status_code}: {response_body}"

        # 7. Verification Endpoint Call
        verification_result = None
        if "verification" in api_method and status_code in (200, 201) and not error_msg:
            v_info = api_method["verification"]
            v_method_path = v_info["method"]
            v_expected_status = v_info.get("expected_status", 200)

            v_parts = v_method_path.split(" ", 1)
            v_http_method = v_parts[0]
            v_path = v_parts[1]

            v_url_path = (
                v_path.replace("{objectType}", object_type)
                .replace("{object_type}", object_type)
                .replace("{name}", name)
            )
            v_url = f"{self.base_url}{v_url_path}"

            try:
                v_resp = await asyncio.to_thread(
                    requests.request,
                    method=v_http_method,
                    url=v_url,
                    headers=self.headers,
                    timeout=30
                )
                v_success = (v_resp.status_code == v_expected_status)
                try:
                    v_body = v_resp.json()
                except ValueError:
                    v_body = {"text": v_resp.text}

                verification_result = {
                    "success": v_success,
                    "status_code": v_resp.status_code,
                    "body": v_body
                }
                
                if not v_success:
                    error_msg = f"Post-execution verification failed. Expected {v_expected_status}, got {v_resp.status_code}."
            except Exception as v_err:
                verification_result = {
                    "success": False,
                    "error": str(v_err)
                }
                error_msg = f"Verification check failed with exception: {v_err}"

        # 8. Build final Step & Result
        step_status = ExecutionStatus.SUCCESS if (status_code in (200, 201) and not error_msg) else ExecutionStatus.FAILED
        
        exec_step = ExecutionStep(
            step_id=1,
            intent=f"Make {http_method} request to {url_path}",
            status=step_status,
            started_at=step_start,
            completed_at=step_end,
            error_message=error_msg,
            reasoning=f"Initiated call for operation {action.operation_id} to HubSpot."
        )

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        action_result = ActionResult(
            action_id=action.action_id,
            operation_id=action.operation_id,
            method_used=ExecutionMethodUsed.API,
            status=step_status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            steps=[exec_step],
            output_data=response_body if step_status == ExecutionStatus.SUCCESS else {},
            error_message=error_msg,
            verification_result=verification_result
        )

        # 9. Persistence
        actions_dir = run_dir / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)

        result_file = actions_dir / f"{action.action_id}.json"
        result_file.write_text(action_result.model_dump_json(indent=2), encoding="utf-8")

        trace_file = actions_dir / f"{action.action_id}_api_trace.json"
        trace_file.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")

        return action_result
