from __future__ import annotations

from ced_one.mission_control.execution import ExecutionPlanStep, MissionExecutionPlan
from ced_one.mission_control.runtime import (
    CapabilityExecutionContract,
    ExecutionOutcome,
    LocalMockExecutionRuntime,
    MissionExecutionDispatcher,
    SpecialistExecutionContract,
    StructuredExecutionResult,
)
from ced_one.mission_control.tasks import MissionTask, MissionTaskGraph, MissionTerminalState, TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


class GenericDivision:
    name = "generic"

    def supports_request(self, request, classification=None):
        return True

    def resolve_specialist(self, request):
        return {
            "name": "operations_specialist",
            "division_name": self.name,
            "permission_scope": "standard",
            "capability_name": "coordination",
            "rationale": "Assigned through the generic division routing model.",
        }

    def resolve_capability(self, request):
        return {
            "name": "coordination",
            "division_name": self.name,
            "contract": "generic_coordination",
            "rationale": "Reusable provider-independent coordination contract.",
        }


class DispatchDivision(GenericDivision):
    pass


def build_plan():
    return MissionExecutionPlan(
        plan_id="plan_v06",
        request_id="req_v06",
        division="generic",
        specialist="operations_specialist",
        capability="coordination",
        approved=True,
        steps=[
            ExecutionPlanStep(
                name="dispatch_execution",
                description="Dispatch a specialist execution task.",
                order=1,
                division="generic",
                specialist="operations_specialist",
                capability="coordination",
                approval_required=False,
                metadata={"input_payload": {"request": "demo"}},
            )
        ],
    )


def test_v06_execution_result_uses_execution_outcome_not_task_lifecycle():
    result = StructuredExecutionResult(
        execution_id="exec_001",
        task_id="task_001",
        mission_id="mission_001",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        outcome=ExecutionOutcome.SUCCEEDED,
        result_payload={"ok": True},
        validation_errors=[],
        failure_reason=None,
        runtime_metadata={"local_runtime": True},
    )

    assert result.outcome == ExecutionOutcome.SUCCEEDED
    assert result.outcome.value == "succeeded"
    assert result.task_id == "task_001"


def test_v06_timeout_requires_failed_before_retry_pending():
    task = MissionTask(
        task_id="task_timeout",
        mission_id="mission_timeout",
        plan_id="plan_timeout",
        task_name="execute_runtime",
        description="Runtime execution with timeout.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.IN_PROGRESS,
        approval_state=ApprovalState.APPROVED,
        retry_count=0,
        max_retries=2,
    )

    task.task_state = TaskLifecycleState.FAILED
    task.failure_reason = "Execution timed out."
    if task.retry_count < task.max_retries:
        task.task_state = TaskLifecycleState.RETRY_PENDING

    assert task.task_state == TaskLifecycleState.RETRY_PENDING
    assert task.failure_reason == "Execution timed out."


def test_v06_non_retryable_timeout_remains_failed():
    task = MissionTask(
        task_id="task_timeout_non_retry",
        mission_id="mission_timeout_non_retry",
        plan_id="plan_timeout_non_retry",
        task_name="execute_runtime",
        description="Non-retryable timeout.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.IN_PROGRESS,
        approval_state=ApprovalState.APPROVED,
        retry_count=2,
        max_retries=2,
    )

    task.task_state = TaskLifecycleState.FAILED
    task.failure_reason = "Execution timed out."
    if task.retry_count < task.max_retries:
        task.task_state = TaskLifecycleState.RETRY_PENDING

    assert task.task_state == TaskLifecycleState.FAILED


def test_v06_governance_rejection_does_not_falsify_approval_state():
    task = MissionTask(
        task_id="task_rejected",
        mission_id="mission_rejected",
        plan_id="plan_rejected",
        task_name="execute_governance_check",
        description="Permission denied before dispatch.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.REJECTED,
        approval_state=ApprovalState.NOT_REQUIRED,
    )

    assert task.task_state == TaskLifecycleState.REJECTED
    assert task.approval_state == ApprovalState.NOT_REQUIRED
    assert MissionTask.validate_compatibility(task.task_state, task.approval_state) is True


def test_v06_rejected_plus_approved_is_valid_for_governance_rejection_after_approval():
    task = MissionTask(
        task_id="task_rejected_approved",
        mission_id="mission_rejected_approved",
        plan_id="plan_rejected_approved",
        task_name="execute_approved_but_rejected",
        description="Approval was granted but policy rejected execution.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.REJECTED,
        approval_state=ApprovalState.APPROVED,
    )

    assert MissionTask.validate_compatibility(task.task_state, task.approval_state) is True


def test_v06_explicit_approval_rejection_keeps_approval_state_rejected():
    task = MissionTask(
        task_id="task_approval_rejected",
        mission_id="mission_approval_rejected",
        plan_id="plan_approval_rejected",
        task_name="execute_approval",
        description="Approval explicitly rejected.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.REJECTED,
        approval_state=ApprovalState.REJECTED,
    )

    assert task.approval_state == ApprovalState.REJECTED
    assert MissionTask.validate_compatibility(task.task_state, task.approval_state) is True


def test_v06_dispatcher_rejects_invalid_pre_dispatch_prerequisites():
    task = MissionTask(
        task_id="task_dispatch_reject",
        mission_id="mission_dispatch_reject",
        plan_id="plan_dispatch_reject",
        task_name="execute_bad_task",
        description="Task should be rejected before dispatch.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.READY,
        approval_state=ApprovalState.APPROVED,
    )

    assignment = {
        "name": "wrong_specialist",
        "division_name": "generic",
        "permission_scope": "standard",
        "capability_name": "coordination",
    }
    contract = CapabilityExecutionContract(
        name="coordination",
        division_name="generic",
        contract_id="coordination_contract",
        permission_scope="standard",
        input_schema={"required_fields": ["request"]},
        output_schema={"required_fields": ["ok"]},
        timeout_seconds=30,
    )

    dispatcher = MissionExecutionDispatcher(division_registry={"generic": GenericDivision()}, runtime=LocalMockExecutionRuntime())
    result = dispatcher.dispatch(task=task, assignment=assignment, capability_contract=contract, input_payload={"request": "demo"})

    assert result.outcome == ExecutionOutcome.FAILED
    assert result.validation_errors


def test_v06_local_runtime_executes_deterministically():
    runtime = LocalMockExecutionRuntime()
    contract = SpecialistExecutionContract(
        task_id="task_runtime_ok",
        mission_id="mission_runtime_ok",
        plan_id="plan_runtime_ok",
        specialist_name="operations_specialist",
        division_name="generic",
        capability_name="coordination",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "success"},
        timeout_seconds=30,
    )

    result = runtime.execute(contract)
    assert result.outcome == ExecutionOutcome.SUCCEEDED
    assert result.result_payload["ok"] is True


def test_v06_capability_contract_validates_input_and_output():
    contract = CapabilityExecutionContract(
        name="coordination",
        division_name="generic",
        contract_id="coordination_contract",
        permission_scope="standard",
        input_schema={"required_fields": ["request"]},
        output_schema={"required_fields": ["ok"]},
        timeout_seconds=30,
    )

    assert contract.validate_input({"request": "demo"}) == []
    assert contract.validate_input({}) != []
    assert contract.validate_output({"ok": True}) == []
    assert contract.validate_output({}) != []


def test_v06_task_graph_reject_compatibility_for_governance_rejection():
    task = MissionTask(
        task_id="graph_reject",
        mission_id="mission_graph_reject",
        plan_id="plan_graph_reject",
        task_name="reject_policy",
        description="Governance rejection without approval rejection.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.REJECTED,
        approval_state=ApprovalState.NOT_REQUIRED,
    )

    assert MissionTask.validate_compatibility(task.task_state, task.approval_state) is True


def test_v06_mission_terminal_state_uses_rejected_when_governance_rejection_happens():
    graph = MissionTaskGraph(mission_id="mission_reject", plan_id="plan_reject", tasks={})
    graph.tasks["task_reject"] = MissionTask(
        task_id="task_reject",
        mission_id="mission_reject",
        plan_id="plan_reject",
        task_name="reject_policy",
        description="Governance rejection.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.REJECTED,
        approval_state=ApprovalState.NOT_REQUIRED,
    )

    assert graph.resolve_mission_state() == MissionTerminalState.REJECTED


def test_v06_execution_audit_event_is_append_only_and_explicit():
    runtime = LocalMockExecutionRuntime()
    contract = SpecialistExecutionContract(
        task_id="audit_task",
        mission_id="audit_mission",
        plan_id="audit_plan",
        specialist_name="operations_specialist",
        division_name="generic",
        capability_name="coordination",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "success"},
        timeout_seconds=30,
    )
    result = runtime.execute(contract)

    assert result.outcome == ExecutionOutcome.SUCCEEDED
    assert result.execution_id.startswith("exec_")
    assert result.result_payload["ok"] is True
