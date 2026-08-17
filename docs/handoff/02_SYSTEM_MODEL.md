# 02 — System Model

## 1. Canonical field model

For the prototype, use one canonical field vocabulary everywhere.

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

These exact IDs should be used for:

- graph PROPERTY nodes
- runtime-state keys
- workflow rule fields
- expectation/policy fields
- evidence references
- test fixtures

Do not create translation logic between alternate field names in this prototype.

Future production architecture may add:

```text
raw customer field
    ↓
semantic normalizer
    ↓
canonical field
```

but that is out of scope here.

## 2. Ontology

An ontology defines the types of things Cord understands and the relationships allowed between them.

### Node types

```text
CRM_OBJECT
PROPERTY
WORKFLOW
WORKFLOW_BRANCH
PIPELINE_STAGE
TEAM
CUSTOM_CODE
INTEGRATION
CHANGE
INCIDENT
```

### Edge types

```text
READS
WRITES
CONTAINS
MOVES_TO
DEPENDS_ON
CALLS
CALLS_OUT_TO
MODIFIED
AFFECTS
TRIGGERS
```

The ontology contains **types**, not customer-specific workflow names.

Example:

```text
WORKFLOW --WRITES--> PROPERTY
```

Actual graph instance:

```text
derive_pricing_segment --WRITES--> pricing_segment
```

## 3. Edge semantics matter

Edges are factual graph semantics supplied to the LLM planner.

```text
WORKFLOW --WRITES--> PROPERTY
```

means the workflow can produce/change the property's value.

```text
WORKFLOW --READS--> PROPERTY
```

means the workflow consumes the property's value.

The LLM does not invent these relationships.

## 4. Graph direction vs semantic role

These are different concepts and must not be conflated.

Consider:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
```

If the current node is `deal_stage`, both edges are graph-theoretically **incoming** because both point toward `deal_stage`.

But their causal/business roles are different:

```text
deal_stage_automation --WRITES--> deal_stage
```

means:

```text
edge_direction = incoming
semantic_role = UPSTREAM_PRODUCER
```

while:

```text
fulfillment_workflow --READS--> deal_stage
```

means:

```text
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER
```

Therefore candidate actions must expose both:

```text
edge_direction
semantic_role
```

Do not use a generic `direction` field because it is ambiguous.

Suggested semantic roles for the prototype:

```text
UPSTREAM_PRODUCER
DOWNSTREAM_CONSUMER
UPSTREAM_DEPENDENCY
DOWNSTREAM_DEPENDENT
CONFIGURATION_PARENT
CONFIGURATION_CHILD
CHANGE_SOURCE
RELATED_COMPONENT
```

Only use roles that can be derived from the stored edge type + traversal perspective.

## 5. Persistent configuration graph

Core graph:

```text
customer_tier
      ▲
      │ READS
      │
derive_pricing_segment
      │
      │ WRITES
      ▼
pricing_segment
      ▲
      │ READS
      │
discount_governance
      │
      ├── READS ──> deal_amount
      ├── READS ──> discount_pct
      │
      │ WRITES
      ▼
approval_required
      ▲
      │ READS
      │
deal_stage_automation
      │
      │ WRITES
      ▼
deal_stage

fulfillment_workflow --READS--> deal_stage
fulfillment_workflow --WRITES--> fulfillment_started
```

For the prototype, graph population may be manual/semi-manual.

## 6. Runtime state

Business records are separate from the persistent graph.

Example:

```json
{
  "deal_id": "DEAL-4821",
  "deal_amount": 250000,
  "discount_pct": 22,
  "customer_tier": "Enterprise",
  "pricing_segment": null,
  "approval_required": false,
  "deal_stage": "Contract Sent",
  "fulfillment_started": false,
  "sales_process_complete": true
}
```

Keep separate:

- graph = how the system is configured
- runtime state = what happened to one record
- incident = how a human describes the failure
- expectations/policies = what should have happened

## 7. Workflow configuration rules

Workflow nodes may contain evaluatable rules using the canonical field names.

Example:

```json
{
  "id": "discount_governance",
  "type": "WORKFLOW",
  "name": "Discount Governance",
  "rule": {
    "all": [
      {"field": "deal_amount", "op": ">", "value": 100000},
      {"field": "discount_pct", "op": ">", "value": 15},
      {"field": "pricing_segment", "op": "==", "value": "Enterprise"}
    ],
    "then": {
      "field": "approval_required",
      "value": true
    },
    "else": {
      "field": "approval_required",
      "value": false
    }
  }
}
```

## 8. Expectation / policy model

Cord needs a structured way to validate whether the ticket's claimed anomaly is actually inconsistent with expected behavior.

Example:

```json
{
  "id": "enterprise_finance_approval_policy",
  "applies_when": [
    {"field": "customer_tier", "op": "==", "value": "Enterprise"},
    {"field": "deal_amount", "op": ">", "value": 100000},
    {"field": "discount_pct", "op": ">", "value": 15}
  ],
  "constraint": {
    "before_stage": {
      "field": "deal_stage",
      "value": "Contract Sent"
    },
    "required_state": {
      "field": "approval_required",
      "value": true
    }
  }
}
```

Example evaluator output:

```json
{
  "status": "VIOLATED",
  "subject_node": "deal_stage",
  "observed": {
    "deal_stage": "Contract Sent",
    "approval_required": false
  },
  "expected": {
    "approval_required": true
  },
  "summary": "Contract Sent occurred before required Finance approval."
}
```

## 9. Normalization seam

The diagnosis engine should consume canonical state.

For the prototype:

```text
normalize_runtime_state(raw_runtime) -> raw_runtime
normalize_rule(raw_rule) -> raw_rule
```

because fixtures are already canonical.

In a later production phase:

```text
customer-specific runtime/config
        ↓
semantic normalizer
        ↓
canonical representation
        ↓
diagnosis engine
```

This seam should exist architecturally, but no LLM-based semantic normalizer needs to be built now.

## 10. Graph / runtime API

Required conceptual functions:

```text
search_graph(query, filters?)
get_node(node_id)
get_neighbors(node_id, direction, edge_types?)
get_edge(source, target)

get_runtime_record(record_id)
get_runtime_value(record_id, canonical_field)

get_workflow_rule(workflow_id)
get_recent_changes(node_id)

evaluate_expectations(record_id, context?)
```

`get_neighbors(..., direction=...)` refers only to **stored graph-edge direction**.

Semantic roles are derived after the neighboring edges are returned.

## 11. Local neighborhood

At each hop, the backend builds a bounded local neighborhood.

Example around `deal_stage`:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
reporting_workflow --READS--> deal_stage
slack_notification_workflow --READS--> deal_stage
```

Relative to current node `deal_stage`:

```text
deal_stage_automation:
edge_direction = incoming
semantic_role = UPSTREAM_PRODUCER

fulfillment_workflow:
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER

reporting_workflow:
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER
```

The planner receives this bounded factual neighborhood, not the entire graph.

## 12. Candidate actions

The backend converts real graph relationships into a finite action set.

```json
[
  {
    "action_id": "A1",
    "action_type": "INSPECT_CONNECTED_NODE",
    "edge_type": "WRITES",
    "edge_direction": "incoming",
    "semantic_role": "UPSTREAM_PRODUCER",
    "target_node_id": "deal_stage_automation",
    "target_node_name": "Deal Stage Automation"
  },
  {
    "action_id": "A2",
    "action_type": "INSPECT_CONNECTED_NODE",
    "edge_type": "READS",
    "edge_direction": "incoming",
    "semantic_role": "DOWNSTREAM_CONSUMER",
    "target_node_id": "fulfillment_workflow",
    "target_node_name": "Fulfillment Workflow"
  }
]
```

The LLM must choose an `action_id`; it must not invent arbitrary nodes.

The planner should reason primarily from:

```text
validated anomaly
+
semantic_role
+
edge_type
+
target metadata
+
prior evidence
```

`edge_direction` is retained because it describes the actual stored graph topology.

## 13. Investigation state

Suggested structure:

```json
{
  "incident_id": "INC-4821",
  "record_id": "DEAL-4821",
  "original_ticket": "...",
  "validated_discrepancies": [],
  "current_node": "deal_stage",
  "visited_nodes": [],
  "visited_edges": [],
  "healthy_nodes": [],
  "suspicious_nodes": [],
  "evidence": [],
  "planner_decisions": [],
  "hop_count": 0
}
```

## 14. Incident subgraph

Track:

```text
candidate_nodes
visited_nodes
visited_edges
healthy_nodes
suspicious_nodes
discarded_nodes
causal_path
```

The UI should render these outputs rather than maintain its own traversal sequence.
