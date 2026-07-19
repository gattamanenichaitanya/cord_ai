"""Pydantic models for stage input/output"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────
# Stage 1: Requirement Extraction
# ────────────────────────────────────────────────

class RequirementType(str, Enum):
    OBJECT_CONFIGURATION = "object_configuration"  # custom objects
    PROPERTY_CONFIGURATION = "property_configuration"  # custom properties
    WORKFLOW = "workflow"  # automation rules
    PIPELINE = "pipeline"  # deal/ticket pipelines
    DASHBOARD = "dashboard"  # reports and dashboards
    INTEGRATION = "integration"  # external system connections
    USER_PERMISSION = "user_permission"  # role and access setup
    OTHER = "other"


class ExtractedRequirement(BaseModel):
    id: str  # e.g., "REQ-001"
    title: str  # short label
    description: str  # full description in plain English
    requirement_type: RequirementType
    source_section: str  # e.g., "Section 6.1"
    source_excerpt: str  # the original text from the doc
    dependencies: list[str] = Field(default_factory=list)  # ids of other requirements this depends on


class Stage1Output(BaseModel):
    document_summary: str  # 2-3 sentence overview of the doc
    requirements: list[ExtractedRequirement]
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)  # tokens used, model, timestamp


# ────────────────────────────────────────────────
# Stage 2: Concept Mapping
# ────────────────────────────────────────────────

class CandidateGraphEntry(BaseModel):
    entry_id: str  # from the graph (e.g., "notes_last_contacted")
    entry_type: str  # "standard_property", "capability", "operation", etc.
    file_path: str  # graph/hubspot/properties/notes_last_contacted.json
    relevance_score: float  # 0.0 to 1.0
    reasoning: str  # why this entry is relevant


class Stage2Output(BaseModel):
    requirement_id: str
    candidates: list[CandidateGraphEntry]
    interpretation: str  # the AI's restatement of what the requirement needs
    ambiguities: list[str] = Field(default_factory=list)  # things that aren't clear from the doc


# ────────────────────────────────────────────────
# Stage 3: Architecture Decision
# ────────────────────────────────────────────────

class ArchitectureDecision(BaseModel):
    requirement_id: str
    approach_summary: str  # one-sentence summary, max 25 words
    rationale: str  # why this approach was chosen
    selected_capabilities: list[str]  # capability_names used
    selected_operations: list[str]  # operation_ids that will execute
    parameters: dict[str, Any] = Field(default_factory=dict)  # specific values to use (property names, workflow names, etc.)
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)  # other options considered with reasons


# ────────────────────────────────────────────────
# Stage 4: Live State Inspection
# ────────────────────────────────────────────────

class StateInspectionItem(BaseModel):
    item_type: str  # "property", "workflow", "integration", etc.
    item_id: str  # name or identifier
    exists: bool
    details: dict[str, Any] | None = None  # full API response if exists


class Stage4Output(BaseModel):
    requirement_id: str
    inspected_items: list[StateInspectionItem]
    inspection_summary: str  # plain English


# ────────────────────────────────────────────────
# Stage 5: Gap Detection
# ────────────────────────────────────────────────

class Severity(str, Enum):
    HIGH = "high"  # blocks execution
    MEDIUM = "medium"  # consultant should address
    LOW = "low"  # informational


class Gap(BaseModel):
    gap_id: str  # unique within this pipeline run
    severity: Severity
    title: str  # short label
    summary: str  # ONE sentence, max 25 words
    description: str | None = None  # full explanation (optional)
    referenced_gotcha: str | None = None  # gotcha_id if surfaced from graph
    suggested_resolution: str | None = None
    blocks_execution: bool


class Stage5Output(BaseModel):
    requirement_id: str
    gaps: list[Gap]
    summary: str  # "Found 2 high-severity gaps, 1 medium..."


# ────────────────────────────────────────────────
# Stage 6: Dependency Resolution
# ────────────────────────────────────────────────

class PlanAction(BaseModel):
    action_id: str  # unique within plan
    operation_id: str  # from graph (e.g., "hubspot.create_custom_property")
    description: str  # human-readable
    parameters: dict[str, Any] = Field(default_factory=dict)  # what to pass to the operation
    depends_on: list[str] = Field(default_factory=list)  # other action_ids that must complete first
    estimated_duration_seconds: int




# ────────────────────────────────────────────────
# Stage 7: Plan Synthesis
# ────────────────────────────────────────────────

class ImplementationPlan(BaseModel):
    plan_id: str  # uuid or timestamp-based
    requirement_id: str
    requirement_title: str
    document_source: str  # original document path
    
    # The actual executable content
    actions: list[PlanAction]
    
    # Context for the consultant reviewing
    approach_summary: str
    rationale: str
    identified_gaps: list[Gap] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime
    pipeline_metadata: dict[str, Any] = Field(default_factory=dict)  # which stages ran, tokens used, etc.
    
    # Approval state (consultant flips this)
    approved: bool = False
    approval_notes: str | None = None






