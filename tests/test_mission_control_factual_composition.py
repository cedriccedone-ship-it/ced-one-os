"""Real producers through one governed composite task; no positive owner mocks."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import causal_snapshot_availability as snapshots
from ced_one.business_divisions.trading import causal_multi_timeframe_context as sources
from ced_one.business_divisions.trading import causal_factual_intelligence_envelope as envelopes
from ced_one.business_divisions.trading import causal_factual_multi_timeframe_context as contexts
from ced_one.business_divisions.trading import factual_market_context_composition as compositions
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control import LocalExecutionRuntime, MissionControlService
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule
from ced_one.mission_control.types import RequestStatus


def policy(decision=PolicyDecision.ALLOW):
    return ExecutionPolicy("test_factual_mission", 1, rules=[PolicyRule(
        "fixed_read_only_profile", 1, 1, decision, division_name="trading",
        specialist_name="factual_market_context_analyst", capability_name="factual_market_context_composition",
        permission_scope="read_only", adapter_name="local", execution_mode="local",
        risk_level="low", impact_level="limited",
    )])


def service(*, configured=None, register=True):
    runtime = LocalExecutionRuntime()
    if register:
        execution.register_factual_market_context_executor(runtime)
    return MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
                                 policy=configured if configured is not None else policy())


def run(payload, *, instance=None, metadata=None):
    return (instance or service()).handle_request(
        "Compose factual market context", business_division="trading", context=payload, metadata=metadata,
    )


@pytest.fixture(scope="module")
def demo():
    path = Path(__file__).parents[1] / "scripts" / "local_factual_market_context.py"
    spec = importlib.util.spec_from_file_location("local_factual_composition_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def payload(demo):
    return demo.synthetic_payload()


@pytest.fixture(scope="module")
def result(payload):
    return run(payload)


def block_unexpected_analysis(monkeypatch):
    calls = []
    real = snapshots.CAUSAL_SNAPSHOT_AVAILABILITY.analyze
    def record(value):
        calls.append(deepcopy(value))
        return real(value)
    monkeypatch.setattr(snapshots.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", record)
    return calls


def assert_failed(result):
    assert result.status == RequestStatus.FAILED and not result.success
    assert result.errors and result.metadata["execution_performed"] is True
    assert result.metadata["task_graph"]["mission_state"] == "failed"


def test_real_mission_returns_fixed_profile_and_complete_trace(payload, result):
    assert result.success and result.status == RequestStatus.COMPLETED, result.errors
    assert (result.division, result.specialist, result.capability) == (
        "trading", "factual_market_context_analyst", "factual_market_context_composition",
    )
    assert result.metadata["execution_performed"] is True
    execution_result = result.metadata["execution_result"]
    assert execution_result["outcome"] == "succeeded" and execution_result["validation_errors"] == []
    assert execution_result["mission_id"] == result.request_id
    body = result.result_payload
    assert set(body) == {"composition", "evidence"}
    evidence = body["evidence"]
    assert set(evidence) == {"sources", "source_context", "factual_envelopes", "factual_context"}
    assert list(evidence["sources"]) == list(contexts.TIMEFRAME_ORDER)
    assert list(evidence["factual_envelopes"]) == list(contexts.TIMEFRAME_ORDER)
    assert sum(len(g) for g in evidence["factual_envelopes"].values()) == 70
    for tf, group in evidence["factual_envelopes"].items():
        assert list(group) == list(contexts.CAPABILITY_ORDER)
        for name, envelope in group.items():
            assert envelope["capability"]["name"] == name
            assert envelope["source_snapshot_id"] == evidence["sources"][tf]["source_snapshot_id"]
            assert envelope["context_id"] == evidence["source_context"]["context_id"]
            assert envelope["provenance"]["controlled_invocation"] is True
            if envelope["factual_availability"] in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}:
                assert envelope["authoritative_result_id"] and envelope["authoritative_result"] is not None
            else:
                assert envelope["factual_availability"] == "UNAVAILABLE"
                assert envelope["factual_envelope_id"] is None
    composition = body["composition"]
    assert len(composition["adjacent_relationships"]) == 60
    assert composition["source_factual_context_id"] == evidence["factual_context"]["factual_context_id"]
    assert composition["evidence"]["source_context_id"] == evidence["source_context"]["context_id"]
    for source in evidence["sources"].values():
        snapshots.validate_source(source)
    sources.validate_source_context(evidence["source_context"])
    for tf, group in evidence["factual_envelopes"].items():
        for envelope in group.values():
            envelopes.validate_factual_envelope(envelope, evidence["source_context"]["timeframes"][tf])
    contexts.validate_factual_context(evidence["factual_context"])
    assert compositions.validate_factual_composition(composition, evidence["factual_context"]) == composition
    graph = result.metadata["task_graph"]
    assert len(graph["tasks"]) == 1 and graph["mission_state"] == "completed"
    events = graph["audit_events"]
    names = [e["event_type"] for e in events]
    ordered = ["REQUEST_RECEIVED", "POLICY_EVALUATED", "PRE_DISPATCH_POLICY", "EXECUTION_STARTED",
               "EXECUTION_RESULT", "TASK_COMPLETED", "MISSION_RESULT"]
    assert [names.index(n) for n in ordered] == sorted(names.index(n) for n in ordered)
    assert all(e["mission_id"] == result.request_id for e in events)
    assert execution_result["result_payload"] == body
    assert payload["timeframe_histories"]["H1"][-1]["timestamp"] == payload["requested_evaluation_timestamp"]


def test_public_validators_run_with_genuine_results(payload, monkeypatch):
    counts = {}
    for module, name in ((snapshots, "validate_source"), (sources, "validate_source_context"),
                         (envelopes, "validate_factual_envelope"), (contexts, "validate_factual_context"),
                         (compositions, "validate_factual_composition")):
        real = getattr(module, name)
        def record(*args, _name=name, _real=real, **kwargs):
            counts[_name] = counts.get(_name, 0) + 1
            return _real(*args, **kwargs)
        monkeypatch.setattr(module, name, record)
    assert run(payload).success
    assert counts["validate_source"] >= 7 and counts["validate_factual_envelope"] >= 70
    assert all(counts[name] >= 1 for name in ("validate_source_context", "validate_factual_context", "validate_factual_composition"))


@pytest.mark.parametrize("decision", list(PolicyDecision))
def test_policy_controls_before_native_invocation(payload, monkeypatch, decision):
    if decision == PolicyDecision.ALLOW:
        configured = ExecutionPolicy("no_matching_allow", 1)  # Unknown policy coverage fails closed.
    else:
        configured = policy(decision)
    calls = block_unexpected_analysis(monkeypatch)
    r = run(payload, instance=service(configured=configured), metadata={"approved": True})
    assert not calls and not r.success and r.metadata["execution_performed"] is False
    assert r.status in {RequestStatus.REJECTED, RequestStatus.AWAITING_APPROVAL}


@pytest.mark.parametrize("mode", ["approval", "missing_executor", "missing_risk", "wrong_policy_scope", "authority_override"])
def test_governance_and_registration_cannot_be_supplied_by_caller(payload, monkeypatch, mode):
    instance = service(register=mode != "missing_executor")
    metadata = {"approved": True, "risk_level": "low", "impact_level": "limited"}
    if mode == "approval": metadata["approval_required"] = True
    elif mode == "authority_override": metadata["authority_override"] = True
    elif mode == "wrong_policy_scope": instance.policy.rules[0].capability_name = "candle_intelligence"
    elif mode == "missing_risk":
        contract = instance.runtime.get_contract("trading", "factual_market_context_composition")
        contract.metadata = {}
        instance.runtime.register(contract, execution.execute_factual_market_context_composition)
    calls = block_unexpected_analysis(monkeypatch)
    r = run(payload, instance=instance, metadata=metadata)
    assert not r.success and not calls and r.metadata["execution_performed"] is False


@pytest.mark.parametrize("field", ["validated_analysis", "approval", "executor", "provenance", "configuration", "factual_context"])
def test_raw_input_rejects_caller_controlled_artifacts(payload, monkeypatch, field):
    value = deepcopy(payload)
    value[field] = {"approved": True}
    calls = block_unexpected_analysis(monkeypatch)
    assert_failed(run(value))
    assert not calls


@pytest.mark.parametrize("mode", ["symbol", "missing_timeframe", "extra_timeframe", "no_timezone", "future_boundary", "missing_history", "extra_candle_fields"])
def test_invalid_execution_input_fails_before_source_production(payload, monkeypatch, mode):
    value = deepcopy(payload)
    if mode == "symbol": value["symbol"] = "EURUSD"
    elif mode == "missing_timeframe": del value["timeframe_histories"]["H1"]
    elif mode == "extra_timeframe": value["timeframe_histories"]["H2"] = []
    elif mode == "no_timezone": value["requested_evaluation_timestamp"] = "2026-09-01T00:00:00"
    elif mode == "future_boundary": value["requested_evaluation_timestamp"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif mode == "missing_history": value["timeframe_histories"]["M1"] = None
    else: value["timeframe_histories"]["M1"][0]["provenance"] = "caller-supplied"
    calls = block_unexpected_analysis(monkeypatch)
    assert_failed(run(value))
    assert not calls


@pytest.mark.parametrize("mode", ["impossible_prices", "duplicate", "future_candle", "boolean_price"])
def test_malformed_sources_fail_before_factual_analysis(payload, monkeypatch, mode):
    value = deepcopy(payload)
    rows = value["timeframe_histories"]["D1"]
    if mode == "impossible_prices": rows[0]["high"] = 1
    elif mode == "duplicate": rows[1]["timestamp"] = rows[0]["timestamp"]
    elif mode == "future_candle": rows[-1]["timestamp"] = "2026-09-02T00:00:00Z"
    else: rows[0]["close"] = True
    calls = []
    real = envelopes.CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze
    def record(value):
        calls.append(1)
        return real(value)
    monkeypatch.setattr(envelopes.CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE, "analyze", record)
    assert_failed(run(value))
    assert not calls


def test_causal_exclusion_input_isolation_and_snapshot_identity(payload, result):
    value = deepcopy(payload)
    before = deepcopy(value)
    for tf, source in result.result_payload["evidence"]["sources"].items():
        assert source["diagnostics"]["approved_candle_count"] == 32
        assert source["diagnostics"]["incomplete_candle_count"] == 1
        assert source["completion_state"] == "INCOMPLETE"
        assert source["effective_causal_cutoff"] == payload["requested_evaluation_timestamp"]
        assert all(c["timestamp"] < payload["requested_evaluation_timestamp"] for c in source["approved_candle_history"])
        value["timeframe_histories"][tf][-1].update(open=9000, high=9999, low=8000, close=8500)
    changed = run(value)
    assert changed.success and value != before and payload == before
    assert changed.result_payload["composition"] == result.result_payload["composition"]
    for tf, source in changed.result_payload["evidence"]["sources"].items():
        assert source["source_snapshot_id"] == result.result_payload["evidence"]["sources"][tf]["source_snapshot_id"]
    assert value["timeframe_histories"]["M1"][-1]["close"] == 8500  # No mutation by the mission.


def test_unavailable_evidence_is_a_valid_degraded_calculation(payload):
    value = deepcopy(payload)
    value["timeframe_histories"]["H1"] = []
    r = run(value)
    assert r.success and r.metadata["execution_result"]["outcome"] == "succeeded"
    body = r.result_payload
    assert body["composition"]["composition_state"] == "UNAVAILABLE"
    assert body["evidence"]["sources"]["H1"]["source_availability"] == "UNAVAILABLE"
    for env in body["evidence"]["factual_envelopes"]["H1"].values():
        assert env["factual_availability"] == "UNAVAILABLE"
        assert env["authoritative_result"] is None and env["factual_envelope_id"] is None
        assert env["provenance"]["controlled_invocation"] is False


@pytest.mark.parametrize("stage", ["source", "source_binding", "source_context", "envelope", "dependency", "factual_context", "composition", "authority"])
def test_native_artifact_tampering_fails_public_validation(payload, monkeypatch, stage):
    if stage in {"source", "source_binding"}:
        owner, target = snapshots.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze"
    elif stage == "source_context": owner, target = sources.CAUSAL_MULTI_TIMEFRAME_CONTEXT, "analyze"
    elif stage in {"envelope", "dependency", "authority"}: owner, target = envelopes.CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE, "analyze"
    elif stage == "factual_context": owner, target = contexts.CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT, "analyze"
    else: owner, target = compositions.FactualMarketContextCompositionAnalyzer, "analyze"
    real = getattr(owner, target)
    calls = 0
    def mutate(*args, **kwargs):
        nonlocal calls
        calls += 1
        if stage == "source_binding":
            return real({**args[0], "timeframe": "H1"})  # Genuine, internally valid wrong-slot source.
        result = real(*args, **kwargs)
        if stage == "source": result.source_snapshot_id = "tampered"
        elif stage == "source_context": result.context_id = "tampered"
        elif stage == "envelope": result.authoritative_result_id = "tampered"
        elif stage == "dependency" and result.capability["name"] == "liquidity_events":
            result.dependency_provenance[0]["source_snapshot_id"] = "wrong-source"
        elif stage == "factual_context": result.factual_context_id = "tampered"
        elif stage == "composition" and calls == 1:
            # Corrupt the delivered artifact; leave the owner's independent
            # reconstruction intact rather than corrupting both sides.
            result.adjacent_relationships[0]["relationship_type"] = "INVENTED"
        elif stage == "authority": result.metadata["execution_output"] = 0
        return result
    monkeypatch.setattr(owner, target, mutate)
    assert_failed(run(payload))


def test_native_invocation_failure_does_not_become_success(payload, monkeypatch):
    adapter = envelopes.ADAPTERS["trading.candle_intelligence.v1"]
    def fail(*args, **kwargs):
        raise ValueError("injected factual invocation failure")
    monkeypatch.setitem(envelopes.ADAPTERS, adapter.contract, replace(adapter, invoke=fail))
    assert_failed(run(payload))


def test_registration_is_fixed_read_only_and_both_executors_coexist(payload):
    instance = service()
    execution.register_candle_executor(instance.runtime)
    contract = instance.runtime.get_contract("trading", "factual_market_context_composition")
    assert contract.permission_scope == "read_only" and contract.retryable is False
    assert contract.metadata["timeframe_order"] == list(contexts.TIMEFRAME_ORDER)
    assert contract.metadata["capability_order"] == list(contexts.CAPABILITY_ORDER)
    assert contract.metadata["configuration"] == "native_defaults"
    configured = ExecutionPolicy("only_candles", 1, rules=[PolicyRule(
        "candles", 1, 1, PolicyDecision.ALLOW, division_name="trading", specialist_name="candle_analyst",
        capability_name="candle_intelligence", permission_scope="read_only", execution_mode="local",
        risk_level="low", impact_level="limited",
    )])
    instance.policy = configured
    result = instance.handle_request("candle intelligence", business_division="trading", context={
        "symbol": "XAUUSD", "timeframe": "H1", "evaluation_time": payload["requested_evaluation_timestamp"],
        "candle_history": payload["timeframe_histories"]["H1"],
    })
    assert result.success and result.result_payload["provenance"]["approved_candle_count"] == 32


def test_observation_only_native_authority_and_no_trading_permission(result):
    body = result.result_payload
    evidence = body["evidence"]
    artifacts = [body["composition"], evidence["source_context"], evidence["factual_context"],
                 *evidence["sources"].values(),
                 *(env for group in evidence["factual_envelopes"].values() for env in group.values())]
    for artifact in artifacts:
        assert artifact["metadata"]["authority_scope"] == "read_only"
        assert artifact["metadata"]["observation_only"] is True
        assert all(artifact["metadata"][k] is False for k in ("advisory_output", "strategy_output", "execution_output"))
    for forbidden in ("trade_authorized", "order_placement", "broker_instruction", "risk_approved", "margin_approved"):
        assert forbidden not in json.dumps(body)


def test_runnable_demo_uses_mission_control_and_reports_separate_states(demo, capsys):
    demo.main()
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "completed" and value["execution_outcome"] == "succeeded"
    assert value["composition_state"] in {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "NOT_EVALUATED"}
    assert value["factual_envelope_count"] == 70 and value["relationship_count"] == 60
    assert value["validation_errors"] == []
    assert value["audit_events"][-1]["event_type"] == "MISSION_RESULT"
    assert value["audit_reference"] == value["mission_id"]
    assert "No trading or financial-risk approval" in value["interpretation"]
