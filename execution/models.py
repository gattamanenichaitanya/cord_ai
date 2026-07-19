from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Import from planning models as requested
from planning.models import PlanAction, ImplementationPlan


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # skipped due to unmet dependency


class LocationResult(BaseModel):
    """Result of a vision-based element location attempt."""
    found: bool
    reasoning: str
    coordinates: Optional[tuple[int, int]] = None
    bounding_box: Optional[Dict[str, int]] = None  # x, y, width, height
    alternative_selector: Optional[str] = None
    confidence: float
    followup_suggestion: Optional[str] = None


class ExecutionMethodUsed(str, Enum):
    API = "api"
    UI = "ui"


class ScreenshotRecord(BaseModel):
    step_id: int
    filename: str  # relative to run_dir/screenshots/
    caption: str  # e.g., "After clicking Save"
    timestamp: datetime


class ExecutionStep(BaseModel):
    """A single sub-step within an action's execution."""
    step_id: int
    intent: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    reasoning: Optional[str] = None  # AI's explanation of what it did
    healing_attempts: int = 0
    screenshots: List[ScreenshotRecord] = Field(default_factory=list)


class ActionResult(BaseModel):
    action_id: str
    operation_id: str
    method_used: Optional[ExecutionMethodUsed] = None
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    steps: List[ExecutionStep] = Field(default_factory=list)
    output_data: Dict[str, Any] = Field(default_factory=dict)  # e.g., {"created_property_id": "acs_risk_score"}
    error_message: Optional[str] = None
    verification_result: Optional[Dict[str, Any]] = None


class ExecutionReport(BaseModel):
    """The full audit trail of a plan execution."""
    plan_id: str
    plan_source_path: str
    run_dir: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    overall_status: ExecutionStatus
    action_results: List[ActionResult]
    total_duration_seconds: Optional[float] = None
    api_cost_estimate: Optional[float] = None  # for LLM calls made during execution
    summary: str = ""  # one-paragraph human-readable summary
