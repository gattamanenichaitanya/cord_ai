"""Deterministic ticket parser. Emits clues only — never RCA, next node, or path."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.incidents import Incident, get_incident

FORBIDDEN_PARSE_KEYS = frozenset(
    {
        "root_cause",
        "root_cause_node",
        "next_node",
        "traversal",
        "traversal_path",
        "path",
        "rca",
        "diagnosis",
        "selected_action_id",
    }
)

_INCIDENT_RE = re.compile(r"\bINC-\d+\b", re.I)
_DEAL_RE = re.compile(r"\bDEAL-\d+\b", re.I)
_AMOUNT_RE = re.compile(r"\$(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([KkMm])?\b")
_DISCOUNT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*discount|discount(?:\s+(?:of|at))?\s+(\d+(?:\.\d+)?)\s*(?:%|percent)",
    re.I,
)

_CONCEPT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"finance approval|without finance|skipped finance|approval", "finance approval"),
    (r"deal stage|moved to|contract sent|pipeline", "deal stage"),
    (r"pricing segment", "pricing segment"),
    (r"discount", "discount"),
    (r"enterprise", "enterprise"),
    (r"\bsmb\b", "smb"),
    (r"fulfillment", "fulfillment"),
)


@dataclass(frozen=True)
class ObservedClaim:
    subject: str
    value: Any
    qualifier: str

    def as_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "value": self.value, "qualifier": self.qualifier}


@dataclass(frozen=True)
class TicketParse:
    incident_id: str | None
    record_id: str | None
    entity_type: str
    mentioned_concepts: list[str]
    observed_claims: list[ObservedClaim]
    mentioned_values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "incident_id": self.incident_id,
            "record_id": self.record_id,
            "entity_type": self.entity_type,
            "mentioned_concepts": list(self.mentioned_concepts),
            "observed_claims": [claim.as_dict() for claim in self.observed_claims],
            "mentioned_values": dict(self.mentioned_values),
        }
        leaked = FORBIDDEN_PARSE_KEYS.intersection(payload)
        if leaked:
            raise RuntimeError(f"Parser must not emit diagnosis fields: {sorted(leaked)}")
        return payload


def _parse_amount(text: str) -> int | None:
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").upper()
    if suffix == "K":
        number *= 1000
    elif suffix == "M":
        number *= 1_000_000
    return int(number)


def _parse_discount(text: str) -> float | None:
    match = _DISCOUNT_RE.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    return float(raw)


def _concepts(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for pattern, label in _CONCEPT_PATTERNS:
        if re.search(pattern, lower) and label not in found:
            found.append(label)
    return found


def _stage_qualifier(lower: str, *, default: str = "mentioned") -> str:
    if "correctly" in lower:
        return "expected"
    if any(token in lower for token in ("without", "skipped", "unexpected", "stuck")):
        return "unexpected"
    return default


def _claims(text: str) -> list[ObservedClaim]:
    claims: list[ObservedClaim] = []
    lower = text.lower()
    seen_subjects: set[str] = set()

    def add(subject: str, value: Any, qualifier: str) -> None:
        if subject not in CANONICAL_FIELDS or subject in seen_subjects:
            return
        seen_subjects.add(subject)
        claims.append(ObservedClaim(subject=subject, value=value, qualifier=qualifier))

    if "contract sent" in lower:
        add("deal_stage", "Contract Sent", _stage_qualifier(lower))
    elif re.search(r"stuck in finance approval", lower):
        add("deal_stage", "Finance Approval", "unexpected")

    if re.search(
        r"without finance approval|skipped finance approval|without finance|no finance approval",
        lower,
    ):
        add("approval_required", False, "unexpected")
    elif re.search(r"stuck in finance approval|finance approval unexpectedly", lower):
        add("approval_required", True, "unexpected")

    if re.search(r"fulfillment never started|never started|fulfillment did not start", lower):
        add("fulfillment_started", False, "unexpected")

    if re.search(r"pricing segment is correct", lower):
        add("pricing_segment", "Enterprise", "expected")

    return claims


def _mentioned_values(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    amount = _parse_amount(text)
    if amount is not None:
        values["deal_amount"] = amount
    discount = _parse_discount(text)
    if discount is not None:
        values["discount_pct"] = discount
    lower = text.lower()
    if re.search(r"\benterprise\b", lower):
        values["customer_tier"] = "Enterprise"
    elif re.search(r"\bsmb\b", lower):
        values["customer_tier"] = "SMB"
    for key in values:
        if key not in CANONICAL_FIELDS:
            raise ValueError(f"Parser emitted non-canonical field {key}")
    return values


def parse_ticket(text: str, *, incident: Incident | None = None) -> TicketParse:
    incident_id = None
    record_id = None
    inc_match = _INCIDENT_RE.search(text)
    if inc_match:
        incident_id = inc_match.group(0).upper()
    deal_match = _DEAL_RE.search(text)
    if deal_match:
        record_id = deal_match.group(0).upper()
    if incident is not None:
        incident_id = incident.id
        record_id = record_id or incident.deal_id
    return TicketParse(
        incident_id=incident_id,
        record_id=record_id,
        entity_type="deal",
        mentioned_concepts=_concepts(text),
        observed_claims=_claims(text),
        mentioned_values=_mentioned_values(text),
    )


def parse_incident(incident_id: str) -> TicketParse:
    incident = get_incident(incident_id)
    return parse_ticket(f"{incident.id}\n\n{incident.text}", incident=incident)
