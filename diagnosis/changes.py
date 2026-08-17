"""Optional configuration-change history (read-only fixture)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from diagnosis.graph import DATA_DIR

CHANGES_PATH = DATA_DIR / "changes.json"


def load_changes(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or CHANGES_PATH
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    return [dict(item) for item in payload["changes"]]


def get_recent_changes(node_id: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    changes = load_changes(path)
    if node_id is None:
        return changes
    return [change for change in changes if change.get("modified_node_id") == node_id]
