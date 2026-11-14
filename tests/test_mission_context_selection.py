"""Explicit historical data selection never restores execution or approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy

import pytest

from ced_one.memory.mission_store import SQLiteMissionArchive, ArchiveError
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.service import ArchivedContextError, validate_archived_context_projection
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule
from ced_one.mission_control.types import RequestStatus
from ced_one.business_divisions.trading.execution import register_factual_market_context_executor
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.factual_market_context_composition import CONTRACT, RULE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def policy(capability="factual_market_context_composition", decision=PolicyDecision.ALLOW):
    return ExecutionPolicy("explicit_factual_analysis", 1, rules=[PolicyRule(
        "read_only", 1, 1, decision, division_name="trading", specialist_name="factual_market_context_analyst",
        capability_name=capability, permission_scope="read_only", adapter_name="local", execution_mode="local",
        risk_level="low", impact_level="limited",
    )])


@pytest.fixture(scope="module")
def source_record(tmp_path_factory):
    store = SQLiteMissionArchive(tmp_path_factory.mktemp("composition-source") / "missions.sqlite3")
    runtime = LocalExecutionRuntime()
    register_factual_market_context_executor(runtime)
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy(), archive=store)
    payload = runpy.run_path(str(ROOT / "scripts/local_factual_market_context.py"))["synthetic_payload"]()
    result = service.handle_request("Compose factual market context", business_division="trading", context=payload)
    assert result.success and result.metadata["archive"] == {"status": "stored"}, result.errors
    return store.get(result.request_id)


def selection(record):
    return {"mission_id": record.mission_id, "record_sha256": record.record_sha256,
            "division": "trading", "capability": "factual_market_context_composition", "contract_id": CONTRACT,
            "rule_version": RULE_VERSION, "evaluation_time": record.request.context["requested_evaluation_timestamp"],
            "created_not_after": datetime.now(timezone.utc).isoformat()}


@pytest.fixture(scope="module")
def archived_store(tmp_path_factory, source_record):
    store = SQLiteMissionArchive(tmp_path_factory.mktemp("selection-store") / "missions.sqlite3")
    store.save(source_record.request, source_record.result, source_record.policy)
    return store


@pytest.fixture
def archived_source(archived_store, source_record):
    store = archived_store
    return store, selection(source_record)


def test_selection_isolated_minimal_and_never_routes_executes_or_restores_authority(archived_source, monkeypatch):
    store, criteria = archived_source
    service = MissionControlService(archive=store)
    def forbidden(*args, **kwargs): raise AssertionError("selection executed or authorized")
    monkeypatch.setattr(service, "handle_request", forbidden)
    monkeypatch.setattr(service.resolver, "resolve", forbidden)
    monkeypatch.setattr(service.runtime, "execute", forbidden)
    monkeypatch.setattr(service.dispatcher, "dispatch", forbidden)
    projection = service.select_archived_context(criteria)
    assert set(projection) == {"selection", "original_payload"}
    assert projection["original_payload"] == store.get(criteria["mission_id"]).result.result_payload
    assert projection["selection"]["source_mission_id"] == criteria["mission_id"]
    assert projection["selection"]["record_sha256"] == criteria["record_sha256"]
    assert projection["selection"]["temporal_scope"] == "HISTORICAL_RECORD_ONLY"
    assert not {"policy", "policy_decision", "approval", "status", "execution_performed"} & projection.keys()
    assert service.execution_history == [] and service.policy.default_decision is PolicyDecision.DENY
    projection["original_payload"].clear()
    projection["selection"]["record_sha256"] = "0" * 64
    assert service.select_archived_context(criteria)["original_payload"]
    assert store.get(criteria["mission_id"]).record_sha256 == criteria["record_sha256"]


@pytest.mark.parametrize("change", ["missing", "extra", "hash", "upper_hash", "hash_type", "id", "division",
                                  "capability", "contract", "rule", "T", "naive", "future_limit", "early_limit"])
def test_explicit_selection_mismatches_fail_without_fallback(archived_source, change):
    store, criteria = archived_source
    if change == "missing": criteria.pop("record_sha256")
    elif change == "extra": criteria["knowledge_at"] = "2026-01-01T00:00:00Z"
    elif change == "hash": criteria["record_sha256"] = "0" * 64
    elif change == "upper_hash": criteria["record_sha256"] = "A" * 64
    elif change == "hash_type": criteria["record_sha256"] = False
    elif change == "id": criteria["mission_id"] = "missing"
    elif change in {"division", "capability"}: criteria[change] = "other"
    elif change == "contract": criteria["contract_id"] = "trading.other.v2"
    elif change == "rule": criteria["rule_version"] = "other_rule"
    elif change == "T": criteria["evaluation_time"] = "2026-08-31T00:00:00Z"
    elif change == "naive": criteria["evaluation_time"] = "2026-09-01T00:00:00"
    elif change == "future_limit": criteria["created_not_after"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    else: criteria["created_not_after"] = criteria["evaluation_time"]
    service = MissionControlService(archive=store)
    with pytest.raises((ArchivedContextError, ArchiveError)):
        service.select_archived_context(criteria)
    assert service.execution_history == []


@pytest.mark.parametrize("change", ["not_completed", "not_executed", "request_origin", "descriptor",
                                  "metadata", "future_request", "missing_T"])
def test_invalid_source_record_is_not_promoted_to_context(tmp_path, source_record, change):
    record = deepcopy(source_record)
    if change == "not_completed": record.result.status = RequestStatus.FAILED
    elif change == "not_executed": record.result.metadata["execution_performed"] = False
    elif change == "request_origin": record.request.business_division = "other"
    elif change == "descriptor": record.result.metadata["capability_contract"]["permission_scope"] = "write"
    elif change == "metadata": record.result.metadata["capability_contract"]["metadata"] = None
    elif change == "future_request": record.request.created_at = datetime.now(timezone.utc) + timedelta(days=1)
    else: record.request.context.pop("requested_evaluation_timestamp")
    store = SQLiteMissionArchive(tmp_path / "bad.sqlite3")
    store.save(record.request, record.result, record.policy)
    ref = selection(source_record)
    ref["record_sha256"] = store.get(record.mission_id).record_sha256
    with pytest.raises(ArchivedContextError):
        MissionControlService(archive=store).select_archived_context(ref)


def test_equivalent_timezone_is_same_economic_instant_not_retiming(archived_source):
    store, criteria = archived_source
    criteria["evaluation_time"] = "2026-09-01T02:00:00+02:00"
    value = MissionControlService(archive=store).select_archived_context(criteria)
    assert value["selection"]["evaluation_time"] == "2026-09-01T00:00:00Z"
    assert value["original_payload"]["composition"]["requested_evaluation_timestamp"] == "2026-09-01T00:00:00Z"


@pytest.mark.parametrize("change", ["payload", "hash", "extra", "scope", "time"])
def test_projection_mutation_fails_its_data_contract(archived_source, change):
    store, criteria = archived_source
    value = MissionControlService(archive=store).select_archived_context(criteria)
    if change == "payload": value["original_payload"]["composition"]["composition_id"] = "changed"
    elif change == "hash": value["selection"]["payload_sha256"] = "0" * 64
    elif change == "extra": value["approved"] = True
    elif change == "scope": value["selection"]["temporal_scope"] = "CURRENT_APPROVAL"
    else: value["selection"]["selected_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ArchivedContextError):
        validate_archived_context_projection(value)


@pytest.mark.parametrize("value", [PolicyDecision.ALLOW, RequestStatus.COMPLETED, datetime(2026, 9, 1, tzinfo=timezone.utc)])
def test_projection_never_coerces_archive_types_into_json_values(archived_source, value):
    store, criteria = archived_source
    projection = MissionControlService(archive=store).select_archived_context(criteria)
    projection["original_payload"]["extra"] = value
    with pytest.raises(ArchivedContextError, match="INVALID_PROJECTION"):
        validate_archived_context_projection(projection)


@pytest.mark.parametrize("native_contract", ["trading.governed_strategy_candidate_replay.v1", "trading.other.v1"])
def test_candidate_time_extension_requires_exact_contract_and_original_projection(tmp_path, source_record, native_contract):
    request, result = deepcopy(source_record.request), deepcopy(source_record.result)
    result.capability = "governed_strategy_candidate_replay"
    contract = result.metadata["capability_contract"]
    contract.update(name=result.capability, contract_id=native_contract)
    contract["metadata"]["rule_version"] = "governed_strategy_candidate_replay_v1"
    # A raw factual context must never be accepted as a strategy replay input.
    del request.context["requested_evaluation_timestamp"]
    store = SQLiteMissionArchive(tmp_path / "wrong-shape.sqlite3")
    store.save(request, result, source_record.policy)
    record = store.get(source_record.mission_id)
    criteria = selection(source_record)
    criteria.update(record_sha256=record.record_sha256, capability=result.capability,
                    contract_id=native_contract, rule_version=contract["metadata"]["rule_version"])
    with pytest.raises(ArchivedContextError):
        MissionControlService(archive=store).select_archived_context(criteria)
