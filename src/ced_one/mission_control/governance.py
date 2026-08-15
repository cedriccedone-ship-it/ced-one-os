"""Execution governance gate and policy handling for Mission Control v0.8."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ced_one.mission_control.policy import (
    ExecutionPolicy,
    PolicyDecision,
    PolicyEvaluationEngine,
    PolicyEvaluationResult,
    PolicyRule,
    RiskImpactClassification,
)
from ced_one.mission_control.tasks import TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


@dataclass
class PolicyEvaluationContext:
    task_id: str
    mission_id: str
    task_lifecycle_state: TaskLifecycleState
    approval_state: ApprovalState
    division_binding: str | None
    specialist_binding: str | None
    capability_binding: str | None
    adapter_binding: str | None
    connector_binding: str | None = None
    connector_version: str | None = None
    permission_scope: str = "standard"
    execution_mode: str = "local"
    risk_impact_classification: RiskImpactClassification | None = None
    policy_id: str = "policy_default"
    policy_version: int = 1
    evaluated_at: datetime | None = None
    task_context: dict[str, Any] = field(default_factory=dict)
    adapter_type: str | None = None
    context_fingerprint: str | None = None

    def __post_init__(self):
        if self.risk_impact_classification is None:
            self.risk_impact_classification = RiskImpactClassification(
                classification_source="system",
                classification_version="1",
                classified_at=datetime.now(timezone.utc),
                risk_level="low",
                impact_level="limited",
                classification_context={},
            )
        if self.evaluated_at is None:
            self.evaluated_at = datetime.now(timezone.utc)

    def compute_fingerprint(self) -> str:
        raw = (
            self.task_id,
            self.mission_id,
            self.task_lifecycle_state.value,
            self.approval_state.value,
            self.division_binding,
            self.specialist_binding,
            self.capability_binding,
            self.adapter_binding,
            self.permission_scope,
            self.execution_mode,
            self.policy_id,
            self.policy_version,
            self.risk_impact_classification.risk_level,
            self.risk_impact_classification.impact_level,
            self.risk_impact_classification.classification_source,
            self.risk_impact_classification.classification_version,
        )
        return str(hash(raw))

    @property
    def fingerprint(self) -> str:
        if self.context_fingerprint is None:
            self.context_fingerprint = self.compute_fingerprint()
        return self.context_fingerprint


@dataclass
class AuthorizationSnapshot:
    task_id: str
    mission_id: str
    task_lifecycle_state: TaskLifecycleState
    approval_state: ApprovalState
    division_binding: str | None
    specialist_binding: str | None
    capability_binding: str | None
    adapter_binding: str | None
    connector_binding: str | None = None
    connector_version: str | None = None
    permission_scope: str = "standard"
    execution_mode: str = "local"
    risk_impact_classification: RiskImpactClassification | None = None
    policy_id: str = "policy_default"
    policy_version: int = 1
    evaluated_at: datetime | None = None
    context_fingerprint: str | None = None

    def __post_init__(self):
        if self.risk_impact_classification is None:
            self.risk_impact_classification = RiskImpactClassification(
                classification_source="system",
                classification_version="1",
                classified_at=datetime.now(timezone.utc),
                risk_level="low",
                impact_level="limited",
                classification_context={},
            )
        if self.evaluated_at is None:
            self.evaluated_at = datetime.now(timezone.utc)

    def to_context(self) -> PolicyEvaluationContext:
        return PolicyEvaluationContext(
            task_id=self.task_id,
            mission_id=self.mission_id,
            task_lifecycle_state=self.task_lifecycle_state,
            approval_state=self.approval_state,
            division_binding=self.division_binding,
            specialist_binding=self.specialist_binding,
            capability_binding=self.capability_binding,
            adapter_binding=self.adapter_binding,
            connector_binding=self.connector_binding,
            connector_version=self.connector_version,
            permission_scope=self.permission_scope,
            execution_mode=self.execution_mode,
            risk_impact_classification=self.risk_impact_classification,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            evaluated_at=self.evaluated_at,
            task_context={},
            context_fingerprint=self.context_fingerprint,
        )

    def is_still_valid(self, current_context: PolicyEvaluationContext) -> bool:
        if self.task_id != current_context.task_id:
            return False
        if self.mission_id != current_context.mission_id:
            return False
        if self.task_lifecycle_state != current_context.task_lifecycle_state:
            return False
        if self.approval_state != current_context.approval_state:
            return False
        if self.division_binding != current_context.division_binding:
            return False
        if self.specialist_binding != current_context.specialist_binding:
            return False
        if self.capability_binding != current_context.capability_binding:
            return False
        if self.adapter_binding != current_context.adapter_binding:
            return False
        if self.connector_binding != current_context.connector_binding:
            return False
        if self.connector_version != current_context.connector_version:
            return False
        if self.permission_scope != current_context.permission_scope:
            return False
        if self.execution_mode != current_context.execution_mode:
            return False
        if self.policy_id != current_context.policy_id:
            return False
        if self.policy_version != current_context.policy_version:
            return False
        if self.risk_impact_classification.risk_level != current_context.risk_impact_classification.risk_level:
            return False
        if self.risk_impact_classification.impact_level != current_context.risk_impact_classification.impact_level:
            return False
        if self.risk_impact_classification.classification_source != current_context.risk_impact_classification.classification_source:
            return False
        if self.risk_impact_classification.classification_version != current_context.risk_impact_classification.classification_version:
            return False
        return True


@dataclass
class PolicyAuditRecord:
    observed_task_state: TaskLifecycleState | None = None
    observed_approval_state: ApprovalState | None = None
    policy_decision: PolicyDecision | None = None
    policy_reason: str | None = None
    policy_id: str | None = None
    rule_id: str | None = None
    policy_version: int | None = None
    rule_version: int | None = None
    context_fingerprint: str | None = None
    evaluated_at: datetime | None = None
    previous_state: str | None = None
    resulting_state: str | None = None


class ExecutionGovernanceGate:
    """Pure evaluator that returns a policy decision without mutating lifecycle state."""

    def evaluate(self, context: PolicyEvaluationContext, *, policy: ExecutionPolicy) -> PolicyEvaluationResult:
        engine = PolicyEvaluationEngine(policy)
        result = engine.evaluate(context)
        result.context_fingerprint = context.fingerprint
        return result


class MissionControlPolicyHandler:
    """Mission Control-owned processing layer for policy results."""

    @staticmethod
    def validate_compatibility(task_state: TaskLifecycleState, approval_state: ApprovalState) -> bool:
        valid_map = {
            TaskLifecycleState.PENDING: {ApprovalState.NOT_REQUIRED, ApprovalState.PENDING, ApprovalState.ESCALATED},
            TaskLifecycleState.BLOCKED: {ApprovalState.PENDING, ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.ESCALATED},
            TaskLifecycleState.READY: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.ASSIGNED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.IN_PROGRESS: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.COMPLETED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.FAILED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.REJECTED},
            TaskLifecycleState.RETRY_PENDING: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.PENDING},
            TaskLifecycleState.REJECTED: {ApprovalState.REJECTED, ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.CANCELLED: {ApprovalState.NOT_REQUIRED, ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.PENDING},
        }
        return approval_state in valid_map.get(task_state, set())

    @staticmethod
    def handle(result: PolicyEvaluationResult) -> dict[str, Any]:
        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            return {
                "mission_control_action": "approval_required",
                "decision": result.decision.value,
                "reason": result.reason,
            }
        if result.decision == PolicyDecision.ESCALATE:
            return {
                "mission_control_action": "escalate",
                "decision": result.decision.value,
                "reason": result.reason,
            }
        if result.decision == PolicyDecision.DENY:
            return {
                "mission_control_action": "deny",
                "decision": result.decision.value,
                "reason": result.reason,
            }
        return {
            "mission_control_action": "allow",
            "decision": result.decision.value,
            "reason": result.reason,
        }

    @staticmethod
    def build_audit_record(
        *,
        task_state: TaskLifecycleState | None,
        approval_state: ApprovalState | None,
        decision: PolicyDecision,
        reason: str,
        policy_id: str,
        rule_id: str,
        policy_version: int,
        rule_version: int,
        context_fingerprint: str,
    ) -> PolicyAuditRecord:
        return PolicyAuditRecord(
            observed_task_state=task_state,
            observed_approval_state=approval_state,
            policy_decision=decision,
            policy_reason=reason,
            policy_id=policy_id,
            rule_id=rule_id,
            policy_version=policy_version,
            rule_version=rule_version,
            context_fingerprint=context_fingerprint,
            evaluated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def is_final_authority() -> bool:
        return True


__all__ = [
    "AuthorizationSnapshot",
    "ExecutionGovernanceGate",
    "MissionControlPolicyHandler",
    "PolicyAuditRecord",
    "PolicyEvaluationContext",
    "PolicyEvaluationResult",
]
