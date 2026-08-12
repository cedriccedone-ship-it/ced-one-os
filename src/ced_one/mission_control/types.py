"""Typed contracts used by Mission Control v0.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class RequestStatus(str, Enum):
    RECEIVED = "received"
    NORMALIZED = "normalized"
    CLASSIFIED = "classified"
    ROUTED = "routed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNROUTEABLE = "unrouteable"
    CANCELLED = "cancelled"


class ApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class MissionRequest:
    user_goal: str
    request_id: str = field(default_factory=lambda: "req_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"))
    request_type: str = "general"
    priority: Literal["low", "normal", "high"] = "normal"
    source: str = "user"
    business_division: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: RequestStatus = RequestStatus.RECEIVED
    approval_required: bool = False
    risk_tags: list[str] = field(default_factory=list)
    scope: str | None = None

    def with_metadata(self, **kwargs: Any) -> "MissionRequest":
        for key, value in kwargs.items():
            setattr(self, key, value)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_goal": self.user_goal,
            "request_type": self.request_type,
            "priority": self.priority,
            "source": self.source,
            "business_division": self.business_division,
            "context": self.context,
            "metadata": self.metadata,
            "constraints": self.constraints,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "approval_required": self.approval_required,
        }


@dataclass
class RouteDecision:
    division_name: str | None
    is_supported: bool
    is_routeable: bool
    confidence: float
    rationale: str
    status: str = "decision"
    classification: str | None = None
    specialist_name: str | None = None
    capability_name: str | None = None


@dataclass
class RequestClassification:
    domain_tags: list[str] = field(default_factory=list)
    risk_level: str = "low"
    confidence: float = 0.0
    division_hint: str | None = None
    rationale: str = ""


@dataclass
class DivisionResolutionResult:
    division_name: str | None
    is_supported: bool
    is_routeable: bool
    confidence: float
    rationale: str
    specialist_name: str | None = None
    capability_name: str | None = None
    status: str = "resolved"


@dataclass
class BusinessDivisionResolver:
    name: str
    scope: str | None = None

    def supports_request(self, request: MissionRequest, classification: RequestClassification | None = None) -> bool:
        return True

    def resolve(self, request: MissionRequest, classification: RequestClassification | None = None) -> DivisionResolutionResult:
        return DivisionResolutionResult(
            division_name=self.name,
            is_supported=True,
            is_routeable=True,
            confidence=0.5,
            rationale="Generic resolver support for a business division.",
            specialist_name=None,
            capability_name=None,
            status="resolved",
        )


@dataclass
class DivisionAssignment:
    division_name: str
    scope: str | None = None
    status: str = "assigned"


@dataclass
class SpecialistAssignment:
    name: str
    division_name: str
    permission_scope: str
    rationale: str


@dataclass
class CapabilityAssignment:
    name: str
    division_name: str
    contract: str
    rationale: str


@dataclass
class ApprovalRequirement:
    required: bool
    reason: str = ""
    level: str = "standard"
    approver_roles: list[str] = field(default_factory=list)
    validation_required: bool = False


@dataclass
class AuthorityValidationResult:
    valid: bool
    violations: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class MissionResult:
    request_id: str
    status: RequestStatus
    division: str | None = None
    specialist: str | None = None
    capability: str | None = None
    summary: str = ""
    result_payload: dict[str, Any] = field(default_factory=dict)
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    errors: list[str] = field(default_factory=list)
    success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
