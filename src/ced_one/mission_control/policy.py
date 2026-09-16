"""Policy and governance primitives for Mission Control v0.8."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import math


def validate_context_data(value: Any) -> list[str]:
    """Validate plain, finite authorization data before copying or serializing it."""
    ancestors = set()
    stack = [(value, False)]
    while stack:
        item, leaving = stack.pop()
        if leaving:
            ancestors.remove(id(item))
            continue
        if type(item) in (dict, list):
            if id(item) in ancestors:
                return ["Cyclic authorization data is unsupported."]
            ancestors.add(id(item))
            stack.append((item, True))
            if type(item) is dict:
                if any(type(key) is not str for key in item):
                    return ["Authorization dictionary keys must be strings."]
                stack.extend((child, False) for child in item.values())
            else:
                stack.extend((child, False) for child in item)
        elif item is None or type(item) in (str, bool, int):
            continue
        elif type(item) is float and math.isfinite(item):
            continue
        else:
            return ["Unsupported authorization data value."]
    return []


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"


@dataclass
class RiskImpactClassification:
    classification_source: str
    classification_version: str
    classified_at: datetime
    risk_level: str
    impact_level: str
    classification_context: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name in ("classification_source", "classification_version", "risk_level", "impact_level"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Invalid classification field: {name}.")
        if not isinstance(self.classified_at, datetime) or self.classified_at.tzinfo is None:
            errors.append("Classification timestamp must include a timezone.")
        if not isinstance(self.classification_context, dict):
            errors.append("Classification context must be a dict.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification_source": self.classification_source,
            "classification_version": self.classification_version,
            "classified_at": self.classified_at.isoformat(),
            "risk_level": self.risk_level,
            "impact_level": self.impact_level,
            "classification_context": dict(self.classification_context),
        }


@dataclass
class PolicyRule:
    rule_id: str
    rule_version: int
    priority: int
    decision: PolicyDecision
    enabled: bool = True
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    division_name: str | None = None
    specialist_name: str | None = None
    capability_name: str | None = None
    permission_scope: str | None = None
    adapter_name: str | None = None
    adapter_type: str | None = None
    execution_mode: str | None = None
    risk_level: str | None = None
    impact_level: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _decision_severity(decision: PolicyDecision) -> int:
        severity_order = {
            PolicyDecision.DENY: 4,
            PolicyDecision.ESCALATE: 3,
            PolicyDecision.REQUIRE_APPROVAL: 2,
            PolicyDecision.ALLOW: 1,
        }
        return severity_order.get(decision, 0)

    def is_complete(self) -> bool:
        return bool(self.rule_id and self.rule_version is not None and self.priority is not None and self.decision)

    def is_active(self, now: datetime | None = None) -> bool:
        if not self.enabled:
            return False
        if not self.is_complete():
            return False
        current = now or datetime.now(timezone.utc)
        if self.effective_from is not None and current < self.effective_from:
            return False
        if self.effective_until is not None and current > self.effective_until:
            return False
        return True

    def matches_context(self, context: Any) -> bool:
        if self.division_name is not None and self.division_name != context.division_binding:
            return False
        if self.specialist_name is not None and self.specialist_name != context.specialist_binding:
            return False
        if self.capability_name is not None and self.capability_name != context.capability_binding:
            return False
        if self.permission_scope is not None and self.permission_scope != context.permission_scope:
            return False
        if self.adapter_name is not None and self.adapter_name != context.adapter_binding:
            return False
        if self.adapter_type is not None and self.adapter_type != context.adapter_type:
            return False
        if self.execution_mode is not None and self.execution_mode != context.execution_mode:
            return False
        if self.risk_level is not None and self.risk_level != context.risk_impact_classification.risk_level:
            return False
        if self.impact_level is not None and self.impact_level != context.risk_impact_classification.impact_level:
            return False
        return True


@dataclass
class PolicyEvaluationResult:
    decision: PolicyDecision
    reason: str
    rule_id: str | None = None
    rule_version: int | None = None
    policy_id: str | None = None
    policy_version: int | None = None
    classification_risk: str | None = None
    classification_impact: str | None = None
    context_fingerprint: str | None = None
    matched_rules: list[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW


@dataclass
class ExecutionPolicy:
    policy_id: str
    policy_version: int
    default_decision: PolicyDecision = PolicyDecision.DENY
    rules: list[PolicyRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def evaluate_match(self, context: Any) -> list[PolicyRule]:
        now = context.evaluated_at if getattr(context, "evaluated_at", None) is not None else datetime.now(timezone.utc)
        matches: list[PolicyRule] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if not rule.is_complete():
                continue
            if not rule.is_active(now):
                continue
            if not rule.matches_context(context):
                continue
            matches.append(rule)
        return matches


class PolicyEvaluationEngine:
    """Deterministic policy engine used by Mission Control governance gate."""

    def __init__(self, policy: ExecutionPolicy):
        self.policy = policy

    @staticmethod
    def _decision_severity(decision: PolicyDecision) -> int:
        return {
            PolicyDecision.DENY: 4,
            PolicyDecision.ESCALATE: 3,
            PolicyDecision.REQUIRE_APPROVAL: 2,
            PolicyDecision.ALLOW: 1,
        }.get(decision, 0)

    @staticmethod
    def validate_context(context: Any) -> list[str]:
        errors = []
        required_text = ("task_id", "mission_id", "division_binding", "specialist_binding", "capability_binding", "adapter_binding", "permission_scope", "execution_mode", "policy_id")
        for name in required_text:
            value = getattr(context, name, None)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Missing or invalid {name}.")
        from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState
        from ced_one.mission_control.types import ApprovalState
        state = getattr(context, "task_lifecycle_state", None)
        approval = getattr(context, "approval_state", None)
        if not isinstance(state, TaskLifecycleState) or not isinstance(approval, ApprovalState) or not MissionTask.validate_compatibility(state, approval):
            errors.append("Invalid task/approval context.")
        if not isinstance(getattr(context, "task_context", None), dict):
            errors.append("Invalid task context.")
        evaluated_at = getattr(context, "evaluated_at", None)
        if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
            errors.append("Invalid evaluation timestamp.")
        version = getattr(context, "policy_version", None)
        if type(version) is not int or version < 1:
            errors.append("Invalid policy version.")
        classification = getattr(context, "risk_impact_classification", None)
        if not isinstance(classification, RiskImpactClassification):
            errors.append("Missing risk/impact classification.")
        else:
            errors.extend(classification.validate())
        errors.extend(validate_context_data(getattr(context, "task_context", None)))
        if isinstance(classification, RiskImpactClassification):
            errors.extend(validate_context_data(classification.classification_context))
        for name in ("connector_binding", "connector_version", "adapter_type", "context_fingerprint"):
            value = getattr(context, name, None)
            if value is not None and not isinstance(value, str):
                errors.append(f"Invalid {name}.")
        return errors

    def evaluate(self, context: Any) -> PolicyEvaluationResult:
        errors = self.validate_context(context)
        if not errors:
            try:
                context.fingerprint
            except (TypeError, ValueError, AttributeError, RecursionError):
                errors.append("Context is not canonically serializable.")
        classification = getattr(context, "risk_impact_classification", None)
        if errors:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY, reason="Invalid execution context; fail closed. " + "; ".join(errors),
                policy_id=self.policy.policy_id, policy_version=self.policy.policy_version,
            )

        matches = self.policy.evaluate_match(context)
        if not matches:
            return PolicyEvaluationResult(
                decision=self.policy.default_decision,
                reason="No active matching policy rule applied; fail closed.",
                policy_id=self.policy.policy_id,
                policy_version=self.policy.policy_version,
                classification_risk=classification.risk_level,
                classification_impact=classification.impact_level,
                context_fingerprint=getattr(context, "context_fingerprint", None),
            )

        highest_priority = max(rule.priority for rule in matches)
        candidates = [rule for rule in matches if rule.priority == highest_priority]

        winner: PolicyRule | None = None
        for candidate in candidates:
            if winner is None:
                winner = candidate
                continue

            if self._decision_severity(candidate.decision) > self._decision_severity(winner.decision):
                winner = candidate
                continue

            if self._decision_severity(candidate.decision) == self._decision_severity(winner.decision):
                if candidate.rule_version > winner.rule_version:
                    winner = candidate
                    continue
                if candidate.rule_version == winner.rule_version:
                    candidate_time = candidate.effective_from.timestamp() if candidate.effective_from is not None else 0.0
                    winner_time = winner.effective_from.timestamp() if winner.effective_from is not None else 0.0
                    if candidate_time > winner_time:
                        winner = candidate
                        continue
                    if candidate_time == winner_time and candidate.rule_id < winner.rule_id:
                        winner = candidate
                        continue

        if winner is None:
            return PolicyEvaluationResult(
                decision=self.policy.default_decision,
                reason="No valid policy winner was deterministically resolved; fail closed.",
                policy_id=self.policy.policy_id,
                policy_version=self.policy.policy_version,
                classification_risk=classification.risk_level,
                classification_impact=classification.impact_level,
                context_fingerprint=getattr(context, "context_fingerprint", None),
            )

        return PolicyEvaluationResult(
            decision=winner.decision,
            reason=f"Policy rule {winner.rule_id} resolved the decision deterministically.",
            rule_id=winner.rule_id,
            rule_version=winner.rule_version,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.policy_version,
            classification_risk=classification.risk_level,
            classification_impact=classification.impact_level,
            context_fingerprint=getattr(context, "context_fingerprint", None),
            matched_rules=[rule.rule_id for rule in matches],
        )


__all__ = [
    "ExecutionPolicy",
    "PolicyDecision",
    "PolicyEvaluationEngine",
    "PolicyEvaluationResult",
    "PolicyRule",
    "RiskImpactClassification",
]
