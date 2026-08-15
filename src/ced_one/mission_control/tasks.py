"""Task delegation and lifecycle layer for Mission Control v0.5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ced_one.mission_control.execution import MissionExecutionPlan
from ced_one.mission_control.types import ApprovalState


class TaskLifecycleState(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    RETRY_PENDING = "retry_pending"


class MissionTerminalState(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass
class TaskDependency:
    source_task_id: str
    target_task_id: str
    dependency_type: str = "depends_on"
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MissionTask:
    task_id: str
    mission_id: str
    plan_id: str
    task_name: str
    description: str
    division_name: str | None = None
    specialist_name: str | None = None
    capability_name: str | None = None
    permission_scope: str = "standard"
    task_state: TaskLifecycleState = TaskLifecycleState.PENDING
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    dependencies: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    retryable: bool = True
    failure_reason: str | None = None
    result_payload: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    terminally_prevented: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def validate_compatibility(task_state: TaskLifecycleState, approval_state: ApprovalState) -> bool:
        valid_map = {
            TaskLifecycleState.PENDING: {ApprovalState.NOT_REQUIRED, ApprovalState.PENDING},
            TaskLifecycleState.BLOCKED: {ApprovalState.PENDING, ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.READY: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.ASSIGNED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.IN_PROGRESS: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.COMPLETED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
            TaskLifecycleState.FAILED: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.REJECTED},
            TaskLifecycleState.RETRY_PENDING: {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.PENDING},
            TaskLifecycleState.REJECTED: {
                ApprovalState.REJECTED,
                ApprovalState.APPROVED,
                ApprovalState.NOT_REQUIRED,
            },
            TaskLifecycleState.CANCELLED: {ApprovalState.NOT_REQUIRED, ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.PENDING},
        }
        return approval_state in valid_map.get(task_state, set())

    def transition_to(self, new_state: TaskLifecycleState, *, approval_state: ApprovalState | None = None, reason: str | None = None) -> None:
        if approval_state is not None:
            self.approval_state = approval_state
        if not self.validate_compatibility(new_state, self.approval_state):
            raise ValueError(
                f"Invalid task/approval compatibility: task_state={new_state.value}, approval_state={self.approval_state.value}"
            )
        self.task_state = new_state
        self.failure_reason = reason
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "plan_id": self.plan_id,
            "task_name": self.task_name,
            "description": self.description,
            "division_name": self.division_name,
            "specialist_name": self.specialist_name,
            "capability_name": self.capability_name,
            "permission_scope": self.permission_scope,
            "task_state": self.task_state.value,
            "approval_state": self.approval_state.value,
            "dependencies": list(self.dependencies),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retryable": self.retryable,
            "failure_reason": self.failure_reason,
            "result_payload": self.result_payload,
            "validation_errors": list(self.validation_errors),
            "metadata": self.metadata,
            "terminally_prevented": self.terminally_prevented,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class TaskAuditEvent:
    event_type: str
    task_id: str | None = None
    mission_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


class TaskAuditLog:
    """Append-only audit history for mission tasks and dependencies."""

    def __init__(self):
        self.events: list[TaskAuditEvent] = []

    def record(self, event_type: str, *, task_id: str | None = None, mission_id: str | None = None, **details: Any) -> TaskAuditEvent:
        event = TaskAuditEvent(
            event_type=event_type,
            task_id=task_id,
            mission_id=mission_id,
            details=dict(details),
        )
        self.events.append(event)
        return event

    def as_list(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]


class MissionTaskGraph:
    """Creates and validates a task graph from an approved execution plan."""

    def __init__(self, mission_id: str, plan_id: str, tasks: dict[str, MissionTask] | None = None):
        self.mission_id = mission_id
        self.plan_id = plan_id
        self.tasks: dict[str, MissionTask] = tasks or {}
        self.dependencies: list[TaskDependency] = []
        self.audit_log = TaskAuditLog()

    @classmethod
    def from_execution_plan(
        cls,
        plan: MissionExecutionPlan,
        *,
        division_name: str | None,
        specialist_name: str | None,
        capability_name: str | None,
    ) -> "MissionTaskGraph":
        graph = cls(mission_id=plan.request_id, plan_id=plan.plan_id, tasks={})
        prior_task_id: str | None = None

        for index, step in enumerate(plan.steps, start=1):
            task_id = f"task_{plan.request_id}_{index}"
            approval_state = ApprovalState.APPROVED if step.approval_required and plan.approved else ApprovalState.PENDING if step.approval_required else ApprovalState.NOT_REQUIRED
            task = MissionTask(
                task_id=task_id,
                mission_id=plan.request_id,
                plan_id=plan.plan_id,
                task_name=step.name,
                description=step.description,
                division_name=division_name,
                specialist_name=specialist_name,
                capability_name=capability_name,
                task_state=TaskLifecycleState.PENDING,
                approval_state=approval_state,
                dependencies=[],
                metadata={
                    "order": step.order,
                    "approval_required": step.approval_required,
                    "step_metadata": step.metadata,
                },
            )
            graph.tasks[task_id] = task
            graph.audit_log.record(
                "TASK_CREATED",
                task_id=task_id,
                mission_id=plan.request_id,
                task_name=task.task_name,
                division_name=division_name,
                specialist_name=specialist_name,
                capability_name=capability_name,
            )

            if prior_task_id is not None:
                dep = TaskDependency(
                    source_task_id=prior_task_id,
                    target_task_id=task_id,
                    dependency_type="depends_on",
                    status="pending",
                    metadata={"reason": "execution-order dependency"},
                )
                graph.dependencies.append(dep)
                task.dependencies.append(prior_task_id)
                graph.audit_log.record(
                    "TASK_DEPENDENCY_BLOCKED",
                    task_id=task_id,
                    mission_id=plan.request_id,
                    source_task_id=prior_task_id,
                    target_task_id=task_id,
                    dependency_type="depends_on",
                )
            prior_task_id = task_id

        return graph

    def validate_task_compatibility(self, task_id: str) -> bool:
        task = self.tasks[task_id]
        if not MissionTask.validate_compatibility(task.task_state, task.approval_state):
            self.audit_log.record(
                "TASK_REJECTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason="Invalid task/approval compatibility.",
                task_state=task.task_state.value,
                approval_state=task.approval_state.value,
            )
            return False
        return True

    def validate_routing(self, division_registry: dict[str, Any]) -> bool:
        for task in self.tasks.values():
            if task.division_name is None:
                return False
            division = division_registry.get(task.division_name)
            if division is None:
                return False
            if task.specialist_name is not None and hasattr(division, "resolve_specialist"):
                specialist = division.resolve_specialist({"user_goal": task.task_name})
                if isinstance(specialist, dict) and specialist.get("name") and task.specialist_name != specialist.get("name"):
                    return False
            if task.capability_name is not None and hasattr(division, "resolve_capability"):
                capability = division.resolve_capability({"user_goal": task.task_name})
                if isinstance(capability, dict) and capability.get("name") and task.capability_name != capability.get("name"):
                    return False
        return True

    def propagate_failure(self, task_id: str, *, reason: str, terminal: bool = True) -> list[str]:
        affected: list[str] = []
        for dependency in self.dependencies:
            if dependency.source_task_id == task_id:
                dependent = self.tasks.get(dependency.target_task_id)
                if dependent is None:
                    continue
                dependent.task_state = TaskLifecycleState.BLOCKED
                dependent.terminally_prevented = terminal
                dependent.failure_reason = reason
                dependent.metadata["blocked_reason"] = reason
                affected.append(dependent.task_id)
                self.audit_log.record(
                    "TASK_DEPENDENCY_TERMINALLY_PREVENTED",
                    task_id=dependent.task_id,
                    mission_id=self.mission_id,
                    blocking_task_id=task_id,
                    reason=reason,
                    terminal=terminal,
                )
        return affected

    def approve_task(self, task_id: str, *, approval_state: ApprovalState, reason: str | None = None) -> None:
        task = self.tasks[task_id]
        if approval_state == ApprovalState.REJECTED:
            task.task_state = TaskLifecycleState.REJECTED
            task.approval_state = ApprovalState.REJECTED
            task.failure_reason = reason or "Approval rejected."
            self.audit_log.record(
                "TASK_APPROVAL_REJECTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=reason or "Approval rejected.",
            )
            self.audit_log.record(
                "TASK_REJECTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=reason or "Approval rejected.",
            )
            self.propagate_failure(task_id, reason=reason or "Approval rejected.", terminal=True)
            return
        if approval_state == ApprovalState.APPROVED:
            task.approval_state = approval_state
            self.audit_log.record(
                "TASK_APPROVAL_GRANTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=reason or "Approval granted.",
            )
            return
        if approval_state == ApprovalState.PENDING:
            task.approval_state = approval_state
            task.task_state = TaskLifecycleState.BLOCKED
            self.audit_log.record(
                "TASK_APPROVAL_REQUESTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=reason or "Approval pending.",
            )
            return

    def mark_task_result(self, task_id: str, *, result_payload: dict[str, Any] | None = None, validation_errors: list[str] | None = None) -> None:
        task = self.tasks[task_id]
        payload = result_payload or {}
        errors = validation_errors or []
        task.result_payload = payload
        task.validation_errors = errors
        if errors:
            task.task_state = TaskLifecycleState.FAILED
            task.failure_reason = "; ".join(errors)
            self.audit_log.record(
                "TASK_FAILED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=task.failure_reason,
            )
            self.propagate_failure(task_id, reason=task.failure_reason, terminal=True)
            return
        task.task_state = TaskLifecycleState.COMPLETED
        task.failure_reason = None
        self.audit_log.record(
            "TASK_COMPLETED",
            task_id=task_id,
            mission_id=self.mission_id,
            payload=payload,
        )

    def resolve_mission_state(self) -> MissionTerminalState:
        if not self.tasks:
            return MissionTerminalState.BLOCKED

        if any(task.task_state == TaskLifecycleState.REJECTED for task in self.tasks.values()):
            return MissionTerminalState.REJECTED

        if any(task.task_state == TaskLifecycleState.FAILED for task in self.tasks.values()):
            return MissionTerminalState.FAILED

        if any(task.task_state == TaskLifecycleState.BLOCKED and task.terminally_prevented for task in self.tasks.values()):
            return MissionTerminalState.FAILED

        if all(task.task_state == TaskLifecycleState.COMPLETED for task in self.tasks.values()):
            return MissionTerminalState.COMPLETED

        if any(task.task_state == TaskLifecycleState.BLOCKED for task in self.tasks.values()):
            return MissionTerminalState.BLOCKED

        return MissionTerminalState.BLOCKED

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "plan_id": self.plan_id,
            "tasks": {task_id: task.to_dict() for task_id, task in self.tasks.items()},
            "dependencies": [
                {
                    "source_task_id": dep.source_task_id,
                    "target_task_id": dep.target_task_id,
                    "dependency_type": dep.dependency_type,
                    "status": dep.status,
                    "metadata": dep.metadata,
                }
                for dep in self.dependencies
            ],
            "mission_state": self.resolve_mission_state().value,
            "audit_events": self.audit_log.as_list(),
        }


__all__ = [
    "MissionTask",
    "MissionTaskGraph",
    "MissionTerminalState",
    "TaskAuditEvent",
    "TaskAuditLog",
    "TaskDependency",
    "TaskLifecycleState",
]
