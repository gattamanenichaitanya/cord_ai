# 05 — UI Specification

The UI must visualize the **real execution trace** from the bounded graph-investigation engine.

Do not create a separate hardcoded animation timeline.

## 1. Canonical names in the UI

Internal graph/runtime identifiers should use:

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

The UI may render friendly labels such as:

```text
deal_amount          → Deal Amount
discount_pct         → Discount %
customer_tier        → Customer Tier
pricing_segment      → Pricing Segment
approval_required    → Approval Required
deal_stage           → Deal Stage
fulfillment_started  → Fulfillment Started
```

The friendly label is presentation only.

The underlying graph node/runtime key remains canonical.

## 2. System Map

Target:

```text
40–80 nodes
60–120 edges
```

Support:

- zoom
- pan
- hover
- click
- node name/type
- typed relationships

## 3. Incident panel

Display:

```text
Incident ID
Ticket text
Affected record ID
Diagnose button
```

## 4. Diagnose interaction

When Diagnose is clicked:

1. call the actual diagnosis engine
2. receive/stream investigation trace
3. update graph state from trace
4. update investigation log from trace
5. generate final RCA from the diagnosis result

No pre-authored `setTimeout()` sequence.

## 5. Show the planner's grounded choice

The UI should make visible:

```text
what Cord knows
what adjacent actions are available
what Cord chose
why it chose it
```

Example:

```text
OBSERVED

Deal Stage = Contract Sent
Finance approval was required first.

CONNECTED COMPONENTS

• Deal Stage Automation — WRITES Deal Stage
• Fulfillment Workflow — READS Deal Stage
• Reporting Workflow — READS Deal Stage

CORD DECISION

Investigate Deal Stage Automation

WHY

It is a producer of the anomalous Deal Stage value.
The other visible components consume that value downstream.
```

The explanation comes from the planner trace.

## 6. Graph states

```text
UNVISITED
CANDIDATE
CURRENT
VISITED_HEALTHY
VISITED_SUSPICIOUS
DISCARDED
ROOT_CAUSE
CAUSAL_PATH
```

Suggested behavior:

```text
unvisited      muted
candidate      emphasized
current        pulse
healthy        fade
suspicious     remain highlighted
discarded      fade strongly
root cause     strongest emphasis
causal path    remain visible at completion
```

## 7. Investigation log

Example:

```text
✓ Found DEAL-4821

✓ Policy violation confirmed
  Contract Sent occurred before required Finance approval.

CURRENT NODE
Deal Stage

CONNECTED
• Deal Stage Automation — WRITES
• Fulfillment Workflow — READS
• Reporting Workflow — READS

CORD DECISION
→ Inspect Deal Stage Automation

WHY
It produces the anomalous Deal Stage value.

✓ Workflow behaved as configured:
  Approval Required = false
  → Contract Sent

NEW SUSPICIOUS STATE
Approval Required = false

CONNECTED
• Discount Governance — WRITES
• Legacy Discount Override — WRITES
• Deal Stage Automation — READS

CORD DECISION
→ Inspect Discount Governance

...

ROOT CAUSE FOUND
Derive Pricing Segment
```

All entries must be generated from backend trace events.

## 8. Same graph, different decision

For Incident D:

```text
Deal reached Contract Sent correctly, but fulfillment never started.
```

The UI should show:

```text
Deal Stage = Contract Sent
✓ expected

Fulfillment Started = false
✕ anomalous
```

Using the same `deal_stage` neighborhood:

```text
• Deal Stage Automation — WRITES Deal Stage
• Fulfillment Workflow — READS Deal Stage
• Reporting Workflow — READS Deal Stage
```

the planner should visibly select:

```text
Fulfillment Workflow
```

This is an important demo moment because it shows the graph is not following a fixed edge policy.

## 9. Final RCA panel

Show:

- root cause
- causal path
- evidence
- affected records / impact
- recommended check
- confidence
- safety statement

Safety statement:

```text
Cord made no changes to the CRM.
```

## 10. Demo flow

```text
1. Open system graph.
2. Show incident.
3. Click Diagnose.
4. Validate anomaly.
5. Highlight anchor/current node.
6. Show bounded adjacent candidate actions.
7. Show Cord's selected action and reason.
8. Execute actual graph/runtime inspection.
9. Add new evidence.
10. Repeat.
11. Fade healthy/discarded branches.
12. Highlight root cause.
13. Reduce graph visually to the causal path.
14. Show RCA + evidence.
```

## 11. UI anti-patterns

Do not:

- animate a predetermined path
- show fake chain-of-thought
- reveal RCA before the engine returns it
- maintain frontend root-cause maps
- hardcode node IDs for tickets
- hardcode edge-direction choices
- let the frontend invent planner decisions
- make graph nodes decorative only

Show concise planner reasons, not hidden chain-of-thought.
