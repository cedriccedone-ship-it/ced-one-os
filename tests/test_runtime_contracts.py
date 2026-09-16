from datetime import datetime, timezone
from ced_one.mission_control.policy import RiskImpactClassification
import pytest

from ced_one.mission_control.runtime import (
    CapabilityExecutionContract, ExecutionOutcome, LocalExecutionRuntime,
    MissionExecutionDispatcher,
)
from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState


def setup_dispatch(executor=lambda request: {"ok": True}):
    contract = CapabilityExecutionContract("observe", "generic", "observe.v1", input_schema={"required_fields": ["value"]}, output_schema={"required_fields": ["ok"]})
    runtime = LocalExecutionRuntime()
    runtime.register(contract, executor)
    task = MissionTask("t", "m", "p", "observe", "test", division_name="generic", specialist_name="observer", capability_name="observe", task_state=TaskLifecycleState.READY, metadata={"input_payload": {"value": 1}})
    return MissionExecutionDispatcher({"generic": object()}, runtime), task, contract


def authorized_kwargs(dispatcher, task, contract, **kwargs):
    from ced_one.mission_control.governance import AuthorizationSnapshot, PolicyEvaluationContext
    from ced_one.mission_control.policy import ExecutionPolicy, PolicyRule, PolicyDecision
    payload = kwargs.get("input_payload", task.metadata.get("input_payload", {}))
    context = PolicyEvaluationContext(task.task_id, task.mission_id, task.task_state, task.approval_state,
        task.division_name, task.specialist_name, task.capability_name, "local",
        risk_impact_classification=RiskImpactClassification("test", "1", datetime(2026, 1, 1, tzinfo=timezone.utc), "low", "limited"), task_context={"input_payload": payload, "capability_contract": contract.to_dict(),
            "registration_id": dispatcher.runtime.get_registration(task.division_name, task.capability_name).registration_id,
            "execution_context": kwargs.get("execution_context") if kwargs.get("execution_context") is not None else {}})
    policy = ExecutionPolicy("policy_default", 1, rules=[PolicyRule("allow", 1, 1, PolicyDecision.ALLOW)])
    return dict(task=task, assignment={"name": "observer", "capability_name": "observe", "permission_scope": "standard"}, capability_contract=contract,
        authorization_snapshot=AuthorizationSnapshot.from_context(context), authorization_context=context, policy=policy, **kwargs)


def dispatch(dispatcher, task, contract, **kwargs):
    return dispatcher.dispatch(**authorized_kwargs(dispatcher, task, contract, **kwargs))


def test_valid_dispatch_serializes_contract_and_uses_explicit_input():
    seen = []
    dispatcher, task, contract = setup_dispatch(lambda request: seen.append(request.input_payload) or {"ok": True})
    assert contract.to_dict()["contract_id"] == "observe.v1"
    assert dispatch(dispatcher, task, contract, input_payload={"value": 2}).outcome == ExecutionOutcome.SUCCEEDED
    assert seen == [{"value": 2}]
    dispatcher, task, contract = setup_dispatch(lambda request: seen.append(request.input_payload) or {"ok": True})
    assert dispatch(dispatcher, task, contract, input_payload={}).outcome == ExecutionOutcome.FAILED
    assert len(seen) == 1


def test_previous_output_cannot_satisfy_input_contract():
    dispatcher, task, contract = setup_dispatch()
    task.metadata.clear()
    task.result_payload = {"value": 3}
    assert dispatch(dispatcher, task, contract).outcome == ExecutionOutcome.FAILED


@pytest.mark.parametrize("field,value", [("name", "wrong"), ("division_name", "wrong"), ("permission_scope", "admin")])
def test_contract_binding_mismatch_blocks_execution(field, value):
    dispatcher, task, contract = setup_dispatch()
    setattr(contract, field, value)
    assert dispatch(dispatcher, task, contract).runtime_metadata["dispatch_rejected"]


def test_invalid_output_and_executor_exception_are_structured_failures():
    dispatcher, task, contract = setup_dispatch(lambda request: {})
    assert dispatch(dispatcher, task, contract).validation_errors
    def broken(request):
        raise RuntimeError("broken")
    dispatcher, task, contract = setup_dispatch(broken)
    result = dispatch(dispatcher, task, contract)
    assert result.outcome == ExecutionOutcome.FAILED
    assert result.failure_reason == "RuntimeError: broken"


def test_public_runtime_exports_exist():
    import ced_one.mission_control as api
    assert all(hasattr(api, name) for name in api.__all__)


def assert_rejected_unchanged(dispatcher, kwargs, calls):
    from copy import deepcopy
    before = deepcopy(kwargs["task"].to_dict())
    result = dispatcher.dispatch(**kwargs)
    assert result.outcome == ExecutionOutcome.FAILED
    assert result.runtime_metadata["dispatch_rejected"]
    assert result.runtime_metadata["execution_performed"] is False
    assert result.validation_errors
    assert calls == []
    assert kwargs["task"].to_dict() == before
    return result


@pytest.mark.parametrize("change", ["executor", "identical", "schema", "classification", "version"])
def test_replaced_registration_cannot_use_old_authorization(change):
    from copy import deepcopy
    calls = []
    original = lambda req: calls.append("original") or {"ok": True}
    dispatcher, task, contract = setup_dispatch(original)
    kwargs = authorized_kwargs(dispatcher, task, contract)
    old_id = kwargs["authorization_context"].task_context["registration_id"]
    replacement = deepcopy(contract)
    if change == "schema":
        replacement.output_schema = {"required_fields": ["new_field"]}
    elif change == "classification":
        replacement.metadata = {"risk_level": "high", "impact_level": "major"}
    elif change == "version":
        replacement.contract_id = "observe.v2"
    executor = original if change == "identical" else lambda req: calls.append("replacement") or {"ok": True}
    dispatcher.runtime.register(replacement, executor)
    assert dispatcher.runtime.get_registration("generic", "observe").registration_id != old_id
    assert_rejected_unchanged(dispatcher, kwargs, calls)


def test_selected_contract_is_isolated_and_compared_in_full():
    calls = []
    dispatcher, task, contract = setup_dispatch(lambda req: calls.append(req) or {"ok": True})
    selected = dispatcher.runtime.get_registration("generic", "observe")
    selected.contract.output_schema["required_fields"].clear()
    assert dispatcher.runtime.get_contract("generic", "observe").output_schema == {"required_fields": ["ok"]}
    contract.output_schema["required_fields"].clear()
    kwargs = authorized_kwargs(dispatcher, task, contract)
    result = assert_rejected_unchanged(dispatcher, kwargs, calls)
    assert "Selected registration contract mismatch." in result.validation_errors


def test_reservation_protects_selection_during_execution_and_releases():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from ced_one.mission_control.runtime import RegistrationError
    entered, finish = Event(), Event()
    calls = []
    def executor(req):
        calls.append("selected")
        entered.set()
        assert finish.wait(5)
        return {"ok": True}
    dispatcher, task, contract = setup_dispatch(executor)
    kwargs = authorized_kwargs(dispatcher, task, contract)
    selected_id = dispatcher.runtime.get_registration("generic", "observe").registration_id
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatcher.dispatch, **kwargs)
        try:
            assert entered.wait(5)
            with pytest.raises(RegistrationError, match="in use"):
                dispatcher.runtime.register(contract, lambda req: calls.append("replacement"))
            assert dispatcher.runtime.get_registration("generic", "observe").registration_id == selected_id
        finally:
            finish.set()
        assert future.result(timeout=5).outcome == ExecutionOutcome.SUCCEEDED
    assert calls == ["selected"]
    dispatcher.runtime.register(contract, lambda req: {"ok": True})
    assert dispatcher.runtime.get_registration("generic", "observe").registration_id != selected_id


@pytest.mark.parametrize("mode", ["rejection", "exception", "invalid_output"])
def test_reservation_released_on_every_exit(mode):
    def executor(req):
        if mode == "exception":
            raise RuntimeError("executor failure")
        return {}
    dispatcher, task, contract = setup_dispatch(executor)
    kwargs = authorized_kwargs(dispatcher, task, contract)
    if mode == "rejection":
        kwargs["input_payload"] = {"value": 2}
    result = dispatcher.dispatch(**kwargs)
    assert result.outcome == ExecutionOutcome.FAILED
    dispatcher.runtime.register(contract, lambda req: {"ok": True})


@pytest.mark.parametrize("change", ["simulate_mode", "attempt_number", "other", "nested"])
def test_execution_context_drift_rejects_dispatch(change):
    calls = []
    dispatcher, task, contract = setup_dispatch(lambda req: calls.append(req) or {"ok": True})
    supplied = {"simulate_mode": "success", "attempt_number": 1, "other": "a", "nested": {"items": [1]}}
    kwargs = authorized_kwargs(dispatcher, task, contract, execution_context=supplied)
    if change == "nested":
        supplied["nested"]["items"].append(2)
    else:
        supplied[change] = "changed"
    assert_rejected_unchanged(dispatcher, kwargs, calls)


def test_captured_nested_context_is_checked_and_executed_without_aliases():
    from copy import deepcopy
    supplied = {"simulate_mode": "success", "attempt_number": 7,
                "nested": {"items": [None, True, 2, 1.5, "text"]}}
    expected = deepcopy(supplied)
    seen = []
    def executor(req):
        seen.append(deepcopy(req.execution_context))
        req.execution_context["nested"]["items"].append("executor")
        return {"ok": True}
    dispatcher, task, contract = setup_dispatch(executor)
    kwargs = authorized_kwargs(dispatcher, task, contract, execution_context=supplied)
    snapshot = kwargs["authorization_snapshot"]
    fingerprint = snapshot.to_context().fingerprint
    class Audit:
        def record(self, event, **details):
            if event == "PRE_DISPATCH_POLICY":
                supplied["nested"]["items"].append("caller")
    kwargs["audit_log"] = Audit()
    result = dispatcher.dispatch(**kwargs)
    assert result.outcome == ExecutionOutcome.SUCCEEDED
    assert seen == [expected]
    assert supplied["nested"]["items"] == expected["nested"]["items"] + ["caller"]
    assert snapshot.task_context["execution_context"] == expected
    assert snapshot.to_context().fingerprint == fingerprint


def cyclic_context():
    value = {}
    value["cycle"] = value
    return value


@pytest.mark.parametrize("bad", [[], "text", 0, False, {1: "value"}, {"value": (1,)},
    {"value": {1}}, {"value": b"bytes"}, {"value": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    {"value": object()}, {"value": float("nan")}, {"value": float("inf")},
    {"value": -float("inf")}, cyclic_context()])
def test_unsupported_execution_context_is_controlled_rejection(bad):
    calls = []
    dispatcher, task, contract = setup_dispatch(lambda req: calls.append(req) or {"ok": True})
    kwargs = authorized_kwargs(dispatcher, task, contract)
    kwargs["execution_context"] = bad
    assert_rejected_unchanged(dispatcher, kwargs, calls)


@pytest.mark.parametrize("target", ["authorization_context", "authorization_snapshot"])
@pytest.mark.parametrize("malformation", ["type", "none_context", "list_context", "classification", "missing_classification", "nested_object", "cycle"])
def test_malformed_authorization_is_rejected_before_task_mutation(target, malformation):
    calls = []
    dispatcher, task, contract = setup_dispatch(lambda req: calls.append(req) or {"ok": True})
    kwargs = authorized_kwargs(dispatcher, task, contract)
    auth = kwargs[target]
    if malformation == "type":
        kwargs[target] = {}
    elif malformation == "none_context":
        auth.task_context = None
    elif malformation == "list_context":
        auth.task_context = []
    elif malformation == "classification":
        auth.risk_impact_classification = {"risk_level": "low"}
    elif malformation == "missing_classification":
        auth.risk_impact_classification = None
    elif malformation == "nested_object":
        auth.task_context["invalid"] = object()
    else:
        auth.task_context["invalid"] = cyclic_context()
    assert_rejected_unchanged(dispatcher, kwargs, calls)


def test_unbound_injected_runtime_has_no_dispatch_fallback():
    calls = []
    dispatcher, task, contract = setup_dispatch()
    kwargs = authorized_kwargs(dispatcher, task, contract)
    class Unbound:
        def execute(self, req):
            calls.append(req)
    dispatcher.runtime = Unbound()
    assert_rejected_unchanged(dispatcher, kwargs, calls)
