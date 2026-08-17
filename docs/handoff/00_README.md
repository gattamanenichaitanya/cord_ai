# Cord 3-Day Prototype — Cursor Handoff v4

## Purpose

This specification describes a **working causal-diagnosis prototype**, not a static UI mock.

The prototype uses a HubSpot-like revenue-operations system because it is fast to model in three days. The long-term thesis is broader: complex enterprise applications accumulate configuration, workflows, custom logic, and dependencies; when a business process fails, Cord should identify the relevant part of the system, validate what is actually abnormal, and use an LLM planner to investigate the graph within strict factual boundaries.

## Canonical field naming for this prototype

To keep the prototype focused on causal diagnosis rather than schema reconciliation, the same canonical field names must be used consistently across:

- graph property node IDs
- runtime-state JSON
- rule/configuration JSON
- policy/expectation JSON
- tests
- diagnosis traces

Canonical fields:

```text
deal_amount
discount_pct
customer_tier
pricing_segment
approval_required
deal_stage
fulfillment_started
sales_process_complete
```

Do not introduce alternate names such as:

```text
company.tier
company_tier
deal.amount
amount
deal.stage
```

inside the prototype data model.

Schema/field reconciliation is intentionally deferred to a later semantic-normalization layer.

## The single most important rule

**Do not hardcode ticket → diagnosis mappings, ticket → traversal paths, or fixed edge orders.**

Forbidden examples:

```python
if incident_id == "INC-4821":
    return "derive_pricing_segment"
```

```python
if "finance approval" in ticket_text:
    traversal = ["deal_stage", "deal_stage_automation", "approval_required"]
```

```python
EDGE_ORDER = ["WRITES", "READS", "DEPENDS_ON"]
# blindly used for every incident
```

Also forbidden:

```python
if current_node == "deal_stage":
    next_node = "deal_stage_automation"
```

The graph may be manually/semi-manually constructed for this prototype.

The **diagnosis path must be selected at runtime** from:

```text
original incident
+
validated anomaly / discrepancy
+
current node
+
relevant runtime/configuration evidence
+
adjacent graph nodes and typed edges
+
evidence accumulated from prior hops
```

## Core architecture

The architecture does **not** use a handcrafted diagnostic-intent engine such as:

```text
UNEXPECTED_STATE_TRANSITION
    ↓
WHY_DID_VALUE_OCCUR
    ↓
incoming WRITES
```

Instead:

```text
Ticket
   ↓
Anchor Retrieval
   ↓
Runtime + Policy / Expectation Validation
   ↓
Validated Discrepancy
   ↓
Build Local Graph Neighborhood
   ↓
Generate Allowed Candidate Actions
   ↓
LLM Planner selects the next investigation action
   ↓
Backend validates the selected action
   ↓
Deterministic graph/runtime tool executes it
   ↓
New evidence
   ↓
Repeat
```

The graph defines what components and relationships actually exist.

The LLM decides **which available investigation action is most useful next**.

The backend never lets the LLM invent nodes, edges, runtime values, or arbitrary tool calls.

## What is deliberately synthetic for the 3-day prototype

- ontology definition
- graph population
- HubSpot-like configuration
- runtime records
- configuration-change history
- support incidents
- peripheral graph complexity

## What must be real

- ticket parsing / clue extraction
- anchor retrieval against actual graph nodes
- runtime-state lookup
- expectation / policy validation
- anomaly/discrepancy validation
- local-neighborhood retrieval
- candidate-action generation from real graph edges
- LLM selection among allowed actions
- backend validation of the selected action
- graph neighbor queries
- rule/configuration inspection
- evidence accumulation across hops
- stopping logic
- root-cause derivation from evidence
- investigation trace
- UI driven from the investigation trace

## Implementation order

Do not start with the frontend.

1. Canonical field model
2. Graph model
3. Runtime-state model
4. Rule / expectation model
5. Graph-query tools
6. Ticket parser
7. Anchor retrieval
8. Expectation / discrepancy validator
9. Local-neighborhood + candidate-action builder
10. LLM planner contract
11. Investigation loop
12. Investigation trace
13. Automated acceptance tests
14. Only after tests pass: UI / graph visualization

## Read order

1. `01_PRODUCT_THESIS.md`
2. `02_SYSTEM_MODEL.md`
3. `03_DIAGNOSIS_ENGINE.md`
4. `04_DEMO_DATA.md`
5. `05_UI_SPEC.md`
6. `06_ACCEPTANCE_TESTS.md`

`03_DIAGNOSIS_ENGINE.md` and `06_ACCEPTANCE_TESTS.md` are the source of truth if any other document creates ambiguity.
