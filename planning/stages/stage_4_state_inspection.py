import json
import sys
from pathlib import Path
from typing import Dict, Any, List

from tools.hubspot_inspector import make_request, APIError, STANDARD_OBJECTS
from planning.claude_client import ClaudeClient
from planning.models import ExtractedRequirement, ArchitectureDecision, Stage4Output, StateInspectionItem


def run_stage_4(
    requirement: ExtractedRequirement,
    architecture_decision: ArchitectureDecision,
    run_dir: Path
) -> Stage4Output:
    parameters = architecture_decision.parameters or {}
    inspected_items: List[StateInspectionItem] = []

    # 1. Determine target object type
    object_type = parameters.get("object_type", "contacts")
    
    # Verify object type exists
    object_exists = False
    object_details = {}
    if object_type in STANDARD_OBJECTS:
        object_exists = True
        object_details = {"standard_object": STANDARD_OBJECTS[object_type]}
    else:
        # Check custom object schemas
        try:
            schemas = make_request("GET", "/crm/v3/schemas")
            found = False
            for schema in schemas.get("results", []):
                if schema.get("name") == object_type or schema.get("objectTypeId") == object_type:
                    object_exists = True
                    object_details = schema
                    found = True
                    break
            if not found:
                object_details = {"error": f"Custom object schema for {object_type} not found in HubSpot."}
        except Exception as e:
            object_details = {"error": f"Error fetching schemas: {e}"}

    inspected_items.append(StateInspectionItem(
        item_type="object",
        item_id=object_type,
        exists=object_exists,
        details=object_details
    ))

    # 2. Extract properties to inspect
    props_to_inspect: List[Dict[str, Any]] = []
    seen_props = set()

    def add_prop(name, p_type=None, group=None):
        if name and name not in seen_props:
            seen_props.add(name)
            props_to_inspect.append({"name": name, "expected_type": p_type, "expected_group": group})

    # From properties_referenced
    for p in parameters.get("properties_referenced", []):
        if isinstance(p, dict):
            name = p.get("internal_name") or p.get("name")
            add_prop(name, p.get("field_type") or p.get("type"), p.get("groupName") or p.get("group"))
        elif isinstance(p, str):
            add_prop(p)

    # From properties list
    for p in parameters.get("properties", []):
        if isinstance(p, dict):
            name = p.get("internal_name") or p.get("name")
            add_prop(name, p.get("field_type") or p.get("type"), p.get("groupName") or p.get("group"))
        elif isinstance(p, str):
            add_prop(p)

    # From trigger conditions
    trigger = parameters.get("trigger", {})
    if isinstance(trigger, dict):
        for cond in trigger.get("conditions", []):
            if isinstance(cond, dict):
                name = cond.get("property_internal_name") or cond.get("property") or cond.get("propertyName")
                add_prop(name)

    # Call HubSpot API to check each property
    existing_properties_metadata = {}
    for p in props_to_inspect:
        prop_name = p["name"]
        exists = False
        details = None
        try:
            prop_data = make_request("GET", f"/crm/v3/properties/{object_type}/{prop_name}")
            exists = True
            details = prop_data
            existing_properties_metadata[prop_name] = prop_data
        except APIError as e:
            details = {"error": str(e)}

        inspected_items.append(StateInspectionItem(
            item_type="property",
            item_id=prop_name,
            exists=exists,
            details=details
        ))

    # 3. Check Workflow existence
    wf_name = parameters.get("workflow_name") or parameters.get("name")
    if wf_name:
        wf_exists = False
        wf_details = None
        try:
            # Try V4 workflows (flows) API first
            try:
                workflows_data = make_request("GET", "/automation/v4/flows")
            except APIError as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    # Fall back to V3 workflows API
                    workflows_data = make_request("GET", "/automation/v3/workflows")
                else:
                    raise e
            
            for wf in workflows_data.get("results", []):
                if wf.get("name") == wf_name:
                    wf_exists = True
                    wf_details = wf
                    break
            if not wf_exists:
                wf_details = {"info": "Workflow name not found in active/inactive workflows list."}
        except Exception as e:
            wf_details = {
                "error": f"Automation API Forbidden/Error: {e}. Workflow check requires manual inspection or additional API scopes."
            }
            wf_exists = False

        inspected_items.append(StateInspectionItem(
            item_type="workflow",
            item_id=wf_name,
            exists=wf_exists,
            details=wf_details
        ))

    # 4. Integration checks (Slack, etc.)
    has_slack_action = False
    for act in parameters.get("actions", []):
        if isinstance(act, dict) and (act.get("action_type") == "send_slack_notification" or "slack" in str(act).lower()):
            has_slack_action = True
            break

    if has_slack_action or "slack" in str(parameters).lower():
        inspected_items.append(StateInspectionItem(
            item_type="integration",
            item_id="slack",
            exists=False,
            details={"note": "Manual check required. Verify HubSpot-Slack integration is installed in target portal."}
        ))

    # 5. Data Quality Checks (THE killer demo moment!)
    total_records = 0
    try:
        search_res = make_request("POST", f"/crm/v3/objects/{object_type}/search", json_data={"limit": 1})
        total_records = search_res.get("total", 0)
    except Exception as e:
        print(f"[Warning] Failed to fetch total record count for data quality check: {e}")

    dq_notes = []
    dq_details = {"total_records": total_records, "properties": {}}

    if total_records > 0:
        for prop_name, meta in existing_properties_metadata.items():
            null_count = 0
            try:
                null_search = make_request(
                    "POST",
                    f"/crm/v3/objects/{object_type}/search",
                    json_data={
                        "filterGroups": [{"filters": [{"propertyName": prop_name, "operator": "NOT_HAS_PROPERTY"}]}],
                        "limit": 1
                    }
                )
                null_count = null_search.get("total", 0)
            except Exception as e:
                print(f"[Warning] Failed to run null search on {prop_name}: {e}")
                continue

            prop_type = meta.get("type", "")
            field_type = meta.get("fieldType", "")

            prop_dq = {
                "null_count": null_count,
                "null_percentage": round((null_count / total_records) * 100, 1),
                "type": prop_type,
                "field_type": field_type
            }

            if prop_dq["null_percentage"] > 20:
                dq_notes.append(f"{prop_dq['null_percentage']}% of records have no value for '{prop_name}'")

            if prop_type == "enumeration" or field_type in ["select", "checkbox"]:
                option_counts = {}
                for opt in meta.get("options", []):
                    opt_val = opt.get("value")
                    try:
                        opt_search = make_request(
                            "POST",
                            f"/crm/v3/objects/{object_type}/search",
                            json_data={
                                "filterGroups": [{"filters": [{"propertyName": prop_name, "operator": "EQ", "value": opt_val}]}],
                                "limit": 1
                            }
                        )
                        option_counts[opt_val] = opt_search.get("total", 0)
                    except Exception as e:
                        print(f"[Warning] Failed to search option value '{opt_val}' on {prop_name}: {e}")
                prop_dq["option_counts"] = option_counts

            dq_details["properties"][prop_name] = prop_dq

    # 6. Build summary
    missing_items = []
    existing_items = []

    for item in inspected_items:
        if item.item_type != "integration":
            if item.exists:
                existing_items.append(f"{item.item_type}:{item.item_id}")
            else:
                missing_items.append(f"{item.item_type}:{item.item_id}")

    summary_parts = [
        f"Inspected {len(inspected_items)} items.",
        f"Found {len(missing_items)} missing items that need to be created: {missing_items}." if missing_items else "No missing items found.",
        f"Found {len(existing_items)} existing items that match: {existing_items}." if existing_items else "No matching existing items found."
    ]
    if dq_notes:
        summary_parts.append(f"Data quality concerns: {'; '.join(dq_notes)} (Total records: {total_records}).")
    else:
        summary_parts.append("No major data quality concerns flagged.")

    inspection_summary = " ".join(summary_parts)

    output = Stage4Output(
        requirement_id=requirement.id,
        inspected_items=inspected_items,
        inspection_summary=inspection_summary
    )

    # 7. Persist
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / f"stage_4_{requirement.id}_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    dq_file = run_dir / f"stage_4_{requirement.id}_data_quality.json"
    with open(dq_file, "w", encoding="utf-8") as f:
        json.dump(dq_details, f, indent=2)

    print(f"Stage 4 [{requirement.id}]: {inspection_summary}")
    return output


if __name__ == "__main__":
    from planning.document_loader import load_document
    from planning.stages.stage_1_extraction import run_stage_1
    from planning.stages.stage_2_concept_mapping import run_stage_2
    from planning.stages.stage_3_architecture_decision import run_stage_3

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    target_req_id = sys.argv[2] if len(sys.argv) > 2 else "REQ-009"

    print(f"Loading document: {doc_path}...")
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_4")

    # Load Stage 1
    s1_file = run_dir / "stage_1_output.json"
    if s1_file.exists():
        print(f"Loading cached Stage 1 output from {s1_file}...")
        from planning.models import Stage1Output
        with open(s1_file, "r", encoding="utf-8") as f:
            s1_output = Stage1Output.model_validate_json(f.read())
    else:
        print("Running Stage 1 Extraction...")
        s1_output = run_stage_1(doc, client, run_dir)

    target_req = None
    for r in s1_output.requirements:
        if r.id == target_req_id:
            target_req = r
            break
    if not target_req:
        target_req = s1_output.requirements[0]

    # Load Stage 2
    s2_file = run_dir / f"stage_2_{target_req.id}_output.json"
    if s2_file.exists():
        print(f"Loading cached Stage 2 output from {s2_file}...")
        from planning.models import Stage2Output
        with open(s2_file, "r", encoding="utf-8") as f:
            s2_output = Stage2Output.model_validate_json(f.read())
    else:
        print(f"Running Stage 2 Concept Mapping for {target_req.id}...")
        s2_output = run_stage_2(target_req, client, run_dir)

    # Load Stage 3
    s3_file = run_dir / f"stage_3_{target_req.id}_output.json"
    if s3_file.exists():
        print(f"Loading cached Stage 3 output from {s3_file}...")
        from planning.models import ArchitectureDecision
        with open(s3_file, "r", encoding="utf-8") as f:
            s3_output = ArchitectureDecision.model_validate_json(f.read())
    else:
        print(f"Running Stage 3 Architecture Decision for {target_req.id}...")
        s3_output = run_stage_3(target_req, s2_output, client, run_dir)

    print(f"\nRunning Stage 4 Live State Inspection for requirement: {target_req.id} - '{target_req.title}'...")
    s4_output = run_stage_4(target_req, s3_output, run_dir)

    print("\n" + "="*80)
    print(f"STAGE 4 STATE INSPECTION RESULTS ({target_req.id})")
    print("="*80)
    print(f"Summary: {s4_output.inspection_summary}\n")
    print("Inspected Items details:")
    for item in s4_output.inspected_items:
        print(f"  - {item.item_type}:{item.item_id} | Exists: {item.exists}")
        if item.details:
            details_str = json.dumps(item.details, indent=2).split("\n")[:8]
            print("    Details (truncated):")
            for line in details_str:
                print(f"      {line}")
    print("="*80)
