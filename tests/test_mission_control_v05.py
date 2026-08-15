from __future__ import annotations

from ced_one.mission_control.execution import ExecutionPlanStep, MissionExecutionPlan
from ced_one.mission_control.tasks import MissionTaskGraph, MissionTerminalState, TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


class GenericDivision:
    name = "generic"

    def supports_request(self, request, classification=None):
        return True

    def resolve_request(self, request, classification=None):
        return {
            "division_name": self.name,
            "is_supported": True,
            "is_routeable": True,
            "confidence": 0.9,
            "rationale": "Assigned to the generic test division.",
            "specialist_name": "operations_specialist",
            "capability_name": "coordination",
            "status": "resolved",
        }

    def resolve_specialist(self, request):
        return {
            "name": "operations_specialist",
            "division_name": self.name,
            "permission_scope": "standard",
            "rationale": "Assigned through the generic division routing model.",
        }

    def resolve_capability(self, request):
        return {
            "name": "coordination",
            "division_name": self.name,
            "contract": "generic_coordination",
            "rationale": "Reused as a provider-independent capability contract.",
        }


def build_plan(approved: bool = False, approval_required: bool = False):
    plan = MissionExecutionPlan(
        plan_id="plan_001",
        request_id="req_001",
        division="generic",
        specialist="operations_specialist",
        capability="coordination",
        approved=approved,
        steps=[
            ExecutionPlanStep(
                name="validate_request",
                description="Validate the request before delegation.",
                order=1,
                division="generic",
                specialist="operations_specialist",
                capability="coordination",
                approval_required=approval_required,
            ),
            ExecutionPlanStep(
                name="delegate_work",
                description="Delegate the controlled task to the selected specialist.",
                order=2,
                division="generic",
                specialist="operations_specialist",
                capability="coordination",
                approval_required=False,
            ),
        ],
    )
    return plan


def test_v05_task_graph_is_created_from_approved_plan():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")

    assert len(graph.tasks) == 2
    assert graph.dependencies[0].source_task_id == list(graph.tasks.keys())[0]
    assert graph.resolve_mission_state() in {MissionTerminalState.BLOCKED, MissionTerminalState.COMPLETED}


def test_v05_task_approval_and_task_state_are_separate_dimensions():
    plan = build_plan(approved=False, approval_required=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task = next(iter(graph.tasks.values()))

    assert task.task_state == TaskLifecycleState.PENDING
    assert task.approval_state == ApprovalState.PENDING
    assert MissionTaskGraph.validate_task_compatibility(graph, task.task_id) is True


def test_v05_rejected_approval_terminalizes_task():
    plan = build_plan(approved=False, approval_required=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task_id = next(iter(graph.tasks.keys()))
    graph.approve_task(task_id, approval_state=ApprovalState.REJECTED, reason="Approval denied.")

    task = graph.tasks[task_id]
    assert task.task_state == TaskLifecycleState.REJECTED
    assert task.approval_state == ApprovalState.REJECTED
    assert graph.resolve_mission_state() == MissionTerminalState.REJECTED


def test_v05_blocked_approved_is_valid_when_dependency_remains():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task = next(iter(graph.tasks.values()))
    task.task_state = TaskLifecycleState.BLOCKED
    task.approval_state = ApprovalState.APPROVED

    assert MissionTaskGraph.validate_task_compatibility(graph, task.task_id) is True


def test_v05_retry_pending_with_approved_or_not_required_is_valid():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task = next(iter(graph.tasks.values()))
    task.task_state = TaskLifecycleState.RETRY_PENDING
    task.approval_state = ApprovalState.APPROVED
    assert MissionTaskGraph.validate_task_compatibility(graph, task.task_id) is True

    task.approval_state = ApprovalState.NOT_REQUIRED
    assert MissionTaskGraph.validate_task_compatibility(graph, task.task_id) is True


def test_v05_task_result_validation_marks_failed_tasks():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task_id = next(iter(graph.tasks.keys()))
    graph.mark_task_result(task_id, result_payload={"ok": False}, validation_errors=["invalid result payload"])

    task = graph.tasks[task_id]
    assert task.task_state == TaskLifecycleState.FAILED
    assert task.failure_reason == "invalid result payload"


def test_v05_dependency_failure_propagates_to_downstream_tasks():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    upstream_id = list(graph.tasks.keys())[0]
    downstream_id = list(graph.tasks.keys())[1]
    graph.propagate_failure(upstream_id, reason="Upstream task failed.", terminal=True)

    assert graph.tasks[downstream_id].task_state == TaskLifecycleState.BLOCKED
    assert graph.tasks[downstream_id].terminally_prevented is True


def test_v05_approval_decisions_are_append_only_audit_events():
    plan = build_plan(approved=False, approval_required=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task_id = next(iter(graph.tasks.keys()))
    graph.approve_task(task_id, approval_state=ApprovalState.APPROVED, reason="Approved.")
    graph.approve_task(task_id, approval_state=ApprovalState.REJECTED, reason="Later rejected.")

    event_types = [event.event_type for event in graph.audit_log.events]
    assert "TASK_APPROVAL_REQUESTED" in event_types or "TASK_APPROVAL_GRANTED" in event_types
    assert "TASK_APPROVAL_REJECTED" in event_types
    assert "TASK_REJECTED" in event_types


def test_v05_mission_state_is_deterministic_for_terminal_outcomes():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    for task in graph.tasks.values():
        task.task_state = TaskLifecycleState.COMPLETED
        task.approval_state = ApprovalState.APPROVED

    assert graph.resolve_mission_state() == MissionTerminalState.COMPLETED

    graph.tasks[next(iter(graph.tasks.keys()))].task_state = TaskLifecycleState.FAILED
    assert graph.resolve_mission_state() == MissionTerminalState.FAILED


def test_v05_route_validation_confirms_division_and_contract_binding():
    plan = build_plan(approved=True)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")

    assert graph.validate_routing({"generic": GenericDivision()}) is True


def test_v05_invalid_compatibility_is_rejected():
    plan = build_plan(approved=False)
    graph = MissionTaskGraph.from_execution_plan(plan, division_name="generic", specialist_name="operations_specialist", capability_name="coordination")
    task = next(iter(graph.tasks.values()))
    task.task_state = TaskLifecycleState.READY
    task.approval_state = ApprovalState.PENDING

    assert MissionTaskGraph.validate_task_compatibility(graph, task.task_id) is False
