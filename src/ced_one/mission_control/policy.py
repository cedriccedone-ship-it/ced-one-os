"""Policy and governance primitives for Mission Control v0.8."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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
        if not self.classification_source:
            errors.append("Classification source is required.")
        if not self.classification_version:
            errors.append("Classification version is required.")
        if not self.risk_level:
            errors.append("Risk level is required.")
        if not self.impact_level:
            errors.append("Impact level is required.")
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
        if self.division_name is not None and context.division_binding is not None and self.division_name != context.division_binding:
            return False
        if self.specialist_name is not None and context.specialist_binding is not None and self.specialist_name != context.specialist_binding:
            return False
        if self.capability_name is not None and context.capability_binding is not None and self.capability_name != context.capability_binding:
            return False
        if self.permission_scope is not None and context.permission_scope is not None and self.permission_scope != context.permission_scope:
            return False
        if self.adapter_name is not None and context.adapter_binding is not None and self.adapter_name != context.adapter_binding:
            return False
        if self.adapter_type is not None and context.adapter_type is not None and self.adapter_type != context.adapter_type:
            return False
        if self.execution_mode is not None and context.execution_mode is not None and self.execution_mode != context.execution_mode:
            return False
        if self.risk_level is not None and context.risk_impact_classification is not None and self.risk_level != context.risk_impact_classification.risk_level:
            return False
        if self.impact_level is not None and context.risk_impact_classification is not None and self.impact_level != context.risk_impact_classification.impact_level:
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

    def evaluate(self, context: Any) -> PolicyEvaluationResult:
        if context is None:
            return PolicyEvaluationResult(
                decision=self.policy.default_decision,
                reason="No evaluation context was provided; fail closed.",
                policy_id=self.policy.policy_id,
                policy_version=self.policy.policy_version,
                classification_risk=None,
                classification_impact=None,
                context_fingerprint=None,
            )

        classification = getattr(context, "risk_impact_classification", None)
        classification_errors: list[str] = []
        if classification is not None:
            classification_errors = classification.validate()
        if classification is None or classification_errors:
            return PolicyEvaluationResult(
                decision=self.policy.default_decision,
                reason="Risk/impact classification is missing or structurally invalid; fail closed.",
                policy_id=self.policy.policy_id,
                policy_version=self.policy.policy_version,
                classification_risk=None,
                classification_impact=None,
                context_fingerprint=getattr(context, "context_fingerprint", None),
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
