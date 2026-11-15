"""Predeclared research, native identity counting and fail-closed batch execution."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

from scripts import local_historical_replay as replay
from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading.historical_market_data import load_dataset, ORDER, digest, parse_timestamp, stamp
from ced_one.memory.mission_store import SQLiteMissionArchive, MAX_RECORD_BYTES, ArchiveDataError
from ced_one.mission_control import LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision


def plan_for(paths, offsets=(0,)):
    data = load_dataset(*paths[:2])
    run = json.loads(paths[2].read_text())
    original = parse_timestamp(run["T"])
    run["K"] = stamp(original+timedelta(hours=24, minutes=max(offsets)))
    profile = json.dumps(run)
    starts = {tf: run["strategy_definition"]["configuration"]["history_starts"].get(tf) for tf in ORDER}
    points = []
    for offset in offsets:
        current = deepcopy(run)
        current["T"] = stamp(original+timedelta(minutes=offset))
        points.append(dict(session_id="fixture", run=current, timeframe_starts=deepcopy(starts)))
    plan = replay.batch_plan(data, profile, points)
    return data, plan


def save_plan(root, plan):
    path = root/"batch.json"
    replay.atomic_json(path, dict(plan=plan, plan_sha256=digest(plan)), create=True)
    return path


@pytest.fixture(scope="module")
def positive(tmp_path_factory):
    root = tmp_path_factory.mktemp("batch-native")
    paths = replay.write_demo_dataset(root)
    _, plan = plan_for(paths, (0, 1))
    plan_path = save_plan(root, plan)
    report_path = root/"report.json"
    report = replay.run_batch(*paths[:2], plan_path, paths[3], report_path)
    return paths, plan, report_path, report


def test_first_plan_pins_thirty_points_profile_hash_and_fixed_domains(tmp_path, monkeypatch):
    paths = replay.write_demo_dataset(tmp_path)
    data = load_dataset(*paths[:2])
    profile = json.loads(paths[2].read_text())
    profile["K"] = "2026-11-01T00:00:00Z"
    profile["relationship_available_at"] = profile["K"]
    raw = json.dumps(profile, indent=2)+"\n"
    def forbidden(*a, **k):
        raise AssertionError("Plan preparation executed a mission")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    plan = replay.first_batch_plan(data, raw)
    # Captured from the unchanged db4c3e0 generator before the schedule extension.
    assert digest(plan) == "7fb96a4b416e5f768100229fafcdb125383aec53ab53bc0df12e9e0f15644dec"
    assert len(plan["points"]) == 30
    assert plan["profile_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    for date in replay.FIRST_DATES:
        points = [p for p in plan["points"] if p["session_id"] == date]
        assert [(p["run"]["T"], p["run"]["strategy_definition"]["direction"]) for p in points] == [
            (date+f"T13:0{m}:00Z", d) for m in range(5) for d in ("LONG", "SHORT")]
        for point in points:
            run = point["run"]
            assert run["setup_ordinal"] == 0 and run["entry_validity_duration_seconds"] == 120
            assert run["relationship_available_at"] == profile["relationship_available_at"]
            assert point["timeframe_starts"]["D1"] is None
            assert run["strategy_definition"]["configuration"]["windows_seconds"] == profile["strategy_definition"]["configuration"]["windows_seconds"]
            for tf, n in replay.WARMUP.items():
                assert parse_timestamp(point["timeframe_starts"][tf]) == parse_timestamp(date+"T12:00:00Z")-n*replay.execution_duration(tf)
        assert len({digest(p["timeframe_starts"]) for p in points}) == 1


@pytest.fixture
def scheduled_inputs(tmp_path):
    paths = replay.write_demo_dataset(tmp_path)
    profile = json.loads(paths[2].read_text())
    profile["K"] = "2026-11-01T00:00:00Z"
    profile["relationship_available_at"] = profile["K"]
    paths[2].write_text(json.dumps(profile, indent=2)+"\n")
    schedule = dict(contract=replay.SCHEDULE_CONTRACT, sessions=[
        dict(founding_start="2026-09-16T12:00:00Z", T="2026-09-16T12:30:00Z"),
        dict(founding_start="2026-09-17T16:00:00Z", T="2026-09-17T16:30:00Z"),
        dict(founding_start="2026-09-24T20:00:00Z", T="2026-09-24T20:30:00Z"),
    ])
    return paths, schedule


def test_scheduled_six_points_bind_profile_windows_and_sources(scheduled_inputs, monkeypatch):
    paths, schedule = scheduled_inputs
    data, raw = load_dataset(*paths[:2]), paths[2].read_text()
    profile, original_schedule = json.loads(raw), deepcopy(schedule)
    def forbidden(*a, **k):
        raise AssertionError("Preparation executed a mission")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    plan = replay.scheduled_batch_plan(data, raw, schedule)
    assert schedule == original_schedule
    assert len(plan["points"]) == 6
    assert plan["profile_json"] == raw
    assert plan["profile_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert plan["dataset_sha256"] == data.dataset_sha256
    assert plan["manifest_sha256"] == hashlib.sha256(paths[1].read_bytes()).hexdigest()
    assert replay.validate_batch_plan(plan, data) == plan
    for i, session in enumerate(schedule["sessions"]):
        for j, direction in enumerate(("LONG", "SHORT")):
            point = plan["points"][2*i+j]
            run = point["run"]
            assert point["session_id"] == session["founding_start"]
            assert run["T"] == session["T"]
            assert run["K"] == profile["K"]
            assert run["relationship_available_at"] == profile["relationship_available_at"]
            assert run["setup_ordinal"] == 0 and run["entry_validity_duration_seconds"] == 120
            config = run["strategy_definition"]["configuration"]
            assert config["founding_start"] == session["founding_start"]
            assert config["founding_end"] == session["T"]
            expected = replay.strategy.normalize_strategy_definition(profile["strategy_definition"])
            expected["direction"] = direction
            expected["configuration"].update(history_starts=deepcopy(config["history_starts"]),
                founding_start=session["founding_start"], founding_end=session["T"])
            assert run["strategy_definition"] == expected
            assert point["timeframe_starts"]["D1"] is None
            for tf, count in replay.WARMUP.items():
                assert parse_timestamp(point["timeframe_starts"][tf]) == parse_timestamp(session["founding_start"])-count*replay.execution_duration(tf)
                if tf in replay.strategy.TIMEFRAMES:
                    assert config["history_starts"][tf] == point["timeframe_starts"][tf]
    changed = deepcopy(schedule)
    changed["sessions"][-1]["T"] = "2026-09-24T20:31:00Z"
    assert digest(replay.scheduled_batch_plan(data, raw, changed)) != digest(plan)
    plan["points"][0]["timeframe_starts"]["M1"] = "tampered"
    assert plan["points"][1]["timeframe_starts"]["M1"] != "tampered"


@pytest.mark.parametrize("change", ["contract", "extra", "empty", "too_many", "not_list", "missing_T", "extra_session",
    "reversed_time", "duplicate_start", "unordered", "naive", "seconds", "off_grid", "after_K"])
def test_invalid_schedule_is_rejected(scheduled_inputs, change):
    paths, schedule = scheduled_inputs
    if change == "contract": schedule["contract"] = "unknown"
    elif change == "extra": schedule["approval"] = True
    elif change == "empty": schedule["sessions"] = []
    elif change == "too_many": schedule["sessions"] *= 167
    elif change == "not_list": schedule["sessions"] = {}
    elif change == "missing_T": schedule["sessions"][0].pop("T")
    elif change == "extra_session": schedule["sessions"][0]["direction"] = "LONG"
    elif change == "reversed_time": schedule["sessions"][0]["T"] = "2026-09-16T11:59:00Z"
    elif change == "duplicate_start": schedule["sessions"][1] = deepcopy(schedule["sessions"][0])
    elif change == "unordered": schedule["sessions"].reverse()
    elif change == "naive": schedule["sessions"][0]["T"] = "2026-09-16T12:30:00"
    elif change == "seconds": schedule["sessions"][0]["T"] = "2026-09-16T12:30:01Z"
    elif change == "off_grid": schedule["sessions"][0]["founding_start"] = "2026-09-16T12:01:00Z"
    elif change == "after_K": schedule["sessions"] = [dict(founding_start="2026-11-01T12:00:00Z", T="2026-11-01T12:30:00Z")]
    with pytest.raises(ValueError):
        replay.scheduled_batch_plan(load_dataset(*paths[:2]), paths[2].read_text(), schedule)


@pytest.mark.parametrize("scheduled", [False, True])
def test_prepare_cli_and_batch_dispatch_without_execution(scheduled_inputs, monkeypatch, capsys, scheduled):
    paths, schedule = scheduled_inputs
    root = paths[0].parent
    schedule_path, plan_path = root/"schedule.json", root/"prepared.json"
    schedule_path.write_text(json.dumps(schedule))
    argv = ["local_historical_replay.py", "--prepare-batch", str(plan_path), "--dataset", str(paths[0]),
            "--manifest", str(paths[1]), "--run", str(paths[2])]
    if scheduled:
        argv += ["--schedule", str(schedule_path)]
    def forbidden(*a, **k):
        raise AssertionError("CLI preparation executed a mission")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    monkeypatch.setattr(replay.sys, "argv", argv)
    assert replay.main() == 0
    summary = json.loads(capsys.readouterr().out)
    sealed = json.loads(plan_path.read_text())
    assert summary["missions_executed"] == 0
    assert summary["points"] == (6 if scheduled else 30)
    assert summary["plan_sha256"] == sealed["plan_sha256"] == digest(sealed["plan"])
    if not scheduled:
        assert sealed["plan_sha256"] == "7fb96a4b416e5f768100229fafcdb125383aec53ab53bc0df12e9e0f15644dec"
    assert not paths[3].exists()
    assert not list(root.glob("report*.json"))
    original = plan_path.read_bytes()
    assert replay.main() == 1  # Exclusive publication must preserve an existing sealed plan.
    assert plan_path.read_bytes() == original
    calls = []
    def dispatch(*args):
        calls.append(args)
        return dict(status="FINISHED", plan_sha256=sealed["plan_sha256"], counts={}, rows=[])
    monkeypatch.setattr(replay, "run_batch", dispatch)
    report_path = root/"report.json"
    monkeypatch.setattr(replay.sys, "argv", ["local_historical_replay.py", "--batch", str(plan_path),
        "--dataset", str(paths[0]), "--manifest", str(paths[1]), "--archive", str(paths[3]), "--report", str(report_path)])
    assert replay.main() == 0
    assert calls == [(str(paths[0]), str(paths[1]), str(plan_path), str(paths[3]), str(report_path))]


def test_schedule_cli_restricts_mode_and_protects_input(scheduled_inputs, monkeypatch):
    paths, schedule = scheduled_inputs
    path = paths[0].parent/"schedule.json"
    path.write_text(json.dumps(schedule))
    original = path.read_bytes()
    monkeypatch.setattr(replay.sys, "argv", ["replay", "--schedule", str(path)])
    with pytest.raises(SystemExit) as error:
        replay.main()
    assert error.value.code == 2
    monkeypatch.setattr(replay.sys, "argv", ["replay", "--prepare-batch", str(path), "--schedule", str(path),
        "--dataset", str(paths[0]), "--manifest", str(paths[1]), "--run", str(paths[2])])
    with pytest.raises(SystemExit) as error:
        replay.main()
    assert error.value.code == 2 and path.read_bytes() == original


def test_schedule_normalizes_explicit_offsets_and_distinguishes_same_day_domains(scheduled_inputs):
    paths, schedule = scheduled_inputs
    schedule["sessions"] = [dict(founding_start="2026-09-16T14:00:00+02:00", T="2026-09-16T14:30:00+02:00"),
                            dict(founding_start="2026-09-16T16:00:00Z", T="2026-09-16T16:30:00Z")]
    plan = replay.scheduled_batch_plan(load_dataset(*paths[:2]), paths[2].read_text(), schedule)
    assert [p["session_id"] for p in plan["points"]] == ["2026-09-16T12:00:00Z"]*2+["2026-09-16T16:00:00Z"]*2
    assert plan["points"][0]["run"]["T"] == "2026-09-16T12:30:00Z"


@pytest.mark.parametrize("change", ["dataset", "manifest", "profile", "version", "duplicate", "moving_window", "changed_strategy", "backdated", "boolean_ordinal"])
def test_invalid_entire_plan_rejects_before_first_mission(tmp_path, monkeypatch, change):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths, (0, 1))
    if change == "dataset": plan["dataset_sha256"] = "0"*64
    elif change == "manifest": plan["manifest_sha256"] = "0"*64
    elif change == "profile": plan["profile_json"] += " "
    elif change == "version": plan["native_versions"]["reference"] = "unknown"
    elif change == "duplicate": plan["points"].append(deepcopy(plan["points"][0]))
    elif change == "moving_window":
        point = plan["points"][1]
        point["timeframe_starts"]["M1"] = stamp(parse_timestamp(point["timeframe_starts"]["M1"])-timedelta(minutes=1))
        point["run"]["strategy_definition"]["configuration"]["history_starts"]["M1"] = point["timeframe_starts"]["M1"]
    elif change == "changed_strategy": plan["points"][0]["run"]["strategy_definition"]["configuration"]["windows_seconds"]["E1"] += 1
    elif change == "backdated": plan["points"][0]["run"]["relationship_available_at"] = "2026-01-01T00:00:00Z"
    else: plan["points"][0]["run"]["setup_ordinal"] = False
    path = save_plan(tmp_path, plan)
    def forbidden(*a, **k): raise AssertionError("Invalid plan reached execution")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    with pytest.raises(ValueError):
        replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    assert not paths[3].exists() and not (tmp_path/"report.json").exists()


def test_native_positive_r_c_ne_t_and_deduplication(positive):
    paths, plan, report_path, report = positive
    first, second = report["rows"]
    assert report == json.loads(report_path.read_text())
    assert report["plan_sha256"] == digest(plan)
    assert [first["status"], second["status"]] == ["RESOLVED", "SKIPPED_C_NE_T"]
    assert len(first["result"]["missions"]) == 3 and len(second["result"]["missions"]) == 2
    assert first["result"]["scenario"]["reference_result"]["lower_r"] == dict(numerator=3, denominator=1)
    assert second["result"]["candidate"] is not None and second["result"]["scenario"] is None
    assert report["counts"]["unique_setups"] == report["counts"]["unique_completions"] == report["counts"]["unique_backtests"] == 1
    assert list(report["counts"]["setup_observations"].values()) == [2]
    assert list(report["counts"]["completion_observations"].values()) == [2]
    store = SQLiteMissionArchive(paths[3])
    for row in report["rows"]:
        assert row["result"]["execution"] is False
        assert all(v is False for v in row["result"]["authority"].values())
        previous = None
        for step in row["result"]["missions"]:
            record = store.get(step["mission_id"])
            assert record.record_sha256 == step["record_sha256"]
            assert 0 < step["record_bytes"] <= MAX_RECORD_BYTES == 67108864
            if previous:
                selection = record.request.context["selection"]
                assert (selection["source_mission_id"], selection["record_sha256"]) == (previous.mission_id, previous.record_sha256)
            previous = record
    last = first["result"]["missions"][-1]
    record = store.get(last["mission_id"])
    assert replay.reference.validate_reference_scenario(record.result.result_payload["scenario"], record.result.result_payload["reconstruction"]) == first["result"]["scenario"]


@pytest.mark.parametrize("failure", ["io", "size"])
def test_storage_failure_aborts_remaining_points_without_retry(tmp_path, monkeypatch, failure):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths, (0, 1))
    path = save_plan(tmp_path, plan)
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise OSError("offline") if failure == "io" else ArchiveDataError()
    monkeypatch.setattr(SQLiteMissionArchive, "save", fail)
    report = replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    assert [r["status"] for r in report["rows"]] == ["ARCHIVE_FAILED", "NOT_RUN_ABORTED"]
    assert report["status"] == "ABORTED" and len(calls) == 1
    assert len(report["rows"][0]["result"]["missions"]) == 1
    assert report["rows"][1]["result"] == {}


@pytest.mark.parametrize("approval", [False, True])
def test_fresh_current_governance_and_durable_plan_before_execution(tmp_path, monkeypatch, approval):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths)
    path, report_path = save_plan(tmp_path, plan), tmp_path/"report.json"
    policy = replay.local_policy() if approval else ExecutionPolicy("deny", 1)
    if approval:
        for rule in policy.rules: rule.decision = PolicyDecision.REQUIRE_APPROVAL
    original = replay.MissionControlService.handle_request
    def check(service, *args, **kwargs):
        persisted = json.loads(report_path.read_text())
        assert persisted["plan_sha256"] == digest(plan)
        assert persisted["rows"][0]["status"] == "RUNNING"
        return original(service, *args, **kwargs)
    def forbidden(*a, **k): raise AssertionError("Denied mission reached analyzer")
    monkeypatch.setattr(replay.MissionControlService, "handle_request", check)
    monkeypatch.setattr(execution.CAUSAL_SNAPSHOT_AVAILABILITY, "analyze", forbidden)
    report = replay.run_batch(*paths[:2], path, paths[3], report_path, policy=policy)
    assert report["rows"][0]["status"] == "MISSION_FAILED"
    step = report["rows"][0]["result"]["missions"][0]
    assert step["status"] == ("awaiting_approval" if approval else "rejected")


def test_plan_hash_mismatch_and_existing_report_never_execute(tmp_path, monkeypatch):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths)
    path = save_plan(tmp_path, plan)
    envelope = json.loads(path.read_text())
    envelope["plan_sha256"] = "0"*64
    path.write_text(json.dumps(envelope))
    def forbidden(*a, **k): raise AssertionError("Invalid/reused batch reached execution")
    monkeypatch.setattr(LocalExecutionRuntime, "execute", forbidden)
    with pytest.raises(ValueError, match="hash mismatch"):
        replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    envelope["plan_sha256"] = digest(plan)
    path.write_text(json.dumps(envelope))
    (tmp_path/"report.json").write_text("preserved")
    with pytest.raises(FileExistsError):
        replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    assert (tmp_path/"report.json").read_text() == "preserved"


@pytest.mark.parametrize("failure", [ValueError, RuntimeError])
def test_technical_error_is_reported_and_next_independent_point_is_accounted(tmp_path, monkeypatch, failure):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths, (0, 1))
    path = save_plan(tmp_path, plan)
    def fail(dataset, run, archive_path, **kwargs):
        raise failure("Bad native input")
    monkeypatch.setattr(replay, "replay_loaded", fail)
    report = replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    assert report["counts"]["statuses"] == {"TECHNICAL_ERROR": 2}


def test_actual_archive_serializer_rejects_oversized_record_and_aborts(tmp_path, monkeypatch):
    paths = replay.write_demo_dataset(tmp_path)
    _, plan = plan_for(paths, (0, 1))
    path = save_plan(tmp_path, plan)
    original = SQLiteMissionArchive.save
    calls = []
    def oversized(store, request, result, policy):
        calls.append(True)
        result.metadata["padding"] = "x"*MAX_RECORD_BYTES
        return original(store, request, result, policy)
    monkeypatch.setattr(SQLiteMissionArchive, "save", oversized)
    report = replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    assert [r["status"] for r in report["rows"]] == ["ARCHIVE_FAILED", "NOT_RUN_ABORTED"]
    assert len(calls) == 1 and not paths[3].exists()


def test_coverage_counts_gaps_and_declared_closures_without_filling(tmp_path):
    from tests.test_historical_market_data import change_csv
    paths = replay.write_demo_dataset(tmp_path)
    data, plan = plan_for(paths)
    before = replay.point_coverage(data, plan["points"][0])
    missing = data.histories["M1"][2]["timestamp"]
    change_csv(paths, lambda value: "\n".join(line for line in value.splitlines() if ","+missing+"," not in line)+"\n")
    data = load_dataset(*paths[:2])
    after = replay.point_coverage(data, plan["points"][0])
    assert after["M1"]["expected"] == before["M1"]["expected"]
    assert after["M1"]["missing"] == before["M1"]["missing"]+1
    assert after["D1"] == {"absent_by_plan": True}


def test_h1_confirmation_needs_closed_neighbour_and_does_not_erase_early_unknown():
    from tests.test_xauusd_causal_liquidity_reversal import scenario, request, candle, ts
    from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
    from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer
    definition, histories = scenario()
    for i, bar in enumerate(histories["H1"]):
        bar["low"] = 90.+i
    histories["H1"][-1]["low"] = 90.
    histories["H1"].append(candle(0, 125, 130, 95, 126))
    def structure(at, rows):
        return MarketStructureAnalyzer().analyze(dict(symbol="XAUUSD", timeframe="H1",
            evaluation_time=ts(at), candle_history=rows)).to_dict()
    assert structure(0, histories["H1"][:-1])["evidence"]["swing_lows"] == []
    assert structure(60, histories["H1"])["evidence"]["swing_lows"][-1]["timestamp"] == ts(-60)
    assessment = strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(request(definition, histories, at=60)).to_dict()
    assert assessment["status"] == "UNKNOWN" and assessment["reason"] == "NO_CONFIRMED_CA1"
    assert assessment["status_boundary"] == ts(0)


@pytest.mark.parametrize("case", ["waiting", "unknown", "late"])
def test_native_nonpositive_results_remain_explicit(tmp_path, case):
    from tests.test_historical_market_data import change_csv
    paths = replay.write_demo_dataset(tmp_path)
    data, plan = plan_for(paths)
    if case == "waiting":
        plan["points"][0]["run"]["setup_ordinal"] = 1
    elif case == "unknown":
        missing = data.histories["M1"][2]["timestamp"]
        change_csv(paths, lambda value: "\n".join(line for line in value.splitlines() if ","+missing+"," not in line)+"\n")
        data = load_dataset(*paths[:2])
        plan["dataset_sha256"] = data.dataset_sha256
        plan["manifest_sha256"] = hashlib.sha256(data.manifest_json.encode()).hexdigest()
    else:
        profile = json.loads(plan["profile_json"])
        profile["relationship_available_at"] = profile["K"]
        raw = json.dumps(profile)
        plan["profile_json"], plan["profile_sha256"] = raw, hashlib.sha256(raw.encode()).hexdigest()
        plan["points"][0]["run"]["relationship_available_at"] = profile["K"]
    path = save_plan(tmp_path, plan)
    report = replay.run_batch(*paths[:2], path, paths[3], tmp_path/"report.json")
    row = report["rows"][0]
    assert row["status"] == {"waiting": "WAITING", "unknown": "UNKNOWN", "late": "MISSING_DATA_CENSORED"}[case]
    if case != "late":
        assert row["result"]["candidate"] is None and row["result"]["scenario"] is None
        assert len(row["result"]["missions"]) == 2
    else:
        assert row["result"]["scenario"]["reference_result"] is None
        record = SQLiteMissionArchive(paths[3]).get(row["result"]["missions"][-1]["mission_id"])
        assert record.result.result_payload["reconstruction"]["evidence"]["declarations"][0]["available_at"] == profile["K"]
