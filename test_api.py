import os
import urllib.request
import json
from dotenv import load_dotenv

def test_connection():
    load_dotenv()
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        print("Error: HUBSPOT_PRIVATE_APP_TOKEN not found in .env file.")
        return

    url = "https://api.hubapi.com/crm/v3/properties/contacts/groups"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            data = json.loads(response.read().decode('utf-8'))
            print(f"SUCCESS: Connected to HubSpot API (Status Code: {status})")
            print(f"Retrieved {len(data.get('results', []))} contact property groups.")
            # Print the names of the first few groups as proof
            group_names = [group.get("name") for group in data.get("results", [])[:5]]
            print(f"Sample groups: {', '.join(group_names)}")
    except urllib.error.HTTPError as e:
        print(f"FAILED: HTTP Error {e.code}: {e.reason}")
        print(e.read().decode('utf-8'))
    except Exception as e:
        print(f"FAILED: Connection error: {str(e)}")

if __name__ == "__main__":
    test_connection()
