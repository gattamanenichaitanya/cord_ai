# 01 — Product Thesis

## What Cord is

Cord is a **configuration-aware causal diagnosis system for complex enterprise applications**.

Enterprise systems such as Salesforce, SAP, Dynamics, ServiceNow, and HubSpot accumulate:

- workflows
- fields/properties
- business rules
- pipelines
- approval logic
- custom code
- integrations
- permissions
- pricing/configuration rules

When something breaks, the visible symptom is frequently several dependencies away from the actual cause.

Example:

> A $250K enterprise deal with a 22% discount moved to `Contract Sent` without mandatory Finance approval.

A possible causal chain:

```text
customer_tier
    ↓
derive_pricing_segment
    ↓
pricing_segment
    ↓
discount_governance
    ↓
approval_required
    ↓
deal_stage_automation
    ↓
deal_stage = Contract Sent
```

Cord should reconstruct this chain from configuration + runtime evidence rather than from a prewritten scenario.

## Long-term product behavior

```text
Incident
   ↓
Interpret ticket and find likely anchors
   ↓
Fetch runtime state
   ↓
Validate what is actually abnormal
   ↓
Build a local graph neighborhood
   ↓
LLM chooses the best next investigation action
   ↓
Backend validates and executes that action
   ↓
Collect new evidence
   ↓
Repeat until root cause or insufficient evidence
```

The first product is **diagnosis, not remediation**.

## Why the graph is necessary

The graph acts as the **factual search space and boundary** for the diagnosis agent.

It tells Cord:

- which nodes actually exist
- which relationships actually exist
- which components are adjacent
- which next graph hops are possible

Example:

```text
derive_pricing_segment --WRITES--> pricing_segment
discount_governance --READS--> pricing_segment
```

## Why the LLM is necessary

The graph alone does not determine which adjacent edge is useful for the current incident.

At:

```text
deal_stage
```

the neighborhood might contain:

```text
deal_stage_automation --WRITES--> deal_stage
fulfillment_workflow --READS--> deal_stage
reporting_workflow --READS--> deal_stage
slack_notification_workflow --READS--> deal_stage
```

For:

> "The deal unexpectedly moved to Contract Sent"

the useful next component is likely the writer.

For:

> "The deal reached Contract Sent correctly but fulfillment did not start"

the useful next component is likely a reader/consumer.

Rather than encoding a growing taxonomy of diagnostic intents, Cord sends the grounded local situation to the LLM and asks:

> Given the validated anomaly, current evidence, and these actual adjacent graph actions, which should we investigate next?

## Canonical schema choice in the prototype

The prototype intentionally assumes that runtime state, graph property nodes, rules, and policies use the same canonical names:

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

This is a deliberate simplification.

The prototype is intended to prove:

```text
validated anomaly
+
graph structure
+
bounded LLM planning
→
dynamic causal diagnosis
```

It is not intended to prove arbitrary schema matching.

A future semantic-normalization layer can map customer-specific field names into these canonical concepts before the diagnosis engine runs.

## Core product boundary

Do not give the LLM the whole customer system and ask it to "figure it out."

Do not encode every diagnostic sequence as deterministic business logic.

Use:

```text
         Deterministic systems
       define facts and boundaries
                  │
                  ▼
        Current evidence state
                  │
                  ▼
          Local graph neighborhood
                  │
                  ▼
            Allowed actions
                  │
                  ▼
              LLM planner
        chooses the next action
                  │
                  ▼
         Backend validates action
                  │
                  ▼
        Deterministic tool executes
                  │
                  ▼
              New evidence
                  │
                  └──── repeat
```

## Where deterministic logic belongs

- retrieve actual graph nodes and edges
- fetch actual runtime values
- evaluate explicit business/configuration rules
- validate whether an observed state violates an expectation
- construct allowed next actions from real graph relationships
- validate LLM-selected actions
- execute graph/runtime queries
- maintain visited nodes, evidence, budgets, and loop state

## Where LLM reasoning belongs

- interpret ambiguous ticket language
- reason over a validated anomaly
- decide which adjacent graph action is most useful next
- use accumulated evidence from previous hops
- explain why an action is chosen
- assess whether evidence is converging on a root cause

## Investor takeaway

> **The graph constrains what is true and where Cord can move; the LLM decides how to investigate within those boundaries.**

## What this prototype is NOT

This is not:

- a HubSpot product
- a generic chatbot
- a static graph visualization
- a predefined animation
- an unconstrained LLM agent
- a handcrafted expert-system decision tree
- an autonomous remediation agent
- proof of automatic ontology generation
- proof of arbitrary schema reconciliation

It is a proof of the **bounded graph-investigation architecture**.
