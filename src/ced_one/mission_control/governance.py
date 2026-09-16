"""Execution governance gate and policy handling for Mission Control v0.8."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
import hashlib
import json
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
from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState
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
        if self.evaluated_at is None:
            self.evaluated_at = datetime.now(timezone.utc)

    def compute_fingerprint(self) -> str:
        errors = PolicyEvaluationEngine.validate_context(self)
        if errors:
            raise ValueError("; ".join(errors))
        raw = asdict(self)
        raw.pop("evaluated_at")
        raw.pop("context_fingerprint")
        classification = raw.get("risk_impact_classification")
        if classification:
            classification["classified_at"] = classification["classified_at"].isoformat()
        encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    @property
    def fingerprint(self) -> str:
        return self.compute_fingerprint()


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

    task_context: dict[str, Any] = field(default_factory=dict)
    adapter_type: str | None = None

    def __post_init__(self):
        if self.evaluated_at is None:
            self.evaluated_at = datetime.now(timezone.utc)

    @classmethod
    def from_context(cls, context: PolicyEvaluationContext) -> "AuthorizationSnapshot":
        if not isinstance(context, PolicyEvaluationContext):
            raise ValueError("Invalid authorization context type.")
        errors = PolicyEvaluationEngine.validate_context(context)
        if errors:
            raise ValueError("; ".join(errors))
        values = {name: deepcopy(getattr(context, name)) for name in cls.__dataclass_fields__}
        values["context_fingerprint"] = context.fingerprint
        return cls(**values)

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
            risk_impact_classification=deepcopy(self.risk_impact_classification),
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            evaluated_at=self.evaluated_at,
            task_context=deepcopy(self.task_context),
            adapter_type=self.adapter_type,
            context_fingerprint=self.context_fingerprint,
        )

    def is_still_valid(self, current_context: PolicyEvaluationContext) -> bool:
        if PolicyEvaluationEngine.validate_context(self) or PolicyEvaluationEngine.validate_context(current_context):
            return False
        try:
            return self.to_context().fingerprint == current_context.fingerprint
        except (TypeError, ValueError, AttributeError, RecursionError):
            return False


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
        try:
            result.context_fingerprint = context.fingerprint
        except (TypeError, ValueError, AttributeError, RecursionError):
            result.context_fingerprint = None
        return result


class MissionControlPolicyHandler:
    """Mission Control-owned processing layer for policy results."""

    @staticmethod
    def validate_compatibility(task_state: TaskLifecycleState, approval_state: ApprovalState) -> bool:
        return MissionTask.validate_compatibility(task_state, approval_state)

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
