from datetime import datetime, timezone
from ced_one.mission_control.policy import RiskImpactClassification
from copy import deepcopy
from datetime import datetime, timezone
import pytest

from ced_one.mission_control import MissionControlService, MissionControlFlow, MissionControlOrchestrator
from ced_one.mission_control.governance import PolicyEvaluationContext, AuthorizationSnapshot, ExecutionGovernanceGate
from ced_one.mission_control.policy import ExecutionPolicy, PolicyRule, PolicyDecision
from ced_one.mission_control.runtime import LocalExecutionRuntime, CapabilityExecutionContract, MissionExecutionDispatcher
from ced_one.mission_control.tasks import MissionTask, MissionTaskGraph, TaskLifecycleState as S
from ced_one.mission_control.types import ApprovalState, RequestStatus
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.execution import register_candle_executor


def policy():
    return ExecutionPolicy("local_candles", 1, rules=[PolicyRule("candles", 1, 1, PolicyDecision.ALLOW,
        division_name="trading", capability_name="candle_intelligence", permission_scope="read_only", execution_mode="local", risk_level="low", impact_level="limited")])


def payload():
    return {"symbol": "XAUUSD", "timeframe": "H1", "evaluation_time": "2026-09-01T02:30:00Z",
        "candle_history": [dict(timestamp=f"2026-09-01T{hour:02}:00:00Z", open=100, high=104, low=99, close=103 if hour < 2 else 99) for hour in range(3)]}


def context():
    return PolicyEvaluationContext("t", "m", S.ASSIGNED, ApprovalState.NOT_REQUIRED, "trading", "candle_analyst", "candle_intelligence", "local", permission_scope="read_only", adapter_type="local", risk_impact_classification=RiskImpactClassification("test", "1", datetime(2026, 1, 1, tzinfo=timezone.utc), "low", "limited"), task_context={"input_payload": {"value": 1}})


@pytest.mark.parametrize("cls", [MissionControlService, MissionControlFlow, MissionControlOrchestrator])
def test_all_entrypoints_execute_real_causal_analysis(cls):
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    service = cls({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy())
    result = service.handle_request("candle intelligence", business_division="trading", context=payload())
    assert result.status == RequestStatus.COMPLETED, result.errors
    assert result.success and result.metadata["execution_performed"]
    assert result.result_payload["candle_direction"] == "bullish"
    assert result.result_payload["timestamp"] == "2026-09-01T01:00:00Z"
    assert result.result_payload["provenance"]["approved_candle_count"] == 2
    assert result.result_payload["provenance"]["source_snapshot_id"].startswith("causal_snapshot_")
    assert result.metadata["task_graph"]["mission_state"] == "completed"
    assert service.execution_history == [result]


def test_missing_executor_and_default_deny_never_report_success():
    service = MissionControlService({"trading": TradingDivisionResolver()})
    result = service.handle_request("candle intelligence", business_division="trading", context=payload())
    assert result.status == RequestStatus.UNSUPPORTED
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime)
    result = service.handle_request("candle intelligence", business_division="trading", context=payload())
    assert result.status == RequestStatus.REJECTED
    assert not result.success and not result.metadata["execution_performed"]


@pytest.mark.parametrize("decision", [PolicyDecision.DENY, PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.ESCALATE])
def test_policy_blocks_executor_calls(decision):
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    calls = []
    runtime.register(runtime.get_contract("trading", "candle_intelligence"), lambda req: calls.append(req))
    configured = policy()
    configured.rules[0].decision = decision
    result = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=configured).handle_request("candle intelligence", business_division="trading", context=payload(), metadata={"approved": True})
    assert not calls and not result.success and not result.metadata["execution_performed"]


@pytest.mark.parametrize("field", ["division_binding", "specialist_binding", "capability_binding", "adapter_binding", "task_id", "permission_scope", "risk_impact_classification"])
def test_missing_context_denies_even_with_allow_default(field):
    current = context()
    setattr(current, field, None)
    result = ExecutionGovernanceGate().evaluate(current, policy=ExecutionPolicy("p", 1, default_decision=PolicyDecision.ALLOW))
    assert result.decision == PolicyDecision.DENY


def test_bounded_rule_does_not_match_missing_division():
    current = context()
    current.division_binding = None
    assert not policy().rules[0].matches_context(current)


@pytest.mark.parametrize("field,value", [("connector_binding", "changed"), ("connector_version", "2"), ("adapter_type", "tool"), ("permission_scope", "admin"), ("task_context", {"input_payload": {"value": 2}})])
def test_fingerprint_and_snapshot_detect_context_drift(field, value):
    current = context()
    snapshot = AuthorizationSnapshot.from_context(current)
    fingerprint = current.fingerprint
    setattr(current, field, value)
    assert fingerprint != current.fingerprint
    assert not snapshot.is_still_valid(current)


def test_snapshot_owns_its_nested_context_and_classification():
    current = context()
    snapshot = AuthorizationSnapshot.from_context(current)
    current.risk_impact_classification.classification_context["new"] = True
    current.task_context["input_payload"]["value"] = 5
    assert not snapshot.is_still_valid(current)
    assert snapshot.task_context["input_payload"]["value"] == 1


def test_dispatch_rechecks_input_and_policy_after_authorization():
    runtime = LocalExecutionRuntime()
    calls = []
    contract = CapabilityExecutionContract("candle_intelligence", "trading", "test", permission_scope="read_only")
    runtime.register(contract, lambda req: calls.append(req) or {})
    task = MissionTask("t", "m", "p", "candle", "test", division_name="trading", specialist_name="candle_analyst", capability_name="candle_intelligence", permission_scope="read_only", task_state=S.ASSIGNED)
    current = context()
    current.policy_id = "local_candles"
    current.task_context["capability_contract"] = contract.to_dict()
    current.task_context["registration_id"] = runtime.get_registration("trading", "candle_intelligence").registration_id
    current.task_context["execution_context"] = {}
    snapshot = AuthorizationSnapshot.from_context(current)
    dispatcher = MissionExecutionDispatcher({"trading": object()}, runtime)
    kwargs = dict(task=task, assignment={"name": "candle_analyst"}, capability_contract=contract, authorization_context=current, authorization_snapshot=snapshot)
    result = dispatcher.dispatch(**kwargs, policy=policy(), input_payload={"value": 2})
    assert result.runtime_metadata["dispatch_rejected"] and not calls
    changed_policy = policy()
    changed_policy.rules[0].decision = PolicyDecision.DENY
    result = dispatcher.dispatch(**kwargs, policy=changed_policy, input_payload={"value": 1})
    assert result.runtime_metadata["dispatch_rejected"] and not calls


@pytest.mark.parametrize("state", [S.COMPLETED, S.CANCELLED, S.REJECTED])
def test_terminal_tasks_cannot_restart_or_change_approval(state):
    task = MissionTask("t", "m", "p", "test", "test", task_state=state)
    before = task.to_dict()
    with pytest.raises(ValueError):
        task.transition_to(S.IN_PROGRESS, approval_state=ApprovalState.APPROVED)
    assert task.to_dict() == before


def test_retry_budget_and_atomic_transition():
    task = MissionTask("t", "m", "p", "test", "test", task_state=S.FAILED, max_retries=1)
    task.transition_to(S.RETRY_PENDING)
    assert task.retry_count == 1
    task.transition_to(S.READY)
    before = task.to_dict()
    with pytest.raises(ValueError):
        task.transition_to(S.ASSIGNED, approval_state=ApprovalState.PENDING)
    assert task.to_dict() == before
    task.transition_to(S.ASSIGNED)
    task.transition_to(S.IN_PROGRESS)
    task.transition_to(S.FAILED)
    with pytest.raises(ValueError):
        task.transition_to(S.RETRY_PENDING)


def test_dependency_failure_reaches_all_descendants_and_blocks_readiness():
    tasks = {name: MissionTask(name, "m", "p", name, name, dependencies=deps) for name, deps in [("a", []), ("b", ["a"]), ("c", ["b"])]}
    graph = MissionTaskGraph("m", "p", tasks)
    with pytest.raises(ValueError):
        graph.transition_task("b", S.READY)
    assert graph.propagate_failure("a", reason="failed") == ["b", "c"]
    assert all(tasks[name].terminally_prevented for name in ("b", "c"))
    with pytest.raises(ValueError):
        graph.transition_task("c", S.READY)


def test_absent_classification_is_not_implicitly_low_risk():
    current = PolicyEvaluationContext("t", "m", S.READY, ApprovalState.NOT_REQUIRED, "trading", "s", "c", "local")
    assert current.risk_impact_classification is None
    result = ExecutionGovernanceGate().evaluate(current, policy=ExecutionPolicy("p", 1, default_decision=PolicyDecision.ALLOW))
    assert result.decision == PolicyDecision.DENY


def test_audit_orders_reauthorization_execution_and_completion():
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    result = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy()).handle_request("candle intelligence", business_division="trading", context=payload())
    events = result.metadata["task_graph"]["audit_events"]
    names = [event["event_type"] for event in events]
    assert names.index("PRE_DISPATCH_POLICY") < names.index("EXECUTION_STARTED") < names.index("EXECUTION_RESULT") < names.index("TASK_COMPLETED")
    assert events[names.index("PRE_DISPATCH_POLICY")]["details"]["context_fingerprint"]


@pytest.mark.parametrize("mode", ["invalid_output", "exception", "cancelled", "timed_out"])
def test_service_failure_and_cancellation_paths(mode):
    from ced_one.mission_control.runtime import ExecutionOutcome
    calls = []
    class InjectedRuntime(LocalExecutionRuntime):
        def execute(self, contract):
            result = super().execute(contract)
            if mode in {"cancelled", "timed_out"}:
                result.outcome = ExecutionOutcome.CANCELLED if mode == "cancelled" else ExecutionOutcome.TIMED_OUT
                result.failure_reason = mode
            return result
    def executor(req):
        calls.append(req)
        if mode == "exception":
            raise RuntimeError("injected failure")
        return {}
    runtime = InjectedRuntime()
    register_candle_executor(runtime)
    runtime.register(runtime.get_contract("trading", "candle_intelligence"), executor)
    result = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy()).handle_request("candle intelligence", business_division="trading", context=payload())
    assert len(calls) == 1
    assert result.status == (RequestStatus.CANCELLED if mode == "cancelled" else RequestStatus.FAILED)
    assert result.metadata["execution_performed"] and not result.success
    task = next(iter(result.metadata["task_graph"]["tasks"].values()))
    assert task["task_state"] == ("cancelled" if mode == "cancelled" else "failed")
    assert result.metadata["task_graph"]["mission_state"] == task["task_state"]


def test_non_retryable_failure_cannot_retry():
    task = MissionTask("t", "m", "p", "test", "test", task_state=S.FAILED, retryable=False)
    with pytest.raises(ValueError, match="not retryable"):
        task.transition_to(S.RETRY_PENDING)
    assert task.retry_count == 0 and task.task_state == S.FAILED


def test_fingerprint_is_stable_across_python_processes():
    import subprocess
    import sys
    script = "from tests.test_execution_guarantees import context; print(context().fingerprint)"
    first = subprocess.check_output([sys.executable, "-c", script], text=True)
    second = subprocess.check_output([sys.executable, "-c", script], text=True)
    assert first == second


@pytest.mark.parametrize("metadata", [None, [], {}, {"risk_level": "low"}, {"impact_level": "limited"},
    {"risk_level": None, "impact_level": "limited"}, {"risk_level": "low", "impact_level": None},
    {"risk_level": " ", "impact_level": "limited"}, {"risk_level": "low", "impact_level": ""},
    {"risk_level": 1, "impact_level": "limited"}, {"risk_level": "low", "impact_level": []}])
def test_service_denies_missing_or_invalid_owner_classification(metadata):
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    contract = runtime.get_contract("trading", "candle_intelligence")
    contract.metadata = metadata
    calls = []
    runtime.register(contract, lambda req: calls.append(req) or {})
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=ExecutionPolicy("allow_default", 1, default_decision=PolicyDecision.ALLOW))
    result = service.handle_request("candle intelligence", business_division="trading", context=payload())
    assert calls == []
    assert result.status == RequestStatus.REJECTED
    assert result.metadata["policy_decision"]["decision"] == PolicyDecision.DENY
    assert result.metadata["execution_performed"] is False
    task = next(iter(result.metadata["task_graph"]["tasks"].values()))
    assert task["task_state"] == "rejected"
    assert task["approval_state"] == "not_required"
    changes = [event["details"] for event in result.metadata["task_graph"]["audit_events"] if event["event_type"] == "TASK_STATE_CHANGED"]
    assert [(change["previous_state"], change["resulting_state"]) for change in changes] == [("pending", "rejected")]


def test_service_selection_cannot_be_replaced_before_dispatch():
    from contextlib import contextmanager
    calls = []
    class ReplacingRuntime(LocalExecutionRuntime):
        @contextmanager
        def reserve_registration(self, division, capability, registration_id):
            self.register(self.get_contract(division, capability), lambda req: calls.append("replacement") or {})
            with super().reserve_registration(division, capability, registration_id) as selected:
                yield selected
    runtime = ReplacingRuntime()
    register_candle_executor(runtime)
    runtime.register(runtime.get_contract("trading", "candle_intelligence"), lambda req: calls.append("original") or {})
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy())
    result = service.handle_request("candle intelligence", business_division="trading", context=payload())
    assert calls == []
    assert result.status == RequestStatus.REJECTED
    assert result.metadata["execution_performed"] is False
    assert "stale" in str(result.metadata["execution_result"]["validation_errors"])


def test_snapshot_does_not_manufacture_missing_classification():
    current = context()
    values = {name: deepcopy(getattr(current, name)) for name in AuthorizationSnapshot.__dataclass_fields__}
    values["risk_impact_classification"] = None
    snapshot = AuthorizationSnapshot(**values)
    assert snapshot.risk_impact_classification is None
    assert snapshot.to_context().risk_impact_classification is None
