# 04 — Demo Data

## 1. Demo company

```text
Acme Cloud
```

System:

```text
HubSpot-like CRM / revenue operations environment
```

## 2. Canonical field names

Use these exact field IDs everywhere:

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

These names must match across:

- graph PROPERTY nodes
- runtime fixtures
- workflow rules
- business policies
- tests

No field-name reconciliation is part of this prototype.

## 3. Business policy

> Enterprise deals above $100,000 with discounts above 15% require Finance approval before they can move to `Contract Sent`.

Canonical representation:

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

## 4. Core property nodes

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

## 5. Core workflow nodes

```text
derive_pricing_segment
discount_governance
deal_stage_automation
legacy_discount_override
fulfillment_workflow
```

## 6. Core relationships

```text
derive_pricing_segment
    READS customer_tier

derive_pricing_segment
    WRITES pricing_segment

discount_governance
    READS deal_amount

discount_governance
    READS discount_pct

discount_governance
    READS pricing_segment

discount_governance
    WRITES approval_required

deal_stage_automation
    READS approval_required

deal_stage_automation
    READS sales_process_complete

deal_stage_automation
    WRITES deal_stage

legacy_discount_override
    READS discount_pct

legacy_discount_override
    WRITES approval_required

fulfillment_workflow
    READS deal_stage

fulfillment_workflow
    WRITES fulfillment_started
```

## 7. Workflow rules

### derive_pricing_segment — healthy version

```json
{
  "id": "derive_pricing_segment",
  "rule": {
    "cases": [
      {
        "when": [
          {"field": "customer_tier", "op": "==", "value": "Enterprise"}
        ],
        "then": {
          "field": "pricing_segment",
          "value": "Enterprise"
        }
      },
      {
        "when": [
          {"field": "customer_tier", "op": "==", "value": "SMB"}
        ],
        "then": {
          "field": "pricing_segment",
          "value": "SMB"
        }
      }
    ]
  }
}
```

### discount_governance — healthy version

```json
{
  "id": "discount_governance",
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

### deal_stage_automation

```json
{
  "id": "deal_stage_automation",
  "rule": {
    "all": [
      {"field": "approval_required", "op": "==", "value": false},
      {"field": "sales_process_complete", "op": "==", "value": true}
    ],
    "then": {
      "field": "deal_stage",
      "value": "Contract Sent"
    }
  }
}
```

### fulfillment_workflow

```json
{
  "id": "fulfillment_workflow",
  "rule": {
    "all": [
      {"field": "deal_stage", "op": "==", "value": "Contract Sent"}
    ],
    "then": {
      "field": "fulfillment_started",
      "value": true
    }
  }
}
```

## 8. Incident A — upstream workflow failure

Ticket:

```text
INC-4821

$250K enterprise deal with a 22% discount moved to Contract Sent without Finance approval.
```

Runtime:

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

Injected fault:

```text
derive_pricing_segment no longer populates pricing_segment
for customer_tier = Enterprise.
```

One possible broken rule fixture:

```json
{
  "id": "derive_pricing_segment",
  "rule": {
    "cases": [
      {
        "when": [
          {"field": "customer_tier", "op": "==", "value": "SMB"}
        ],
        "then": {
          "field": "pricing_segment",
          "value": "SMB"
        }
      }
    ]
  }
}
```

Optional change record:

```text
CHANGE-1007
modified: derive_pricing_segment
time: yesterday 18:42
summary: Enterprise branch removed from workflow
```

Expected diagnosis in tests:

```text
derive_pricing_segment
```

## 9. Incident B — same symptom class, different fault

Ticket:

```text
INC-4920

$250K enterprise deal with a 22% discount skipped Finance approval even though Pricing Segment is correct.
```

Runtime:

```json
{
  "deal_id": "DEAL-4920",
  "deal_amount": 250000,
  "discount_pct": 22,
  "customer_tier": "Enterprise",
  "pricing_segment": "Enterprise",
  "approval_required": false,
  "deal_stage": "Contract Sent",
  "fulfillment_started": false,
  "sales_process_complete": true
}
```

Injected fault:

```text
discount_governance rule is incorrect and fails to set approval_required=true.
```

Example broken rule fixture:

```json
{
  "id": "discount_governance",
  "rule": {
    "all": [
      {"field": "deal_amount", "op": ">", "value": 500000},
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

Expected diagnosis in tests:

```text
discount_governance
```

## 10. Incident C — multiple writers / different branch

Ticket:

```text
INC-5033

$50K SMB deal is stuck in Finance approval unexpectedly.
```

Runtime:

```json
{
  "deal_id": "DEAL-5033",
  "deal_amount": 50000,
  "discount_pct": 8,
  "customer_tier": "SMB",
  "pricing_segment": "SMB",
  "approval_required": true,
  "deal_stage": "Finance Approval",
  "fulfillment_started": false,
  "sales_process_complete": true
}
```

Injected fault:

```text
legacy_discount_override incorrectly writes approval_required=true.
```

Graph already contains:

```text
legacy_discount_override --WRITES--> approval_required
```

Expected diagnosis in tests:

```text
legacy_discount_override
```

This proves multiple writers and branch selection are supported.

## 11. Incident D — same anchor, different planner direction

Ticket:

```text
INC-5101

DEAL-5101 reached Contract Sent correctly, but fulfillment never started.
```

Runtime:

```json
{
  "deal_id": "DEAL-5101",
  "deal_amount": 80000,
  "discount_pct": 5,
  "customer_tier": "SMB",
  "pricing_segment": "SMB",
  "approval_required": false,
  "deal_stage": "Contract Sent",
  "fulfillment_started": false,
  "sales_process_complete": true
}
```

Injected fault:

```text
fulfillment_workflow is disabled or its rule is broken.
```

Expected context:

```text
deal_stage = Contract Sent
→ healthy

fulfillment_started = false
→ anomalous
```

Expected planner behavior:

```text
from the deal_stage neighborhood,
prefer fulfillment_workflow over deal_stage_automation
because the missing behavior is downstream.
```

Expected diagnosis in tests:

```text
fulfillment_workflow
```

## 12. Peripheral graph complexity

Add 30–60 unrelated but valid nodes.

Examples:

```text
lead_assignment_workflow
renewal_reminder_workflow
customer_health_score
territory_assignment
marketing_source
billing_contact_sync
sales_owner
renewal_date
nps_score
industry
region
partner_tier
slack_notification_integration
data_warehouse_sync
```

Purpose:

- make the graph visually rich
- test retrieval/pruning
- prevent a trivial five-node demo

Do not introduce alternate aliases for the canonical core fields.
