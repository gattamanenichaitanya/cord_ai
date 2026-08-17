"""Incident ticket catalog. Identity only: incident_id → deal_id + text. No RCA."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from diagnosis.graph import DATA_DIR

INCIDENTS_PATH = DATA_DIR / "incidents.json"


@dataclass(frozen=True)
class Incident:
    id: str
    deal_id: str
    text: str
    summary: str = ""
    priority: str = "MED"
    source: str = "ServiceNow"


def load_incidents(path: Path | None = None) -> dict[str, Incident]:
    target = path or INCIDENTS_PATH
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    loaded: dict[str, Incident] = {}
    for raw in payload["incidents"]:
        incident = Incident(
            id=raw["id"],
            deal_id=raw["deal_id"],
            text=raw["text"],
            summary=raw.get("summary") or raw["text"][:80],
            priority=raw.get("priority", "MED"),
            source=raw.get("source", "ServiceNow"),
        )
        if "root_cause" in raw or "root_cause_node" in raw or "traversal" in raw:
            raise ValueError(f"Incident catalog must not include diagnosis fields: {incident.id}")
        loaded[incident.id] = incident
    return loaded


def get_incident(incident_id: str, path: Path | None = None) -> Incident:
    incidents = load_incidents(path)
    if incident_id not in incidents:
        raise KeyError(f"Unknown incident: {incident_id}")
    return incidents[incident_id]
