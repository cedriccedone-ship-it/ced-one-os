"""Governed variant A research with genuine archived candidates and native replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as candidates
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY, snapshot_identity
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.governance import AuthorizationSnapshot
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision
from ced_one.mission_control.types import RequestStatus
from tests.test_mission_context_selection import policy, selection
from tests.test_mission_control_strategy_candidate_replay import source_factory, service as replay_service, run as replay
from tests.test_xauusd_causal_liquidity_reversal import ts

CAPABILITY = execution.REFERENCE_BACKTEST_CAPABILITY


def stamp(at):
    return at.isoformat().replace("+00:00", "Z")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def criteria(record):
    return dict(mission_id=record.mission_id, record_sha256=record.record_sha256, division="trading",
        capability=execution.STRATEGY_REPLAY_CAPABILITY, contract_id=execution.STRATEGY_REPLAY_CONTRACT,
        rule_version=execution.STRATEGY_REPLAY_RULE, evaluation_time=record.request.context["selection"]["evaluation_time"],
        created_not_after=datetime.now(timezone.utc).isoformat())


@pytest.fixture(scope="module")
def candidate_factory(source_factory):
    cache = {}
    def build(direction="LONG", at=31, ordinal=0):
        key = direction, at, ordinal
        if key not in cache:
            store, original, definition = source_factory(direction)
            if at != 31:
                runtime = LocalExecutionRuntime()
                execution.register_factual_market_context_executor(runtime)
                service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy(), archive=store)
                payload = deepcopy(original.request.context)
                payload["requested_evaluation_timestamp"] = ts(at)
                result = service.handle_request("Compose factual market context", business_division="trading", context=payload)
                assert result.success, result.errors
                original = store.get(result.request_id)
            result = replay(replay_service(store, definition, ordinal=ordinal), original)
            assert result.success and result.metadata["archive"]["status"] == "stored", result.errors
            cache[key] = store, store.get(result.request_id)
        return cache[key]
    return build


def observations(record, case="target"):
    """Synthetic research assumptions, not authenticated historical availability."""
    body = record.result.result_payload
    candidate = body["candidate"]
    start = datetime.fromisoformat(candidate["valid_from"].replace("Z", "+00:00"))
    horizon = start + timedelta(minutes=1440)
    entry = Fraction(repr(candidate["entry_reference"]["value"]))
    risk = abs(entry - Fraction(repr(candidate["stop_reference"]["value"])))
    sign = 1 if candidate["direction"] == "LONG" else -1
    bars = {"target": [(0, 3, -.5, 0)], "stop": [(0, .5, -1, 0)],
        "ambiguous": [(0, 4, -2, 0)], "missing": [], "gap_stop": [(-1.5, .5, -2, 0)],
        "gap_target": [(3.5, 4, -2, 0)], "endpoint": [(0, .5, -.5, 0)],
        "horizon": [(0, .5, -.5, 0)] * 1440}[case]
    rows = [deepcopy(candidate["entry_reference"]["evidence"]["candle"])]
    for i, values in enumerate(bars):
        o, favorable, adverse, close = [float(entry + sign * risk * Fraction(str(v))) for v in values]
        rows.append(dict(timestamp=stamp(start + timedelta(minutes=i)), open=o,
                         high=max(favorable, adverse), low=min(favorable, adverse), close=close))
    m1 = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="M1",
        requested_evaluation_timestamp=stamp(horizon), candle_history=rows)).to_dict()
    formulation, native_input = body["candidate_formulation"], body["reconstruction"]["candidate_input"]
    def source_ref(source):
        return dict(contract=source["metadata"]["contract"], rule_version=source["metadata"]["rule_version"],
            symbol=source["symbol"], timeframe=source["timeframe"], source_snapshot_id=source["source_snapshot_id"],
            full_artifact_sha256=digest(source))
    declaration = dict(contract=reference.DATASET_RELATIONSHIP_CONTRACT, rule_version=reference.RELATIONSHIP_RULE_VERSION,
        declaration_id="synthetic-base", declaration_revision=1, relationship_type=reference.BASE_RELATIONSHIP,
        source_namespace="synthetic-manual-research", dataset_revision="fixture-v1-" + case,
        price_domain="synthetic-reference-prices", available_at=stamp(start),
        subject_bindings=dict(candidate_origin=dict(contract=formulation["contract"], rule_version=formulation["rule_version"],
            candidate_identity=candidate["candidate_identity"], full_artifact_sha256=digest(formulation),
            reconstruction_input_sha256=digest(native_input), original_m1_source=source_ref(formulation["m1_origin_source"]),
            price_references=["entry_reference", "stop_reference"]), m1=source_ref(m1)),
        timeframe_grid_bindings=dict(M1=dict(timeframe="M1", anchor_open=stamp(start), duration_seconds=60)),
        coverage_declarations=dict(M1=dict(requested_start=stamp(start-timedelta(minutes=1)), requested_end=stamp(horizon),
            declared_coverage_start=stamp(start-timedelta(minutes=1)), declared_coverage_end=stamp(horizon),
            dataset_end=stamp(start+timedelta(minutes=1)) if case == "endpoint" else None)),
        declaration_provenance=dict(declarant_namespace="synthetic-fixture", record_id="base-" + case),
        authority=dict(authenticated_source_truth=False, trade_decision=False, financial_risk=False, execution=False))
    return dict(research_boundary=stamp(horizon), m1=m1, declarations=[declaration])


def service(store, profile, decision=PolicyDecision.ALLOW, register=True):
    runtime = LocalExecutionRuntime()
    if register:
        execution.register_governed_reference_backtest_executor(runtime, observation_profile=profile)
    return MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=policy(CAPABILITY, decision) if decision is not None else None, archive=store)


def run(instance, record, **kwargs):
    return instance.handle_request("Governed reference backtest", business_division="trading",
        archive_selection=criteria(record), **kwargs)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("case,status,lower,upper", [("stop", "RESOLVED", -1, -1), ("target", "RESOLVED", 3, 3),
    ("gap_stop", "RESOLVED", Fraction(-3, 2), Fraction(-3, 2)),
    ("gap_target", "RESOLVED", Fraction(7, 2), Fraction(7, 2)),
    ("ambiguous", "AMBIGUOUS", -1, 3), ("missing", "MISSING_DATA_CENSORED", None, None),
    ("endpoint", "END_OF_DATA_UNRESOLVED", None, None), ("horizon", "HORIZON_CENSORED", None, None)])
def test_real_variant_a_and_native_reconstruction(candidate_factory, direction, case, status, lower, upper):
    store, record = candidate_factory(direction)
    profile = observations(record, case)
    result = run(service(store, profile), record)
    assert result.success, result.metadata.get("execution_result", result.errors)
    body = result.result_payload
    assert set(body) == {"outcome", "scenario", "reconstruction", "provenance", "metadata", "authority", "execution"}
    assert body["outcome"] == status
    assert reference.validate_reference_scenario(body["scenario"], body["reconstruction"]) == body["scenario"]
    native = body["scenario"]
    assert native["variant"] == "A" and native["transitions"] == [] and native["final_state"]["stage"] == 0
    if lower is None:
        assert native["reference_result"] is None
    else:
        for key, expected in (("lower_r", lower), ("upper_r", upper)):
            ratio = native["reference_result"][key]
            assert Fraction(ratio["numerator"], ratio["denominator"]) == expected
    assert body["reconstruction"]["evidence"]["m5"] is None
    assert body["provenance"]["candidate_provenance"] == record.result.result_payload["provenance"]
    assert body["provenance"]["source_selection"]["record_sha256"] == record.record_sha256
    assert body["provenance"]["new_mission_id"] == result.request_id != record.mission_id
    assert body["provenance"]["candidate_start"] == body["provenance"]["evaluation_time"] == ts(31)
    for artifact in (body, native):
        assert artifact["execution"] is False and all(v is False for v in artifact["authority"].values())
    assert len(body["authority"]) == 7
    assert result.metadata["archive"] == {"status": "stored"}
    assert store.get(result.request_id).result == result
    events = result.metadata["task_graph"]["audit_events"]
    for name in ("ARCHIVED_CONTEXT_SELECTED", "ARCHIVED_CONTEXT_USED"):
        assert next(e["details"] for e in events if e["event_type"] == name) == body["provenance"]["source_selection"]


@pytest.mark.parametrize("decision", [None, PolicyDecision.DENY, PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.ESCALATE])
def test_current_governance_before_native_owners(candidate_factory, monkeypatch, decision):
    store, record = candidate_factory()
    instance = service(store, observations(record), decision)
    def forbidden(*args, **kwargs): raise AssertionError("analysis before governance")
    monkeypatch.setattr(execution, "_validated_reference_candidate", forbidden)
    monkeypatch.setattr(reference, "evaluate_reference_scenario", forbidden)
    result = run(instance, record, metadata={"approved": True, "policy_decision": "ALLOW"})
    assert result.status in (RequestStatus.REJECTED, RequestStatus.AWAITING_APPROVAL)
    assert not result.success and result.metadata["execution_performed"] is False


def test_registration_and_selection_required(candidate_factory):
    store, record = candidate_factory()
    profile = observations(record)
    result = run(service(store, profile, register=False), record)
    assert result.status is RequestStatus.UNSUPPORTED and not result.metadata["execution_performed"]
    instance = service(store, profile)
    projection = instance.select_archived_context(criteria(record))
    assert instance.execution_history == []
    for kwargs in ({"context": projection}, {"context": projection, "archive_selection": criteria(record)}):
        result = instance.handle_request("Governed reference backtest", business_division="trading", **kwargs)
        assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]


@pytest.mark.parametrize("field,value", [("record_sha256", "0"*64), ("mission_id", "absent"), ("evaluation_time", ts(30)),
    ("capability", "other"), ("contract_id", "other"), ("rule_version", "old")])
def test_selection_mismatch_prevents_execution(candidate_factory, monkeypatch, field, value):
    store, record = candidate_factory()
    instance = service(store, observations(record))
    selected = criteria(record); selected[field] = value
    def forbidden(*a, **k): raise AssertionError("bad selection dispatched")
    monkeypatch.setattr(instance.runtime, "execute", forbidden)
    result = instance.handle_request("Governed reference backtest", business_division="trading", archive_selection=selected)
    assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]


@pytest.mark.parametrize("phase", ["first_policy", "after_snapshot", "second_policy"])
@pytest.mark.parametrize("change", ["selection", "observation", "hidden_view"])
def test_context_mutation_never_reuses_authorization(candidate_factory, monkeypatch, phase, change):
    store, record = candidate_factory()
    instance = service(store, observations(record))
    def mutate(context):
        if change == "observation":
            # First policy sees an isolated contract copy. Changing that view
            # cannot change the actual registered observation profile.
            meta = context.task_context["capability_contract"]["metadata"]
            meta["observation_profile"]["declarations"][0]["dataset_revision"] = "mutated"
            meta["profile_sha256"] = digest(meta["observation_profile"])
            if phase == "after_snapshot":
                execution.register_governed_reference_backtest_executor(instance.runtime,
                    observation_profile={k: meta["observation_profile"][k] for k in ("research_boundary", "m1", "declarations")})
        else:
            payload = context.task_context["input_payload"]
            clean = deepcopy(payload)
            payload["selection"]["record_sha256"] = "0"*64
            if change == "hidden_view": context.task_context["input_payload"] = clean
    if phase == "after_snapshot":
        original = AuthorizationSnapshot.from_context
        def changed(context):
            snapshot = original(context); mutate(context); return snapshot
        monkeypatch.setattr(AuthorizationSnapshot, "from_context", changed)
    else:
        class MutatingPolicy(ExecutionPolicy):
            calls = 0
            def evaluate_match(self, context):
                match = super().evaluate_match(context); self.calls += 1
                if self.calls == (1 if phase == "first_policy" else 2): mutate(context)
                return match
        instance.policy = MutatingPolicy(**vars(instance.policy))
    if phase == "first_policy" and change == "observation":
        result = run(instance, record)
        assert result.success
        assert result.result_payload["reconstruction"]["evidence"]["declarations"][0]["dataset_revision"] != "mutated"
    else:
        def forbidden(*a, **k): raise AssertionError("mutated context dispatched")
        monkeypatch.setattr(instance.runtime, "execute", forbidden)
        result = run(instance, record)
        assert result.status is RequestStatus.REJECTED and not result.metadata["execution_performed"]
        assert not any(e["event_type"] == "ARCHIVED_CONTEXT_USED" for e in result.metadata["task_graph"]["audit_events"])


@pytest.mark.parametrize("change", ["version", "identity", "time", "anchor", "ohlc", "relationship", "authority", "declaration_time"])
def test_invalid_observation_fails_in_native_validation(candidate_factory, monkeypatch, change):
    store, record = candidate_factory()
    profile = observations(record)
    if change == "version": profile["m1"]["metadata"]["rule_version"] = "old"
    elif change == "identity": profile["m1"]["source_snapshot_id"] = "forged"
    elif change == "time": profile["research_boundary"] = stamp(datetime.fromisoformat(profile["research_boundary"].replace("Z", "+00:00"))+timedelta(minutes=1))
    elif change == "anchor": profile["m1"]["approved_candle_history"][0]["high"] += 1
    elif change == "ohlc": profile["m1"]["approved_candle_history"][1]["high"] = 1
    elif change == "relationship": profile["declarations"][0]["subject_bindings"]["candidate_origin"]["candidate_identity"] = "forged"
    elif change == "authority": profile["declarations"][0]["authority"]["execution"] = 0
    else: profile["declarations"][0]["available_at"] = stamp(datetime.fromisoformat(profile["research_boundary"].replace("Z", "+00:00"))+timedelta(minutes=1))
    if change in ("anchor", "ohlc"):
        source = profile["m1"]
        source["source_snapshot_id"] = snapshot_identity(source)
        source["evidence"]["source_snapshot_id"] = source["source_snapshot_id"]
        binding = profile["declarations"][0]["subject_bindings"]["m1"]
        binding.update(source_snapshot_id=source["source_snapshot_id"], full_artifact_sha256=digest(source))
    result = run(service(store, profile), record)
    assert result.status is RequestStatus.FAILED and result.result_payload == {}
    if change == "anchor":
        assert "Frozen M1 history" in result.metadata["execution_result"]["failure_reason"]


def test_missing_and_late_relationship_are_uncertainty_not_repaired(candidate_factory):
    store, record = candidate_factory()
    for late in (False, True):
        profile = observations(record)
        if late: profile["declarations"][0]["available_at"] = ts(33)
        else: profile["declarations"] = []
        result = run(service(store, profile), record)
        assert result.success and result.result_payload["outcome"] == "MISSING_DATA_CENSORED"
        assert result.result_payload["scenario"]["completion_reason"] == "MISSING_CANDIDATE_M1_RELATIONSHIP"
        assert result.result_payload["scenario"]["reference_result"] is None


def test_c_equals_t_is_required_and_no_candidate_is_explicit(candidate_factory):
    store, record = candidate_factory(at=32)
    result = run(service(store, observations(record)), record)
    assert result.status is RequestStatus.FAILED
    assert "C = T" in result.metadata["execution_result"]["failure_reason"]
    store, waiting = candidate_factory(ordinal=1)
    result = run(service(store, observations(record)), waiting)
    assert result.status is RequestStatus.FAILED
    assert "NO_CANDIDATE" in result.metadata["execution_result"]["failure_reason"]


def test_profile_detachment_versions_and_no_lookahead(candidate_factory, monkeypatch):
    store, record = candidate_factory()
    first, second = observations(record, "stop"), observations(record, "target")
    instance = service(store, first)
    first["declarations"].clear()
    a, b = run(instance, record), run(service(store, second), record)
    assert a.success and b.success
    assert a.result_payload["scenario"]["reference_result"] != b.result_payload["scenario"]["reference_result"]
    assert a.result_payload["provenance"]["candidate_identity"] == b.result_payload["provenance"]["candidate_identity"]
    assert a.result_payload["reconstruction"]["candidate_formulation"] == b.result_payload["reconstruction"]["candidate_formulation"]
    instance = service(store, second)
    monkeypatch.setattr(reference, "RULE_VERSION", "unsupported_upgrade")
    result = run(instance, record)
    assert result.status is RequestStatus.FAILED and "native version mismatch" in result.metadata["execution_result"]["failure_reason"]


def test_native_validation_calls_and_rehashed_result_rejection(candidate_factory, monkeypatch):
    store, record = candidate_factory()
    counts = {}
    for owner, name in ((reference, "validate_reference_scenario"), (candidates, "validate_technical_candidate_formulation")):
        original = getattr(owner, name)
        def checked(*a, _original=original, _name=name, **k):
            counts[_name] = counts.get(_name, 0)+1
            return _original(*a, **k)
        monkeypatch.setattr(owner, name, checked)
    result = run(service(store, observations(record)), record)
    assert result.success and len(counts) == 2 and all(n > 0 for n in counts.values())
    changed = deepcopy(result.result_payload["scenario"])
    changed["authority"]["execution"] = 0
    changed["scenario_identity"] = "reference_scenario_" + digest({k:v for k,v in changed.items() if k != "scenario_identity"})
    with pytest.raises(ValueError): reference.validate_reference_scenario(changed, result.result_payload["reconstruction"])


def test_archive_failure_does_not_rerun_and_fresh_process_recovers(candidate_factory, monkeypatch):
    store, record = candidate_factory()
    result = run(service(store, observations(record)), record)
    assert result.success
    code = '''
import sys
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
a = __import__('ced_one.memory.mission_store', fromlist=['SQLiteMissionArchive']).SQLiteMissionArchive(sys.argv[1])
def forbidden(*a, **k): raise AssertionError('recovery executed')
LocalExecutionRuntime.execute = forbidden
s = MissionControlService(archive=a)
r = s.get_archived_mission(sys.argv[2])
assert s.execution_history == [] and r.temporal_scope == 'HISTORICAL_RECORD_ONLY'
assert r.result.result_payload['execution'] is False
assert all(v is False for v in r.result.result_payload['authority'].values())
print(r.record_sha256)
'''
    process = subprocess.run([sys.executable, "-B", "-c", code, str(store.path), result.request_id],
        capture_output=True, text=True, timeout=20, env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"})
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == store.get(result.request_id).record_sha256
    instance = service(store, observations(record))
    original, calls = instance.runtime.execute, []
    def counted(*a, **k): calls.append(True); return original(*a, **k)
    monkeypatch.setattr(instance.runtime, "execute", counted)
    def failed(*a, **k): raise OSError("unavailable store")
    monkeypatch.setattr(store, "save", failed)
    result = run(instance, record)
    assert result.success and len(calls) == 1
    assert result.metadata["archive"] == {"status":"failed", "error_code":"ARCHIVE_ERROR"}


@pytest.mark.parametrize("change", ["candidate", "assessment", "source", "profile", "ordinal", "duration", "version",
                                  "parent_origin", "parent_hash", "parent_payload_hash", "authority", "mission_id", "T", "action"])
def test_rehashed_candidate_archive_does_not_replace_native_proof(candidate_factory, tmp_path, change):
    _, record = candidate_factory()
    request, result = deepcopy(record.request), deepcopy(record.result)
    body = result.result_payload
    if change == "candidate": body["candidate"]["entry_reference"]["value"] += 1
    elif change == "assessment": body["strategy_assessment"]["authority"]["execution"] = 0
    elif change == "source": body["provenance"]["strategy_source_snapshot_ids"]["M1"] = "forged"
    elif change == "parent_origin": body["provenance"]["source_selection"]["capability"] = "other"
    elif change == "parent_hash": body["provenance"]["source_selection"]["record_sha256"] = "0"*64
    elif change == "parent_payload_hash": body["provenance"]["source_selection"]["payload_sha256"] = "0"*64
    elif change == "authority": body["authority"]["execution"] = 0
    elif change == "mission_id": body["provenance"]["new_mission_id"] = "other"
    elif change == "T": body["provenance"]["evaluation_time"] = ts(30)
    elif change == "action": body["action_formulation"]["formulated_action"]["direction"] = "SHORT"
    else:
        profile = body["provenance"]["replay_profile"]
        if change == "profile": profile["strategy_definition"]["configuration"]["history_starts"]["M1"] = ts(-4)
        elif change == "ordinal": profile["setup_ordinal"] = 1
        elif change == "duration": profile["entry_validity_duration_seconds"] = 121
        else: profile["native_versions"]["strategy"]["rule_version"] = "old"
        body["provenance"]["profile_sha256"] = digest(profile)
    store = SQLiteMissionArchive(tmp_path / "rehashed.sqlite3")
    store.save(request, result, record.policy)
    changed = store.get(record.mission_id)
    assert changed.record_sha256 != record.record_sha256
    result = run(service(store, observations(record)), changed)
    assert result.status is RequestStatus.FAILED and result.result_payload == {}


def test_observation_horizon_and_future_boundary_are_explicit(candidate_factory):
    store, record = candidate_factory()
    profile = observations(record)
    profile["research_boundary"] = ts(32)
    result = run(service(store, profile), record)
    assert result.status is RequestStatus.FAILED
    assert "24-hour horizon" in result.metadata["execution_result"]["failure_reason"]
    profile["research_boundary"] = stamp(datetime.now(timezone.utc) + timedelta(days=1))
    with pytest.raises(ValueError, match="future"):
        service(store, profile)


def test_native_result_tampering_is_rejected_before_return(candidate_factory, monkeypatch):
    store, record = candidate_factory()
    original = reference.evaluate_reference_scenario
    def changed(request):
        result = original(request)
        result["completion_status"] = "HORIZON_CENSORED"
        result["scenario_identity"] = "reference_scenario_" + digest({k:v for k,v in result.items() if k != "scenario_identity"})
        return result
    # Mutate only the first owner result. Detached validation must reconstruct.
    calls = []
    def once(request):
        calls.append(True)
        return changed(request) if len(calls) == 1 else original(request)
    monkeypatch.setattr(reference, "evaluate_reference_scenario", once)
    result = run(service(store, observations(record)), record)
    assert result.status is RequestStatus.FAILED and result.result_payload == {}
