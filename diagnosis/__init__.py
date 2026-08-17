"""Causal diagnosis package (prototype). Read-only; no HubSpot writes."""

from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import Neighbor, SystemGraph, load_graph

__all__ = [
    "CANONICAL_FIELDS",
    "Neighbor",
    "SystemGraph",
    "load_graph",
]
