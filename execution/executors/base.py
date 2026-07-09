from abc import ABC, abstractmethod
from pathlib import Path
from planning.models import PlanAction
from execution.models import ActionResult


class ExecutorBase(ABC):
    """Abstract base class for plan executors using async interface."""

    @abstractmethod
    async def can_execute(self, operation_entry: dict) -> bool:
        """Check if this executor can handle the given operation."""
        pass

    @abstractmethod
    async def execute(
        self,
        action: PlanAction,
        operation_entry: dict,
        run_dir: Path
    ) -> ActionResult:
        """Execute one action. Returns the result with audit trail."""
        pass
