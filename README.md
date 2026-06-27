# Cord AI POC

This is the Cord AI Proof of Concept (POC) demonstrating an AI agent performing SaaS implementation work.

Detailed specifications and documentation live in the `docs/` folder.

## Graph Status

The HubSpot knowledge graph contains **14 verified entries** across 5 entry types. All entries are indexed in ChromaDB (`graph_db/chroma/`) for semantic retrieval during automated planning.

| Entry Type | File | Description |
|---|---|---|
| **Object** | [`graph/hubspot/objects/contact.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/objects/contact.json) | Central record for individual contacts, unique identifier rules, and capabilities. |
| **Property** | [`graph/hubspot/properties/email.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/email.json) | Primary email address acting as HubSpot's unique identifier and deduplication key. |
| **Property** | [`graph/hubspot/properties/lifecyclestage.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/lifecyclestage.json) | Tracks progression through the buyer journey (Subscriber to Customer/Evangelist). |
| **Property** | [`graph/hubspot/properties/notes_last_contacted.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/notes_last_contacted.json) | Timestamp of the last outbound communication logged against a contact. |
| **Property** | [`graph/hubspot/properties/hs_last_sales_activity_timestamp.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/hs_last_sales_activity_timestamp.json) | Timestamp of the last inbound engagement with sales content or touchpoints. |
| **Property** | [`graph/hubspot/properties/engagements_last_meeting_booked.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/engagements_last_meeting_booked.json) | Date of the most recent meeting scheduled via HubSpot's meetings tool. |
| **Property** | [`graph/hubspot/properties/hubspot_owner_id.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/properties/hubspot_owner_id.json) | Designates the assigned HubSpot user or owner responsible for the contact. |
| **Capability** | [`graph/hubspot/capabilities/custom_property.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/capabilities/custom_property.json) | Documents rules, limits, and 14 field types for creating custom properties. |
| **Capability** | [`graph/hubspot/capabilities/workflow.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/capabilities/workflow.json) | Defines automation capabilities, triggers, actions, and re-enrollment logic. |
| **Operation** | [`graph/hubspot/operations/create_custom_property.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/operations/create_custom_property.json) | Execution steps and API endpoints for creating custom properties on objects. |
| **Operation** | [`graph/hubspot/operations/create_workflow.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/operations/create_workflow.json) | End-to-end steps for building, configuring, and publishing workflows. |
| **Gotcha** | [`graph/hubspot/gotchas/notes_last_contacted_population.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/gotchas/notes_last_contacted_population.json) | Warns that `notes_last_contacted` only updates via activity logged through HubSpot. |
| **Gotcha** | [`graph/hubspot/gotchas/property_internal_name_immutable.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/gotchas/property_internal_name_immutable.json) | Highlights that property internal names cannot be changed after creation. |
| **Gotcha** | [`graph/hubspot/gotchas/workflow_re_enrollment_behavior.json`](file:///c:/Users/gatta/OneDrive/Documents/CordAI/cord-ai-poc/graph/hubspot/gotchas/workflow_re_enrollment_behavior.json) | Warns that workflow re-enrollment will overwrite manual property edits. |

## Running Tests

To run the test suites:
```bash
# Run graph search vector DB tests
python -m pytest tests/test_graph_search.py -v

# Run Playwright verification test
python -m tests.test_playwright_hello
```

## Session Management

Cord AI uses a **persistent browser session** so you only need to log into HubSpot once. Session cookies are saved locally and reused for every subsequent run — no repeated logins, no 2FA prompts.

### How it works

1. **First run** — `HubSpotSession` detects that `.auth/hubspot_state.json` does not exist, opens a Chrome window, navigates to `https://app.hubspot.com/login`, and waits for you to log in manually (including any 2FA). Once you press Enter, it saves all cookies and localStorage to disk.

2. **Subsequent runs** — The saved state is loaded into a fresh browser context. Chrome goes straight to the HubSpot dashboard without any login prompt (~10–11 seconds per run).

3. **Expired sessions** — If HubSpot redirects back to `/login` when restoring a session, the manager automatically deletes the stale state file and triggers the first-run login flow again.

### Security

> **⚠️ WARNING:** `.auth/hubspot_state.json` contains active session cookies. Anyone with this file can act as you on HubSpot. It is excluded from git via `.gitignore` and must never be committed or shared.

### Resetting the session

If the session breaks or you want to force a fresh login:
```bash
# Delete the saved state — the next run will prompt for manual login
del .auth\hubspot_state.json
```

### Running the session test
```bash
# Single run
python -m tests.test_session

# Stress test (5 runs in a row — verifies robustness)
python -m tests.test_session_stress
```

### Using the session in your own scripts

```python
from execution.hubspot_session import HubSpotSession

with HubSpotSession() as session:
    page = session.page
    page.goto("https://app.hubspot.com/contacts/...")
    # ... do work ...
```

The `slow_mo` parameter (default 500ms) slows each action so you can watch it work. Set it to `0` for full speed:
```python
with HubSpotSession(slow_mo=0) as session:
    ...
```
