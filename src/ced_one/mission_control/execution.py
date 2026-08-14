"""Controlled execution orchestration primitives for Mission Control v0.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExecutionPlanStep:
    """A single controlled step within the internal execution plan."""

    name: str
    description: str
    order: int
    status: str = "pending"
    division: str | None = None
    specialist: str | None = None
    capability: str | None = None
    approval_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "status": self.status,
            "division": self.division,
            "specialist": self.specialist,
            "capability": self.capability,
            "approval_required": self.approval_required,
            "metadata": self.metadata,
        }


@dataclass
class MissionExecutionPlan:
    """Internal execution plan used to orchestrate a MissionRequest."""

    plan_id: str
    request_id: str
    division: str | None
    specialist: str | None = None
    capability: str | None = None
    execution_mode: str = "controlled"
    provider: str | None = None
    approved: bool = False
    steps: list[ExecutionPlanStep] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "division": self.division,
            "specialist": self.specialist,
            "capability": self.capability,
            "execution_mode": self.execution_mode,
            "provider": self.provider,
            "approved": self.approved,
            "steps": [step.as_dict() for step in self.steps],
            "validation_errors": self.validation_errors,
            "created_at": self.created_at.isoformat(),
        }


__all__ = ["ExecutionPlanStep", "MissionExecutionPlan"]
