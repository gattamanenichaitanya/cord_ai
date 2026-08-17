"""Canonical runtime-state lookup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diagnosis.fields import CANONICAL_FIELDS, FORBIDDEN_ALIASES, assert_canonical_field
from diagnosis.graph import DATA_DIR

RUNTIME_PATH = DATA_DIR / "runtime.json"


@dataclass(frozen=True)
class RuntimeState:
    deal_id: str
    values: dict[str, Any]

    def get(self, field_id: str) -> Any:
        assert_canonical_field(field_id)
        return self.values[field_id]

    def as_dict(self) -> dict[str, Any]:
        return {"deal_id": self.deal_id, **self.values}


def _validate_record(record: dict[str, Any]) -> RuntimeState:
    deal_id = record.get("deal_id")
    if not deal_id:
        raise ValueError("Runtime record missing deal_id")
    for alias in FORBIDDEN_ALIASES:
        if alias in record:
            raise ValueError(f"Forbidden alias in runtime record {deal_id}: {alias}")
    values: dict[str, Any] = {}
    for field_id in CANONICAL_FIELDS:
        if field_id not in record:
            raise ValueError(f"Runtime record {deal_id} missing canonical field {field_id}")
        values[field_id] = record[field_id]
    extra = set(record) - CANONICAL_FIELDS - {"deal_id"}
    if extra:
        raise ValueError(f"Runtime record {deal_id} has unknown keys: {sorted(extra)}")
    return RuntimeState(deal_id=str(deal_id), values=values)


def load_runtime(path: Path | None = None) -> dict[str, RuntimeState]:
    target = path or RUNTIME_PATH
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    records = payload["records"] if isinstance(payload, dict) else payload
    loaded: dict[str, RuntimeState] = {}
    for record in records:
        state = _validate_record(record)
        if state.deal_id in loaded:
            raise ValueError(f"Duplicate deal_id: {state.deal_id}")
        loaded[state.deal_id] = state
    return loaded


def get_runtime(deal_id: str, path: Path | None = None) -> RuntimeState:
    records = load_runtime(path)
    if deal_id not in records:
        raise KeyError(f"Unknown deal_id: {deal_id}")
    return records[deal_id]
