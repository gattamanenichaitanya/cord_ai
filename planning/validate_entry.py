import json
import sys
import os
from jsonschema import validate, ValidationError

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schemas')

SCHEMA_MAP = {
    "object": "object_schema.json",
    "standard_property": "property_schema.json",
    "capability": "capability_schema.json",
    "operation": "operation_schema.json",
    "idiom": "idiom_schema.json",
    "gotcha": "gotcha_schema.json"
}

def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_entry.py <path_to_json>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[FAIL] Could not read JSON file: {e}")
        sys.exit(1)
        
    graph_entry_type = data.get("graph_entry_type")
    if not graph_entry_type:
        print("[FAIL] Missing 'graph_entry_type' in JSON file.")
        sys.exit(1)
        
    schema_file = SCHEMA_MAP.get(graph_entry_type)
    if not schema_file:
        print(f"[FAIL] Unknown graph_entry_type: {graph_entry_type}")
        sys.exit(1)
        
    schema_path = os.path.join(SCHEMA_DIR, schema_file)
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except Exception as e:
        print(f"[FAIL] Could not read schema file: {e}")
        sys.exit(1)
        
    try:
        validate(instance=data, schema=schema)
        print(f"[PASS] {file_path} is a valid {graph_entry_type} entry.")
        sys.exit(0)
    except ValidationError as e:
        print(f"[FAIL] Validation error for {file_path}:\n{e.message}")
        sys.exit(1)

if __name__ == "__main__":
    main()
