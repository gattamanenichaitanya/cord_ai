# 03 — Diagnosis Engine

This is the most important implementation document.

## 1. Objective

Given:

```text
incident
+
configuration graph
+
canonical runtime state
+
expectation/policy rules
+
workflow/configuration rules
+
optional change history
```

produce:

```text
root-cause candidate
causal path
supporting evidence
confidence
investigation trace
```

without:

- ticket-specific root-cause mappings
- fixed graph paths
- globally fixed edge orders
- a handcrafted diagnostic-intent taxonomy
- runtime-to-rule schema matching inside the investigation loop

## 2. Canonical schema assumption

For this prototype, all property references use the same canonical keys:

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

No semantic field reconciliation is required in the prototype.

## 3. Core architecture

The diagnosis engine is a **bounded LLM graph investigator**.

```text
Ticket
   ↓
Ticket interpretation / anchor retrieval
   ↓
Canonical runtime lookup
   ↓
Expectation validation
   ↓
Validated discrepancy
   ↓
Current investigation node
   ↓
Fetch local graph neighborhood
   ↓
Construct allowed candidate actions
   ↓
LLM Planner
   ↓
Select exactly one allowed action
   ↓
Backend validates selection
   ↓
Execute deterministic graph/runtime/config tool
   ↓
Collect evidence
   ↓
Update investigation state
   ↓
Repeat
```

The division of labor is:

```text
Graph + tools:
what is true and what actions exist

LLM:
which available action is most useful next
```

## 4. Graph direction and semantic role

The planner must not infer causal meaning from graph-edge direction alone.

Example around `deal_stage`:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
```

From current node `deal_stage`, both edges are graph-theoretically incoming.

But:

```text
deal_stage_automation
edge_direction = incoming
semantic_role = UPSTREAM_PRODUCER
```

and:

```text
fulfillment_workflow
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER
```

Candidate actions therefore expose both fields:

```text
edge_direction
semantic_role
```

The field name `direction` should not be used in planner-facing action objects because it is ambiguous.

## 5. Stage 1 — Ticket interpretation

Input:

```text
"$250K enterprise deal with a 22% discount moved to Contract Sent without Finance approval."
```

Possible structured output:

```json
{
  "record_id": "DEAL-4821",
  "entity_type": "deal",
  "mentioned_concepts": [
    "finance approval",
    "deal stage",
    "discount",
    "enterprise"
  ],
  "observed_claims": [
    {
      "subject": "deal_stage",
      "value": "Contract Sent",
      "qualifier": "unexpected"
    },
    {
      "subject": "approval_required",
      "value": false,
      "qualifier": "unexpected"
    }
  ],
  "mentioned_values": {
    "deal_amount": 250000,
    "discount_pct": 22,
    "customer_tier": "Enterprise"
  }
}
```

The output must not include root cause, next node, or traversal path.

## 6. Stage 2 — Anchor retrieval

Use ticket concepts + record identifiers to retrieve likely graph nodes.

Example:

```json
[
  {"node_id": "deal_stage", "score": 0.94},
  {"node_id": "approval_required", "score": 0.92},
  {"node_id": "deal_stage_automation", "score": 0.83},
  {"node_id": "discount_governance", "score": 0.79}
]
```

The goal is a ranked starting region, not a root-cause guess.

## 7. Stage 3 — Validate the anomaly

Example runtime:

```text
customer_tier = Enterprise
deal_amount = 250000
discount_pct = 22
approval_required = false
deal_stage = Contract Sent
```

Policy:

```text
customer_tier = Enterprise
AND deal_amount > 100000
AND discount_pct > 15
→ approval_required must be true before deal_stage = Contract Sent
```

Result:

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

This is the validated discrepancy.

## 8. Stage 4 — Build local investigation context

Suppose current node is:

```text
deal_stage
```

Backend retrieves:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
reporting_workflow --READS--> deal_stage
```

Then it derives planner-facing semantic roles:

```text
deal_stage_automation:
edge_type = WRITES
edge_direction = incoming
semantic_role = UPSTREAM_PRODUCER

fulfillment_workflow:
edge_type = READS
edge_direction = incoming
semantic_role = DOWNSTREAM_CONSUMER
```

Semantic roles must be derived from graph semantics, not generated freely by the LLM.

## 9. Stage 5 — Generate allowed candidate actions

Example:

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
  },
  {
    "action_id": "A3",
    "action_type": "INSPECT_CONNECTED_NODE",
    "edge_type": "READS",
    "edge_direction": "incoming",
    "semantic_role": "DOWNSTREAM_CONSUMER",
    "target_node_id": "reporting_workflow",
    "target_node_name": "Reporting Workflow"
  }
]
```

Possible action types:

```text
INSPECT_CONNECTED_NODE
READ_RUNTIME_VALUE
INSPECT_RULE
CHECK_RECENT_CHANGES
RETURN_TO_CANDIDATE
STOP_WITH_ROOT_CAUSE
STOP_NEEDS_HUMAN
```

Only graph/tool-backed actions may be generated.

## 10. Stage 6 — LLM planner

Suggested input:

```json
{
  "incident": {
    "text": "$250K enterprise deal with a 22% discount moved to Contract Sent without Finance approval."
  },
  "validated_discrepancy": {
    "subject_node": "deal_stage",
    "summary": "Contract Sent occurred before required Finance approval."
  },
  "current_node": {
    "id": "deal_stage",
    "type": "PROPERTY",
    "runtime_value": "Contract Sent"
  },
  "important_prior_evidence": [],
  "candidate_actions": [
    {
      "action_id": "A1",
      "edge_type": "WRITES",
      "edge_direction": "incoming",
      "semantic_role": "UPSTREAM_PRODUCER",
      "target": "Deal Stage Automation"
    },
    {
      "action_id": "A2",
      "edge_type": "READS",
      "edge_direction": "incoming",
      "semantic_role": "DOWNSTREAM_CONSUMER",
      "target": "Fulfillment Workflow"
    },
    {
      "action_id": "A3",
      "edge_type": "READS",
      "edge_direction": "incoming",
      "semantic_role": "DOWNSTREAM_CONSUMER",
      "target": "Reporting Workflow"
    }
  ]
}
```

Require strict output:

```json
{
  "selected_action_id": "A1",
  "reason": "Deal Stage Automation is an upstream producer of the anomalous deal_stage value.",
  "confidence": 0.94
}
```

The planner may use `semantic_role` to reason causally, while `edge_direction` preserves actual topology.

## 11. Stage 7 — Validate and execute

Backend must verify:

```text
selected_action_id exists
target node exists
edge exists
edge_type matches
edge_direction matches stored graph
semantic_role matches deterministic derivation
```

Only then execute.

## 12. Same anchor, different planner decision

Incident:

```text
Deal reached Contract Sent correctly, but fulfillment never started.
```

Validation:

```text
deal_stage = Contract Sent
→ valid

fulfillment_started = false
→ anomalous
```

The same local neighborhood may be:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
reporting_workflow --READS--> deal_stage
```

Candidate actions expose:

```text
deal_stage_automation:
UPSTREAM_PRODUCER

fulfillment_workflow:
DOWNSTREAM_CONSUMER
```

Because the missing behavior is downstream, the planner should choose:

```text
fulfillment_workflow
```

This is not because the graph edge is outgoing. It is not.

The stored `READS` edge is incoming to `deal_stage`; the semantic role is downstream consumer.

## 13. Investigation trace

Planner trace should include:

```json
{
  "event": "PLANNER_DECISION",
  "current_node": "deal_stage",
  "candidate_actions": ["A1", "A2", "A3"],
  "selected_action_id": "A1",
  "selected_target": "deal_stage_automation",
  "edge_type": "WRITES",
  "edge_direction": "incoming",
  "semantic_role": "UPSTREAM_PRODUCER",
  "reason": "This component produces the anomalous deal_stage value."
}
```

The trace should never use ambiguous `direction` when describing planner-facing actions.

## 14. Deterministic vs LLM responsibilities

### Deterministic

- graph node/edge retrieval
- runtime-state lookup
- expectation evaluation
- workflow/rule evaluation
- local-neighborhood generation
- edge-direction calculation
- semantic-role derivation
- candidate-action generation
- action validation
- tool execution
- visited-state tracking
- budgets

### LLM

- ticket interpretation
- choosing among grounded next actions
- prioritizing evidence
- using semantic roles + incident context to select the useful branch
- explaining the planner decision
- proposing when RCA evidence is sufficient

## 15. Failure behavior

If planner selects an invalid action:

```text
retry once with validation error
then fail safely
```

If evidence remains insufficient:

```json
{
  "status": "needs_human",
  "confidence": 0.35,
  "reason": "No sufficiently supported causal explanation found within the investigation budget."
}
```

Never manufacture an RCA.
