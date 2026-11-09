"""Durable historical evidence with real producers and separate-process recovery."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
import threading

import pytest

from ced_one.memory import mission_store as archive
from ced_one.mission_control import LocalExecutionRuntime, MissionControlService
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule
from ced_one.mission_control.types import (
    ApprovalRequirement, ApprovalState, AuthorityValidationResult, DivisionResolutionResult,
    MissionRequest, MissionResult, RequestClassification, RequestStatus,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/local_factual_market_context.py"
POLICY = dict(policy_id="p", policy_version=1, default_decision=PolicyDecision.DENY)


@pytest.fixture
def store(tmp_path):
    return archive.SQLiteMissionArchive(tmp_path / "missions.sqlite3")


@pytest.fixture
def pair():
    request = MissionRequest("observe", request_id="mission-1", context={"number": 1, "flag": False})
    result = MissionResult(request.request_id, RequestStatus.COMPLETED, success=True,
                           metadata={"execution_performed": True}, result_payload={"unavailable": True})
    return request, result


def candle_service(store=None, decision=PolicyDecision.ALLOW, register=True):
    from ced_one.business_divisions.trading.execution import register_candle_executor
    from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
    runtime = LocalExecutionRuntime()
    if register:
        register_candle_executor(runtime)
    policy = ExecutionPolicy("candles", 1, rules=[PolicyRule(
        "allow", 1, 1, decision, division_name="trading", capability_name="candle_intelligence",
        permission_scope="read_only", execution_mode="local", risk_level="low", impact_level="limited",
    )])
    return MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy, archive=store)


def candle_input():
    return dict(symbol="XAUUSD", timeframe="H1", evaluation_time="2026-09-01T02:30:00Z", candle_history=[
        dict(timestamp=f"2026-09-01T{h:02}:00:00Z", open=100, high=104, low=99, close=103) for h in range(3)])


def execute(instance, **kwargs):
    return instance.handle_request("candle intelligence", business_division="trading", context=candle_input(), **kwargs)


def replace_record(store, mutate, rehash=True):
    with sqlite3.connect(store.path) as connection:
        text = connection.execute("SELECT record_json FROM missions").fetchone()[0]
        value = json.loads(text)
        mutate(value)
        text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if rehash:
            digest = hashlib.sha256(text.encode()).hexdigest()
            connection.execute("UPDATE missions SET record_json=?, record_sha256=?", (text, digest))
        else:
            connection.execute("UPDATE missions SET record_json=?", (text,))


def field(node, name):
    return next(row for row in node[-1] if row[0] == name)


def test_exact_supported_types_determinism_and_isolated_reads(store, pair):
    request, result = pair
    named = timezone(timedelta(hours=5, minutes=30), "fixed-zone")
    request.context = {
        "false": False, "integer": 0, "negative_zero": -0.0, "big_integer": 2 ** 20000,
        "text": "☃", "list": [None, 1, True], "enum": RequestStatus.FAILED,
        "date": datetime(2026, 9, 1, 4, 5, 6, 7, tzinfo=named, fold=1),
        "classification": RequestClassification(), "resolution": DivisionResolutionResult("trading", True, True, 1.0, "test"),
        "approval": ApprovalRequirement(True), "authority": AuthorityValidationResult(True),
    }
    text = archive.serialize_mission(request, result, POLICY)
    reordered = deepcopy(request)
    reordered.context = dict(reversed(list(request.context.items())))
    assert archive.serialize_mission(request, result, POLICY) == text
    assert archive.serialize_mission(reordered, result, POLICY) != text
    digest = store.save(request, result, POLICY)
    assert store.save(request, result, POLICY) == digest
    loaded = store.get(request.request_id)
    assert loaded.temporal_scope == "HISTORICAL_RECORD_ONLY" and loaded.record_sha256 == digest
    assert type(loaded.request) is MissionRequest and type(loaded.result) is MissionResult
    assert loaded.request == request and loaded.result == result
    assert list(loaded.request.context) == list(request.context)
    value = loaded.request.context
    assert type(value["false"]) is bool and type(value["integer"]) is int
    assert math.copysign(1, value["negative_zero"]) == -1
    assert type(value["enum"]) is RequestStatus and type(loaded.result.approval_state) is ApprovalState
    assert type(value["classification"]) is RequestClassification
    assert value["date"].fold == 1 and value["date"].tzname() == "fixed-zone"
    request.context.clear()
    loaded.result.success = False
    assert store.get("mission-1").result.success is True
    assert store.get("mission-1").request.context
    assert store.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("value", [float("nan"), float("inf"), b"bytes", {1, 2}, (1, 2),
                                   datetime(2026, 1, 1), {1: "non-string key"}])
def test_unsupported_data_refuses_save_before_creating_database(store, pair, value):
    pair[0].context["unsupported"] = value
    with pytest.raises(archive.ArchiveDataError):
        store.save(*pair, POLICY)
    assert not store.path.exists()


def test_cycles_unknown_classes_and_zoneinfo_are_explicit(store, pair):
    from zoneinfo import ZoneInfo
    @dataclass
    class Unknown:
        value: int
    cyclic = []
    cyclic.append(cyclic)
    for value in (cyclic, Unknown(1), datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Amsterdam"))):
        pair[0].context = {"value": value}
        with pytest.raises(archive.ArchiveDataError):
            store.save(*pair, POLICY)
    assert not store.path.exists()


@pytest.mark.parametrize("key", ["password", "api_key", "Authorization", "credentials", "access-token", "client_secret",
                                  "api_secret", "secret_access_key", "AWS_SECRET_ACCESS_KEY", "aws_access_key_id",
                                  "bearer-token", "sessionToken", "aws_session_token", "id_token"])
def test_credentials_refuse_whole_record_without_leaking_values(store, pair, key):
    pair[1].metadata["nested"] = [{key: "never-store-this"}]
    with pytest.raises(archive.ArchiveSensitiveDataError) as exc:
        store.save(*pair, POLICY)
    assert str(exc.value) == "SENSITIVE_DATA" and not store.path.exists()


def test_id_conflict_never_overwrites_original(store, pair):
    digest = store.save(*pair, POLICY)
    pair[1].result_payload["new"] = True
    with pytest.raises(archive.MissionConflictError):
        store.save(*pair, POLICY)
    assert store.get("mission-1").record_sha256 == digest
    pair[1].request_id = "other"
    with pytest.raises(archive.MissionConflictError):
        store.save(*pair, POLICY)
    assert store.get("mission-1").record_sha256 == digest


def test_read_is_read_only_missing_id_and_no_implicit_database_creation(store, pair):
    with pytest.raises(archive.ArchiveIOError):
        store.get("mission-1")
    assert not store.path.exists()
    store.save(*pair, POLICY)
    before = store.path.read_bytes()
    store.get("mission-1")
    with pytest.raises(archive.MissionNotFoundError):
        store.get("missing")
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("mode", ["checksum", "root_version", "row_version", "db_version", "root_keys", "duplicate_json",
                                  "dataclass_field", "unknown_class", "enum_as_string", "boolean_as_int",
                                  "duplicate_dict_key", "database_schema", "identity", "bad_json", "noncanonical"])
def test_corruption_schema_and_type_mutations_fail_closed(store, pair, mode):
    store.save(*pair, POLICY)
    expected = archive.ArchiveIntegrityError
    if mode in {"row_version", "db_version", "database_schema", "bad_json", "duplicate_json", "noncanonical"}:
        with sqlite3.connect(store.path) as connection:
            if mode == "row_version":
                connection.execute("UPDATE missions SET version=2")
                expected = archive.ArchiveVersionError
            elif mode == "db_version":
                connection.execute("PRAGMA user_version=2")
                expected = archive.ArchiveVersionError
            elif mode == "database_schema":
                connection.execute("CREATE TABLE surprise (value TEXT)")
                expected = archive.ArchiveSchemaError
            else:
                text = connection.execute("SELECT record_json FROM missions").fetchone()[0]
                if mode == "bad_json": text = "not json"
                elif mode == "duplicate_json": text = text[:-1] + ',"version":1}'
                else: text += "\n"
                connection.execute("UPDATE missions SET record_json=?, record_sha256=?", (text, hashlib.sha256(text.encode()).hexdigest()))
    else:
        def mutate(v):
            if mode == "checksum": v["mission_id"] = "changed"
            elif mode == "root_version": v["version"] = 2
            elif mode == "root_keys": v["extra"] = True
            elif mode == "dataclass_field": v["request"][-1].pop()
            elif mode == "unknown_class": v["request"][1] = "AuthorizationSnapshot"
            elif mode == "enum_as_string": field(v["result"], "status")[1] = ["str", "completed"]
            elif mode == "boolean_as_int": field(v["result"], "success")[1] = ["int", "1"]
            elif mode == "duplicate_dict_key":
                context = field(v["request"], "context")[1]
                context[-1].append(context[-1][0])
            elif mode == "identity": v["mission_id"] = "other"
        replace_record(store, mutate, rehash=mode != "checksum")
        if mode == "root_version": expected = archive.ArchiveVersionError
        if mode == "identity": expected = archive.MissionConflictError
    with pytest.raises(expected):
        store.get("mission-1")


def test_commit_failure_rolls_back_the_entire_new_record(store, pair, monkeypatch):
    store.save(*pair, POLICY)
    original = store.path.read_bytes()
    real_connect = sqlite3.connect
    class FailingCommit(sqlite3.Connection):
        def __exit__(self, *args):
            self.rollback()
            raise sqlite3.OperationalError("injected commit failure")
    monkeypatch.setattr(archive.sqlite3, "connect", lambda *a, **kw: real_connect(*a, **kw, factory=FailingCommit))
    pair[0].request_id = pair[1].request_id = "mission-2"
    with pytest.raises(archive.ArchiveIOError):
        store.save(*pair, POLICY)
    assert store.path.read_bytes() == original
    with pytest.raises(archive.MissionNotFoundError):
        store.get("mission-2")


@pytest.mark.parametrize("mode", ["allow", "deny", "approval", "escalate", "missing", "malformed", "caller_approval"])
def test_service_archives_actual_terminal_handling_without_changing_meaning(store, mode):
    decisions = {"deny": PolicyDecision.DENY, "approval": PolicyDecision.REQUIRE_APPROVAL,
                 "escalate": PolicyDecision.ESCALATE}
    service = candle_service(store, decision=decisions.get(mode, PolicyDecision.ALLOW), register=mode != "missing")
    context = candle_input()
    if mode == "malformed": context["candle_history"][0]["close"] = -1
    result = service.handle_request("candle intelligence", business_division="trading", context=context,
                                    metadata={"approval_required": True} if mode == "caller_approval" else None)
    loaded = MissionControlService(archive=archive.SQLiteMissionArchive(store.path)).get_archived_mission(result.request_id)
    assert loaded.result == result and loaded.request.context == context
    assert result.metadata["archive"] == {"status": "stored"}
    assert loaded.policy["policy_id"] == "candles"
    assert loaded.request.created_at.tzinfo is not None
    assert type(loaded.result.status) is RequestStatus
    if mode == "allow": assert result.success
    else: assert not result.success
    if mode in {"approval", "caller_approval", "escalate"}:
        assert result.status is RequestStatus.AWAITING_APPROVAL
        if mode == "caller_approval":
            assert type(loaded.result.metadata["approval_requirement"]) is ApprovalRequirement


@pytest.mark.parametrize("failure", ["io", "secret", "unsupported", "conflict", "unexpected"])
def test_archive_failure_is_visible_without_changing_execution_or_retrying(tmp_path, monkeypatch, failure):
    store = archive.SQLiteMissionArchive(tmp_path / "absent" / "missions.sqlite3" if failure == "io" else tmp_path / "missions.sqlite3")
    instance = candle_service(store)
    calls = []
    selected = instance.runtime.get_contract("trading", "candle_intelligence")
    from ced_one.business_divisions.trading.execution import execute_candle_intelligence
    def counted(request):
        calls.append(1)
        return execute_candle_intelligence(request)
    instance.runtime.register(selected, counted)
    kwargs = {}
    if failure == "secret": kwargs["metadata"] = {"api_key": "do-not-persist"}
    elif failure == "unsupported": kwargs["metadata"] = {"unsupported": object()}
    elif failure == "conflict":
        def conflict(*args): raise archive.MissionConflictError()
        monkeypatch.setattr(store, "save", conflict)
    elif failure == "unexpected":
        def unexpected(*args): raise RuntimeError("private error detail")
        monkeypatch.setattr(store, "save", unexpected)
    result = execute(instance, **kwargs)
    assert result.success and result.status is RequestStatus.COMPLETED
    assert calls == [1] and len(instance.execution_history) == 1
    assert result.errors == [] and result.metadata["archive"]["status"] == "failed"
    assert result.metadata["archive"]["error_code"] == {
        "io": "STORAGE_ERROR", "secret": "SENSITIVE_DATA", "unsupported": "UNSUPPORTED_DATA", "conflict": "IDENTITY_CONFLICT",
        "unexpected": "ARCHIVE_ERROR",
    }[failure]
    assert "do-not-persist" not in str(result.metadata["archive"])


def test_retrieval_does_not_execute_route_authorize_or_restore_live_history(store, monkeypatch):
    result = execute(candle_service(store))
    reader = MissionControlService(archive=store)
    def forbidden(*a, **kw): raise AssertionError("read activated execution")
    monkeypatch.setattr(reader, "handle_request", forbidden)
    monkeypatch.setattr(reader.resolver, "resolve", forbidden)
    monkeypatch.setattr(reader.runtime, "execute", forbidden)
    monkeypatch.setattr(reader.dispatcher, "dispatch", forbidden)
    assert reader.get_archived_mission(result.request_id).result == result
    assert reader.execution_history == []
    # A remembered success does not permit a new execution under default deny.
    fresh = candle_service()
    fresh.policy = ExecutionPolicy("default_deny", 1)
    denied = execute(fresh, metadata={"approved": True, "archived_mission": result.request_id})
    assert denied.status is RequestStatus.REJECTED and denied.metadata["execution_performed"] is False
    with pytest.raises(archive.ArchiveNotConfiguredError):
        fresh.get_archived_mission(result.request_id)


def test_optional_archive_preserves_existing_behavior():
    result = execute(candle_service())
    assert result.success and "archive" not in result.metadata


def test_invalid_path_and_damaged_database_are_fixed_storage_errors(tmp_path, pair):
    for path in (tmp_path / "bad\x00path", tmp_path / "broken.sqlite3"):
        store = archive.SQLiteMissionArchive(path)
        if "\x00" not in str(path):
            path.write_bytes(b"not a SQLite database")
        with pytest.raises(archive.ArchiveIOError) as exc:
            store.save(*pair, POLICY)
        assert str(exc.value) == "STORAGE_ERROR"


def test_symlink_archive_is_refused_without_modifying_target(tmp_path, pair):
    target = tmp_path / "target"
    target.write_bytes(b"original")
    link = tmp_path / "archive"
    link.symlink_to(target)
    store = archive.SQLiteMissionArchive(link)
    with pytest.raises(archive.ArchiveIOError):
        store.save(*pair, POLICY)
    with pytest.raises(archive.ArchiveIOError):
        store.get("mission-1")
    assert target.read_bytes() == b"original"


def test_genuine_factual_evidence_survives_two_separate_processes(tmp_path):
    database = tmp_path / "recover.sqlite3"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}
    first = subprocess.run([sys.executable, "-B", str(SCRIPT), "--archive", str(database)],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stderr
    produced = json.loads(first.stdout)
    assert produced["archive"] == {"status": "stored"}
    mission_id = produced["mission_id"]
    original = archive.SQLiteMissionArchive(database).get(mission_id)
    code = '''
import importlib.abc, json, os, sys
class NoTrading(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("ced_one.business_divisions.trading"):
            raise AssertionError("archive recovery must not import Trading analyzers")
sys.meta_path.insert(0, NoTrading())
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService
from ced_one.mission_control.runtime import LocalExecutionRuntime
def forbidden(*a, **kw): raise AssertionError("recovery must not execute")
LocalExecutionRuntime.execute = forbidden
MissionControlService.handle_request = forbidden
reader = MissionControlService(archive=SQLiteMissionArchive(sys.argv[1]))
record = reader.get_archived_mission(sys.argv[2])
assert not reader.execution_history
assert type(record.result.success) is bool
from ced_one.mission_control.types import RequestStatus, RequestClassification
assert type(record.result.status) is RequestStatus
assert type(record.result.metadata["classification"]) is RequestClassification
print(json.dumps({"pid": os.getpid(), "hash": record.record_sha256,
 "composition_id": record.result.result_payload["composition"]["composition_id"],
 "state": record.result.result_payload["composition"]["composition_state"],
 "scope": record.temporal_scope}))
'''
    second = subprocess.run([sys.executable, "-B", "-c", code, str(database), mission_id],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert second.returncode == 0, second.stderr
    recovered = json.loads(second.stdout)
    assert recovered["hash"] == original.record_sha256
    assert recovered["composition_id"] == produced["composition_id"]
    assert recovered["state"] == produced["composition_state"] == "UNAVAILABLE"
    assert recovered["scope"] == "HISTORICAL_RECORD_ONLY"
    payload = original.result.result_payload
    evidence = payload["evidence"]
    assert sum(len(g) for g in evidence["factual_envelopes"].values()) == 70
    assert len(payload["composition"]["adjacent_relationships"]) == 60
    assert original.request.context["requested_evaluation_timestamp"] == "2026-09-01T00:00:00Z"
    assert list(evidence["sources"]) == ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]
    assert original.result.metadata["task_graph"]["audit_events"][-1]["event_type"] == "MISSION_RESULT"
    # Explicit independent validation of retrieved native evidence; not part of retrieval.
    from ced_one.business_divisions.trading.causal_snapshot_availability import validate_source
    from ced_one.business_divisions.trading.causal_multi_timeframe_context import validate_source_context
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import validate_factual_envelope
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import validate_factual_context
    from ced_one.business_divisions.trading.factual_market_context_composition import validate_factual_composition
    for tf, source in evidence["sources"].items():
        validate_source(source)
        for envelope in evidence["factual_envelopes"][tf].values():
            validate_factual_envelope(envelope, evidence["source_context"]["timeframes"][tf])
    validate_source_context(evidence["source_context"])
    validate_factual_context(evidence["factual_context"])
    validate_factual_composition(payload["composition"], evidence["factual_context"])
    third = subprocess.run([sys.executable, "-B", str(SCRIPT), "--archive", str(database), "--read", mission_id],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert third.returncode == 0, third.stderr
    display = json.loads(third.stdout)
    assert display["operation"] == "archive_read" and display["execution_performed_now"] is False
    assert display["composition_id"] == produced["composition_id"]


def test_archive_first_import_works_in_fresh_interpreter():
    run = subprocess.run([sys.executable, "-B", "-c", "from ced_one.memory.mission_store import SQLiteMissionArchive"],
                         capture_output=True, text=True, cwd=ROOT, timeout=15)
    assert run.returncode == 0, run.stderr


PROCESS_SETUP = '''
import os, sqlite3, sys
from ced_one.memory import mission_store as archive
from ced_one.mission_control.types import MissionRequest, MissionResult, RequestStatus
from ced_one.mission_control.policy import PolicyDecision
policy = dict(policy_id="p", policy_version=1, default_decision=PolicyDecision.DENY)
store = archive.SQLiteMissionArchive(sys.argv[1])
def save(mission_id, context=None):
    return store.save(MissionRequest("observe", request_id=mission_id, context=context or {}),
                      MissionResult(mission_id, RequestStatus.COMPLETED), policy)
'''


def process_args(code, database, *args):
    return [sys.executable, "-B", "-c", PROCESS_SETUP + code, str(database), *args]


def process_env():
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}


def crash_writer(database):
    # A small real page cache forces dirty pages to disk before abrupt exit.
    code = '''
real_connect = sqlite3.connect
class Crash(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        result = super().execute(sql, *args, **kwargs)
        if sql.startswith("INSERT INTO"):
            os._exit(91)
        return result
def connect(*args, **kwargs):
    connection = real_connect(*args, **kwargs, factory=Crash)
    connection.execute("PRAGMA cache_size=8")
    return connection
sqlite3.connect = connect
save("uncommitted", {"large": "x" * 200000})
'''
    result = subprocess.run(process_args(code, database), cwd=ROOT, env=process_env(),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 91, result.stderr
    assert Path(str(database) + "-journal").exists()


def test_abrupt_writer_crash_recovers_committed_native_evidence_in_new_process(store):
    result = execute(candle_service(store))
    original = store.get(result.request_id)
    crash_writer(store.path)
    # Prove the original failure condition exists before official recovery.
    with sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True) as connection:
        with pytest.raises(sqlite3.OperationalError) as error:
            connection.execute("SELECT * FROM missions").fetchall()
        assert error.value.sqlite_errorcode == sqlite3.SQLITE_READONLY_ROLLBACK
    code = '''
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
def forbidden(*args, **kwargs): raise AssertionError("recovery executed a mission")
MissionControlService.handle_request = forbidden
LocalExecutionRuntime.execute = forbidden
reader = MissionControlService(archive=store)
record = reader.get_archived_mission(sys.argv[2])
assert reader.execution_history == []
assert record.temporal_scope == "HISTORICAL_RECORD_ONLY"
print(record.record_sha256)
'''
    recovered = subprocess.run(process_args(code, store.path, result.request_id), cwd=ROOT,
                               env=process_env(), capture_output=True, text=True, timeout=15)
    assert recovered.returncode == 0, recovered.stderr
    assert recovered.stdout.strip() == original.record_sha256
    assert store.get(result.request_id).result == result
    with pytest.raises(archive.MissionNotFoundError):
        store.get("uncommitted")
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("SELECT mission_id FROM missions").fetchall() == [(result.request_id,)]


@pytest.mark.parametrize("failure", ["unwritable_recovery", "checksum"])
def test_crash_recovery_preserves_failure_and_integrity_checks(store, pair, monkeypatch, failure):
    digest = store.save(*pair, POLICY)
    if failure == "checksum":
        replace_record(store, lambda value: value.update(mission_id="tampered"), rehash=False)
    crash_writer(store.path)
    if failure == "unwritable_recovery":
        real_connect = sqlite3.connect
        def connect(path, *args, **kwargs):
            if "mode=rw" in str(path):
                raise sqlite3.OperationalError("private storage details")
            return real_connect(path, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(archive.sqlite3, "connect", connect)
            with pytest.raises(archive.ArchiveIOError) as error:
                store.get("mission-1")
            assert str(error.value) == "STORAGE_ERROR"
        assert store.get("mission-1").record_sha256 == digest
    else:
        with pytest.raises(archive.ArchiveIntegrityError):
            store.get("mission-1")


def test_concurrent_first_processes_publish_only_complete_databases(store):
    code = '''
real_link = os.link
def paused_link(*args, **kwargs):
    print("READY", flush=True)
    sys.stdin.readline()
    return real_link(*args, **kwargs)
os.link = paused_link
save("first")
print("SAVED", flush=True)
'''
    first = subprocess.Popen(process_args(code, store.path), cwd=ROOT, env=process_env(),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(first.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=15), "first initializer did not reach publication"
        assert first.stdout.readline().strip() == "READY"
        assert not store.path.exists()
        second = subprocess.run(process_args('save("second")', store.path), cwd=ROOT, env=process_env(),
                                capture_output=True, text=True, timeout=15)
        assert second.returncode == 0, second.stderr
        stdout, stderr = first.communicate(input="publish\n", timeout=15)
        assert first.returncode == 0, stderr
        assert stdout.strip() == "SAVED"
    finally:
        if first.poll() is None:
            first.kill()
        first.communicate()
    assert store.get("first").mission_id == "first"
    assert store.get("second").mission_id == "second"
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert list(store.path.parent.glob(f".{store.path.name}.init-*")) == []


@pytest.mark.parametrize("stage", ["empty_temporary", "before_publication", "after_publication"])
def test_abrupt_initialization_loss_never_publishes_partial_database(store, pair, stage):
    code = '''
stage = sys.argv[2]
if stage == "empty_temporary":
    sqlite3.connect = lambda *args, **kwargs: os._exit(92)
elif stage == "before_publication":
    os.link = lambda *args, **kwargs: os._exit(92)
else:
    real_link = os.link
    def link(*args, **kwargs):
        real_link(*args, **kwargs)
        os._exit(92)
    os.link = link
save("interrupted")
'''
    result = subprocess.run(process_args(code, store.path, stage), cwd=ROOT, env=process_env(),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 92, result.stderr
    assert store.path.exists() is (stage == "after_publication")
    leftovers = {p: p.read_bytes() for p in store.path.parent.glob(f".{store.path.name}.init-*")}
    assert len(leftovers) == 1
    with pytest.raises(archive.MissionNotFoundError if stage == "after_publication" else archive.ArchiveIOError):
        store.get("interrupted")
    store.save(*pair, POLICY)
    assert store.get("mission-1").result == pair[1]
    with pytest.raises(archive.MissionNotFoundError):
        store.get("interrupted")
    if stage == "after_publication":
        # A crash between link and unlink leaves an alias, not a second snapshot.
        assert all(p.samefile(store.path) for p in leftovers)
    else:
        assert all(p.read_bytes() == data for p, data in leftovers.items())


@pytest.mark.parametrize("kind", ["empty", "foreign_sqlite", "foreign_bytes"])
def test_unknown_existing_files_including_legacy_empty_file_are_never_initialized(store, pair, kind):
    if kind == "foreign_sqlite":
        with sqlite3.connect(store.path) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
    else:
        store.path.write_bytes(b"" if kind == "empty" else b"unrelated data")
    original = store.path.read_bytes()
    for operation in (lambda: store.save(*pair, POLICY), lambda: store.get("mission-1")):
        with pytest.raises(archive.ArchiveIOError if kind == "foreign_bytes" else archive.ArchiveVersionError):
            operation()
        assert store.path.read_bytes() == original


def test_concurrent_conflicting_saves_have_exactly_one_winner(store, pair):
    store.save(*pair, POLICY)
    barrier = threading.Barrier(2)
    def contender(value):
        request, result = deepcopy(pair)
        request.request_id = result.request_id = "contested"
        request.context["contender"] = value
        barrier.wait(timeout=10)
        try:
            store.save(request, result, POLICY)
            return value, "stored"
        except archive.MissionConflictError:
            return value, "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(contender, [0, 1]))
    assert sorted(status for _, status in outcomes) == ["conflict", "stored"]
    winner = next(value for value, status in outcomes if status == "stored")
    assert store.get("contested").request.context["contender"] == winner
    assert store.get("mission-1").result == pair[1]


@pytest.mark.parametrize("operation", ["save", "get"])
def test_lock_timeout_is_explicit_and_never_reexecutes_analysis(store, monkeypatch, operation):
    service = candle_service(store)
    original = execute(service)
    calls = []
    contract = service.runtime.get_contract("trading", "candle_intelligence")
    from ced_one.business_divisions.trading.execution import execute_candle_intelligence
    def counted(request):
        calls.append(1)
        return execute_candle_intelligence(request)
    service.runtime.register(contract, counted)
    real_connect = sqlite3.connect
    def short_timeout(*args, **kwargs):
        assert kwargs["timeout"] == 5
        kwargs["timeout"] = 0.02
        return real_connect(*args, **kwargs)
    with real_connect(store.path) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        with monkeypatch.context() as patch:
            patch.setattr(archive.sqlite3, "connect", short_timeout)
            if operation == "save":
                result = execute(service)
                assert result.success is True and calls == [1]
                assert result.metadata["archive"] == {"status": "failed", "error_code": "STORAGE_ERROR"}
                assert len(service.execution_history) == 2
            else:
                with pytest.raises(archive.ArchiveIOError) as error:
                    service.get_archived_mission(original.request_id)
                assert str(error.value) == "STORAGE_ERROR" and calls == []
        lock.rollback()
    assert store.get(original.request_id).result == original
    if operation == "save":
        with pytest.raises(archive.MissionNotFoundError):
            store.get(result.request_id)


@pytest.mark.parametrize("location", ["context", "request_metadata", "payload", "result_metadata"])
def test_nested_credentials_reject_whole_record_and_preserve_existing_evidence(store, pair, location, caplog):
    digest = store.save(*pair, POLICY)
    request, result = deepcopy(pair)
    request.request_id = result.request_id = "credential-attempt"
    target = {"context": request.context, "request_metadata": request.metadata,
              "payload": result.result_payload, "result_metadata": result.metadata}[location]
    target["nested"] = [{"api_secret": "sensitive-test-value", "secret_access_key": "sensitive-test-value"}]
    with pytest.raises(archive.ArchiveSensitiveDataError) as error:
        store.save(request, result, POLICY)
    assert str(error.value) == "SENSITIVE_DATA"
    assert "sensitive-test-value" not in caplog.text
    assert b"sensitive-test-value" not in store.path.read_bytes()
    assert store.get("mission-1").record_sha256 == digest
    with pytest.raises(archive.MissionNotFoundError):
        store.get("credential-attempt")
