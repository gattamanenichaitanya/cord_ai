"""Canonical field IDs for the diagnosis prototype.

Do not introduce aliases. Schema reconciliation is out of scope.
"""

from __future__ import annotations

CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        "deal_amount",
        "discount_pct",
        "customer_tier",
        "pricing_segment",
        "approval_required",
        "deal_stage",
        "fulfillment_started",
        "sales_process_complete",
    }
)

FORBIDDEN_ALIASES: frozenset[str] = frozenset(
    {
        "company.tier",
        "company_tier",
        "deal.amount",
        "amount",
        "deal.stage",
        "deal.pricing_segment",
    }
)


def is_canonical_field(field_id: str) -> bool:
    return field_id in CANONICAL_FIELDS


def assert_canonical_field(field_id: str) -> None:
    if field_id in FORBIDDEN_ALIASES or field_id not in CANONICAL_FIELDS:
        raise ValueError(
            f"Non-canonical field id {field_id!r}. "
            f"Use one of: {sorted(CANONICAL_FIELDS)}"
        )
