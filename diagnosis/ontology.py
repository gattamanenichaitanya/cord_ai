"""Ontology: types of things Cord understands, not customer-specific names."""

from enum import StrEnum


class NodeType(StrEnum):
    CRM_OBJECT = "CRM_OBJECT"
    PROPERTY = "PROPERTY"
    WORKFLOW = "WORKFLOW"
    WORKFLOW_BRANCH = "WORKFLOW_BRANCH"
    PIPELINE_STAGE = "PIPELINE_STAGE"
    TEAM = "TEAM"
    CUSTOM_CODE = "CUSTOM_CODE"
    INTEGRATION = "INTEGRATION"
    CHANGE = "CHANGE"
    INCIDENT = "INCIDENT"


class EdgeType(StrEnum):
    READS = "READS"
    WRITES = "WRITES"
    CONTAINS = "CONTAINS"
    MOVES_TO = "MOVES_TO"
    DEPENDS_ON = "DEPENDS_ON"
    CALLS = "CALLS"
    CALLS_OUT_TO = "CALLS_OUT_TO"
    MODIFIED = "MODIFIED"
    AFFECTS = "AFFECTS"
    TRIGGERS = "TRIGGERS"
