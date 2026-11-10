"""Real archived producers and public native replay under fresh governance."""
from copy import deepcopy
import json
import os
import subprocess
import sys

import pytest

from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as candidates
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import LocalExecutionRuntime, MissionControlService
from ced_one.mission_control.governance import AuthorizationSnapshot
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision
from ced_one.mission_control.types import MissionRequest, RequestStatus
from tests.test_mission_context_selection import policy, selection
from tests.test_xauusd_causal_liquidity_reversal import scenario, ts


CAPABILITY = execution.STRATEGY_REPLAY_CAPABILITY


@pytest.fixture(scope="module")
def source_factory(tmp_path_factory):
    cache = {}

    def build(direction="LONG", *, unavailable=False, later_changed=False):
        key = direction, unavailable, later_changed
        if key in cache:
            return cache[key]
        definition, histories = scenario(direction)
        if later_changed:
            for tf, rows in histories.items():
                for row in rows:
                    if strategy.parse_timestamp(row["timestamp"]) >= strategy.parse_timestamp(ts(31)):
                        row.update(open=200., high=205., low=195., close=201.)
        # Supply the historical raw prefix, as required by the real source owner.
        # The owner separately excludes the unfinished candle opening at/before T.
        histories = {tf: [row for row in rows if strategy.parse_timestamp(row["timestamp"]) <= strategy.parse_timestamp(ts(31))]
                     for tf, rows in histories.items()}
        histories.update(D1=[], M30=[])
        if unavailable:
            histories["M1"] = []
        runtime = LocalExecutionRuntime()
        execution.register_factual_market_context_executor(runtime)
        store = SQLiteMissionArchive(tmp_path_factory.mktemp("strategy-source") / "missions.sqlite3")
        service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy(), archive=store)
        result = service.handle_request("Compose factual market context", business_division="trading", context={
            "symbol": "XAUUSD", "requested_evaluation_timestamp": ts(31), "timeframe_histories": histories,
        })
        assert result.success and result.metadata["archive"] == {"status": "stored"}, result.metadata.get("execution_result", result.errors)
        cache[key] = store, store.get(result.request_id), definition
        return cache[key]
    return build


def service(store, definition, *, configured=True, register=True, ordinal=0, seconds=120):
    runtime = LocalExecutionRuntime()
    if register:
        execution.register_governed_strategy_candidate_replay_executor(runtime, strategy_definition=definition,
            setup_ordinal=ordinal, entry_validity_duration_seconds=seconds)
    return MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=policy(CAPABILITY) if configured else None, archive=store)


def run(instance, record, **kwargs):
    return instance.handle_request("Governed strategy candidate replay", business_division="trading",
        archive_selection=selection(record), **kwargs)


@pytest.fixture(scope="module")
def completed(source_factory):
    store, record, definition = source_factory()
    result = run(service(store, definition), record)
    assert result.success, result.errors
    assert result.result_payload["outcome"] == "CANDIDATE_FORMULATED"
    return store, record, definition, result


def test_real_historical_candidate_with_native_reconstruction(completed):
    store, record, _, result = completed
    body = result.result_payload
    candidate = body["candidate"]
    assert candidate["direction"] == "LONG"
    assert candidate["entry_reference"]["value"] == 124.
    assert candidate["stop_reference"]["value"] == 107.
    assert candidate["valid_from"] == ts(31) and candidate["valid_until"] == ts(33)
    reconstruction = body["reconstruction"]
    assert strategy.validate_strategy_assessment(body["strategy_assessment"], reconstruction["assessment_input"]) == body["strategy_assessment"]
    assert candidates.validate_technical_candidate_formulation(body["candidate_formulation"], reconstruction["candidate_input"]) == body["candidate_formulation"]
    assert body["candidate_formulation"]["candidate"] == candidate
    assert set(reconstruction["assessment_input"]["sources"]) == set(strategy.TIMEFRAMES)
    assert body["provenance"]["evaluation_time"] == ts(31)
    original = record.result.result_payload["evidence"]["sources"]
    assert body["provenance"]["source_snapshot_ids"] == {tf: s["source_snapshot_id"] for tf, s in original.items()}
    for tf in strategy.TIMEFRAMES:
        assert reconstruction["assessment_input"]["sources"][tf] == original[tf]
    assert original["D1"]["source_availability"] == "UNAVAILABLE"  # Not a Strategy #1 dependency.
    assert result.metadata["archive"] == {"status": "stored"}
    assert store.get(result.request_id).result == result
    events = result.metadata["task_graph"]["audit_events"]
    for name in ("ARCHIVED_CONTEXT_SELECTED", "ARCHIVED_CONTEXT_USED"):
        event = next(e for e in events if e["event_type"] == name)
        assert event["mission_id"] == result.request_id != record.mission_id
        assert event["details"] == body["provenance"]["source_selection"]


def test_no_new_financial_or_execution_authority(completed):
    body = completed[-1].result_payload
    for item in (body, body["strategy_assessment"], body["action_formulation"], body["candidate_formulation"], body["candidate"]):
        assert item["execution"] is False
        assert all(value is False for value in item["authority"].values())
    assert len(body["authority"]) == 7
    assert body["metadata"]["candidate_scope"] == "HISTORICAL_TECHNICAL_REFERENCE_ONLY"
    for field in ("quantity", "fill_price", "pnl", "trade_authorized", "broker_instruction"):
        assert field not in body["candidate"]


def test_no_lookahead_preserves_native_result_when_future_prices_change(source_factory, completed):
    store, record, definition = source_factory(later_changed=True)
    assert record.request.context["timeframe_histories"]["M1"] != completed[1].request.context["timeframe_histories"]["M1"]
    result = run(service(store, definition), record)
    assert result.success, result.errors
    original = completed[-1].result_payload
    assert result.result_payload["strategy_assessment"] == original["strategy_assessment"]
    assert result.result_payload["candidate"] == original["candidate"]
    assert result.result_payload["provenance"]["strategy_source_snapshot_ids"] == original["provenance"]["strategy_source_snapshot_ids"]


def test_real_short_producer_chain(source_factory):
    store, record, definition = source_factory("SHORT")
    result = run(service(store, definition), record)
    assert result.success, result.errors
    assert result.result_payload["candidate"]["direction"] == "SHORT"
    assert result.result_payload["candidate"]["entry_reference"]["value"] == 176.
    assert result.result_payload["candidate"]["stop_reference"]["value"] == 193.


@pytest.mark.parametrize("case,expected", [("waiting", "WAITING"), ("gap", "UNKNOWN"), ("unavailable", "UNAVAILABLE")])
def test_insufficient_evidence_is_not_a_candidate(source_factory, case, expected):
    store, record, definition = source_factory(unavailable=case == "unavailable")
    definition = deepcopy(definition)
    if case == "gap":
        definition["configuration"]["history_starts"]["M1"] = ts(-4)
    result = run(service(store, definition, ordinal=1 if case == "waiting" else 0), record)
    assert result.success, result.errors
    body = result.result_payload
    assert body["outcome"] == expected
    assert body["candidate"] is body["candidate_formulation"] is None
    assert body["reconstruction"]["candidate_input"] is None
    assert body["action_formulation"]["formulation_status"] == "NOT_FORMULATED"
    assert body["execution"] is False


@pytest.mark.parametrize("decision", [None, PolicyDecision.DENY, PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.ESCALATE])
def test_governance_precedes_every_native_analyzer(source_factory, monkeypatch, decision):
    store, record, definition = source_factory()
    instance = service(store, definition, configured=decision is not None)
    if decision is not None:
        instance.policy = policy(CAPABILITY, decision)
    def forbidden(*args, **kwargs):
        raise AssertionError("native analysis before authorization")
    monkeypatch.setattr(execution, "_validated_archived_composition", forbidden)
    monkeypatch.setattr(strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL, "analyze", forbidden)
    result = run(instance, record, metadata={"approved": True, "policy_decision": "ALLOW"})
    assert not result.success and result.metadata["execution_performed"] is False
    assert result.status in (RequestStatus.REJECTED, RequestStatus.AWAITING_APPROVAL)


def test_missing_registration_and_direct_payload_fail_closed(source_factory):
    store, record, definition = source_factory()
    result = run(service(store, definition, register=False), record)
    assert result.status is RequestStatus.UNSUPPORTED and not result.metadata["execution_performed"]
    instance = service(store, definition)
    projection = instance.select_archived_context(selection(record))
    for arguments in ({"context": projection}, {"context": projection, "archive_selection": selection(record)}):
        result = instance.handle_request("Governed strategy candidate replay", business_division="trading", **arguments)
        assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]


@pytest.mark.parametrize("field,value", [("mission_id", "missing"), ("record_sha256", "0" * 64),
    ("division", "other"), ("capability", CAPABILITY), ("contract_id", "other"),
    ("rule_version", "old"), ("evaluation_time", ts(30)), ("created_not_after", ts(0))])
def test_wrong_archive_selection_never_invokes_executor(source_factory, monkeypatch, field, value):
    store, record, definition = source_factory()
    criteria = selection(record); criteria[field] = value
    def forbidden(*args, **kwargs): raise AssertionError("bad selection reached executor")
    monkeypatch.setattr(execution, "execute_governed_strategy_candidate_replay", forbidden)
    result = service(store, definition).handle_request("Governed strategy candidate replay", business_division="trading", archive_selection=criteria)
    assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]


@pytest.mark.parametrize("change", ["source_version", "source_identity", "source_time", "source_slot", "missing_source", "composition_identity"])
def test_rehashed_archive_still_requires_original_native_evidence(source_factory, tmp_path, monkeypatch, change):
    _, record, definition = source_factory()
    request, result = deepcopy(record.request), deepcopy(record.result)
    sources = result.result_payload["evidence"]["sources"]
    if change == "source_version": sources["M1"]["metadata"]["rule_version"] = "old"
    elif change == "source_identity": sources["M1"]["source_snapshot_id"] = "forged"
    elif change == "source_time": sources["M1"]["requested_evaluation_timestamp"] = ts(32)
    elif change == "source_slot": sources["M1"] = deepcopy(sources["M5"])
    elif change == "missing_source": del sources["H4"]
    else: result.result_payload["composition"]["composition_id"] = "forged"
    store = SQLiteMissionArchive(tmp_path / "tampered.sqlite3")
    store.save(request, result, record.policy)
    forged_record = store.get(record.mission_id)
    assert forged_record.record_sha256 != record.record_sha256
    def forbidden(*args, **kwargs): raise AssertionError("invalid source reached strategy")
    monkeypatch.setattr(strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL, "analyze", forbidden)
    result = run(service(store, definition), forged_record)
    assert result.status is RequestStatus.FAILED and not result.success
    assert not any("invalid source reached strategy" in e for e in result.errors)
    assert result.result_payload == {}


@pytest.mark.parametrize("phase", ["first_policy", "after_snapshot", "second_policy"])
@pytest.mark.parametrize("change", ["reference", "evidence_digest"])
def test_mutations_do_not_reuse_authorization(source_factory, monkeypatch, phase, change):
    store, record, definition = source_factory()
    instance = service(store, definition)
    def mutate(context):
        payload = context.task_context["input_payload"]
        if change == "reference": payload["selection"]["record_sha256"] = "0" * 64
        else:
            from ced_one.mission_control.service import _digest
            payload["original_payload"]["extra"] = True
            payload["selection"]["payload_sha256"] = _digest(payload["original_payload"])
    if phase == "after_snapshot":
        original = AuthorizationSnapshot.from_context
        def changed(context):
            snapshot = original(context); mutate(context); return snapshot
        monkeypatch.setattr(AuthorizationSnapshot, "from_context", changed)
    else:
        class MutatingPolicy(ExecutionPolicy):
            calls = 0
            def evaluate_match(self, context):
                matches = super().evaluate_match(context)
                self.calls += 1
                if self.calls == (1 if phase == "first_policy" else 2): mutate(context)
                return matches
        instance.policy = MutatingPolicy(**vars(instance.policy))
    def forbidden(*args, **kwargs): raise AssertionError("mutation reached executor")
    monkeypatch.setattr(instance.runtime, "execute", forbidden)
    result = run(instance, record)
    assert result.status is RequestStatus.REJECTED and not result.metadata["execution_performed"]
    assert result.result_payload == {} and not result.success
    assert any("stale" in e.lower() for e in result.errors)
    assert not any(e["event_type"] == "ARCHIVED_CONTEXT_USED" for e in result.metadata["task_graph"]["audit_events"])


@pytest.mark.parametrize("change", ["profile", "native_version", "hidden_payload"])
def test_final_policy_cannot_replace_authorized_profile_or_view(source_factory, monkeypatch, change):
    store, record, definition = source_factory()
    instance = service(store, definition)
    class MutatingPolicy(ExecutionPolicy):
        calls = 0
        def evaluate_match(self, context):
            matches = super().evaluate_match(context); self.calls += 1
            if self.calls == 2:
                if change == "hidden_payload":
                    original = deepcopy(context.task_context["input_payload"])
                    context.task_context["input_payload"]["selection"]["record_sha256"] = "0" * 64
                    context.task_context["input_payload"] = original
                else:
                    meta = context.task_context["capability_contract"]["metadata"]
                    if change == "profile": meta["replay_profile"]["setup_ordinal"] = 1
                    else: meta["replay_profile"]["native_versions"]["strategy"]["rule_version"] = "old"
                    meta["profile_sha256"] = strategy.identity("", meta["replay_profile"])
            return matches
    instance.policy = MutatingPolicy(**vars(instance.policy))
    def forbidden(*args, **kwargs): raise AssertionError("changed profile reached executor")
    monkeypatch.setattr(instance.runtime, "execute", forbidden)
    result = run(instance, record)
    assert result.status is RequestStatus.REJECTED and not result.metadata["execution_performed"]


def test_profile_is_detached_and_bound_to_registration_and_authorization(source_factory):
    store, record, definition = source_factory()
    supplied = deepcopy(definition)
    instance = service(store, supplied)
    selected = instance.runtime.get_registration("trading", CAPABILITY)
    profile = selected.contract.metadata["replay_profile"]
    supplied["direction"] = "SHORT"
    assert instance.runtime.get_contract("trading", CAPABILITY).metadata["replay_profile"] == profile
    assert profile["strategy_definition"]["direction"] == "LONG"
    assert profile["native_versions"]["strategy"]["rule_version"] == "revision_2.1"
    assert selected.contract.metadata["profile_sha256"] == strategy.identity("", profile)
    assert selected.contract.permission_scope == "read_only" and selected.contract.retryable is False
    request = MissionRequest(user_goal="Governed strategy candidate replay", business_division="trading")
    resolver = TradingDivisionResolver()
    assert resolver.resolve_request(request).capability_name == CAPABILITY
    assert resolver.resolve_capability(request)["contract"] == execution.STRATEGY_REPLAY_CONTRACT
    assert resolver.resolve_specialist(request)["name"] == "factual_market_context_analyst"


def test_native_version_drift_after_registration_fails_before_analysis(source_factory, monkeypatch):
    store, record, definition = source_factory()
    instance = service(store, definition)
    from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as native
    monkeypatch.setattr(native, "RULE_VERSION", "unsupported_upgrade")
    def forbidden(*args, **kwargs): raise AssertionError("version drift reached source replay")
    monkeypatch.setattr(execution, "_validated_archived_composition", forbidden)
    result = run(instance, record)
    assert result.status is RequestStatus.FAILED and not result.success
    assert "native version mismatch" in result.metadata["execution_result"]["failure_reason"]


def test_public_native_validators_are_called_with_original_evidence(source_factory, monkeypatch):
    from ced_one.business_divisions.trading import causal_snapshot_availability as sources
    from ced_one.business_divisions.trading import causal_multi_timeframe_context as contexts
    from ced_one.business_divisions.trading import causal_factual_intelligence_envelope as envelopes
    from ced_one.business_divisions.trading import causal_factual_multi_timeframe_context as factual
    from ced_one.business_divisions.trading import factual_market_context_composition as composition
    store, record, definition = source_factory()
    calls = {}
    for owner, name in [(sources, "validate_source"), (contexts, "validate_source_context"),
        (envelopes, "validate_factual_envelope"), (factual, "validate_factual_context"),
        (composition, "validate_factual_composition"), (strategy, "validate_strategy_assessment"),
        (candidates, "validate_technical_candidate_formulation")]:
        original = getattr(owner, name)
        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] = calls.get(_name, 0) + 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(owner, name, counted)
    result = run(service(store, definition), record)
    assert result.success, result.errors
    assert len(calls) == 7 and all(n >= 1 for n in calls.values())
    assert calls["validate_source"] >= 7 and calls["validate_factual_envelope"] >= 70


@pytest.mark.parametrize("field,value", [("setup_ordinal", True), ("setup_ordinal", -1),
    ("entry_validity_duration_seconds", True), ("entry_validity_duration_seconds", 0),
    ("entry_validity_duration_seconds", 10**20)])
def test_profile_requires_explicit_supported_values(field, value):
    definition, _ = scenario()
    kwargs = dict(strategy_definition=definition, setup_ordinal=0, entry_validity_duration_seconds=120)
    kwargs[field] = value
    with pytest.raises(ValueError): execution.register_governed_strategy_candidate_replay_executor(LocalExecutionRuntime(), **kwargs)


def test_recovery_in_fresh_process_does_not_reexecute_or_authorize(completed):
    store, _, _, result = completed
    code = '''
import json, sys
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
def forbidden(*a, **k): raise AssertionError("archive recovery executed")
LocalExecutionRuntime.execute = forbidden
service = MissionControlService(archive=SQLiteMissionArchive(sys.argv[1]))
record = service.get_archived_mission(sys.argv[2])
assert service.execution_history == []
assert record.temporal_scope == "HISTORICAL_RECORD_ONLY"
print(json.dumps({"hash": record.record_sha256, "candidate": record.result.result_payload["candidate"], "authority": record.result.result_payload["authority"]}))
'''
    process = subprocess.run([sys.executable, "-B", "-c", code, str(store.path), result.request_id],
        capture_output=True, text=True, timeout=20, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert process.returncode == 0, process.stderr
    recovered = json.loads(process.stdout)
    assert recovered["hash"] == store.get(result.request_id).record_sha256
    assert recovered["candidate"] == result.result_payload["candidate"]
    assert all(v is False for v in recovered["authority"].values())


def test_native_candidate_validator_rejects_rehashed_boolean_mutation(completed):
    body = completed[-1].result_payload
    changed = deepcopy(body["candidate_formulation"])
    changed["candidate"]["authority"]["execution"] = 0
    changed["candidate"]["candidate_identity"] = strategy.identity("technical_candidate_", {
        k: v for k, v in changed["candidate"].items() if k != "candidate_identity"})
    with pytest.raises(ValueError):
        candidates.validate_technical_candidate_formulation(changed, body["reconstruction"]["candidate_input"])
