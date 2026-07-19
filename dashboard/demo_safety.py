import os
import requests
import streamlit as st

BASE_URL = "https://api.hubapi.com"

def _get_headers():
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def check_hubspot_connection() -> bool:
    """Verifies that the private app token is valid and can connect to HubSpot."""
    headers = _get_headers()
    try:
        # Check access to contact object properties
        url = f"{BASE_URL}/crm/v3/properties/contacts/email"
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False

def reset_demo_state() -> dict:
    """
    Deletes the demo properties and workflows created by the CordAI POC.
    Returns a dictionary summarizing deleted items.
    """
    headers = _get_headers()
    summary = {"deleted_properties": [], "deleted_workflows": [], "errors": []}
    
    # 1. Properties to delete
    props_to_delete = ["acs_risk_score", "acs_nps_score", "acs_customer_segment"]
    for prop in props_to_delete:
        try:
            url = f"{BASE_URL}/crm/v3/properties/contacts/{prop}"
            # Check if it exists first
            check_resp = requests.get(url, headers=headers, timeout=10)
            if check_resp.status_code == 200:
                del_resp = requests.delete(url, headers=headers, timeout=10)
                if del_resp.status_code in (204, 200):
                    summary["deleted_properties"].append(prop)
                else:
                    summary["errors"].append(f"Failed to delete property {prop}: Status {del_resp.status_code}")
        except Exception as e:
            summary["errors"].append(f"Error checking/deleting property {prop}: {str(e)}")

    # 2. Workflows to delete
    # Try V3 workflows first
    try:
        url = f"{BASE_URL}/automation/v3/workflows"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            wf_data = resp.json()
            workflows = wf_data.get("workflows", [])
            for wf in workflows:
                wf_id = wf.get("id")
                wf_name = wf.get("name", "")
                # Delete any workflows created by our demo (starting with ACS or containing "At-Risk Customer")
                if wf_name.startswith("ACS ") or "At-Risk Customer" in wf_name:
                    del_url = f"{BASE_URL}/automation/v3/workflows/{wf_id}"
                    del_resp = requests.delete(del_url, headers=headers, timeout=10)
                    if del_resp.status_code in (200, 204):
                        summary["deleted_workflows"].append(wf_name)
                    else:
                        summary["errors"].append(f"Failed to delete workflow '{wf_name}' (ID {wf_id}): Status {del_resp.status_code}")
    except Exception as e:
        summary["errors"].append(f"Error listing/deleting workflows (V3): {str(e)}")

    # Also try V4 flows just in case
    try:
        url = f"{BASE_URL}/automation/v4/flows"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            flow_data = resp.json()
            flows = flow_data.get("results", [])
            for flow in flows:
                flow_id = flow.get("id")
                flow_name = flow.get("name", "")
                if flow_name.startswith("ACS ") or "At-Risk Customer" in flow_name:
                    if flow_name not in summary["deleted_workflows"]:
                        del_url = f"{BASE_URL}/automation/v4/flows/{flow_id}"
                        del_resp = requests.delete(del_url, headers=headers, timeout=10)
                        if del_resp.status_code in (200, 204):
                            summary["deleted_workflows"].append(flow_name)
                        else:
                            summary["errors"].append(f"Failed to delete flow '{flow_name}' (ID {flow_id}): Status {del_resp.status_code}")
    except Exception as e:
        # Don't error out if V4 is simply not supported in this portal
        pass

    return summary

def get_session_cost() -> float:
    """Calculates session cost using in-memory plan counts and execution report values."""
    # LLM costs (estimated standard prices: Sonnet 3.5 input/output, Flash 3.5)
    # Plus Vision API costs from execution reports
    total_cost = 0.0
    
    # 1. Base cost for each plan generated (approx $0.05 per stage pipeline)
    plans_count = len(st.session_state.get("plans", {}))
    total_cost += plans_count * 0.15 # 15 cents per plan (5 stages of Sonnet)
    
    # 2. Vision API costs from the current execution report
    report = st.session_state.get("execution_report")
    if report:
        total_cost += getattr(report, "api_cost_estimate", 0.0)
        
    return total_cost
