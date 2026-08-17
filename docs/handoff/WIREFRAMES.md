# CordAI Diagnose Mode — Wireframes

## 1. Product shell

CordAI remains a single product with two top-level working modes:

```text
[ Implement ] [ Diagnose ]
```

This behaves like a mode switch, not two separate applications.

- **Implement** keeps the current implementation workflow.
- **Diagnose** opens the maintenance / support workspace.

The existing Streamlit shell, CordAI branding, sidebar, user profile, and visual language should be preserved.

---

## 2. Global shell

```text
┌───────────────────────┬──────────────────────────────────────────────────────────────┐
│ ✦ CordAI              │                                                              │
│                       │                    CURRENT PAGE                               │
│ [Implement][Diagnose] │                                                              │
│                       │                                                              │
│ DIAGNOSE              │                                                              │
│ ▣ Dashboard           │                                                              │
│ ◉ System Graph        │                                                              │
│ ◫ Tickets             │                                                              │
│ ◌ Chat                │                                                              │
│                       │                                                              │
│                       │                                                              │
│───────────────────────│                                                              │
│ JD  John Doe          │                                                              │
│     john@acme.com     │                                                              │
└───────────────────────┴──────────────────────────────────────────────────────────────┘
```

When `Implement` is selected, preserve the existing CordAI implementation UI.

When `Diagnose` is selected, the sidebar navigation becomes:

```text
Dashboard
System Graph
Tickets
Chat
```

Default Diagnose page: `Dashboard`.

---

## 3. Diagnose — Dashboard

Purpose:

> Give an operations/support user a concise view of support load and diagnosis outcomes.

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Dashboard                                             Acme Cloud · HubSpot ▾          │
│ System health and support activity                                                  │
│                                                                                    │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐ │
│ │ OPEN TICKETS │ │ DIAGNOSED    │ │ NEEDS HUMAN  │ │ AVG DIAGNOSIS TIME         │ │
│ │ 18           │ │ 41           │ │ 3            │ │ 42 sec                     │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ └────────────────────────────┘ │
│                                                                                    │
│ ┌───────────────────────────────────────┐ ┌──────────────────────────────────────┐ │
│ │ Ticket activity                       │ │ Diagnosis outcomes                   │ │
│ │                                       │ │                                      │ │
│ │         [ trend / bar chart ]         │ │ Diagnosed          76%              │ │
│ │                                       │ │ Needs Human        14%              │ │
│ │                                       │ │ No Validated       6%               │ │
│ │                                       │ │ Diagnosing          4%               │ │
│ └───────────────────────────────────────┘ └──────────────────────────────────────┘ │
│                                                                                    │
│ Recent tickets                                                       View all →    │
│ ┌────────────────────────────────────────────────────────────────────────────────┐ │
│ │ INC-4821 HIGH Finance approval bypassed      Diagnosed      12m ago   [View] │ │
│ │ INC-4819 MED  Renewal discount incorrect    Diagnosing     20m ago   [Open] │ │
│ │ INC-4815 HIGH Fulfillment did not trigger   Needs Human    1h ago    [View] │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Do not overload the dashboard. It exists to show that tickets arrive, Cord diagnoses them, some require humans, and users can drill into tickets or the graph.

---

## 4. Diagnose — System Graph

Purpose:

> Show Cord's persistent understanding of how the customer's SaaS instance is wired.

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ System Graph                                          Acme Cloud · HubSpot ▾          │
│                                                                                    │
│ [Search component...] [All ▾] [Workflows] [Properties] [Integrations] [Custom Code]│
│                                                                                    │
│ ┌──────────────────────────────────────────────────────────┬───────────────────────┐ │
│ │                                                          │ COMPONENT             │ │
│ │                                                          │                       │ │
│ │                   FULL SYSTEM GRAPH                      │ Discount Governance   │ │
│ │                                                          │ Workflow              │ │
│ │              ○────○──────○                              │                       │ │
│ │             ╱     │       ╲                             │ Reads                 │ │
│ │       ○────○──────○───────○                            │ • deal_amount         │ │
│ │             ╲     │       ╱                             │ • discount_pct        │ │
│ │              ○────○──────○                              │ • pricing_segment     │ │
│ │                   │                                      │                       │ │
│ │                 ...                                      │ Writes                │ │
│ │                                                          │ • approval_required   │ │
│ │                                                          │                       │ │
│ │                                                          │ [View related tickets]│ │
│ └──────────────────────────────────────────────────────────┴───────────────────────┘ │
│                                                                                    │
│ 74 components · 128 dependencies · 11 workflows · 4 integrations                  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Interactions:

- zoom / pan;
- search node;
- filter by node type;
- click node → inspector panel;
- hover/click edge → relation type;
- highlight immediate neighborhood;
- link from component to related tickets.

When opened from a diagnosed ticket, allow:

```text
[ Full System ] [ Incident Path ]
```

In `Incident Path` mode:

- unrelated nodes fade;
- visited investigation nodes remain visible;
- causal path is emphasized;
- root-cause node is marked.

---

## 5. Diagnose — Tickets

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Tickets                                               Acme Cloud · HubSpot ▾          │
│                                                                                    │
│ [All ▾] [Status ▾] [Priority ▾] [Source ▾]   [Search tickets.....................]│
│                                                                                    │
│ ┌────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Ticket   Priority   Summary                       Source      Diagnosis   Updated│ │
│ ├────────────────────────────────────────────────────────────────────────────────┤ │
│ │ INC-4821 HIGH       Finance approval bypassed    ServiceNow  Diagnosed   12m   │ │
│ │ INC-4819 MED        Renewal discount incorrect   Jira        Diagnosing  20m   │ │
│ │ INC-4815 HIGH       Fulfillment did not trigger  ServiceNow  Needs Human 1h    │ │
│ │ INC-4803 LOW        Sales owner not populated    HubSpot     Ready       3h    │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Diagnosis states:

```text
READY
DIAGNOSING
DIAGNOSED
NEEDS_HUMAN
NO_VALIDATED_ANOMALY
```

Clicking a row opens Ticket Detail.

---

## 6. Ticket Detail — before diagnosis

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ← Tickets   INC-4821                                      HIGH      Ready            │
│                                                                                    │
│ Finance approval bypassed on enterprise deal                                      │
│ ServiceNow · Opened 12 minutes ago · DEAL-4821                                     │
│                                                                                    │
│ ┌────────────────────────────────────────────────────────────────────────────────┐ │
│ │ $250K enterprise deal with a 22% discount moved to Contract Sent without      │ │
│ │ Finance approval.                                                              │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                    │
│ Affected system        Relevant record        Source                               │
│ HubSpot                DEAL-4821              ServiceNow                           │
│                                                                                    │
│                              [ Run Diagnosis ]                                     │
│                                                                                    │
│ Related system context                                                             │
│ ┌────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 6 potentially relevant components identified from 74 total components          │ │
│ │ [Preview graph]                                                                │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Ticket Detail — diagnosis running

This is the central demo view.

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ← Tickets   INC-4821                                ● Diagnosing                    │
│                                                                                    │
│ ┌─────────────────────────────────────────────────┬───────────────────────────────┐ │
│ │ INVESTIGATION GRAPH                             │ INVESTIGATION                 │ │
│ │                                                 │                               │ │
│ │          ○ fulfillment_workflow                 │ ✓ Runtime loaded             │ │
│ │           ╲ READS                               │                               │ │
│ │            ╲                                    │ ✓ Policy violation           │ │
│ │       ● deal_stage                              │   confirmed                  │ │
│ │            ▲                                    │                               │ │
│ │            │ WRITES                             │ CURRENT                      │ │
│ │       ◉ deal_stage_automation                   │ Deal Stage                   │ │
│ │            │                                    │                               │ │
│ │            │ READS                              │ Connected                    │ │
│ │       ○ approval_required                       │ • Stage Automation           │ │
│ │                                                 │ • Fulfillment Workflow       │ │
│ │                                                 │ • Reporting Workflow         │ │
│ │                                                 │                               │ │
│ │                                                 │ CORD DECISION               │ │
│ │                                                 │ Inspect Stage Automation     │ │
│ │                                                 │                               │ │
│ │                                                 │ Why                          │ │
│ │                                                 │ It produces the anomalous    │ │
│ │                                                 │ Deal Stage value.            │ │
│ └─────────────────────────────────────────────────┴───────────────────────────────┘ │
│                                                                                    │
│ [Open in Chat]                                                                     │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

The graph and feed must be driven by the backend investigation trace. No frontend-defined traversal.

---

## 8. Ticket Detail — diagnosed

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ← Tickets   INC-4821                                  ✓ Diagnosed                    │
│                                                                                    │
│ ROOT CAUSE                                                                         │
│ Derive Pricing Segment no longer populates Pricing Segment for Enterprise deals.   │
│ Confidence: High                                                                   │
│                                                                                    │
│ ┌────────────────────────────────────┐ ┌─────────────────────────────────────────┐ │
│ │ CAUSAL PATH                        │ │ EVIDENCE                                │ │
│ │ customer_tier = Enterprise         │ │ Deal Amount        $250,000             │ │
│ │        ↓                           │ │ Discount           22%                  │ │
│ │ derive_pricing_segment ← ROOT      │ │ Customer Tier      Enterprise           │ │
│ │        ↓                           │ │ Pricing Segment    NULL                 │ │
│ │ pricing_segment = NULL             │ │ Approval Required  false                │ │
│ │        ↓                           │ │ Deal Stage         Contract Sent        │ │
│ │ discount_governance                │ │                                         │ │
│ │        ↓                           │ │ Recent change                           │ │
│ │ approval_required = false          │ │ Enterprise branch removed yesterday    │ │
│ │        ↓                           │ │                                         │ │
│ │ deal_stage_automation              │ │                                         │ │
│ │        ↓                           │ │                                         │ │
│ │ Contract Sent                      │ │                                         │ │
│ └────────────────────────────────────┘ └─────────────────────────────────────────┘ │
│                                                                                    │
│ [View in System Graph]   [Open in Chat]                                            │
│ Cord made no changes to the target system.                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Diagnose — Chat

Chat is for questioning Cord's diagnosis and system understanding, not for running the diagnosis itself.

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Chat                                                  Acme Cloud · HubSpot ▾          │
│ Context: [ INC-4821 ▾ ]                                                           │
│                                                                                    │
│ ┌──────────────────────────────────────────────────┬─────────────────────────────┐ │
│ │ CONVERSATION                                     │ ACTIVE CONTEXT              │ │
│ │                                                  │                             │ │
│ │ You                                              │ Ticket                      │ │
│ │ Why did Cord inspect Deal Stage Automation      │ INC-4821                    │ │
│ │ first?                                           │                             │ │
│ │                                                  │ Root Cause                  │ │
│ │ Cord                                             │ Derive Pricing Segment      │ │
│ │ The observed Deal Stage was invalid. Among      │                             │ │
│ │ connected components, Deal Stage Automation     │ Relevant graph              │ │
│ │ produces that value while Fulfillment and       │ [ small incident graph ]    │ │
│ │ Reporting consume it downstream.                │                             │ │
│ │                                                  │ Evidence                    │ │
│ │ You                                              │ 5 items                     │ │
│ │ Show me what changed yesterday.                 │                             │ │
│ │                                                  │ [Open full diagnosis]       │ │
│ │ ───────────────────────────────────────────────  │                             │ │
│ │ Ask about this ticket or system...         [↑]  │                             │ │
│ └──────────────────────────────────────────────────┴─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Chat contexts:

```text
Current Ticket
Current System
Selected Graph Component
```

Example questions:

- Why did Cord choose this branch?
- What evidence makes this the root cause?
- What changed recently?
- What else depends on `pricing_segment`?
- Which other tickets involved this workflow?

---

## 10. Navigation flows

Ticket-driven:

```text
Diagnose
→ Tickets
→ Ticket
→ Run Diagnosis
→ Investigation Graph + Feed
→ RCA
→ View in System Graph / Open in Chat
```

Graph-driven:

```text
Diagnose
→ System Graph
→ Select component
→ View related tickets
→ Ticket
```

Chat-driven:

```text
Diagnose
→ Chat
→ Select ticket/system/component context
→ Ask question
→ Open graph or diagnosis
```

---

## 11. Visual priorities

Priority order:

```text
1. Business incident
2. Diagnosis state/result
3. System graph
4. Evidence
5. Conversation
6. Implementation internals
```

Do not expose normal users to:

```text
semantic_role
edge_direction
candidate_action_id
planner JSON
raw model response
```

Translate these to product language:

```text
Producer
Consumer
Cord chose
Evidence
Root cause
Causal path
```
