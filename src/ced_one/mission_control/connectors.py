"""External connector boundary for Mission Control v0.9."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ConnectorRegistrationState(str, Enum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ConnectorHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ConnectorReadinessState(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"


class ConnectorCircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RateLimitState(str, Enum):
    OK = "ok"
    EXCEEDED = "exceeded"
    UNKNOWN = "unknown"


@dataclass
class ConnectorInvocationEnvelope:
    request_id: str
    execution_id: str
    task_id: str
    mission_id: str
    division_name: str
    specialist_name: str
    capability_name: str
    adapter_name: str
    connector_id: str
    connector_version: str
    operation_idempotency_key: str
    invocation_id: str
    attempt_number: int
    permission_scope: str = "standard"
    execution_mode: str = "local"
    policy_version: int = 1
    context_fingerprint: str | None = None
    timeout_seconds: int | None = 30
    request_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    config_reference: str | None = None
    credential_reference: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None
    request_fingerprint: str | None = None


@dataclass
class ConnectorResponseEnvelope:
    request_id: str
    execution_id: str
    task_id: str
    mission_id: str
    connector_id: str
    connector_version: str
    outcome: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None
    blocked_reason: str | None = None
    retryable: bool = False
    rate_limited: bool = False
    timeout: bool = False
    cancellation: bool = False
    safe_response_metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    response_fingerprint: str | None = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None


@dataclass
class ConnectorBinding:
    connector_id: str
    connector_version: str
    adapter_name: str
    adapter_type: str
    capability_name: str
    division_name: str
    permission_scope: str = "standard"
    execution_mode: str = "local"
    priority: int = 1
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ExternalConnector:
    """Abstract boundary for future external service integration. This is technical-only and non-authoritative."""

    connector_id: str = "external_connector"
    connector_name: str = "external_connector"
    connector_version: str = "1.0.0"
    connector_type: str = "external"
    capability_name: str = "generic"
    division_name: str = "generic"
    permission_scope: str = "standard"
    execution_mode: str = "local"
    adapter_name: str = "default_adapter"
    adapter_type: str = "provider"
    requires_credentials: bool = False
    is_live_external: bool = False
    registration_state: ConnectorRegistrationState = ConnectorRegistrationState.REGISTERED
    health_state: ConnectorHealthState = ConnectorHealthState.HEALTHY
    readiness_state: ConnectorReadinessState = ConnectorReadinessState.READY
    circuit_state: ConnectorCircuitState = ConnectorCircuitState.CLOSED
    rate_limit_state: RateLimitState = RateLimitState.OK
    config_reference: str | None = None
    credential_reference: str | None = None

    def is_authorized_for(self, *, capability_name: str, division_name: str, permission_scope: str) -> bool:
        return (
            self.capability_name == capability_name
            and self.division_name == division_name
            and self.permission_scope == permission_scope
            and self.registration_state == ConnectorRegistrationState.REGISTERED
        )

    def register(self) -> None:
        self.registration_state = ConnectorRegistrationState.REGISTERED

    def disable(self, *, reason: str | None = None) -> None:
        self.registration_state = ConnectorRegistrationState.DISABLED

    def revoke(self, *, reason: str | None = None) -> None:
        self.registration_state = ConnectorRegistrationState.REVOKED

    def set_health_state(self, state: ConnectorHealthState) -> None:
        self.health_state = state

    def set_readiness_state(self, state: ConnectorReadinessState) -> None:
        self.readiness_state = state

    def open_circuit(self) -> None:
        self.circuit_state = ConnectorCircuitState.OPEN
        self.health_state = ConnectorHealthState.UNAVAILABLE

    def half_open_circuit(self) -> None:
        self.circuit_state = ConnectorCircuitState.HALF_OPEN
        self.health_state = ConnectorHealthState.DEGRADED

    def close_circuit(self) -> None:
        self.circuit_state = ConnectorCircuitState.CLOSED

    def can_invoke(self, *, request: ConnectorInvocationEnvelope | None = None) -> bool:
        if self.registration_state == ConnectorRegistrationState.REVOKED:
            return False
        if self.registration_state == ConnectorRegistrationState.DISABLED:
            return False
        if self.readiness_state != ConnectorReadinessState.READY:
            return False
        if self.health_state == ConnectorHealthState.UNAVAILABLE:
            return False
        if self.circuit_state == ConnectorCircuitState.OPEN:
            return False
        return True

    def build_invocation(
        self,
        *,
        task_id: str,
        mission_id: str,
        division_name: str,
        specialist_name: str,
        capability_name: str,
        adapter_name: str,
        permission_scope: str,
        execution_mode: str,
        request_payload: dict[str, Any],
        operation_idempotency_key: str,
        attempt_number: int,
        config_reference: str | None = None,
        credential_reference: str | None = None,
        timeout_seconds: int | None = 30,
        request_id: str | None = None,
        execution_id: str | None = None,
        invocation_id: str | None = None,
        policy_version: int = 1,
        context_fingerprint: str | None = None,
    ) -> ConnectorInvocationEnvelope:
        return ConnectorInvocationEnvelope(
            request_id=request_id or f"req_{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            execution_id=execution_id or f"exec_{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            task_id=task_id,
            mission_id=mission_id,
            division_name=division_name,
            specialist_name=specialist_name,
            capability_name=capability_name,
            adapter_name=adapter_name,
            connector_id=self.connector_id,
            connector_version=self.connector_version,
            operation_idempotency_key=operation_idempotency_key,
            invocation_id=invocation_id or f"inv_{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            attempt_number=attempt_number,
            permission_scope=permission_scope,
            execution_mode=execution_mode,
            policy_version=policy_version,
            context_fingerprint=context_fingerprint,
            timeout_seconds=timeout_seconds,
            request_payload=dict(request_payload),
            metadata={},
            config_reference=config_reference,
            credential_reference=credential_reference,
            correlation_id=f"corr_{task_id}",
            trace_id=f"trace_{task_id}",
            parent_span_id=None,
            request_fingerprint=self._request_fingerprint(operation_idempotency_key, request_payload),
        )

    @staticmethod
    def _request_fingerprint(operation_key: str, payload: dict[str, Any]) -> str:
        return f"{operation_key}:{sorted((str(k), str(v)) for k, v in payload.items())}"

    @staticmethod
    def detect_idempotency_conflict(first: ConnectorInvocationEnvelope, second: ConnectorInvocationEnvelope) -> bool:
        return (
            first.operation_idempotency_key == second.operation_idempotency_key
            and first.request_fingerprint is not None
            and second.request_fingerprint is not None
            and first.request_fingerprint != second.request_fingerprint
        )

    def invoke(self, request: ConnectorInvocationEnvelope) -> ConnectorResponseEnvelope:
        if self.registration_state == ConnectorRegistrationState.REVOKED:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="rejected",
                status="rejected",
                payload={},
                failure_reason="Connector is revoked and cannot be invoked.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"connector_state": self.registration_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if self.registration_state == ConnectorRegistrationState.DISABLED:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="blocked",
                status="blocked",
                payload={},
                failure_reason="Connector is disabled and cannot accept this invocation.",
                blocked_reason="Connector is disabled and cannot accept this invocation.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"connector_state": self.registration_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if self.readiness_state != ConnectorReadinessState.READY:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="blocked",
                status="blocked",
                payload={},
                failure_reason="Connector is not ready for invocation.",
                blocked_reason="Connector is not ready for invocation.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"connector_readiness": self.readiness_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if self.health_state == ConnectorHealthState.UNAVAILABLE:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="blocked",
                status="blocked",
                payload={},
                failure_reason="Connector is unavailable for technical invocation.",
                blocked_reason="Connector is unavailable for technical invocation.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"connector_health": self.health_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if self.circuit_state == ConnectorCircuitState.OPEN:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="blocked",
                status="blocked",
                payload={},
                failure_reason="Circuit breaker is open; connector invocation is blocked before execution.",
                blocked_reason="Circuit breaker is open; connector invocation is blocked before execution.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"circuit_state": self.circuit_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if self.rate_limit_state == RateLimitState.EXCEEDED:
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="blocked",
                status="blocked",
                payload={},
                failure_reason="Connector rate limit is currently exhausted.",
                blocked_reason="Connector rate limit is currently exhausted.",
                retryable=True,
                rate_limited=True,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"rate_limit_state": self.rate_limit_state.value},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if getattr(self, "simulate_mode", None) == "timeout":
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="timed_out",
                status="failed",
                payload={},
                failure_reason="Connector timed out after the configured execution window.",
                retryable=True,
                rate_limited=False,
                timeout=True,
                cancellation=False,
                safe_response_metadata={"timeout": True},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if getattr(self, "simulate_mode", None) == "fail":
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="failed",
                status="failed",
                payload={"ok": False},
                failure_reason="Connector execution failed as simulated.",
                retryable=True,
                rate_limited=False,
                timeout=False,
                cancellation=False,
                safe_response_metadata={"simulate_mode": "fail"},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        if getattr(self, "simulate_mode", None) == "cancelled":
            return ConnectorResponseEnvelope(
                request_id=request.request_id,
                execution_id=request.execution_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                connector_id=self.connector_id,
                connector_version=self.connector_version,
                outcome="cancelled",
                status="cancelled",
                payload={"cancelled": True},
                failure_reason="Connector execution was cancelled by Mission Control.",
                retryable=False,
                rate_limited=False,
                timeout=False,
                cancellation=True,
                safe_response_metadata={"simulate_mode": "cancelled"},
                correlation_id=request.correlation_id,
                response_fingerprint=f"resp_{request.request_id}",
                executed_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=request.trace_id,
            )

        return ConnectorResponseEnvelope(
            request_id=request.request_id,
            execution_id=request.execution_id,
            task_id=request.task_id,
            mission_id=request.mission_id,
            connector_id=self.connector_id,
            connector_version=self.connector_version,
            outcome="succeeded",
            status="completed",
            payload={"ok": True, "request": request.request_payload},
            failure_reason=None,
            retryable=False,
            rate_limited=False,
            timeout=False,
            cancellation=False,
            safe_response_metadata={"safe": True, "result": "success"},
            correlation_id=request.correlation_id,
            response_fingerprint=f"resp_{request.request_id}",
            executed_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            trace_id=request.trace_id,
        )

    def is_replayed_result_valid(self, response: ConnectorResponseEnvelope, current_context: Any) -> bool:
        if current_context is None:
            return False
        if getattr(current_context, "policy_version", None) is None:
            return False
        if getattr(current_context, "adapter_binding", None) is None:
            return False
        if getattr(current_context, "permission_scope", None) is not None and getattr(current_context, "permission_scope", None) != self.permission_scope:
            return False
        if getattr(current_context, "execution_mode", None) is not None and getattr(current_context, "execution_mode", None) != self.execution_mode:
            return False
        if getattr(current_context, "connector_binding", None) is not None and getattr(current_context, "connector_binding", None) != self.connector_id:
            return False
        if getattr(current_context, "connector_version", None) is not None and getattr(current_context, "connector_version", None) != self.connector_version:
            return False
        return True


class MockLocalExternalConnector(ExternalConnector):
    """Deterministic mock connector used for architecture validation only."""

    connector_id = "mock_connector"
    connector_name = "mock_connector"
    connector_version = "1.0.0"
    connector_type = "external"
    capability_name = "coordination"
    division_name = "generic"
    permission_scope = "standard"
    execution_mode = "local"
    adapter_name = "mock_adapter"
    adapter_type = "provider"
    requires_credentials = False
    is_live_external = False
    simulate_mode: str | None = None

    def __init__(
        self,
        *,
        connector_id: str | None = None,
        connector_name: str | None = None,
        connector_version: str | None = None,
        capability_name: str | None = None,
        division_name: str | None = None,
        permission_scope: str | None = None,
        execution_mode: str | None = None,
        adapter_name: str | None = None,
        adapter_type: str | None = None,
        simulate_mode: str | None = None,
    ):
        self.connector_id = connector_id or self.connector_id
        self.connector_name = connector_name or self.connector_name
        self.connector_version = connector_version or self.connector_version
        self.capability_name = capability_name or self.capability_name
        self.division_name = division_name or self.division_name
        self.permission_scope = permission_scope or self.permission_scope
        self.execution_mode = execution_mode or self.execution_mode
        self.adapter_name = adapter_name or self.adapter_name
        self.adapter_type = adapter_type or self.adapter_type
        self.simulate_mode = simulate_mode


class ConnectorRegistry:
    """Registry of known external connectors. Registration does not grant permission."""

    def __init__(self):
        self._connectors: dict[str, ExternalConnector] = {}

    def register(self, connector: ExternalConnector) -> ExternalConnector:
        self._connectors[connector.connector_id] = connector
        return connector

    def get(self, connector_id: str) -> ExternalConnector | None:
        return self._connectors.get(connector_id)

    def get_eligible(
        self,
        *,
        capability_name: str,
        division_name: str,
        permission_scope: str,
        execution_mode: str,
        adapter_name: str | None = None,
    ) -> list[ExternalConnector]:
        eligible: list[ExternalConnector] = []
        for connector in self._connectors.values():
            if connector.capability_name != capability_name:
                continue
            if connector.division_name != division_name:
                continue
            if connector.permission_scope != permission_scope:
                continue
            if connector.execution_mode != execution_mode:
                continue
            if adapter_name is not None and connector.adapter_name != adapter_name:
                continue
            if connector.registration_state != ConnectorRegistrationState.REGISTERED:
                continue
            if connector.readiness_state != ConnectorReadinessState.READY:
                continue
            eligible.append(connector)
        return sorted(eligible, key=lambda c: (c.connector_name, c.connector_version))


__all__ = [
    "ConnectorBinding",
    "ConnectorCircuitState",
    "ConnectorHealthState",
    "ConnectorInvocationEnvelope",
    "ConnectorReadinessState",
    "ConnectorRegistrationState",
    "ConnectorRegistry",
    "ConnectorResponseEnvelope",
    "ExternalConnector",
    "MockLocalExternalConnector",
    "RateLimitState",
]
