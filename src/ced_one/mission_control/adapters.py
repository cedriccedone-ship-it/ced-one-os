"""Provider and tool adapter layer for Mission Control v0.7."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CapabilityAdapterBinding:
    """Policy-level binding between a capability and an eligible provider/tool adapter."""

    capability_name: str
    division_name: str
    adapter_name: str
    adapter_type: str
    permission_scope: str = "standard"
    execution_mode: str = "local"
    priority: int = 1
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class AdapterBindingPolicy:
    """Defines how capabilities bind to eligible adapter implementations without embedding provider logic into the capability contract."""

    def __init__(self):
        self.bindings: list[CapabilityAdapterBinding] = []

    def bind(
        self,
        *,
        capability_name: str,
        division_name: str,
        adapter_name: str,
        adapter_type: str,
        permission_scope: str = "standard",
        execution_mode: str = "local",
        priority: int = 1,
        available: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityAdapterBinding:
        binding = CapabilityAdapterBinding(
            capability_name=capability_name,
            division_name=division_name,
            adapter_name=adapter_name,
            adapter_type=adapter_type,
            permission_scope=permission_scope,
            execution_mode=execution_mode,
            priority=priority,
            available=available,
            metadata=metadata or {},
        )
        self.bindings.append(binding)
        return binding

    def get_eligible(self, *, capability_name: str, division_name: str, permission_scope: str, execution_mode: str) -> list[CapabilityAdapterBinding]:
        eligible = [
            binding
            for binding in self.bindings
            if binding.capability_name == capability_name
            and binding.division_name == division_name
            and binding.permission_scope == permission_scope
            and binding.execution_mode == execution_mode
            and binding.available
        ]
        return sorted(eligible, key=lambda binding: (binding.priority, binding.adapter_name))


@dataclass
class StructuredProviderRequest:
    """Provider-agnostic invocation request created by the execution runtime under authorized capability policy."""

    request_id: str
    task_id: str
    mission_id: str
    division_name: str
    specialist_name: str
    capability_name: str
    adapter_name: str
    permission_scope: str = "standard"
    input_payload: dict[str, Any] = field(default_factory=dict)
    execution_context: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = 30
    attempt_number: int = 1
    config_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredProviderResult:
    """Adapter-normalized output. Provider-specific raw responses are converted here and never passed directly to Mission Control."""

    request_id: str
    task_id: str
    mission_id: str
    division_name: str
    specialist_name: str
    capability_name: str
    adapter_name: str
    outcome: str = "succeeded"
    payload: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    normalized: bool = True
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter:
    """Abstract provider interface. Provider-specific raw output is normalized by the adapter into StructuredProviderResult."""

    adapter_name: str = "provider_adapter"
    adapter_type: str = "provider"
    permission_scope: str = "standard"
    execution_mode: str = "local"
    requires_credentials: bool = False

    def execute(self, request: StructuredProviderRequest) -> StructuredProviderResult:
        raise NotImplementedError("Provider adapters must define execute().")


class ToolAdapter:
    """Abstract tool adapter interface. Tool adapters are not a risk classification; they are invocation-specialized adapters."""

    adapter_name: str = "tool_adapter"
    adapter_type: str = "tool"
    permission_scope: str = "standard"
    execution_mode: str = "local"
    requires_credentials: bool = False

    def execute(self, request: StructuredProviderRequest) -> StructuredProviderResult:
        raise NotImplementedError("Tool adapters must define execute().")


class MockLocalProviderAdapter(ProviderAdapter):
    """Deterministic local provider adapter used only for architecture validation and tests."""

    adapter_name = "mock_provider"
    adapter_type = "provider"
    permission_scope = "standard"
    execution_mode = "local"
    requires_credentials = False

    def execute(self, request: StructuredProviderRequest) -> StructuredProviderResult:
        mode = str(request.execution_context.get("simulate_mode", "success")).lower()
        now = datetime.now(timezone.utc)

        if mode == "timeout":
            return StructuredProviderResult(
                request_id=request.request_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                division_name=request.division_name,
                specialist_name=request.specialist_name,
                capability_name=request.capability_name,
                adapter_name=self.adapter_name,
                outcome="timed_out",
                payload={},
                validation_errors=[],
                failure_reason="Provider timed out.",
                normalized=True,
                started_at=now,
                completed_at=now,
                metadata={"simulate_mode": mode, "local_adapter": True},
            )

        if mode == "fail":
            return StructuredProviderResult(
                request_id=request.request_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                division_name=request.division_name,
                specialist_name=request.specialist_name,
                capability_name=request.capability_name,
                adapter_name=self.adapter_name,
                outcome="failed",
                payload={"ok": False},
                validation_errors=["Provider execution failed intentionally."],
                failure_reason="Provider failure was injected for deterministic validation.",
                normalized=True,
                started_at=now,
                completed_at=now,
                metadata={"simulate_mode": mode, "local_adapter": True},
            )

        if mode == "cancelled":
            return StructuredProviderResult(
                request_id=request.request_id,
                task_id=request.task_id,
                mission_id=request.mission_id,
                division_name=request.division_name,
                specialist_name=request.specialist_name,
                capability_name=request.capability_name,
                adapter_name=self.adapter_name,
                outcome="cancelled",
                payload={"cancelled": True},
                validation_errors=[],
                failure_reason="Provider execution was cancelled by Mission Control.",
                normalized=True,
                started_at=now,
                completed_at=now,
                metadata={"simulate_mode": mode, "local_adapter": True},
            )

        payload = {
            "ok": True,
            "request": request.input_payload,
            "division": request.division_name,
            "specialist": request.specialist_name,
            "capability": request.capability_name,
            "adapter": self.adapter_name,
        }
        return StructuredProviderResult(
            request_id=request.request_id,
            task_id=request.task_id,
            mission_id=request.mission_id,
            division_name=request.division_name,
            specialist_name=request.specialist_name,
            capability_name=request.capability_name,
            adapter_name=self.adapter_name,
            outcome="succeeded",
            payload=payload,
            validation_errors=[],
            failure_reason=None,
            normalized=True,
            started_at=now,
            completed_at=now,
            metadata={"simulate_mode": mode, "local_adapter": True},
        )


class MockLocalToolAdapter(ToolAdapter):
    """Deterministic local tool adapter used only for architecture validation and end-to-end tests."""

    adapter_name = "mock_tool"
    adapter_type = "tool"
    permission_scope = "standard"
    execution_mode = "local"
    requires_credentials = False

    def execute(self, request: StructuredProviderRequest) -> StructuredProviderResult:
        now = datetime.now(timezone.utc)
        return StructuredProviderResult(
            request_id=request.request_id,
            task_id=request.task_id,
            mission_id=request.mission_id,
            division_name=request.division_name,
            specialist_name=request.specialist_name,
            capability_name=request.capability_name,
            adapter_name=self.adapter_name,
            outcome="succeeded",
            payload={"ok": True, "tool_result": request.input_payload},
            validation_errors=[],
            failure_reason=None,
            normalized=True,
            started_at=now,
            completed_at=now,
            metadata={"local_adapter": True, "tool": True},
        )


class AdapterRegistry:
    """Registry that enforces capability, permission, availability, execution-mode, and policy compatibility."""

    def __init__(self):
        self.bindings: list[CapabilityAdapterBinding] = []

    def register(self, binding: CapabilityAdapterBinding) -> CapabilityAdapterBinding:
        self.bindings.append(binding)
        return binding

    def get_eligible(
        self,
        *,
        capability_name: str,
        division_name: str,
        permission_scope: str,
        execution_mode: str,
    ) -> list[CapabilityAdapterBinding]:
        eligible = [
            binding
            for binding in self.bindings
            if binding.capability_name == capability_name
            and binding.division_name == division_name
            and binding.permission_scope == permission_scope
            and binding.execution_mode == execution_mode
            and binding.available
        ]
        return sorted(eligible, key=lambda binding: (binding.priority, binding.adapter_name))

    def is_authorized(
        self,
        *,
        binding: CapabilityAdapterBinding,
        capability_name: str,
        division_name: str,
        permission_scope: str,
    ) -> bool:
        return (
            binding.capability_name == capability_name
            and binding.division_name == division_name
            and binding.permission_scope == permission_scope
            and binding.available
        )

    def select(
        self,
        *,
        capability_name: str,
        division_name: str,
        permission_scope: str,
        execution_mode: str,
    ) -> CapabilityAdapterBinding | None:
        eligible = self.get_eligible(
            capability_name=capability_name,
            division_name=division_name,
            permission_scope=permission_scope,
            execution_mode=execution_mode,
        )
        if not eligible:
            return None
        return eligible[0]


__all__ = [
    "AdapterBindingPolicy",
    "AdapterRegistry",
    "CapabilityAdapterBinding",
    "MockLocalProviderAdapter",
    "MockLocalToolAdapter",
    "ProviderAdapter",
    "StructuredProviderRequest",
    "StructuredProviderResult",
    "ToolAdapter",
]
