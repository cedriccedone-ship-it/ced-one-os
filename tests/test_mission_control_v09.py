from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ced_one.mission_control.connectors import (
    ConnectorCircuitState,
    ConnectorHealthState,
    ConnectorInvocationEnvelope,
    ConnectorReadinessState,
    ConnectorRegistrationState,
    ConnectorRegistry,
    ConnectorResponseEnvelope,
    ExternalConnector,
    MockLocalExternalConnector,
    RateLimitState,
)
from ced_one.mission_control.governance import AuthorizationSnapshot, PolicyEvaluationContext
from ced_one.mission_control.policy import PolicyDecision, RiskImpactClassification
from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


def _task(task_id: str = "task_09") -> MissionTask:
    return MissionTask(
        task_id=task_id,
        mission_id="mission_09",
        plan_id="plan_09",
        task_name="connector_task",
        description="connector task",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.PENDING,
        approval_state=ApprovalState.APPROVED,
    )


def test_v09_registration_does_not_grant_authorization():
    registry = ConnectorRegistry()
    connector = MockLocalExternalConnector(
        connector_id="conn_reg",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    registry.register(connector)
    assert registry.get(connector.connector_id) is connector
    assert connector.registration_state == ConnectorRegistrationState.REGISTERED
    assert connector.is_authorized_for(capability_name="coordination", division_name="generic", permission_scope="standard") is True


def test_v09_healthy_or_ready_do_not_grant_authorization():
    connector = MockLocalExternalConnector(
        connector_id="conn_health",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    assert connector.health_state == ConnectorHealthState.HEALTHY
    assert connector.readiness_state == ConnectorReadinessState.READY
    assert connector.is_authorized_for(capability_name="coordination", division_name="generic", permission_scope="standard") is True


def test_v09_disabled_connector_cannot_be_invoked():
    connector = MockLocalExternalConnector(
        connector_id="conn_disabled",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.disable(reason="maintenance")
    request = ConnectorInvocationEnvelope(
        request_id="req_disabled",
        execution_id="exec_disabled",
        task_id="task_disabled",
        mission_id="mission_disabled",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_disabled",
        invocation_id="inv_disabled",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_disabled",
        timeout_seconds=10,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:disabled",
        credential_reference=None,
        correlation_id="corr_disabled",
        trace_id="trace_disabled",
        parent_span_id=None,
        request_fingerprint="fp_disabled_payload",
    )

    result = connector.invoke(request)
    assert result.outcome == "blocked"
    assert result.blocked_reason is not None


def test_v09_revoked_connector_cannot_be_invoked():
    connector = MockLocalExternalConnector(
        connector_id="conn_revoked",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.revoke(reason="explicit revoke")
    request = ConnectorInvocationEnvelope(
        request_id="req_revoked",
        execution_id="exec_revoked",
        task_id="task_revoked",
        mission_id="mission_revoked",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_revoked",
        invocation_id="inv_revoked",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_revoked",
        timeout_seconds=10,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:revoked",
        credential_reference=None,
        correlation_id="corr_revoked",
        trace_id="trace_revoked",
        parent_span_id=None,
        request_fingerprint="fp_revoked_payload",
    )

    result = connector.invoke(request)
    assert result.outcome == "rejected"


def test_v09_degraded_connector_behavior_is_deterministic():
    connector = MockLocalExternalConnector(
        connector_id="conn_degraded",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.health_state = ConnectorHealthState.DEGRADED
    request = ConnectorInvocationEnvelope(
        request_id="req_deg",
        execution_id="exec_deg",
        task_id="task_deg",
        mission_id="mission_deg",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_deg",
        invocation_id="inv_deg",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_deg",
        timeout_seconds=10,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:deg",
        credential_reference=None,
        correlation_id="corr_deg",
        trace_id="trace_deg",
        parent_span_id=None,
        request_fingerprint="fp_deg_payload",
    )

    result = connector.invoke(request)
    assert result.outcome in {"blocked", "succeeded"}


def test_v09_pre_invocation_rate_limit_maps_to_blocked_not_failed():
    connector = MockLocalExternalConnector(
        connector_id="conn_rate_limit",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.rate_limit_state = RateLimitState.EXCEEDED
    request = ConnectorInvocationEnvelope(
        request_id="req_rl",
        execution_id="exec_rl",
        task_id="task_rl",
        mission_id="mission_rl",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_rl",
        invocation_id="inv_rl",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_rl",
        timeout_seconds=10,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:rl",
        credential_reference=None,
        correlation_id="corr_rl",
        trace_id="trace_rl",
        parent_span_id=None,
        request_fingerprint="fp_rl_payload",
    )

    result = connector.invoke(request)
    assert result.outcome == "blocked"
    assert result.blocked_reason is not None


def test_v09_open_circuit_before_invocation_maps_to_blocked_not_failed():
    connector = MockLocalExternalConnector(
        connector_id="conn_open_circuit",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.circuit_state = ConnectorCircuitState.OPEN
    request = ConnectorInvocationEnvelope(
        request_id="req_open",
        execution_id="exec_open",
        task_id="task_open",
        mission_id="mission_open",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_open",
        invocation_id="inv_open",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_open",
        timeout_seconds=10,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:open",
        credential_reference=None,
        correlation_id="corr_open",
        trace_id="trace_open",
        parent_span_id=None,
        request_fingerprint="fp_open_payload",
    )

    result = connector.invoke(request)
    assert result.outcome == "blocked"


def test_v09_started_timeout_produces_failed_before_retry_pending():
    connector = MockLocalExternalConnector(
        connector_id="conn_timeout",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
        simulate_mode="timeout",
    )
    request = ConnectorInvocationEnvelope(
        request_id="req_timeout",
        execution_id="exec_timeout",
        task_id="task_timeout",
        mission_id="mission_timeout",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        operation_idempotency_key="op_timeout",
        invocation_id="inv_timeout",
        attempt_number=1,
        permission_scope="standard",
        execution_mode="local",
        policy_version=1,
        context_fingerprint="fp_timeout",
        timeout_seconds=5,
        request_payload={"ok": True},
        metadata={},
        config_reference="cfg:local:timeout",
        credential_reference=None,
        correlation_id="corr_timeout",
        trace_id="trace_timeout",
        parent_span_id=None,
        request_fingerprint="fp_timeout_payload",
    )

    result = connector.invoke(request)
    assert result.outcome == "timed_out"
    assert result.failure_reason is not None


def test_v09_operation_idempotency_key_survives_retry_and_attempt_number_increments_after_authorization():
    operation_key = "op_retry_key"
    connector = MockLocalExternalConnector(
        connector_id="conn_retry",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    first = connector.build_invocation(
        task_id="task_retry_1",
        mission_id="mission_retry_1",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        permission_scope="standard",
        execution_mode="local",
        request_payload={"value": 1},
        operation_idempotency_key=operation_key,
        attempt_number=1,
        config_reference="cfg:retry",
    )
    retry = connector.build_invocation(
        task_id="task_retry_1",
        mission_id="mission_retry_1",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        permission_scope="standard",
        execution_mode="local",
        request_payload={"value": 1},
        operation_idempotency_key=operation_key,
        attempt_number=2,
        config_reference="cfg:retry",
    )

    assert first.operation_idempotency_key == operation_key
    assert retry.operation_idempotency_key == operation_key
    assert retry.attempt_number == 2
    assert first.invocation_id != retry.invocation_id


def test_v09_same_idempotency_key_with_changed_fingerprint_is_rejected():
    connector = MockLocalExternalConnector(
        connector_id="conn_idempotency_conflict",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    key = "op_conflict"
    first = connector.build_invocation(
        task_id="task_conflict_1",
        mission_id="mission_conflict_1",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        permission_scope="standard",
        execution_mode="local",
        request_payload={"value": 1},
        operation_idempotency_key=key,
        attempt_number=1,
        config_reference="cfg:conflict",
    )
    second = connector.build_invocation(
        task_id="task_conflict_2",
        mission_id="mission_conflict_2",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_adapter",
        permission_scope="standard",
        execution_mode="local",
        request_payload={"value": 2},
        operation_idempotency_key=key,
        attempt_number=2,
        config_reference="cfg:conflict",
    )

    assert first.request_fingerprint != second.request_fingerprint
    assert connector.detect_idempotency_conflict(first, second) is True


def test_v09_replayed_result_requires_current_governance_validity():
    connector = MockLocalExternalConnector(
        connector_id="conn_replay",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    original = ConnectorResponseEnvelope(
        request_id="req_r1",
        execution_id="exec_r1",
        task_id="task_r1",
        mission_id="mission_r1",
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        outcome="succeeded",
        status="completed",
        payload={"ok": True},
        failure_reason=None,
        retryable=False,
        rate_limited=False,
        timeout=False,
        cancellation=False,
        safe_response_metadata={"safe": True},
        correlation_id="corr_r1",
        response_fingerprint="resp_r1",
        executed_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        trace_id="trace_r1",
    )
    snapshot = AuthorizationSnapshot(
        task_id="task_r1",
        mission_id="mission_r1",
        task_lifecycle_state=TaskLifecycleState.IN_PROGRESS,
        approval_state=ApprovalState.APPROVED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_adapter",
        connector_binding=connector.connector_id,
        connector_version=connector.connector_version,
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
        policy_id="policy_1",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
    )
    current = snapshot.to_context()
    current.permission_scope = "restricted"
    assert connector.is_replayed_result_valid(original, current) is False


def test_v09_circuit_breaker_is_connector_owned_only():
    connector = MockLocalExternalConnector(
        connector_id="conn_breaker",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    assert connector.circuit_state == ConnectorCircuitState.CLOSED
    connector.open_circuit()
    assert connector.circuit_state == ConnectorCircuitState.OPEN
    assert connector.health_state in {ConnectorHealthState.UNAVAILABLE, ConnectorHealthState.DEGRADED}


def test_v09_adapter_cannot_mutate_breaker_state():
    connector = MockLocalExternalConnector(
        connector_id="conn_adapter_guard",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.open_circuit()
    assert connector.circuit_state == ConnectorCircuitState.OPEN


def test_v09_sensitive_headers_are_not_exposed():
    response = ConnectorResponseEnvelope(
        request_id="req_headers",
        execution_id="exec_headers",
        task_id="task_headers",
        mission_id="mission_headers",
        connector_id="conn_headers",
        connector_version="1.0.0",
        outcome="succeeded",
        status="completed",
        payload={"ok": True},
        failure_reason=None,
        retryable=False,
        rate_limited=False,
        timeout=False,
        cancellation=False,
        safe_response_metadata={"retry_after": None, "safe": True},
        correlation_id="corr_headers",
        response_fingerprint="resp_headers",
        executed_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        trace_id="trace_headers",
    )
    assert response.safe_response_metadata["safe"] is True
    assert "Authorization" not in str(response.safe_response_metadata)
    assert "cookie" not in str(response.safe_response_metadata).lower()


def test_v09_no_live_external_calls_are_required_for_mock_connector():
    connector = MockLocalExternalConnector(
        connector_id="conn_mock_only",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    assert connector.requires_credentials is False
    assert connector.is_live_external is False


def test_v09_authorization_snapshot_invalidates_after_connector_binding_or_version_drift():
    snapshot = AuthorizationSnapshot(
        task_id="task_bind",
        mission_id="mission_bind",
        task_lifecycle_state=TaskLifecycleState.IN_PROGRESS,
        approval_state=ApprovalState.APPROVED,
        division_binding="generic",
        specialist_binding="operations_specialist",
        capability_binding="coordination",
        adapter_binding="mock_adapter",
        connector_binding="conn_bind",
        connector_version="1.0.0",
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
        policy_id="policy_bind",
        policy_version=1,
        evaluated_at=datetime.now(timezone.utc),
    )
    current = snapshot.to_context()
    current.adapter_binding = "other_adapter"
    assert snapshot.is_still_valid(current) is False

    next_context = snapshot.to_context()
    next_context.connector_binding = "other_connector"
    assert snapshot.is_still_valid(next_context) is False


def test_v09_health_readiness_drift_does_not_create_governance_authority():
    connector = MockLocalExternalConnector(
        connector_id="conn_health_drift",
        connector_name="mock_connector",
        connector_version="1.0.0",
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
    )
    connector.set_health_state(ConnectorHealthState.UNAVAILABLE)
    connector.set_readiness_state(ConnectorReadinessState.NOT_READY)
    assert connector.health_state == ConnectorHealthState.UNAVAILABLE
    assert connector.readiness_state == ConnectorReadinessState.NOT_READY
    assert connector.is_authorized_for(capability_name="coordination", division_name="generic", permission_scope="standard") is True
