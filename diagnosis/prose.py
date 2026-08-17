"""Strip LLM markdown so user-facing Diagnose copy stays body text."""

from __future__ import annotations

import re


def plain_user_prose(text: str) -> str:
    cleaned = re.sub(r"```[\s\S]*?```", " ", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", cleaned).strip()
