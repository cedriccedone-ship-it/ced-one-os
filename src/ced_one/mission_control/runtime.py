"""Execution runtime contracts and deterministic specialist execution for Mission Control v0.6."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ced_one.mission_control.tasks import TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


class ExecutionOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class CapabilityExecutionContract:
    """Provider-independent capability contract governing execution inputs and outputs."""

    name: str
    division_name: str
    contract_id: str
    permission_scope: str = "standard"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    retryable: bool = True
    timeout_seconds: int | None = 30
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_input(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required_fields = self.input_schema.get("required_fields", [])
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(f"Missing required input field: {field_name}")
        return errors

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required_fields = self.output_schema.get("required_fields", [])
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")
        return errors


@dataclass
class SpecialistExecutionContract:
    """Execution assignment issued to a specialist under an approved capability contract."""

    task_id: str
    mission_id: str
    plan_id: str
    specialist_name: str
    division_name: str
    capability_name: str
    permission_scope: str
    input_payload: dict[str, Any] = field(default_factory=dict)
    execution_context: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = 30
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredExecutionResult:
    """Structured result reported by the runtime. Mission Control determines final task state."""

    execution_id: str
    task_id: str
    mission_id: str
    division_name: str
    specialist_name: str
    capability_name: str
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCEEDED
    result_payload: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_number: int = 1
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "division_name": self.division_name,
            "specialist_name": self.specialist_name,
            "capability_name": self.capability_name,
            "outcome": self.outcome.value,
            "result_payload": self.result_payload,
            "validation_errors": list(self.validation_errors),
            "failure_reason": self.failure_reason,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "attempt_number": self.attempt_number,
            "runtime_metadata": self.runtime_metadata,
        }


class BaseExecutionRuntime:
    """Execution runtime abstraction used to run assigned specialist work."""

    def execute(self, contract: SpecialistExecutionContract) -> StructuredExecutionResult:
        raise NotImplementedError("Execution runtime implementations must define execute().")


class LocalMockExecutionRuntime(BaseExecutionRuntime):
    """Deterministic local runtime used for architecture validation without external systems."""

    def execute(self, contract: SpecialistExecutionContract) -> StructuredExecutionResult:
        mode = str(contract.execution_context.get("simulate_mode", "success")).lower()
        now = datetime.now(timezone.utc)
        if mode == "timeout":
            return StructuredExecutionResult(
                execution_id=f"exec_{contract.task_id}_timeout",
                task_id=contract.task_id,
                mission_id=contract.mission_id,
                division_name=contract.division_name,
                specialist_name=contract.specialist_name,
                capability_name=contract.capability_name,
                outcome=ExecutionOutcome.TIMED_OUT,
                result_payload={},
                validation_errors=[],
                failure_reason="Execution timed out before returning a result.",
                started_at=now,
                completed_at=now,
                attempt_number=contract.execution_context.get("attempt_number", 1),
                runtime_metadata={"simulate_mode": mode, "local_runtime": True},
            )

        if mode == "cancelled":
            return StructuredExecutionResult(
                execution_id=f"exec_{contract.task_id}_cancelled",
                task_id=contract.task_id,
                mission_id=contract.mission_id,
                division_name=contract.division_name,
                specialist_name=contract.specialist_name,
                capability_name=contract.capability_name,
                outcome=ExecutionOutcome.CANCELLED,
                result_payload={"cancelled": True},
                validation_errors=[],
                failure_reason="Execution was cancelled by Mission Control.",
                started_at=now,
                completed_at=now,
                attempt_number=contract.execution_context.get("attempt_number", 1),
                runtime_metadata={"simulate_mode": mode, "local_runtime": True},
            )

        if mode == "fail":
            return StructuredExecutionResult(
                execution_id=f"exec_{contract.task_id}_failed",
                task_id=contract.task_id,
                mission_id=contract.mission_id,
                division_name=contract.division_name,
                specialist_name=contract.specialist_name,
                capability_name=contract.capability_name,
                outcome=ExecutionOutcome.FAILED,
                result_payload={"ok": False},
                validation_errors=["Local mock execution failed intentionally."],
                failure_reason="Local mock execution deliberately failed.",
                started_at=now,
                completed_at=now,
                attempt_number=contract.execution_context.get("attempt_number", 1),
                runtime_metadata={"simulate_mode": mode, "local_runtime": True},
            )

        payload = {
            "ok": True,
            "input": contract.input_payload,
            "specialist": contract.specialist_name,
            "division": contract.division_name,
            "capability": contract.capability_name,
            "execution_context": contract.execution_context,
        }
        if mode == "bad_output":
            payload = {"unexpected": "value"}
            validation_errors = ["Output payload does not match the capability contract."]
            return StructuredExecutionResult(
                execution_id=f"exec_{contract.task_id}_bad_output",
                task_id=contract.task_id,
                mission_id=contract.mission_id,
                division_name=contract.division_name,
                specialist_name=contract.specialist_name,
                capability_name=contract.capability_name,
                outcome=ExecutionOutcome.FAILED,
                result_payload=payload,
                validation_errors=validation_errors,
                failure_reason="Output contract validation failed.",
                started_at=now,
                completed_at=now,
                attempt_number=contract.execution_context.get("attempt_number", 1),
                runtime_metadata={"simulate_mode": mode, "local_runtime": True},
            )

        return StructuredExecutionResult(
            execution_id=f"exec_{contract.task_id}_ok",
            task_id=contract.task_id,
            mission_id=contract.mission_id,
            division_name=contract.division_name,
            specialist_name=contract.specialist_name,
            capability_name=contract.capability_name,
            outcome=ExecutionOutcome.SUCCEEDED,
            result_payload=payload,
            validation_errors=[],
            failure_reason=None,
            started_at=now,
            completed_at=now,
            attempt_number=contract.execution_context.get("attempt_number", 1),
            runtime_metadata={"simulate_mode": mode, "local_runtime": True},
        )


class MissionExecutionDispatcher:
    """Dispatch validated specialist tasks to a runtime without performing routing logic."""

    def __init__(self, division_registry: dict[str, Any] | None = None, runtime: BaseExecutionRuntime | None = None):
        self.division_registry = division_registry or {}
        self.runtime = runtime or LocalMockExecutionRuntime()

    def validate_pre_dispatch(
        self,
        *,
        task: Any,
        assignment: dict[str, Any],
        capability_contract: CapabilityExecutionContract | None = None,
    ) -> list[str]:
        errors: list[str] = []

        if task.division_name is None:
            errors.append("Task is missing a division assignment.")
        else:
            division = self.division_registry.get(task.division_name)
            if division is None:
                errors.append(f"Division '{task.division_name}' is not registered.")

        if task.specialist_name is None:
            errors.append("Task is missing a specialist assignment.")
        elif assignment.get("name") is not None and task.specialist_name != assignment.get("name"):
            errors.append("Assigned specialist does not match the task binding.")

        if task.capability_name is None:
            errors.append("Task is missing a capability assignment.")
        elif assignment.get("capability_name") is not None and task.capability_name != assignment.get("capability_name"):
            errors.append("Assigned capability does not match the task binding.")

        if assignment.get("permission_scope") is not None and task.permission_scope != assignment.get("permission_scope"):
            errors.append("Assigned permission scope does not match the task permission scope.")

        if task.approval_state == ApprovalState.PENDING:
            errors.append("Task approval is pending; dispatch is blocked until approval is granted.")
        if task.approval_state == ApprovalState.REJECTED:
            errors.append("Task approval was rejected; dispatch is not permitted.")
        if task.approval_state == ApprovalState.ESCALATED:
            errors.append("Task approval is escalated; dispatch is blocked pending governance resolution.")

        if task.task_state in {TaskLifecycleState.BLOCKED, TaskLifecycleState.PENDING}:
            errors.append("Task is not ready for execution dispatch.")

        if task.task_state == TaskLifecycleState.REJECTED:
            errors.append("Task is in a terminal governance-rejected state and cannot dispatch.")

        if task.failure_reason and task.task_state == TaskLifecycleState.FAILED and task.retry_count >= task.max_retries:
            errors.append("Task has already failed and exhausted retry budget; dispatch is not permitted.")

        if capability_contract is not None:
            input_errors = capability_contract.validate_input(task.result_payload if task.result_payload else task.metadata.get("input_payload"))
            for error in input_errors:
                errors.append(f"Capability input contract validation failed: {error}")

        return errors

    def dispatch(
        self,
        *,
        task: Any,
        assignment: dict[str, Any],
        capability_contract: CapabilityExecutionContract | None = None,
        input_payload: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
        attempt_number: int = 1,
    ) -> StructuredExecutionResult:
        errors = self.validate_pre_dispatch(task=task, assignment=assignment, capability_contract=capability_contract)
        if errors:
            return StructuredExecutionResult(
                execution_id=f"exec_{task.task_id}_pre_dispatch_rejected",
                task_id=task.task_id,
                mission_id=task.mission_id,
                division_name=task.division_name or "unknown",
                specialist_name=task.specialist_name or "unknown",
                capability_name=task.capability_name or "unknown",
                outcome=ExecutionOutcome.FAILED,
                result_payload={},
                validation_errors=errors,
                failure_reason="Pre-dispatch validation failed.",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                attempt_number=attempt_number,
                runtime_metadata={"pre_dispatch_validation": True, "dispatch_rejected": True},
            )

        execution_contract = SpecialistExecutionContract(
            task_id=task.task_id,
            mission_id=task.mission_id,
            plan_id=task.plan_id,
            specialist_name=task.specialist_name or assignment.get("name"),
            division_name=task.division_name or assignment.get("division_name"),
            capability_name=task.capability_name or assignment.get("capability_name"),
            permission_scope=task.permission_scope or assignment.get("permission_scope", "standard"),
            input_payload=input_payload or task.metadata.get("input_payload", {}),
            execution_context=execution_context or {},
            timeout_seconds=capability_contract.timeout_seconds if capability_contract else 30,
            metadata={
                "task_name": task.task_name,
                "division_assignment": assignment,
                "capability_contract": capability_contract.to_dict() if capability_contract else None,
            },
        )
        return self.runtime.execute(execution_contract)


__all__ = [
    "BaseExecutionRuntime",
    "CapabilityExecutionContract",
    "ExecutionOutcome",
    "LocalMockExecutionRuntime",
    "MissionExecutionDispatcher",
    "SpecialistExecutionContract",
    "StructuredExecutionResult",
]
