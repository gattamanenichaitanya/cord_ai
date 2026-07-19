"""
hubspot_qa.py
=============
Handles the INSPECT_HUBSPOT intent by:
  1. Fetching live data from the HubSpot portal (properties, workflows, objects).
  2. Passing the raw data + user question to Claude for a conversational answer.

This module is deliberately isolated so it can be tested independently
without touching any Streamlit state.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from tools.hubspot_inspector import make_request, APIError, STANDARD_OBJECTS


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def answer_hubspot_question(
    question: str,
    inspect_object: str,
    client,  # ClaudeClient
) -> str:
    """
    Fetch the relevant live HubSpot data needed to answer `question`
    and return a Claude-synthesised conversational answer.

    Parameters
    ----------
    question       : The user's raw question string.
    inspect_object : HubSpot object type to query ('contacts', 'companies', etc.)
    client         : Initialised ClaudeClient instance.

    Returns
    -------
    A markdown-safe string ready to be displayed in the chat.
    """
    object_type = _normalise_object_type(inspect_object or "contacts")

    # 1. Decide what data is needed and fetch it
    fetched: dict[str, Any] = {}

    question_lower = question.lower()

    # Always fetch the full property list for the object (it covers most questions)
    fetched["properties"] = _fetch_properties(object_type)

    # If the question mentions workflows / automation, also fetch workflows
    if any(kw in question_lower for kw in ["workflow", "automation", "flow", "sequence"]):
        fetched["workflows"] = _fetch_workflows()

    # If the question asks about property groups specifically
    if any(kw in question_lower for kw in ["group", "groups"]):
        fetched["property_groups"] = _fetch_property_groups(object_type)

    # If the question explicitly asks for custom objects
    if any(kw in question_lower for kw in ["custom object", "schema"]):
        fetched["custom_objects"] = _fetch_custom_objects()

    # 2. Build a synthesis prompt and ask Claude
    return _synthesise(question, object_type, fetched, client)


# ─────────────────────────────────────────────────────────────────────────────
# HubSpot fetch helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_properties(object_type: str) -> dict:
    """Return a compact summary of all properties for the object."""
    try:
        data = make_request("GET", f"/crm/v3/properties/{object_type}")
        results = data.get("results", [])
        # Return a compact representation to keep the Claude prompt short
        compact = [
            {
                "name": p.get("name"),
                "label": p.get("label"),
                "type": p.get("type"),
                "fieldType": p.get("fieldType"),
                "groupName": p.get("groupName"),
                "hubspotDefined": p.get("hubspotDefined", True),
            }
            for p in results
        ]
        return {"ok": True, "count": len(compact), "properties": compact}
    except APIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _fetch_property_groups(object_type: str) -> dict:
    try:
        data = make_request("GET", f"/crm/v3/properties/{object_type}/groups")
        groups = [
            {"name": g.get("name"), "label": g.get("label")}
            for g in data.get("results", [])
        ]
        return {"ok": True, "groups": groups}
    except APIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _fetch_workflows() -> dict:
    try:
        try:
            data = make_request("GET", "/automation/v4/flows")
        except APIError:
            data = make_request("GET", "/automation/v3/workflows")
        workflows = [
            {"id": w.get("id"), "name": w.get("name"), "enabled": w.get("enabled")}
            for w in data.get("results", [])
        ]
        return {"ok": True, "count": len(workflows), "workflows": workflows}
    except APIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _fetch_custom_objects() -> dict:
    try:
        data = make_request("GET", "/crm/v3/schemas")
        schemas = [
            {
                "name": s.get("name"),
                "label": s.get("labels", {}).get("singular"),
                "objectTypeId": s.get("objectTypeId"),
            }
            for s in data.get("results", [])
        ]
        return {"ok": True, "schemas": schemas}
    except APIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Claude synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _synthesise(
    question: str,
    object_type: str,
    fetched: dict[str, Any],
    client,
) -> str:
    """Ask Claude to read the live portal data and answer the user's question."""

    # Serialise fetched data compactly (truncate huge property lists if needed)
    props_data = fetched.get("properties", {})
    properties = props_data.get("properties", [])

    # Keep full list but cap at 300 to avoid token explosion
    if len(properties) > 300:
        properties_excerpt = properties[:300]
        truncation_note = f"\n(Showing first 300 of {len(properties)} properties — full list truncated for brevity)"
    else:
        properties_excerpt = properties
        truncation_note = ""

    serialised_props = json.dumps(properties_excerpt, indent=None)
    serialised_extra = {}
    for key in ["workflows", "property_groups", "custom_objects"]:
        if key in fetched:
            serialised_extra[key] = fetched[key]

    extra_str = json.dumps(serialised_extra, indent=None) if serialised_extra else "None fetched."

    prompt = f"""You are a live HubSpot portal inspector assistant embedded in Cord AI.

A consultant has asked: "{question}"

I have just queried the LIVE HubSpot portal and retrieved the following data for the '{object_type}' object:

PROPERTIES ({props_data.get('count', 0)} total){truncation_note}:
{serialised_props}

ADDITIONAL DATA (workflows / groups / schemas if relevant):
{extra_str}

Instructions:
- Answer the consultant's question directly and clearly using ONLY the data above.
- Be specific: if a field exists, say so and give its internal name, label, type, and group.
- If a field does NOT exist in the data above, say it clearly: "No property called X was found on the {object_type} object in your HubSpot portal."
- If the question is about workflows, reference the workflow names and enabled status from the data.
- Keep the answer concise: 2–5 sentences unless a list is clearly needed.
- Do NOT say "based on the document" or "based on the requirements". This is LIVE portal data.
- Format field names as `code` for clarity.
"""

    try:
        return client.call_text(prompt, max_tokens=600)
    except Exception as e:
        return f"I fetched the live portal data but couldn't synthesise an answer: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_OBJECT_ALIASES: dict[str, str] = {
    "contact": "contacts",
    "contacts": "contacts",
    "company": "companies",
    "companies": "companies",
    "deal": "deals",
    "deals": "deals",
    "ticket": "tickets",
    "tickets": "tickets",
    "product": "products",
    "products": "products",
    "quote": "quotes",
    "quotes": "quotes",
    "line item": "line_items",
    "line_items": "line_items",
}


def _normalise_object_type(raw: str) -> str:
    key = raw.strip().lower()
    return _OBJECT_ALIASES.get(key, key)
