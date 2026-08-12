"""Approval guard logic for Mission Control v0.1."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import ApprovalRequirement, ApprovalState


class ApprovalGate:
    """Evaluate whether a request requires approval before proceeding."""

    @staticmethod
    def evaluate(request_metadata: dict[str, Any] | None = None) -> ApprovalRequirement:
        metadata = request_metadata or {}
        impact_level = str(metadata.get("impact_level", "low")).lower()
        approval_required = bool(metadata.get("approval_required", False))

        if impact_level in {"high", "critical", "irreversible"} or approval_required:
            return ApprovalRequirement(
                required=True,
                reason="High-impact or approval-gated action requires validation before continuation.",
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
    def status_for(requirement: ApprovalRequirement, approved: bool | None = None) -> ApprovalState:
        if not requirement.required:
            return ApprovalState.NOT_REQUIRED
        if approved is None:
            return ApprovalState.PENDING
        if approved:
            return ApprovalState.APPROVED
        return ApprovalState.REJECTED


__all__ = ["ApprovalGate"]
