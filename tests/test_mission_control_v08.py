from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ced_one.mission_control.policy import (
    ExecutionPolicy,
    PolicyDecision,
    PolicyEvaluationEngine,
    PolicyRule,
    RiskImpactClassification,
)
from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState
from ced_one.mission_control.types import ApprovalState
from ced_one.mission_control.governance import (
    AuthorizationSnapshot,
    ExecutionGovernanceGate,
    MissionControlPolicyHandler,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


def _task(task_id: str = "task_01") -> MissionTask:
    return MissionTask(
        task_id=task_id,
        mission_id="mission_01",
        plan_id="plan_01",
        task_name="sample_task",
        description="sample",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
    )


def test_v08_higher_priority_allow_beats_lower_priority_deny():
    policy = ExecutionPolicy(
        policy_id="policy_1",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="r_deny",
                rule_version=1,
                priority=1,
                decision=PolicyDecision.DENY,
                capability_name="coordination",
                permission_scope="standard",
            ),
            PolicyRule(
                rule_id="r_allow",
                rule_version=1,
                priority=2,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
            ),
        ],
    )
    context = PolicyEvaluationContext(
        task_id="task_01",
        mission_id="mission_01",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.ALLOW


def test_v08_equal_priority_deny_beats_equal_priority_allow():
    policy = ExecutionPolicy(
        policy_id="policy_2",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="allow_1",
                rule_version=1,
                priority=5,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
            ),
            PolicyRule(
                rule_id="deny_1",
                rule_version=1,
                priority=5,
                decision=PolicyDecision.DENY,
                capability_name="coordination",
                permission_scope="standard",
            ),
        ],
    )
    context = PolicyEvaluationContext(
        task_id="task_02",
        mission_id="mission_02",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.DENY


def test_v08_equal_priority_escalate_beats_require_approval():
    policy = ExecutionPolicy(
        policy_id="policy_3",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="approval_1",
                rule_version=1,
                priority=7,
                decision=PolicyDecision.REQUIRE_APPROVAL,
                capability_name="coordination",
                permission_scope="standard",
            ),
            PolicyRule(
                rule_id="escalate_1",
                rule_version=1,
                priority=7,
                decision=PolicyDecision.ESCALATE,
                capability_name="coordination",
                permission_scope="standard",
            ),
        ],
    )
    context = PolicyEvaluationContext(
        task_id="task_03",
        mission_id="mission_03",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="moderate",
            impact_level="material",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.ESCALATE


def test_v08_rule_tie_breaking_by_version_then_effective_from_then_rule_id():
    now = datetime.now(timezone.utc)
    older = now - timedelta(minutes=10)
    newer = now - timedelta(minutes=5)
    policy = ExecutionPolicy(
        policy_id="policy_4",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="z_rule",
                rule_version=1,
                priority=3,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
                effective_from=older,
            ),
            PolicyRule(
                rule_id="a_rule",
                rule_version=2,
                priority=3,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
                effective_from=newer,
            ),
        ],
    )
    context = PolicyEvaluationContext(
        task_id="task_04",
        mission_id="mission_04",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=now,
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=now,
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.rule_id == "a_rule"


def test_v08_default_policy_is_deny_when_no_bounded_allow_applies():
    policy = ExecutionPolicy(
        policy_id="policy_5",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="rule_1",
                rule_version=1,
                priority=1,
                decision=PolicyDecision.ALLOW,
                capability_name="other_capability",
                permission_scope="standard",
            )
        ],
    )
    context = PolicyEvaluationContext(
        task_id="task_05",
        mission_id="mission_05",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.DENY


def test_v08_stale_or_incomplete_policy_evaluation_fails_closed():
    expired_rule = PolicyRule(
        rule_id="expired_rule",
        rule_version=1,
        priority=10,
        decision=PolicyDecision.ALLOW,
        capability_name="coordination",
        permission_scope="standard",
        effective_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    policy = ExecutionPolicy(
        policy_id="policy_6",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[expired_rule],
    )
    context = PolicyEvaluationContext(
        task_id="task_06",
        mission_id="mission_06",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.NOT_REQUIRED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.DENY


def test_v08_policy_uses_validated_classification_not_raw_task_content():
    task = _task()
    task.metadata["risk_level"] = "critical"
    task.metadata["impact_level"] = "irreversible"

    policy = ExecutionPolicy(
        policy_id="policy_7",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="allow_low",
                rule_version=1,
                priority=1,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
                risk_level="low",
                impact_level="limited",
            )
        ],
    )
    context = PolicyEvaluationContext(
        task_id=task.task_id,
        mission_id=task.mission_id,
        task_lifecycle_state=task.task_state,
        approval_state=task.approval_state,
        division_binding=task.division_name,
        specialist_binding=task.specialist_name,
        capability_binding=task.capability_name,
        adapter_binding="mock_provider",
        permission_scope=task.permission_scope,
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"source": "validated"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={"raw_task_metadata": task.metadata},
    )

    result = PolicyEvaluationEngine(policy).evaluate(context)
    assert result.decision == PolicyDecision.ALLOW
    assert result.classification_risk == "low"
    assert result.classification_impact == "limited"


def test_v08_governance_gate_never_mutates_task_or_approval_state():
    task = _task()
    gate = ExecutionGovernanceGate()
    context = PolicyEvaluationContext(
        task_id=task.task_id,
        mission_id=task.mission_id,
        task_lifecycle_state=task.task_state,
        approval_state=task.approval_state,
        division_binding=task.division_name,
        specialist_binding=task.specialist_name,
        capability_binding=task.capability_name,
        adapter_binding="mock_provider",
        permission_scope=task.permission_scope,
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id="policy_8",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )
    policy = ExecutionPolicy(
        policy_id="policy_8",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="allow_ok",
                rule_version=1,
                priority=1,
                decision=PolicyDecision.ALLOW,
                capability_name="coordination",
                permission_scope="standard",
            )
        ],
    )

    result = gate.evaluate(context, policy=policy)

    assert isinstance(result, PolicyEvaluationResult)
    assert result.decision == PolicyDecision.ALLOW
    assert task.task_state == TaskLifecycleState.PENDING
    assert task.approval_state == ApprovalState.NOT_REQUIRED


def test_v08_require_approval_requires_mission_control_handling():
    policy = ExecutionPolicy(
        policy_id="policy_9",
        policy_version=1,
        default_decision=PolicyDecision.DENY,
        rules=[
            PolicyRule(
                rule_id="require_approval_rule",
                rule_version=1,
                priority=4,
                decision=PolicyDecision.REQUIRE_APPROVAL,
                capability_name="coordination",
                permission_scope="standard",
            )
        ],
    )
    task = _task()
    context = PolicyEvaluationContext(
        task_id=task.task_id,
        mission_id=task.mission_id,
        task_lifecycle_state=task.task_state,
        approval_state=task.approval_state,
        division_binding=task.division_name,
        specialist_binding=task.specialist_name,
        capability_binding=task.capability_name,
        adapter_binding="mock_provider",
        permission_scope=task.permission_scope,
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="moderate",
            impact_level="material",
            classification_context={"scope": "standard"},
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        evaluated_at=datetime.now(timezone.utc),
        task_context={},
    )

    gate_result = ExecutionGovernanceGate().evaluate(context, policy=policy)
    handled = MissionControlPolicyHandler().handle(gate_result)

    assert gate_result.decision == PolicyDecision.REQUIRE_APPROVAL
    assert handled["mission_control_action"] == "approval_required"
    assert task.approval_state == ApprovalState.NOT_REQUIRED


def test_v08_pending_plus_escalated_is_valid_and_retry_pending_plus_escalated_is_invalid():
    task = _task()
    task.task_state = TaskLifecycleState.PENDING
    task.approval_state = ApprovalState.ESCALATED
    assert MissionControlPolicyHandler().validate_compatibility(task.task_state, task.approval_state) is True

    retry_task = _task("task_retry")
    retry_task.task_state = TaskLifecycleState.RETRY_PENDING
    retry_task.approval_state = ApprovalState.ESCALATED
    assert MissionControlPolicyHandler().validate_compatibility(retry_task.task_state, retry_task.approval_state) is False

    blocked_task = _task("task_blocked")
    blocked_task.task_state = TaskLifecycleState.BLOCKED
    blocked_task.approval_state = ApprovalState.ESCALATED
    assert MissionControlPolicyHandler().validate_compatibility(blocked_task.task_state, blocked_task.approval_state) is True


def test_v08_authorization_snapshot_invalidates_after_permission_drift():
    snapshot = AuthorizationSnapshot(
        task_id="task_10",
        mission_id="mission_10",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.APPROVED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id="policy_10",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
    )

    mutated = snapshot.to_context()
    mutated.permission_scope = "restricted"
    assert snapshot.is_still_valid(mutated) is False


def test_v08_authorization_snapshot_invalidates_after_binding_drift():
    snapshot = AuthorizationSnapshot(
        task_id="task_11",
        mission_id="mission_11",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.APPROVED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id="policy_11",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
    )
    mutated = snapshot.to_context()
    mutated.adapter_binding = "different_provider"
    assert snapshot.is_still_valid(mutated) is False


def test_v08_authorization_snapshot_invalidates_after_policy_version_drift():
    snapshot = AuthorizationSnapshot(
        task_id="task_12",
        mission_id="mission_12",
        task_lifecycle_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.APPROVED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_provider",
        permission_scope="standard",
        execution_mode="local",
        risk_impact_classification=RiskImpactClassification(
            classification_source="division",
            classification_version="1",
            classified_at=datetime.now(timezone.utc),
            risk_level="low",
            impact_level="limited",
            classification_context={"scope": "standard"},
        ),
        policy_id="policy_12",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
    )
    mutated = snapshot.to_context()
    mutated.policy_version = 2
    assert snapshot.is_still_valid(mutated) is False


def test_v08_policy_audit_records_observed_state_without_claiming_lifecycle_mutation():
    audit = MissionControlPolicyHandler().build_audit_record(
        task_state=TaskLifecycleState.BLOCKED,
        approval_state=ApprovalState.PENDING,
        decision=PolicyDecision.REQUIRE_APPROVAL,
        reason="approval required",
        policy_id="policy_13",
        rule_id="r_approval",
        policy_version=1,
        rule_version=1,
        context_fingerprint="abc123",
    )

    assert audit.observed_task_state == TaskLifecycleState.BLOCKED
    assert audit.observed_approval_state == ApprovalState.PENDING
    assert audit.policy_decision == PolicyDecision.REQUIRE_APPROVAL
    assert audit.previous_state is None
    assert audit.resulting_state is None


def test_v08_mission_control_remains_final_authority():
    assert MissionControlPolicyHandler().is_final_authority() is True
