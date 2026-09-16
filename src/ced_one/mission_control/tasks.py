"""Task delegation and lifecycle layer for Mission Control v0.5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ced_one.mission_control.execution import MissionExecutionPlan
from ced_one.mission_control.types import ApprovalState, MissionRequest


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


# All mutations through the task/graph API use this single transition table.
S = TaskLifecycleState
TERMINAL_STATES = {S.COMPLETED, S.REJECTED, S.CANCELLED}
TASK_TRANSITIONS = {
    S.PENDING: {S.READY, S.BLOCKED, S.REJECTED, S.CANCELLED},
    S.BLOCKED: {S.READY, S.REJECTED, S.CANCELLED},
    S.READY: {S.ASSIGNED, S.BLOCKED, S.REJECTED, S.CANCELLED},
    S.ASSIGNED: {S.IN_PROGRESS, S.BLOCKED, S.REJECTED, S.CANCELLED},
    S.IN_PROGRESS: {S.COMPLETED, S.FAILED, S.CANCELLED},
    S.FAILED: {S.RETRY_PENDING, S.REJECTED, S.CANCELLED},
    S.RETRY_PENDING: {S.READY, S.BLOCKED, S.REJECTED, S.CANCELLED},
    S.COMPLETED: set(), S.REJECTED: set(), S.CANCELLED: set(),
}


class MissionTerminalState(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
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
            TaskLifecycleState.PENDING: {ApprovalState.NOT_REQUIRED, ApprovalState.PENDING, ApprovalState.APPROVED, ApprovalState.ESCALATED},
            TaskLifecycleState.BLOCKED: {ApprovalState.PENDING, ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED, ApprovalState.ESCALATED},
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

    def transition_to(self, new_state: TaskLifecycleState, *, approval_state: ApprovalState | None = None, reason: str | None = None, completed_dependencies: set[str] | None = None) -> None:
        proposed_approval = self.approval_state if approval_state is None else approval_state
        if new_state not in TASK_TRANSITIONS[self.task_state]:
            raise ValueError(f"Invalid task transition: {self.task_state.value} -> {new_state.value}")
        if not self.validate_compatibility(new_state, proposed_approval):
            raise ValueError(f"Invalid task/approval compatibility: task_state={new_state.value}, approval_state={proposed_approval.value}")
        if new_state in {S.READY, S.ASSIGNED, S.IN_PROGRESS}:
            if self.terminally_prevented or not set(self.dependencies) <= (completed_dependencies or set()):
                raise ValueError("Task dependencies are not completed.")
        if new_state == S.RETRY_PENDING:
            if not self.retryable or self.retry_count >= self.max_retries:
                raise ValueError("Task retry budget exhausted or task is not retryable.")
        self.approval_state = proposed_approval
        self.task_state = new_state
        if new_state == S.RETRY_PENDING:
            self.retry_count += 1
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
                specialist = division.resolve_specialist(MissionRequest(user_goal=task.task_name, business_division=task.division_name))
                if isinstance(specialist, dict) and specialist.get("name") and task.specialist_name != specialist.get("name"):
                    return False
            if task.capability_name is not None and hasattr(division, "resolve_capability"):
                capability = division.resolve_capability(MissionRequest(user_goal=task.task_name, business_division=task.division_name))
                if isinstance(capability, dict) and capability.get("name") and task.capability_name != capability.get("name"):
                    return False
        return True

    def transition_task(self, task_id: str, new_state: TaskLifecycleState, **kwargs: Any) -> None:
        completed = {key for key, task in self.tasks.items() if task.task_state == S.COMPLETED}
        task = self.tasks[task_id]
        previous = task.task_state
        task.transition_to(new_state, completed_dependencies=completed, **kwargs)
        self.audit_log.record("TASK_STATE_CHANGED", task_id=task_id, mission_id=self.mission_id, previous_state=previous.value, resulting_state=new_state.value)

    def propagate_failure(self, task_id: str, *, reason: str, terminal: bool = True) -> list[str]:
        affected = []
        queue = [task_id]
        seen = {task_id}
        while queue:
            source = queue.pop(0)
            targets = {dep.target_task_id for dep in self.dependencies if dep.source_task_id == source}
            targets.update(key for key, task in self.tasks.items() if source in task.dependencies)
            for target in sorted(targets):
                if target in seen or target not in self.tasks:
                    continue
                seen.add(target)
                queue.append(target)
                dependent = self.tasks[target]
                if dependent.task_state in TERMINAL_STATES:
                    continue
                if dependent.task_state not in {S.BLOCKED, S.FAILED}:
                    self.transition_task(target, S.BLOCKED, reason=reason)
                dependent.terminally_prevented = terminal
                dependent.failure_reason = reason
                dependent.metadata["blocked_reason"] = reason
                affected.append(target)
                self.audit_log.record("TASK_DEPENDENCY_TERMINALLY_PREVENTED", task_id=target, mission_id=self.mission_id, blocking_task_id=source, reason=reason, terminal=terminal)
        return affected

    def approve_task(self, task_id: str, *, approval_state: ApprovalState, reason: str | None = None) -> None:
        task = self.tasks[task_id]
        if task.task_state in TERMINAL_STATES:
            raise ValueError("Cannot change approval of a terminal task.")
        if approval_state == ApprovalState.REJECTED:
            self.transition_task(task_id, S.REJECTED, approval_state=approval_state, reason=reason or "Approval rejected.")
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
            if not task.validate_compatibility(task.task_state, approval_state):
                raise ValueError("Invalid approval change.")
            task.approval_state = approval_state
            self.audit_log.record(
                "TASK_APPROVAL_GRANTED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=reason or "Approval granted.",
            )
            return
        if approval_state in {ApprovalState.PENDING, ApprovalState.ESCALATED}:
            if task.task_state == S.BLOCKED:
                if not task.validate_compatibility(S.BLOCKED, approval_state):
                    raise ValueError("Invalid approval change.")
                task.approval_state = approval_state
            else:
                self.transition_task(task_id, S.BLOCKED, approval_state=approval_state, reason=reason)
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
        self.transition_task(task_id, S.FAILED if errors else S.COMPLETED, reason="; ".join(errors) if errors else None)
        task.result_payload = payload
        task.validation_errors = errors
        if errors:
            self.audit_log.record(
                "TASK_FAILED",
                task_id=task_id,
                mission_id=self.mission_id,
                reason=task.failure_reason,
            )
            self.propagate_failure(task_id, reason=task.failure_reason, terminal=not task.retryable or task.retry_count >= task.max_retries)
            return
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

        if any(task.task_state == TaskLifecycleState.CANCELLED for task in self.tasks.values()):
            return MissionTerminalState.CANCELLED

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
