"""Authority, approval, and safety gates for Mission Control v0.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ced_one.mission_control.types import ApprovalRequirement, ApprovalState, AuthorityValidationResult


@dataclass
class GuardResult:
    valid: bool
    message: str = ""
    violations: list[str] = field(default_factory=list)
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED


class MissionGuard:
    """Validate authority boundaries and approval requirements."""

    @staticmethod
    def validate_authority(metadata: dict[str, Any] | None = None) -> AuthorityValidationResult:
        metadata = metadata or {}
        violations: list[str] = []
        blocked_by: list[str] = []

        if metadata.get("authority_override") is True:
            violations.append("A lower layer attempted to override the governing authority.")
            blocked_by.append("constitution")

        if metadata.get("core_override") is True:
            violations.append("A lower layer attempted to override Ced-One Core authority.")
            blocked_by.append("core")

        if not violations:
            return AuthorityValidationResult(
                valid=True,
                violations=[],
                blocked_by=[],
                message="Authority validation passed.",
            )

        return AuthorityValidationResult(
            valid=False,
            violations=violations,
            blocked_by=blocked_by,
            message="Authority validation failed; governance and core boundaries must be preserved.",
        )

    @staticmethod
    def evaluate_approval(metadata: dict[str, Any] | None = None) -> ApprovalRequirement:
        metadata = metadata or {}
        impact_level = str(metadata.get("impact_level", "low")).lower()
        requested = bool(metadata.get("approval_required", False))

        if impact_level in {"high", "critical", "irreversible"} or requested:
            return ApprovalRequirement(
                required=True,
                reason="High-impact or approval-gated action requires explicit validation before continuation.",
                level="high",
                approver_roles=["mission_control", "governance"],
                validation_required=True,
            )

        return ApprovalRequirement(
            required=False,
            reason="No approval gate required at this stage.",
            level="standard",
            approver_roles=[],
            validation_required=False,
        )

    @staticmethod
    def approval_state(requirement: ApprovalRequirement, approved: bool | None = None) -> ApprovalState:
        if not requirement.required:
            return ApprovalState.NOT_REQUIRED
        if approved is None:
            return ApprovalState.PENDING
        if approved:
            return ApprovalState.APPROVED
        return ApprovalState.REJECTED


__all__ = ["GuardResult", "MissionGuard"]
