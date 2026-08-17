# 06 — Acceptance Tests

These tests define whether the prototype is genuinely dynamic under the bounded LLM-planner architecture.

## Test 0 — Canonical field consistency

Canonical fields remain:

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

## Test 1 — Primary RCA

Expected:

```text
root_cause_node == derive_pricing_segment
```

## Test 2 — Runtime mutation invalidates RCA

Changing:

```text
pricing_segment = Enterprise
```

and making `derive_pricing_segment` healthy must invalidate that RCA.

## Test 3 — Same symptom, different root cause

Broken `discount_governance` must diagnose:

```text
root_cause_node == discount_governance
```

## Test 4 — Different incident, same graph

Broken `legacy_discount_override` must diagnose:

```text
root_cause_node == legacy_discount_override
```

## Test 5 — Same anchor, different planner choice

For the shared `deal_stage` neighborhood:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
reporting_workflow --READS--> deal_stage
```

candidate metadata must be:

```text
deal_stage_automation:
edge_direction = incoming
semantic_role = UPSTREAM_PRODUCER

fulfillment_workflow:
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER
```

Incident A, where `deal_stage` is anomalous, should favor an upstream producer.

Incident D, where `deal_stage` is healthy but fulfillment is missing, should favor the downstream consumer.

## Test 6 — Graph direction and semantic role are distinct

For:

```text
fulfillment_workflow --READS--> deal_stage
```

with current node:

```text
deal_stage
```

assert:

```text
edge_direction == incoming
semantic_role == DOWNSTREAM_CONSUMER
```

For:

```text
deal_stage_automation --WRITES--> deal_stage
```

assert:

```text
edge_direction == incoming
semantic_role == UPSTREAM_PRODUCER
```

If either semantic role is derived merely from `incoming/outgoing`, fail.

## Test 7 — Planner cannot invent a node

Selected action must exist in generated candidate actions.

## Test 8 — Candidate actions are graph-derived

For every `INSPECT_CONNECTED_NODE` action:

- source/current node exists
- target node exists
- edge exists
- `edge_type` matches stored edge
- `edge_direction` matches current-node perspective
- `semantic_role` matches deterministic edge-semantics derivation

## Test 9 — No ambiguous direction field

Planner-facing candidate actions and planner traces must use:

```text
edge_direction
semantic_role
```

and must not use:

```text
direction
```

as an ambiguous replacement for either concept.

## Test 10 — Same local graph + different context changes selection

Keep local neighborhood identical.

Case A:

```text
deal_stage itself is anomalous
```

Case B:

```text
deal_stage is healthy; fulfillment_started=false is anomalous
```

Expected planner choices differ appropriately.

## Test 11 — Irrelevant graph complexity

Add unrelated nodes and edges.

Expected:

```text
same RCA
visited_nodes <= 30
```

## Test 12 — Ticket paraphrase

Paraphrasing the same incident must preserve diagnosis for identical runtime/config state.

## Test 13 — No validated anomaly

If policy/runtime validation finds no anomaly, engine must not begin causal traversal as though one were confirmed.

## Test 14 — No evidence for root cause

If discrepancy is real but evidence is insufficient:

```text
status == needs_human
```

## Test 15 — Trace integrity

Every planner step should expose:

```text
current node
validated anomaly
candidate actions
selected action ID
selected target
edge_type
edge_direction
semantic_role
short reason
action result
```

Every field must correspond to real graph/runtime evidence.

## Test 16 — No forbidden mappings

Repository must not contain production/demo mappings equivalent to:

```text
incident_id -> root_cause
ticket phrase -> root_cause
incident_id -> traversal_steps
node_type -> fixed next node
global fixed edge order
incident_id -> planner action ID
```

## Test 17 — UI driven from trace

Incident A and Incident D must produce different planner selections and graph-highlight sequences without frontend code changes.

## Definition of Done

```text
[ ] canonical field tests pass
[ ] edge_direction and semantic_role are represented separately
[ ] semantic roles are derived deterministically from graph semantics
[ ] planner cannot invent nodes or actions
[ ] backend validates every planner action
[ ] same graph neighborhood supports different planner choices by context
[ ] runtime mutation changes diagnosis
[ ] UI consumes backend trace
```
