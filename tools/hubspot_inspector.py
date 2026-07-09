import os
import sys
import json
import time
import argparse
import requests
from tabulate import tabulate
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

STANDARD_OBJECTS = {
    "contacts": {"singular": "Contact", "type-id": "0-1"},
    "companies": {"singular": "Company", "type-id": "0-2"},
    "deals": {"singular": "Deal", "type-id": "0-3"},
    "tickets": {"singular": "Ticket", "type-id": "0-5"},
    "quotes": {"singular": "Quote", "type-id": "0-14"},
    "products": {"singular": "Product", "type-id": "0-7"},
    "line_items": {"singular": "Line Item", "type-id": "0-8"},
}

BASE_URL = "https://api.hubapi.com"

class APIError(Exception):
    pass

def get_headers():
    load_dotenv()
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        print("Set HUBSPOT_PRIVATE_APP_TOKEN in .env")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def make_request(method, endpoint, params=None, json_data=None):
    url = f"{BASE_URL}{endpoint}"
    headers = get_headers()
    
    for attempt in range(2):
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=json_data)
            
            if resp.status_code == 401:
                raise APIError("Token is invalid or lacks required scopes")
            elif resp.status_code == 404:
                raise APIError(f"Object/property not found: {endpoint}")
                
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == 0:
                time.sleep(2)
            else:
                raise APIError(f"Network error: {e}")

def cmd_objects(args):
    table = []
    for internal_name, data in STANDARD_OBJECTS.items():
        table.append([internal_name, data["singular"], data["type-id"]])
    print(tabulate(table, headers=["Internal Name", "Singular Label", "Object Type ID"], tablefmt="grid"))

def cmd_custom_objects(args):
    try:
        data = make_request("GET", "/crm/v3/schemas")
        results = data.get("results", [])
        table = []
        for schema in results:
            table.append([
                schema.get("name"),
                schema.get("labels", {}).get("singular"),
                schema.get("labels", {}).get("plural"),
                schema.get("objectTypeId")
            ])
        print(tabulate(table, headers=["Name", "Singular Label", "Plural Label", "Object Type ID"], tablefmt="grid"))
    except APIError as e:
        print(e)

def cmd_groups(args):
    endpoint = f"/crm/v3/properties/{args.object_type}/groups"
    try:
        data = make_request("GET", endpoint)
        results = data.get("results", [])
        
        table = []
        for group in results:
            table.append([
                group.get("name"),
                group.get("label"),
                group.get("archived", False)
            ])
        print(tabulate(table, headers=["Name", "Label", "Archived"], tablefmt="grid"))
    except APIError as e:
        print(e)

def cmd_properties(args):
    endpoint = f"/crm/v3/properties/{args.object_type}"
    try:
        data = make_request("GET", endpoint)
        results = data.get("results", [])
        
        if args.filter:
            results = [p for p in results if p.get("groupName") == args.filter]
            
        results.sort(key=lambda x: (x.get("groupName", ""), x.get("name", "")))
        
        table = []
        for prop in results:
            table.append([
                prop.get("name"),
                prop.get("label"),
                prop.get("type"),
                prop.get("fieldType"),
                prop.get("groupName"),
                prop.get("calculated"),
                prop.get("hubspotDefined")
            ])
        print(tabulate(table, headers=["Name", "Label", "Type", "Field Type", "Group Name", "Calculated", "HubSpot Defined"], tablefmt="grid"))
    except APIError as e:
        print(e)

def cmd_property(args):
    endpoint = f"/crm/v3/properties/{args.object_type}/{args.property_name}"
    try:
        data = make_request("GET", endpoint)
        print(json.dumps(data, indent=2))
    except APIError as e:
        print(e)

def cmd_verify(args):
    try:
        with open(args.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"\u2717 Could not read JSON file: {e}")
        return

    entry_type = data.get("graph_entry_type")
    
    if entry_type not in ["object", "standard_property"]:
        print(f"Programmatic verification isn't available for type '{entry_type}' — these are manually verified.")
        return

    print(f"Verifying {entry_type} entry from {args.path}...\n")
    all_passed = True
    
    def report(name, passed, error_msg=""):
        nonlocal all_passed
        if passed:
            print(f"\u2713 PASS: {name}")
        else:
            print(f"\u2717 FAIL: {name} - {error_msg}")
            all_passed = False

    if entry_type == "object":
        internal_name = data.get("internal_name")
        object_type_id = data.get("object_type_id")
        
        if internal_name in STANDARD_OBJECTS:
            expected_id = STANDARD_OBJECTS[internal_name]["type-id"]
            report("Object Type ID matches STANDARD_OBJECTS", object_type_id == expected_id, f"Expected {expected_id}, got {object_type_id}")
        else:
            try:
                schemas_data = make_request("GET", "/crm/v3/schemas")
                found = False
                for schema in schemas_data.get("results", []):
                    if schema.get("name") == internal_name:
                        found = True
                        expected_id = schema.get("objectTypeId")
                        report("Object Type ID matches custom schema", object_type_id == expected_id, f"Expected {expected_id}, got {object_type_id}")
                        break
                if not found:
                    report("Object exists", False, f"Could not find object {internal_name} in standard or custom schemas")
            except APIError as e:
                report("Object exists", False, str(e))
        
        default_groups = data.get("object_level_capabilities", {}).get("default_property_groups", [])
        if default_groups:
            endpoint = f"/crm/v3/properties/{internal_name}/groups"
            try:
                groups_data = make_request("GET", endpoint)
                actual_groups = {g.get("name") for g in groups_data.get("results", [])}
                for group in default_groups:
                    report(f"Group exists: {group}", group in actual_groups, f"Group '{group}' not found in API")
            except APIError as e:
                report("Fetch groups", False, str(e))
                
        key_props = data.get("key_standard_properties", [])
        if key_props:
            for prop in key_props:
                prop_name = prop.get("internal_name", prop.get("name"))
                endpoint = f"/crm/v3/properties/{internal_name}/{prop_name}"
                try:
                    make_request("GET", endpoint)
                    report(f"Key property exists: {prop_name}", True)
                except APIError as e:
                    report(f"Key property exists: {prop_name}", False, str(e))

    elif entry_type == "standard_property":
        internal_name = data.get("internal_name")
        obj_type = data.get("object")
        endpoint = f"/crm/v3/properties/{obj_type}/{internal_name}"
        
        try:
            prop_data = make_request("GET", endpoint)
            report("Property exists", True)
            
            expected_field_type = data.get("field_type")
            actual_field_type = prop_data.get("fieldType")
            report("Field type matches", expected_field_type == actual_field_type, f"Expected {expected_field_type}, got {actual_field_type}")
            
            expected_group = data.get("property_group")
            if expected_group:
                actual_group = prop_data.get("groupName")
                report("Group name matches", expected_group == actual_group, f"Expected {expected_group}, got {actual_group}")
                
        except APIError as e:
            report("Property exists", False, str(e))

def main():
    parser = argparse.ArgumentParser(description="HubSpot API Inspector CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("objects", help="List standard objects")
    
    subparsers.add_parser("custom-objects", help="List custom objects schemas")
    
    parser_groups = subparsers.add_parser("groups", help="List property groups for an object")
    parser_groups.add_argument("object_type", help="Internal name of the object (e.g. contacts)")
    
    parser_props = subparsers.add_parser("properties", help="List properties for an object")
    parser_props.add_argument("object_type", help="Internal name of the object")
    parser_props.add_argument("--filter", help="Filter by groupName")
    
    parser_prop = subparsers.add_parser("property", help="Get JSON for a specific property")
    parser_prop.add_argument("object_type", help="Internal name of the object")
    parser_prop.add_argument("property_name", help="Internal name of the property")
    
    parser_verify = subparsers.add_parser("verify", help="Verify a graph entry JSON file")
    parser_verify.add_argument("path", help="Path to the JSON file")
    
    args = parser.parse_args()
    
    if args.command == "objects":
        cmd_objects(args)
    elif args.command == "custom-objects":
        cmd_custom_objects(args)
    elif args.command == "groups":
        cmd_groups(args)
    elif args.command == "properties":
        cmd_properties(args)
    elif args.command == "property":
        cmd_property(args)
    elif args.command == "verify":
        cmd_verify(args)

if __name__ == "__main__":
    main()
