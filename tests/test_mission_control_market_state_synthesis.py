"""Real archived evidence through fresh governance and native factual owners."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.governance import AuthorizationSnapshot
from ced_one.mission_control.governance import ExecutionGovernanceGate
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision
from ced_one.mission_control.types import RequestStatus
from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import causal_snapshot_availability as sources
from ced_one.business_divisions.trading import causal_multi_timeframe_context as source_contexts
from ced_one.business_divisions.trading import causal_factual_intelligence_envelope as envelopes
from ced_one.business_divisions.trading import causal_factual_multi_timeframe_context as contexts
from ced_one.business_divisions.trading import factual_market_context_composition as compositions
from ced_one.business_divisions.trading import causal_factual_event_chronology as chronology
from ced_one.business_divisions.trading import causal_market_state_synthesis as synthesis
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from tests.test_mission_context_selection import source_record, archived_store, archived_source, selection, policy, ROOT


def service(store, decision=PolicyDecision.ALLOW, register=True):
    runtime = LocalExecutionRuntime()
    if register:
        execution.register_archived_market_state_synthesis_executor(runtime)
    return MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
                                 policy=policy("archived_market_state_synthesis", decision), archive=store)


def run(instance, criteria, **kwargs):
    return instance.handle_request("Archived market state synthesis", business_division="trading",
                                   archive_selection=criteria, **kwargs)


@pytest.fixture(scope="module")
def completed(tmp_path_factory, source_record):
    store = SQLiteMissionArchive(tmp_path_factory.mktemp("governed-synthesis") / "missions.sqlite3")
    store.save(source_record.request, source_record.result, source_record.policy)
    result = run(service(store), selection(source_record))
    assert result.success, result.errors
    return store, result


def test_real_mission_validates_full_result_and_preserves_native_identities(completed, source_record):
    store, result = completed
    body = result.result_payload
    upstream = body["upstream_bundle"]
    original = source_record.result.result_payload
    assert result.capability == "archived_market_state_synthesis" and result.specialist == "factual_market_context_analyst"
    assert result.request_id != source_record.mission_id
    assert body["source_evidence"]["sources"] == original["evidence"]["sources"]
    assert body["source_evidence"]["source_context"] == original["evidence"]["source_context"]
    assert upstream["factual_context"] == original["evidence"]["factual_context"]
    assert upstream["factual_envelopes"] == original["evidence"]["factual_envelopes"]
    assert upstream["composition"] == original["composition"]
    chronology.validate_factual_chronology(upstream["chronology"], upstream["factual_context"], upstream["factual_envelopes"], upstream["composition"])
    synthesis.validate_market_state_synthesis(body["synthesis"], upstream)
    assert body["provenance"]["new_mission_id"] == result.request_id
    assert body["provenance"]["source_selection"]["record_sha256"] == source_record.record_sha256
    assert body["provenance"]["source_snapshot_ids"] == {tf: v["source_snapshot_id"] for tf, v in original["evidence"]["sources"].items()}
    assert store.get(source_record.mission_id).record_sha256 == source_record.record_sha256
    recovered = store.get(result.request_id)
    assert recovered.result == result and recovered.request.context["original_payload"] == original
    assert set(recovered.request.context) == {"selection", "original_payload"}
    events = result.metadata["task_graph"]["audit_events"]
    selected = next(e for e in events if e["event_type"] == "ARCHIVED_CONTEXT_SELECTED")
    used = next(e for e in events if e["event_type"] == "ARCHIVED_CONTEXT_USED")
    assert selected["mission_id"] == used["mission_id"] == result.request_id
    assert selected["details"]["source_mission_id"] == used["details"]["source_mission_id"] == source_record.mission_id
    names = [e["event_type"] for e in events]
    assert names.index("ARCHIVED_CONTEXT_SELECTED") < names.index("POLICY_EVALUATED") < names.index("EXECUTION_STARTED") < names.index("ARCHIVED_CONTEXT_USED")


def test_degraded_evidence_and_equal_time_ordering_keep_native_meaning(completed):
    _, result = completed
    upstream, value = result.result_payload["upstream_bundle"], result.result_payload["synthesis"]
    assert upstream["composition"]["composition_state"] == "UNAVAILABLE"
    assert upstream["chronology"]["chronology_state"] == "UNAVAILABLE"
    assert upstream["chronology"]["events"]
    assert all(g["within_group_ordering"] == "ORDER_UNPROVEN" for g in value["ordering_groups"])
    claims = [claim for frame in value["timeframes"].values() for rows in frame["dimensions"].values() for claim in rows]
    assert any(c["support_state"] == "UNKNOWN" for c in claims)
    assert any(c["support_state"] == "EVIDENCED" for c in claims)
    assert all(c["value"] is None for c in claims if c["support_state"] in {"UNKNOWN", "ABSENT_IN_SCOPE"})
    for item in (result.result_payload, value, upstream["chronology"]):
        assert item["metadata"]["observation_only"] is True
        assert item["metadata"]["authority_scope"] == "read_only"
        assert all(item["metadata"][key] is False for key in ("advisory_output", "strategy_output", "execution_output"))
    assert not any(word in json.dumps(result.result_payload) for word in ("trade_authorized", "margin_approved", "payout_authorized"))


@pytest.mark.parametrize("decision", [PolicyDecision.DENY, PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.ESCALATE, None])
def test_current_governance_blocks_before_any_native_analysis(archived_source, monkeypatch, decision):
    store, criteria = archived_source
    instance = service(store, decision or PolicyDecision.DENY)
    if decision is None: instance.policy = ExecutionPolicy("default_deny", 1)
    def forbidden(*args, **kwargs): raise AssertionError("native owner invoked before authorization")
    monkeypatch.setattr(chronology.CAUSAL_FACTUAL_EVENT_CHRONOLOGY, "analyze", forbidden)
    monkeypatch.setattr(synthesis.CAUSAL_MARKET_STATE_SYNTHESIS, "analyze", forbidden)
    monkeypatch.setattr(sources, "validate_source", forbidden)
    result = run(instance, criteria, metadata={"approved": True, "policy_decision": "ALLOW"})
    assert result.status in {RequestStatus.REJECTED, RequestStatus.AWAITING_APPROVAL}
    assert result.success is False and result.metadata["execution_performed"] is False
    assert not any(e["event_type"] == "ARCHIVED_CONTEXT_USED" for e in result.metadata["task_graph"]["audit_events"])


def test_missing_registration_and_caller_projection_cannot_bypass_selection(archived_source):
    store, criteria = archived_source
    missing = run(service(store, register=False), criteria)
    assert missing.status is RequestStatus.UNSUPPORTED and not missing.metadata["execution_performed"]
    instance = service(store)
    projection = instance.select_archived_context(criteria)
    for kwargs in ({"context": projection}, {"context": projection, "archive_selection": criteria}):
        result = instance.handle_request("Archived market state synthesis", business_division="trading", **kwargs)
        assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]
    result = run(service(None), criteria)
    assert result.status is RequestStatus.FAILED and not result.metadata["execution_performed"]


def test_projection_mutated_before_authorization_is_rejected(archived_source, monkeypatch):
    store, criteria = archived_source
    instance = service(store)
    real = instance.select_archived_context
    def changed(value):
        projection = real(value)
        projection["original_payload"]["composition"]["composition_id"] = "changed"
        return projection
    monkeypatch.setattr(instance, "select_archived_context", changed)
    result = run(instance, criteria)
    assert not result.metadata["execution_performed"]
    assert any("PROJECTION_CONTENT_MISMATCH" in e for e in result.errors)


def test_mutation_after_snapshot_cannot_reuse_authorization(archived_source, monkeypatch):
    store, criteria = archived_source
    real = AuthorizationSnapshot.from_context
    def changed(context):
        snapshot = real(context)
        context.task_context["input_payload"]["original_payload"]["extra"] = True
        return snapshot
    monkeypatch.setattr(AuthorizationSnapshot, "from_context", changed)
    result = run(service(store), criteria)
    assert result.status is RequestStatus.REJECTED and not result.metadata["execution_performed"]
    assert any("stale" in e.lower() for e in result.errors)


@pytest.mark.parametrize("change", ["reference", "payload_and_digest"])
def test_policy_time_mutation_cannot_replace_the_selected_source(archived_source, monkeypatch, change):
    store, criteria = archived_source
    real = ExecutionGovernanceGate.evaluate
    calls = []
    def changed(gate, context, *args, **kwargs):
        decision = real(gate, context, *args, **kwargs)
        if not calls:
            payload = context.task_context["input_payload"]
            if change == "reference": payload["selection"]["record_sha256"] = "0" * 64
            else:
                payload["original_payload"]["extra"] = True
                payload["selection"]["payload_sha256"] = hashlib.sha256(json.dumps(
                    payload["original_payload"], ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        calls.append(1)
        return decision
    def forbidden(*args, **kwargs): raise AssertionError("modified context reached native owners")
    monkeypatch.setattr(ExecutionGovernanceGate, "evaluate", changed)
    monkeypatch.setattr(sources, "validate_source", forbidden)
    result = run(service(store), criteria)
    assert result.status is RequestStatus.REJECTED and result.metadata["execution_performed"] is False
    assert result.errors == ["STALE_ARCHIVED_CONTEXT"]


@pytest.mark.parametrize("change", ["reference", "payload_and_digest", "detached_reference"])
def test_second_policy_mutation_rejects_before_executor(archived_source, monkeypatch, change):
    store, criteria = archived_source
    instance = service(store)
    evaluations, executions = [], []

    class MutatingPolicy(ExecutionPolicy):
        def evaluate_match(self, context):
            matches = super().evaluate_match(context)
            evaluations.append(context.task_id)
            if len(evaluations) == 2:
                payload = context.task_context["input_payload"]
                original = deepcopy(payload) if change == "detached_reference" else None
                if change == "payload_and_digest":
                    payload["original_payload"]["extra"] = True
                    payload["selection"]["payload_sha256"] = hashlib.sha256(json.dumps(
                        payload["original_payload"], ensure_ascii=True, separators=(",", ":"),
                        allow_nan=False).encode()).hexdigest()
                else:
                    payload["selection"]["record_sha256"] = "0" * 64
                if original is not None:
                    # Hide the changed execution payload behind an unchanged policy view.
                    context.task_context["input_payload"] = original
            return matches

    instance.policy = MutatingPolicy(**vars(instance.policy))
    execute = instance.runtime.execute

    def counted(request):
        executions.append(request.mission_id)
        return execute(request)

    monkeypatch.setattr(instance.runtime, "execute", counted)
    result = run(instance, criteria)
    assert len(evaluations) == 2
    assert executions == []
    assert result.status is RequestStatus.REJECTED and result.success is False
    assert result.metadata["execution_performed"] is False and result.result_payload == {}
    assert any("stale" in error.lower() for error in result.errors)
    assert result.metadata["archived_context_selection"]["record_sha256"] == criteria["record_sha256"]
    events = result.metadata["task_graph"]["audit_events"]
    assert not any(e["event_type"] in {"EXECUTION_STARTED", "ARCHIVED_CONTEXT_USED"} for e in events)
    selected = next(e for e in events if e["event_type"] == "ARCHIVED_CONTEXT_SELECTED")
    assert selected["details"]["record_sha256"] == criteria["record_sha256"]


@pytest.mark.parametrize("change", ["source", "envelope", "context", "composition", "version", "T", "matrix", "authority"])
def test_rehashed_archive_content_still_requires_native_proof(tmp_path, source_record, change):
    record = deepcopy(source_record)
    body = record.result.result_payload
    evidence = body["evidence"]
    if change == "source": evidence["sources"]["H1"]["source_snapshot_id"] = "changed"
    elif change == "envelope": evidence["factual_envelopes"]["H1"]["candle_intelligence"]["context_id"] = "changed"
    elif change == "context": evidence["factual_context"]["source_context_id"] = "changed"
    elif change == "composition": body["composition"]["composition_id"] = "changed"
    elif change == "version": evidence["sources"]["H1"]["metadata"]["rule_version"] = "old"
    elif change == "T": evidence["sources"]["H1"]["requested_evaluation_timestamp"] = "2026-08-31T00:00:00Z"
    elif change == "matrix": evidence["factual_envelopes"].pop("M1")
    else: evidence["sources"]["H1"]["metadata"]["execution_output"] = 0
    store = SQLiteMissionArchive(tmp_path / "mutated.sqlite3")
    store.save(record.request, record.result, record.policy)
    criteria = selection(store.get(record.mission_id))
    result = run(service(store), criteria)
    assert result.status is RequestStatus.FAILED and not result.success
    assert result.metadata["execution_performed"] is True and not result.result_payload


def test_all_public_owners_validate_real_evidence_without_detectors(archived_source, monkeypatch):
    store, criteria = archived_source
    counts = {}
    for module, name in ((sources, "validate_source"), (source_contexts, "validate_source_context"),
                         (envelopes, "validate_factual_envelope"), (contexts, "validate_factual_context"),
                         (compositions, "validate_factual_composition"), (chronology, "validate_factual_chronology"),
                         (synthesis, "validate_market_state_synthesis")):
        real = getattr(module, name)
        def counted(*args, _name=name, _real=real, **kwargs):
            counts[_name] = counts.get(_name, 0) + 1
            return _real(*args, **kwargs)
        monkeypatch.setattr(module, name, counted)
    def forbidden(*args, **kwargs): raise AssertionError("source mission or detector rerun")
    monkeypatch.setattr(sources.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    for adapter in envelopes.ADAPTERS.values():
        from dataclasses import replace
        monkeypatch.setitem(envelopes.ADAPTERS, adapter.contract, replace(adapter, invoke=forbidden))
    result = run(service(store), criteria)
    assert result.success, result.errors
    assert len(counts) == 7 and counts["validate_source"] >= 7 and counts["validate_factual_envelope"] >= 70


@pytest.mark.parametrize("owner,identity", [(chronology.CAUSAL_FACTUAL_EVENT_CHRONOLOGY, "chronology_id"),
                                           (synthesis.CAUSAL_MARKET_STATE_SYNTHESIS, "synthesis_id")])
def test_tampered_new_native_output_is_rejected_by_detached_validation(archived_source, monkeypatch, owner, identity):
    store, criteria = archived_source
    real = owner.analyze
    calls = []
    def corrupted(payload):
        output = real(payload).to_dict()
        if not calls: output[identity] = "tampered-output"
        calls.append(1)
        return SimpleNamespace(to_dict=lambda: deepcopy(output))
    monkeypatch.setattr(owner, "analyze", corrupted)
    result = run(service(store), criteria)
    assert result.status is RequestStatus.FAILED and not result.success
    assert result.metadata["execution_performed"] is True and result.result_payload == {}


def test_demo_selects_after_process_exit_and_archives_distinct_missions(tmp_path):
    script = ROOT / "scripts/local_factual_market_context.py"
    database = tmp_path / "restart.sqlite3"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}
    def command(*args):
        result = subprocess.run([sys.executable, "-B", str(script), "--archive", str(database), *args],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    first = command()
    second = command("--synthesize", first["mission_id"], "--record-sha256", first["record_sha256"],
                     "--evaluation-time", first["requested_evaluation_timestamp"],
                     "--created-not-after", datetime.now(timezone.utc).isoformat())
    assert first["process_id"] != second["process_id"]
    assert first["mission_id"] != second["mission_id"]
    assert first["archive"] == second["archive"] == {"status": "stored"}
    assert second["source_mission_id"] == first["mission_id"]
    assert second["source_record_sha256"] == first["record_sha256"]
    assert second["composition_id"] == first["composition_id"]
    assert second["native_validation"] == "passed" and second["event_count"] > 0
    store = SQLiteMissionArchive(database)
    assert store.get(first["mission_id"]).record_sha256 == first["record_sha256"]
    recovered = store.get(second["mission_id"])
    assert recovered.record_sha256 == second["record_sha256"]
    assert recovered.result.result_payload["synthesis"]["synthesis_id"] == second["synthesis_id"]
    read = command("--read", second["mission_id"])
    assert read["execution_performed_now"] is False and read["validation_scope"] == "archived_execution"
    assert read["synthesis_id"] == second["synthesis_id"]
