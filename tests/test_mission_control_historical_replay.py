"""Existing owners, fresh governance, exact archival links and post-T isolation."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.local_historical_replay import run_replay, write_demo_dataset, local_policy, selection, observation_profile
from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
from ced_one.business_divisions.trading.historical_market_data import load_dataset, digest
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    root = tmp_path_factory.mktemp("historical-import")
    results = {}
    for direction, case in (("LONG", "target"), ("LONG", "stop"), ("SHORT", "target")):
        paths = write_demo_dataset(root/direction/case, direction, case)
        report = run_replay(*paths)
        assert report["stopped_reason"] is None, report
        results[direction, case] = paths, report
    return results


@pytest.mark.parametrize("direction,case,r", [("LONG", "target", 3), ("LONG", "stop", -1), ("SHORT", "target", 3)])
def test_real_chain_native_validation_and_archive_identities(completed, direction, case, r):
    paths, report = completed[direction, case]
    assert len(report["missions"]) == 3
    store = SQLiteMissionArchive(paths[3])
    records = [store.get(m["mission_id"]) for m in report["missions"]]
    for i, record in enumerate(records):
        assert record.record_sha256 == report["missions"][i]["record_sha256"]
        if i:
            selected = record.request.context["selection"]
            assert (selected["source_mission_id"], selected["record_sha256"]) == (records[i-1].mission_id, records[i-1].record_sha256)
        if i in (0, 2):
            binding = record.result.metadata["capability_contract"]["metadata"]["import_binding"]
            assert binding["dataset_sha256"] == report["dataset_sha256"]
            assert binding["manifest_sha256"] == report["manifest_sha256"]
    scenario = report["scenario"]
    assert reference.validate_reference_scenario(scenario, records[2].result.result_payload["reconstruction"]) == scenario
    assert scenario["reference_result"]["lower_r"] == dict(numerator=r, denominator=1)
    for body in (records[1].result.result_payload, records[2].result.result_payload, scenario):
        assert body["execution"] is False and all(v is False for v in body["authority"].values())
    assert report["candidate"]["direction"] == direction


def test_changed_outcome_has_identical_native_candidate_entry_stop_and_input(completed):
    p1, first = completed["LONG", "target"]
    p2, second = completed["LONG", "stop"]
    assert first["dataset_sha256"] != second["dataset_sha256"]
    assert first["candidate"] == second["candidate"]
    assert first["scenario"]["reference_result"] != second["scenario"]["reference_result"]
    a = SQLiteMissionArchive(p1[3]).get(first["missions"][1]["mission_id"])
    b = SQLiteMissionArchive(p2[3]).get(second["missions"][1]["mission_id"])
    assert a.result.result_payload["reconstruction"] == b.result.result_payload["reconstruction"]


def test_default_deny_before_analysis(tmp_path, monkeypatch):
    paths = write_demo_dataset(tmp_path)
    def forbidden(*a, **k): raise AssertionError("Denied input reached analyzer")
    monkeypatch.setattr(execution.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    report = run_replay(*paths, policy=ExecutionPolicy("deny", 1))
    assert len(report["missions"]) == 1 and report["stopped_reason"]["reason"] == "MISSION_FAILED"
    assert report["missions"][0]["status"] == "rejected"


@pytest.mark.parametrize("step", [1, 2, 3])
def test_archive_failure_stops_chain_without_reexecution(tmp_path, monkeypatch, step):
    paths = write_demo_dataset(tmp_path)
    original_save, original_execute = SQLiteMissionArchive.save, LocalExecutionRuntime.execute
    saves, executions = [], []
    def save(*a, **k):
        saves.append(True)
        if len(saves) == step: raise OSError("Storage offline")
        return original_save(*a, **k)
    def execute(*a, **k):
        executions.append(True)
        return original_execute(*a, **k)
    monkeypatch.setattr(SQLiteMissionArchive, "save", save)
    monkeypatch.setattr(LocalExecutionRuntime, "execute", execute)
    report = run_replay(*paths)
    assert report["stopped_reason"] == "ARCHIVE_FAILED"
    assert len(saves) == len(executions) == len(report["missions"]) == step


@pytest.mark.parametrize("ordinal", [1])
def test_missing_candidate_stops_before_reference_experiment(tmp_path, monkeypatch, ordinal):
    paths = write_demo_dataset(tmp_path)
    run = json.loads(paths[2].read_text()); run["setup_ordinal"] = ordinal
    paths[2].write_text(json.dumps(run))
    def forbidden(*a, **k): raise AssertionError("No candidate reached experiment")
    monkeypatch.setattr(reference, "evaluate_reference_scenario", forbidden)
    report = run_replay(*paths)
    assert len(report["missions"]) == 2 and report["candidate"] is None
    assert report["stopped_reason"] and report["scenario"] is None


def test_explicit_late_availability_remains_censored(completed):
    paths, previous = completed["LONG", "target"]
    store = SQLiteMissionArchive(paths[3])
    record = store.get(previous["missions"][1]["mission_id"])
    dataset, run = load_dataset(*paths[:2]), json.loads(paths[2].read_text())
    run["relationship_available_at"] = run["K"]
    profile = observation_profile(dataset, record, run)
    runtime = LocalExecutionRuntime()
    execution.register_governed_reference_backtest_executor(runtime, observation_profile=profile, import_binding=dataset.binding(profile))
    s = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=local_policy(), archive=store)
    result = s.handle_request("Governed reference backtest", business_division="trading",
        archive_selection=selection(record, run["T"], execution.STRATEGY_REPLAY_CAPABILITY,
            execution.STRATEGY_REPLAY_CONTRACT, execution.STRATEGY_REPLAY_RULE))
    assert result.success
    assert result.result_payload["outcome"] == "MISSING_DATA_CENSORED"
    assert result.result_payload["scenario"]["reference_result"] is None
    assert result.result_payload["reconstruction"]["evidence"]["declarations"][0]["available_at"] == run["K"]


@pytest.mark.parametrize("phase", ["first", "last", "after_snapshot"])
def test_import_payload_mutation_never_reuses_governance(tmp_path, monkeypatch, phase):
    from ced_one.mission_control.policy import ExecutionPolicy
    paths = write_demo_dataset(tmp_path)
    dataset, run = load_dataset(*paths[:2]), json.loads(paths[2].read_text())
    payload = dataset.factual_input(run["T"], run["strategy_definition"])
    runtime = LocalExecutionRuntime()
    execution.register_factual_market_context_executor(runtime, import_binding=dataset.binding(payload))
    class MutatingPolicy(ExecutionPolicy):
        calls = 0
        def evaluate_match(self, context):
            decision = super().evaluate_match(context)
            self.calls += 1
            if self.calls == (1 if phase == "first" else 2):
                context.task_context["input_payload"]["timeframe_histories"]["M1"][0]["high"] += 1
            return decision
    s = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=MutatingPolicy(**vars(local_policy())))
    if phase == "after_snapshot":
        from ced_one.mission_control.governance import AuthorizationSnapshot
        original = AuthorizationSnapshot.from_context
        def mutated(context):
            snapshot = original(context)
            context.task_context["input_payload"]["timeframe_histories"]["M1"][0]["high"] += 1
            return snapshot
        monkeypatch.setattr(AuthorizationSnapshot, "from_context", mutated)
    def forbidden(*a, **k): raise AssertionError("Changed import reached native analysis")
    monkeypatch.setattr(execution.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    result = s.handle_request("Compose factual market context", business_division="trading", context=payload)
    assert not result.success


def test_recovery_in_separate_process_never_executes(completed):
    paths, report = completed["LONG", "target"]
    code = '''
import sys
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
def forbidden(*a, **k): raise AssertionError('Recovery executed')
LocalExecutionRuntime.execute = forbidden
s = MissionControlService(archive=SQLiteMissionArchive(sys.argv[1]))
r = s.get_archived_mission(sys.argv[2])
assert r.record_sha256 == sys.argv[3] and r.temporal_scope == 'HISTORICAL_RECORD_ONLY'
assert s.execution_history == [] and r.result.result_payload['execution'] is False
print('RECOVERED_WITHOUT_EXECUTION')
'''
    last = report["missions"][-1]
    result = subprocess.run([sys.executable, "-B", "-c", code, str(paths[3]), last["mission_id"], last["record_sha256"]],
        capture_output=True, text=True, timeout=20, env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1",
            "PYTHONPATH":str(Path(__file__).resolve().parents[1]/"src")})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RECOVERED_WITHOUT_EXECUTION"


def test_wrong_import_binding_prevents_analysis(tmp_path, monkeypatch):
    paths = write_demo_dataset(tmp_path)
    dataset, run = load_dataset(*paths[:2]), json.loads(paths[2].read_text())
    payload = dataset.factual_input(run["T"], run["strategy_definition"])
    binding = dataset.binding(payload); binding["input_sha256"] = "0"*64
    runtime = LocalExecutionRuntime()
    execution.register_factual_market_context_executor(runtime, import_binding=binding)
    s = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=local_policy())
    def forbidden(*a, **k): raise AssertionError("Misbound import reached analysis")
    monkeypatch.setattr(execution.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    result = s.handle_request("Compose factual market context", business_division="trading", context=payload)
    assert not result.success and "Import identity/input mismatch" in result.metadata["execution_result"]["failure_reason"]


def test_missing_candidate_history_retains_unknown(tmp_path, monkeypatch):
    from tests.test_historical_market_data import change_csv
    paths = write_demo_dataset(tmp_path)
    data = load_dataset(*paths[:2])
    removed = data.histories["M1"][2]["timestamp"]
    change_csv(paths, lambda s: "\n".join(row for row in s.splitlines() if ","+removed+"," not in row)+"\n")
    def forbidden(*a, **k): raise AssertionError("Unknown candidate reached experiment")
    monkeypatch.setattr(reference, "evaluate_reference_scenario", forbidden)
    report = run_replay(*paths)
    assert len(report["missions"]) == 2 and report["candidate"] is None
    assert report["assessment"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("case,status", [("ambiguous", "AMBIGUOUS"), ("missing", "MISSING_DATA_CENSORED"),
                                       ("endpoint", "END_OF_DATA_UNRESOLVED"), ("horizon", "HORIZON_CENSORED")])
def test_imported_observations_preserve_native_uncertainty(completed, tmp_path, case, status):
    import csv
    from datetime import timedelta
    from ced_one.business_divisions.trading.historical_market_data import stamp, parse_timestamp
    from tests.test_historical_market_data import change_csv
    paths, previous = completed["LONG", "target"]
    record = SQLiteMissionArchive(paths[3]).get(previous["missions"][1]["mission_id"])
    export = write_demo_dataset(tmp_path)
    at = parse_timestamp(previous["T"])
    if case == "missing":
        change_csv(export, lambda s: "\n".join(row for row in s.splitlines() if ","+previous["T"]+"," not in row)+"\n")
    else:
        def modify(value):
            lines = value.splitlines()
            lines.pop()  # Original single post-T fixture candle.
            for i in range(1440 if case == "horizon" else 1):
                lines.append(",".join(["M1", stamp(at+timedelta(minutes=i)), "124",
                    "180" if case == "ambiguous" else "125", "100" if case == "ambiguous" else "123", "124"]))
            return "\n".join(lines)+"\n"
        change_csv(export, modify)
        if case == "endpoint":
            m = json.loads(export[1].read_text()); m["dataset_end"] = stamp(at+timedelta(minutes=1))
            export[1].write_text(json.dumps(m))
    dataset = load_dataset(*export[:2])
    run = json.loads(export[2].read_text())
    profile = observation_profile(dataset, record, run)
    runtime = LocalExecutionRuntime()
    execution.register_governed_reference_backtest_executor(runtime, observation_profile=profile, import_binding=dataset.binding(profile))
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=local_policy(), archive=SQLiteMissionArchive(paths[3]))
    result = service.handle_request("Governed reference backtest", business_division="trading",
        archive_selection=selection(record, run["T"], execution.STRATEGY_REPLAY_CAPABILITY,
            execution.STRATEGY_REPLAY_CONTRACT, execution.STRATEGY_REPLAY_RULE))
    assert result.success, result.errors
    assert result.result_payload["outcome"] == status
    if case != "ambiguous": assert result.result_payload["scenario"]["reference_result"] is None


def test_current_approval_blocks_before_analysis(tmp_path, monkeypatch):
    from ced_one.mission_control.policy import PolicyDecision
    paths = write_demo_dataset(tmp_path)
    policy = local_policy()
    for rule in policy.rules: rule.decision = PolicyDecision.REQUIRE_APPROVAL
    def forbidden(*a, **k): raise AssertionError("Pending approval reached analyzer")
    monkeypatch.setattr(execution.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    report = run_replay(*paths, policy=policy)
    assert len(report["missions"]) == 1 and report["missions"][0]["status"] == "awaiting_approval"
