"""Native discovery must agree with independently governed archived replay."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from scripts import local_historical_candidate_scan as scan
from scripts import local_historical_replay as replay
from ced_one.business_divisions.trading.historical_market_data import load_dataset, digest, stamp, parse_timestamp, ORDER
from ced_one.memory.mission_store import SQLiteMissionArchive
from ced_one.mission_control import LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision


def fixture_plan(root, direction="LONG"):
    paths = replay.write_demo_dataset(root, direction)
    dataset = load_dataset(*paths[:2])
    run = json.loads(paths[2].read_text())
    at = parse_timestamp(run["T"])
    run["K"] = stamp(at+timedelta(hours=24, minutes=1))
    points = []
    starts = {tf: run["strategy_definition"]["configuration"]["history_starts"].get(tf) for tf in ORDER}
    for offset in (-1, 0, 1):
        current = deepcopy(run)
        current["T"] = stamp(at+timedelta(minutes=offset))
        points.append(dict(session_id=direction, run=current, timeframe_starts=deepcopy(starts)))
    envelope = scan.seal_plan(dataset, replay.batch_plan(dataset, json.dumps(run), points), [digest(p) for p in points])
    plan_path = root/"scan-plan.json"
    replay.atomic_json(plan_path, envelope, create=True)
    return paths, dataset, envelope, plan_path


def test_preparation_seals_186_points_and_18_controls_before_any_execution(tmp_path, monkeypatch):
    paths = replay.write_demo_dataset(tmp_path)
    data = load_dataset(*paths[:2])
    run = json.loads(paths[2].read_text())
    run["K"] = run["relationship_available_at"] = "2026-11-01T00:00:00Z"
    raw = json.dumps(run)
    def forbidden(*a, **k): raise AssertionError("Preparation invoked an analyzer/runtime")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    monkeypatch.setattr(scan.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    sealed = scan.prepare_plan(data, raw)
    assert sealed["plan_sha256"] == digest(sealed["plan"])
    plan = sealed["plan"]
    assert len(plan["batch_plan"]["points"]) == 186
    assert len(plan["negative_control_point_ids"]) == 18
    for start in scan.STARTS:
        points = [p for p in plan["batch_plan"]["points"] if p["session_id"] == start]
        assert len(points) == 62
        assert [(p["run"]["T"], p["run"]["strategy_definition"]["direction"]) for p in points] == [
            (stamp(parse_timestamp(start)+timedelta(minutes=m)),d) for m in range(31) for d in ("LONG","SHORT")]
        for point in points:
            current = point["run"]
            assert current["K"] == current["relationship_available_at"] == run["K"]
            assert current["setup_ordinal"] == 0 and current["entry_validity_duration_seconds"] == 120
            config = current["strategy_definition"]["configuration"]
            assert config["founding_start"] == start
            assert config["founding_end"] == stamp(parse_timestamp(start)+timedelta(minutes=30))
            assert point["timeframe_starts"]["D1"] is None
            for tf,n in replay.WARMUP.items():
                assert parse_timestamp(point["timeframe_starts"][tf]) == parse_timestamp(start)-n*replay.execution_duration(tf)
            assert (digest(point) in plan["negative_control_point_ids"]) == ((parse_timestamp(current["T"])-parse_timestamp(start)).seconds//60 in (0,15,30))
    assert not paths[3].exists()


@pytest.fixture(scope="module", params=["LONG", "SHORT"])
def completed(request, tmp_path_factory):
    root = tmp_path_factory.mktemp("scan-"+request.param)
    paths, data, envelope, plan_path = fixture_plan(root, request.param)
    report_path = root/"report.json"
    report = scan.run_scan(*paths[:2], plan_path, report_path, paths[3])
    return paths, data, envelope, report_path, report


def test_exact_positive_set_and_surrounding_minutes_match_full_route(completed):
    paths, data, sealed, report_path, report = completed
    assert report["status"] == "FINISHED"
    assert report == json.loads(report_path.read_text())
    assert [r["scan"]["possible_c_eq_t"] for r in report["rows"]] == [False,True,False]
    actual = {r["point_id"] for r in report["rows"] if r["scan"]["possible_c_eq_t"]}
    full = set()
    store = SQLiteMissionArchive(paths[3])
    for row in report["rows"]:
        v = row["verification"]
        assert v["status"].startswith("MATCH_") and not v["differences"]
        assert all(v["comparison"].values())
        if v["candidate"] and v["candidate"]["valid_from"] == row["T"]:
            full.add(row["point_id"])
        for step in v["missions"]:
            assert store.get(step["mission_id"]).record_sha256 == step["record_sha256"]
        if v["candidate"]:
            assert v["candidate"]["execution"] is False
            assert all(x is False for x in v["candidate"]["authority"].values())
    assert actual == full and len(full) == 1
    assert report["rows"][1]["verification"]["scenario"]["reference_result"]["lower_r"] == dict(numerator=3,denominator=1)
    assert report["rows"][2]["verification"]["backtest_status"] == "SKIPPED_C_NE_T"
    assert report["counts"]["verification"]["MATCH_CANDIDATE"] == 2
    assert all(v is False for v in report["authority"].values()) and report["execution"] is False


def test_post_T_isolation_and_native_input_identity(completed):
    paths, data, sealed, _, report = completed
    point = sealed["plan"]["batch_plan"]["points"][1]
    histories = data.histories
    at = parse_timestamp(point["run"]["T"])
    for c in histories["M1"]:
        if parse_timestamp(c["timestamp"]) >= at:
            c.update(open=1000.,high=1001.,low=999.,close=1000.)
    from dataclasses import replace
    changed = replace(data, _histories_json=json.dumps(histories))
    assert scan.scan_point(changed,point) == report["rows"][1]["scan"]


@pytest.mark.parametrize("change", ["hash", "dataset", "manifest", "profile", "versions", "controls", "windows"])
def test_changed_plan_fails_before_analysis_or_report(tmp_path, monkeypatch, change):
    paths, data, sealed, plan_path = fixture_plan(tmp_path)
    plan = sealed["plan"]
    if change == "hash": sealed["plan_sha256"] = "0"*64
    elif change == "dataset": plan["batch_plan"]["dataset_sha256"] = "0"*64
    elif change == "manifest": plan["batch_plan"]["manifest_sha256"] = "0"*64
    elif change == "profile": plan["batch_plan"]["profile_json"] += " "
    elif change == "versions": plan["batch_plan"]["native_versions"]["strategy"] = "unknown"
    elif change == "controls": plan["negative_control_point_ids"] = []
    else: plan["batch_plan"]["points"][0]["timeframe_starts"]["M1"] = "2026-01-01T00:00:00Z"
    if change != "hash": sealed["plan_sha256"] = digest(plan)
    plan_path.write_text(json.dumps(sealed))
    def forbidden(*a, **k): raise AssertionError("Bad plan reached native calculation")
    monkeypatch.setattr(scan,"scan_point",forbidden)
    with pytest.raises(ValueError): scan.run_scan(*paths[:2],plan_path,tmp_path/"report.json",paths[3])
    assert not (tmp_path/"report.json").exists() and not paths[3].exists()


def test_changed_scan_result_cannot_trigger_verification(completed,monkeypatch):
    paths,data,sealed,_,report = completed
    point = sealed["plan"]["batch_plan"]["points"][1]
    changed = deepcopy(report["rows"][1]["scan"])
    changed["assessment"]["completion_identity"] = "forged"
    def forbidden(*a, **k): raise AssertionError("Tampered scan invoked executor")
    monkeypatch.setattr(replay,"replay_loaded",forbidden)
    assert scan.verify_point(data,point,changed,paths[3])["status"] == "MISMATCH"


def test_official_result_disagreement_is_reported(completed,monkeypatch):
    paths,data,sealed,_,report = completed
    original = scan.scan_point
    def consistent_but_wrong(*a,**k):
        scanned = original(*a,**k)
        scanned["source_snapshot_ids"]["M30"] = "different"
        return scanned
    monkeypatch.setattr(scan,"scan_point",consistent_but_wrong)
    point = sealed["plan"]["batch_plan"]["points"][0]
    result = scan.verify_point(data,point,scan.scan_point(data,point),paths[3])
    assert result["status"] == "MISMATCH" and result["differences"] == ["source_snapshot_ids"]


@pytest.mark.parametrize("approval", [False, True])
def test_deny_is_fresh_and_not_a_match(tmp_path,monkeypatch,approval):
    paths,data,sealed,plan_path = fixture_plan(tmp_path)
    def forbidden(*a,**k): raise AssertionError("Denied governance invoked executor")
    monkeypatch.setattr(LocalExecutionRuntime,"execute",forbidden)
    policy = replay.local_policy() if approval else ExecutionPolicy("deny",1)
    if approval:
        for rule in policy.rules: rule.decision = PolicyDecision.REQUIRE_APPROVAL
    report = scan.run_scan(*paths[:2],plan_path,tmp_path/"report.json",paths[3],policy=policy)
    assert report["status"] == "FINISHED_WITH_ERRORS"
    assert all(r["verification"]["status"] == "VERIFICATION_DENIED" for r in report["rows"])
    assert all(r["verification"]["missions"][0]["status"] == ("awaiting_approval" if approval else "rejected") for r in report["rows"])


def test_storage_failure_aborts_verifications_without_losing_scan_points(tmp_path,monkeypatch):
    paths,data,sealed,plan_path = fixture_plan(tmp_path)
    calls=[]
    def fail(*a,**k):
        calls.append(True)
        raise OSError("offline")
    monkeypatch.setattr(SQLiteMissionArchive,"save",fail)
    report = scan.run_scan(*paths[:2],plan_path,tmp_path/"report.json",paths[3])
    assert report["status"] == "ABORTED" and len(calls) == 1
    assert [r["verification"]["status"] for r in report["rows"]] == ["ARCHIVE_FAILED","NOT_RUN_ABORTED","NOT_RUN_ABORTED"]
    assert all(r["scan"] for r in report["rows"])


@pytest.mark.parametrize("phase", ["during_replay", "after_replay"])
def test_archive_read_failure_preserves_collected_mission_references(tmp_path, monkeypatch, phase):
    paths, _, _, plan_path = fixture_plan(tmp_path)
    original_replay, original_get = replay.replay_loaded, SQLiteMissionArchive.get
    original_execute = LocalExecutionRuntime.execute
    state = dict(replays=0, executions=0, armed=False, report=None, expected=None)
    seen = set()

    def execute(*args, **kwargs):
        state["executions"] += 1
        return original_execute(*args, **kwargs)

    def replay_once(*args, **kwargs):
        state["replays"] += 1
        # Observe the replay's existing progress channel, including pre-read IDs.
        state["report"] = kwargs.setdefault("report", {})
        result = original_replay(*args, **kwargs)
        state["armed"] = True
        state["expected"] = deepcopy(result["missions"])
        return result

    def read(store, mission_id):
        second_mission = bool(seen) and mission_id not in seen
        if state["armed"] or (phase == "during_replay" and second_mission):
            state["expected"] = deepcopy(state["report"]["missions"])
            raise OSError("injected archive read failure")
        seen.add(mission_id)
        return original_get(store, mission_id)

    monkeypatch.setattr(LocalExecutionRuntime, "execute", execute)
    monkeypatch.setattr(replay, "replay_loaded", replay_once)
    monkeypatch.setattr(SQLiteMissionArchive, "get", read)
    report_path = tmp_path/"report.json"
    report = scan.run_scan(*paths[:2], plan_path, report_path, paths[3])
    assert report == json.loads(report_path.read_text())
    assert report["status"] == "ABORTED"
    assert state["replays"] == 1 and state["executions"] == 2
    assert len(state["expected"]) == 2
    assert state["expected"][0]["record_sha256"] is not None
    if phase == "after_replay":
        assert all(m["record_sha256"] is not None for m in state["expected"])
    assert report["rows"][0]["verification"]["missions"] == state["expected"]
    assert [r["verification"]["status"] for r in report["rows"]] == [
        "ARCHIVE_FAILED", "NOT_RUN_ABORTED", "NOT_RUN_ABORTED"]
    assert report["counts"]["verified_c_eq_t_candidates"] == 0
    assert not any(status.startswith("MATCH_") for status in report["counts"]["verification"])


def test_native_errors_and_unavailable_remain_distinct(tmp_path,monkeypatch):
    paths,data,sealed,plan_path = fixture_plan(tmp_path)
    original = scan.scan_point
    def fail_first(dataset,point):
        if point == sealed["plan"]["batch_plan"]["points"][0]: raise ValueError("malformed")
        return original(dataset,point)
    monkeypatch.setattr(scan,"scan_point",fail_first)
    report = scan.run_scan(*paths[:2],plan_path,tmp_path/"report.json",paths[3],policy=ExecutionPolicy("deny",1))
    assert len(report["rows"]) == 3 and report["rows"][0]["status"] == "TECHNICAL_ERROR"
    assert report["rows"][0]["verification"]["status"] == "NOT_RUN_SCAN_ERROR"
    native = data.histories
    native["H1"] = []
    from dataclasses import replace
    missing = replace(data,_histories_json=json.dumps(native))
    result = original(missing,sealed["plan"]["batch_plan"]["points"][1])
    assert result["source_availability"]["H1"] == "UNAVAILABLE"
    assert result["assessment"]["status"] == "UNKNOWN" and not result["possible_c_eq_t"]


def test_late_declaration_is_preserved_and_reference_remains_censored(tmp_path):
    paths,data,sealed,_ = fixture_plan(tmp_path)
    point = deepcopy(sealed["plan"]["batch_plan"]["points"][1])
    point["run"]["relationship_available_at"] = point["run"]["K"]
    scanned = scan.scan_point(data,point)
    result = scan.verify_point(data,point,scanned,paths[3])
    assert result["status"] == "MATCH_CANDIDATE"
    assert result["scenario"]["completion_status"] == "MISSING_DATA_CENSORED"
    assert result["scenario"]["reference_result"] is None
    assert result["scenario"]["reconstruction"]["evidence"]["declarations"][0]["available_at"] == point["run"]["K"]
