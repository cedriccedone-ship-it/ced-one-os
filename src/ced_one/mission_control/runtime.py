"""Execution runtime contracts and deterministic specialist execution for Mission Control v0.6."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4
import json

from ced_one.mission_control.policy import ExecutionPolicy, PolicyEvaluationEngine, validate_context_data
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate_input(self, payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(payload, dict):
            return ["Payload must be a dictionary."]
        errors: list[str] = []
        required_fields = self.input_schema.get("required_fields", [])
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(f"Missing required input field: {field_name}")
        return errors

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(payload, dict):
            return ["Payload must be a dictionary."]
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


class RegistrationError(ValueError):
    """A registration cannot be selected or reserved for this dispatch."""


@dataclass(frozen=True)
class RegistrationSelection:
    registration_id: str
    contract: CapabilityExecutionContract


class LocalExecutionRuntime(BaseExecutionRuntime):
    """Explicit registrations, protected against replacement during dispatch."""

    def __init__(self):
        self._executors = {}
        self._reservations = {}
        self._registration_lock = Lock()

    def register(self, contract: CapabilityExecutionContract, executor: Callable[[SpecialistExecutionContract], dict[str, Any]]) -> None:
        isolated = deepcopy(contract)
        key = (isolated.division_name, isolated.name)
        with self._registration_lock:
            if self._reservations.get(key, 0):
                raise RegistrationError("Registration is in use.")
            self._executors[key] = (uuid4().hex, isolated, executor)

    def get_registration(self, division_name: str, capability_name: str) -> RegistrationSelection | None:
        with self._registration_lock:
            entry = self._executors.get((division_name, capability_name))
            return RegistrationSelection(entry[0], deepcopy(entry[1])) if entry else None

    def get_contract(self, division_name: str, capability_name: str) -> CapabilityExecutionContract | None:
        selection = self.get_registration(division_name, capability_name)
        return selection.contract if selection else None

    @contextmanager
    def reserve_registration(self, division_name: str, capability_name: str, registration_id: str):
        key = (division_name, capability_name)
        with self._registration_lock:
            entry = self._executors.get(key)
            if entry is None or entry[0] != registration_id:
                raise RegistrationError("Execution registration is stale or missing.")
            selection = RegistrationSelection(entry[0], deepcopy(entry[1]))
            self._reservations[key] = self._reservations.get(key, 0) + 1
        try:
            yield selection
        finally:
            with self._registration_lock:
                self._reservations[key] -= 1
                if not self._reservations[key]:
                    del self._reservations[key]

    def execute(self, contract: SpecialistExecutionContract) -> StructuredExecutionResult:
        with self._registration_lock:
            _, registered, executor = self._executors[(contract.division_name, contract.capability_name)]
        if contract.permission_scope != registered.permission_scope:
            raise ValueError("Executor permission scope mismatch.")
        started = datetime.now(timezone.utc)
        payload = executor(contract)
        return StructuredExecutionResult(
            execution_id=f"exec_{contract.task_id}", task_id=contract.task_id,
            mission_id=contract.mission_id, division_name=contract.division_name,
            specialist_name=contract.specialist_name, capability_name=contract.capability_name,
            result_payload=payload, started_at=started,
            runtime_metadata={"local_runtime": True},
        )


class MissionExecutionDispatcher:
    """Dispatch validated specialist tasks to a runtime without performing routing logic."""

    def __init__(self, division_registry: dict[str, Any] | None = None, runtime: BaseExecutionRuntime | None = None):
        self.division_registry = division_registry or {}
        self.runtime = runtime or LocalExecutionRuntime()

    def validate_pre_dispatch(
        self,
        *,
        task: Any,
        assignment: dict[str, Any],
        capability_contract: CapabilityExecutionContract | None = None,
        input_payload: dict[str, Any] | None = None,
        completed_dependencies: set[str] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if capability_contract is None:
            errors.append("Capability contract is required.")

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

        if assignment.get("division_name") is not None and task.division_name != assignment["division_name"]:
            errors.append("Assigned division does not match the task binding.")

        if assignment.get("permission_scope") is not None and task.permission_scope != assignment.get("permission_scope"):
            errors.append("Assigned permission scope does not match the task permission scope.")

        if task.terminally_prevented or not set(task.dependencies) <= (completed_dependencies or set()):
            errors.append("Task dependencies are not completed.")
        if task.approval_state == ApprovalState.PENDING:
            errors.append("Task approval is pending; dispatch is blocked until approval is granted.")
        if task.approval_state == ApprovalState.REJECTED:
            errors.append("Task approval was rejected; dispatch is not permitted.")
        if task.approval_state == ApprovalState.ESCALATED:
            errors.append("Task approval is escalated; dispatch is blocked pending governance resolution.")

        if task.task_state not in {TaskLifecycleState.READY, TaskLifecycleState.ASSIGNED}:
            errors.append("Task is not ready for execution dispatch.")

        if task.task_state == TaskLifecycleState.REJECTED:
            errors.append("Task is in a terminal governance-rejected state and cannot dispatch.")

        if task.failure_reason and task.task_state == TaskLifecycleState.FAILED and task.retry_count >= task.max_retries:
            errors.append("Task has already failed and exhausted retry budget; dispatch is not permitted.")

        if capability_contract is not None:
            for actual, expected in [(task.capability_name, capability_contract.name), (task.division_name, capability_contract.division_name), (task.permission_scope, capability_contract.permission_scope)]:
                if actual != expected:
                    errors.append("Capability contract binding mismatch.")
            input_errors = capability_contract.validate_input(input_payload if input_payload is not None else task.metadata.get("input_payload", {}))
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
        authorization_snapshot=None,
        authorization_context=None,
        policy=None,
        completed_dependencies: set[str] | None = None,
        audit_log=None,
    ) -> StructuredExecutionResult:
        from ced_one.mission_control.governance import AuthorizationSnapshot, ExecutionGovernanceGate, PolicyEvaluationContext

        def reject(errors):
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
                runtime_metadata={"pre_dispatch_validation": True, "dispatch_rejected": True, "execution_performed": False},
            )


        errors = []
        if not isinstance(authorization_context, PolicyEvaluationContext):
            errors.append("Invalid authorization context type.")
        else:
            errors.extend(PolicyEvaluationEngine.validate_context(authorization_context))
        if not isinstance(authorization_snapshot, AuthorizationSnapshot):
            errors.append("Invalid authorization snapshot type.")
        else:
            errors.extend(PolicyEvaluationEngine.validate_context(authorization_snapshot))
        if not isinstance(policy, ExecutionPolicy):
            errors.append("Current execution policy is required.")
        if not isinstance(capability_contract, CapabilityExecutionContract):
            errors.append("Capability contract is required.")
        effective_context = {} if execution_context is None else execution_context
        effective_payload = input_payload if input_payload is not None else task.metadata.get("input_payload", {})
        for label, value in (("execution_context", effective_context), ("input_payload", effective_payload), ("assignment", assignment)):
            if type(value) is not dict:
                errors.append(f"{label} must be a dictionary.")
            errors.extend(validate_context_data(value))
        if not callable(getattr(self.runtime, "reserve_registration", None)):
            errors.append("Runtime does not support bound registration dispatch.")
        if errors:
            return reject(errors)
        try:
            payload = deepcopy(effective_payload)
            captured_context = deepcopy(effective_context)
            current = deepcopy(authorization_context)
            snapshot = deepcopy(authorization_snapshot)
            supplied_contract = capability_contract.to_dict()
        except RecursionError:
            return reject(["Authorization data exceeds supported nesting."])
        registration_id = current.task_context.get("registration_id")
        if not isinstance(registration_id, str) or not registration_id:
            return reject(["Execution registration identity is required."])
        # Catch only acquisition errors; executor failures use the runtime result path.
        reservation = self.runtime.reserve_registration(task.division_name, task.capability_name, registration_id)
        try:
            selected = reservation.__enter__()
        except RegistrationError as exc:
            return reject([str(exc)])
        try:
            capability_contract = selected.contract
            actual_contract = capability_contract.to_dict()
            errors = validate_context_data(supplied_contract) + validate_context_data(actual_contract)
            if errors:
                return reject(errors)
            if json.dumps(supplied_contract, sort_keys=True) != json.dumps(actual_contract, sort_keys=True):
                return reject(["Selected registration contract mismatch."])
            errors = self.validate_pre_dispatch(task=task, assignment=assignment, capability_contract=capability_contract, input_payload=payload, completed_dependencies=completed_dependencies)
            current.task_id = task.task_id
            current.mission_id = task.mission_id
            current.task_lifecycle_state = task.task_state
            current.approval_state = task.approval_state
            current.division_binding = task.division_name
            current.specialist_binding = task.specialist_name
            current.capability_binding = task.capability_name
            current.permission_scope = task.permission_scope
            current.policy_id = policy.policy_id
            current.policy_version = policy.policy_version
            current.task_context["input_payload"] = payload
            current.task_context["execution_context"] = captured_context
            current.task_context["registration_id"] = selected.registration_id
            current.task_context["capability_contract"] = actual_contract
            current.evaluated_at = datetime.now(timezone.utc)
            if not snapshot.is_still_valid(current):
                errors.append("Execution authorization is stale.")
            current_decision = ExecutionGovernanceGate().evaluate(current, policy=policy)
            if audit_log is not None:
                audit_log.record("PRE_DISPATCH_POLICY", task_id=task.task_id, mission_id=task.mission_id, decision=current_decision.decision.value, reason=current_decision.reason, context_fingerprint=current_decision.context_fingerprint, policy_id=policy.policy_id, policy_version=policy.policy_version)
            if not current_decision.is_allowed:
                errors.append("Current policy does not authorize execution.")
            if errors:
                return reject(errors)
            execution_contract = SpecialistExecutionContract(
                task_id=task.task_id,
                mission_id=task.mission_id,
                plan_id=task.plan_id,
                specialist_name=task.specialist_name or assignment.get("name"),
                division_name=task.division_name or assignment.get("division_name"),
                capability_name=task.capability_name or assignment.get("capability_name"),
                permission_scope=task.permission_scope or assignment.get("permission_scope", "standard"),
                input_payload=payload,
                execution_context=captured_context,
                timeout_seconds=capability_contract.timeout_seconds if capability_contract else 30,
                metadata={
                    "task_name": task.task_name,
                    "division_assignment": assignment,
                    "capability_contract": capability_contract.to_dict() if capability_contract else None,
                },
            )
            try:
                if task.task_state == TaskLifecycleState.READY:
                    task.transition_to(TaskLifecycleState.ASSIGNED, completed_dependencies=completed_dependencies)
                task.transition_to(TaskLifecycleState.IN_PROGRESS, completed_dependencies=completed_dependencies)
                if audit_log is not None:
                    audit_log.record("EXECUTION_STARTED", task_id=task.task_id, mission_id=task.mission_id, resulting_state=task.task_state.value, attempt_number=attempt_number)
                result = self.runtime.execute(execution_contract)
                if not isinstance(result, StructuredExecutionResult):
                    raise ValueError("Runtime must return StructuredExecutionResult.")
                binding_errors = ["Runtime result binding mismatch."] if (
                    result.task_id, result.mission_id, result.division_name, result.specialist_name, result.capability_name
                ) != (task.task_id, task.mission_id, task.division_name, task.specialist_name, task.capability_name) else []
                if not isinstance(result.outcome, ExecutionOutcome):
                    binding_errors.append("Unknown execution outcome.")
                output_errors = capability_contract.validate_output(result.result_payload) if capability_contract and result.outcome == ExecutionOutcome.SUCCEEDED else []
                result.validation_errors.extend(binding_errors + output_errors)
                if result.validation_errors or (result.failure_reason and result.outcome == ExecutionOutcome.SUCCEEDED):
                    result.outcome = ExecutionOutcome.FAILED
                    result.failure_reason = result.failure_reason or "; ".join(result.validation_errors)
                result.runtime_metadata["execution_performed"] = True
                return result
            except Exception as exc:
                return StructuredExecutionResult(
                    execution_id=f"exec_{task.task_id}_failed", task_id=task.task_id,
                    mission_id=task.mission_id, division_name=task.division_name,
                    specialist_name=task.specialist_name, capability_name=task.capability_name,
                    outcome=ExecutionOutcome.FAILED, failure_reason=f"{type(exc).__name__}: {exc}",
                    attempt_number=attempt_number, runtime_metadata={"execution_performed": True},
                )
        finally:
            reservation.__exit__(None, None, None)



__all__ = [
    "BaseExecutionRuntime",
    "CapabilityExecutionContract",
    "ExecutionOutcome",
    "LocalMockExecutionRuntime",
    "LocalExecutionRuntime",
    "MissionExecutionDispatcher",
    "SpecialistExecutionContract",
    "StructuredExecutionResult",
]
