"""Native discovery must agree with independently governed archived replay."""
from copy import deepcopy
import csv
from datetime import timedelta
import hashlib
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
    # Captured from the unchanged f7509d9 generator before --schedule.
    assert sealed["plan_sha256"] == "c30f0442354daa860ae2322970417a7111b793492b67af69d7e2bf596aef07e7"
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
    diagnostics = scan.preparation_h4_diagnostics(data, plan["batch_plan"])
    assert diagnostics["counts"] == {"UNKNOWN": 3}
    assert all(row["reason"] == "MISSING_CONTIGUOUS_H4" for row in diagnostics["blocks"])


@pytest.fixture
def schedule_inputs(tmp_path, monkeypatch):
    """Continuous synthetic grid for preparation only; no market setup selection."""
    paths = replay.write_demo_dataset(tmp_path)
    profile = json.loads(paths[2].read_text())
    profile["K"] = profile["relationship_available_at"] = "2026-11-01T00:00:00Z"
    paths[2].write_text(json.dumps(profile))
    left, right = parse_timestamp("2025-12-31T00:00:00Z"), parse_timestamp("2026-01-03T05:00:00Z")
    with paths[0].open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timeframe", "timestamp", "open", "high", "low", "close"])
        writer.writeheader()
        for tf in replay.WARMUP:
            tick = left
            while tick+replay.execution_duration(tf) <= right:
                writer.writerow(dict(timeframe=tf, timestamp=stamp(tick), open=100, high=101, low=99, close=100))
                tick += replay.execution_duration(tf)
    manifest = json.loads(paths[1].read_text())
    manifest.update(csv_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        timeframes={tf: dict(anchor=stamp(left), coverage_start=stamp(left), coverage_end=stamp(right)) for tf in replay.WARMUP},
        sessions=[dict(open=stamp(left), close=stamp(right))])
    paths[1].write_text(json.dumps(manifest))
    schedule = dict(contract=scan.SCHEDULE_CONTRACT, blocks=[dict(
        founding_start=start, founding_end=stamp(parse_timestamp(start)+timedelta(minutes=n)),
        measurement_step_seconds=60, directions=["LONG", "SHORT"], control_offsets_minutes=[0,n//2,n])
        for start,n in (("2026-01-02T00:00:00Z",2),("2026-01-03T04:00:00Z",3))])
    schedule_path = tmp_path/"schedule.json"
    schedule_path.write_text(json.dumps(schedule))
    def forbidden(*a, **k): raise AssertionError("Preparation invoked an analyzer/runtime/archive")
    for owner, method in ((LocalExecutionRuntime,"execute"),(scan.CAUSAL_SNAPSHOT_AVAILABILITY,"analyze"),
                          (SQLiteMissionArchive,"save"),(scan.strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL,"analyze")):
        monkeypatch.setattr(owner,method,forbidden)
    return paths, load_dataset(*paths[:2]), paths[2].read_text(), schedule, schedule_path


def test_schedule_multiple_blocks_determinism_windows_and_observations(schedule_inputs):
    paths, data, raw, schedule, _ = schedule_inputs
    before = deepcopy(schedule)
    sealed = scan.prepare_plan(data,raw,schedule=schedule)
    assert scan.prepare_plan(data,raw,schedule=deepcopy(schedule)) == sealed
    assert schedule == before
    plan = sealed["plan"]
    assert len(plan["batch_plan"]["points"]) == 14 and len(plan["negative_control_point_ids"]) == 12
    assert scan.validate_plan(plan,data) == plan
    for block in schedule["blocks"]:
        start = parse_timestamp(block["founding_start"])
        points = [p for p in plan["batch_plan"]["points"] if p["session_id"] == block["founding_start"]]
        n = (parse_timestamp(block["founding_end"])-start)//timedelta(minutes=1)
        assert [(p["run"]["T"],p["run"]["strategy_definition"]["direction"]) for p in points] == [
            (stamp(start+timedelta(minutes=m)),d) for m in range(n+1) for d in ("LONG","SHORT")]
        for p in points:
            run, config = p["run"], p["run"]["strategy_definition"]["configuration"]
            assert config["founding_end"] == block["founding_end"]
            assert run["K"] == run["relationship_available_at"] == json.loads(raw)["K"]
            assert run["setup_ordinal"] == 0 and run["entry_validity_duration_seconds"] == 120
            for tf,warmup in replay.WARMUP.items():
                assert parse_timestamp(p["timeframe_starts"][tf]) == start-warmup*replay.execution_duration(tf)
            assert (digest(p) in plan["negative_control_point_ids"]) == (
                (parse_timestamp(run["T"])-start)//timedelta(minutes=1) in block["control_offsets_minutes"])
    coverage = scan.preparation_coverage(data,plan["batch_plan"])
    assert all(b["within_session"] and all(not c["missing_open_times"] for c in b["candidate"].values()) for b in coverage)
    assert coverage[-1]["observation_M1"]["missing_open_times"]  # Does not block preparation.
    changed = deepcopy(schedule)
    changed["blocks"][-1].update(founding_end="2026-01-03T04:04:00Z",control_offsets_minutes=[0,2,4])
    assert scan.prepare_plan(data,raw,schedule=changed)["plan_sha256"] != sealed["plan_sha256"]
    assert not paths[3].exists()


def test_prepare_h4_diagnostics_preserves_plan_and_uses_closed_candles(
    schedule_inputs, tmp_path, monkeypatch, capsys,
):
    paths, _, _, schedule, schedule_path = schedule_inputs
    schedule["blocks"][1].update(
        founding_start="2026-01-03T00:00:00Z", founding_end="2026-01-03T00:03:00Z",
    )
    schedule_path.write_text(json.dumps(schedule))
    second_start = parse_timestamp(schedule["blocks"][1]["founding_start"])
    h4_duration = replay.execution_duration("H4")
    with paths[0].open() as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    closed = [(101, 99), (105, 101), (103, 98), (106, 102), (104, 100), (108, 104), (106, 102)]
    for row in rows:
        if row["timeframe"] != "H4":
            continue
        position = (parse_timestamp(row["timestamp"]) - second_start) // h4_duration
        if -len(closed) <= position < 0:
            high, low = closed[position]
        elif position == 0:
            high, low = 1000, 1
        else:
            continue
        midpoint = (high + low) / 2
        row.update(high=high, low=low, open=midpoint, close=midpoint)
    with paths[0].open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = json.loads(paths[1].read_text())
    manifest["csv_sha256"] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    paths[1].write_text(json.dumps(manifest))

    analyzer = scan.MARKET_STRUCTURE.analyze
    calls = []

    def capture(payload):
        calls.append(payload)
        return analyzer(payload)

    monkeypatch.setattr(scan.MARKET_STRUCTURE, "analyze", capture)
    inputs = ["--dataset", str(paths[0]), "--manifest", str(paths[1]),
              "--run", str(paths[2]), "--schedule", str(schedule_path)]
    plain_path, diagnostic_path = tmp_path / "plain.json", tmp_path / "diagnostic.json"
    monkeypatch.setattr(scan.sys, "argv", ["scan", "--prepare", str(plain_path), *inputs])
    assert scan.main() == 0
    assert "h4_diagnostics" not in json.loads(capsys.readouterr().out)
    assert calls == []
    monkeypatch.setattr(scan.sys, "argv", ["scan", "--prepare", str(diagnostic_path), *inputs, "--h4-diagnostics"])
    assert scan.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["points"] == 14
    assert output["controls"] == 12
    assert output["missions_executed"] == 0
    assert plain_path.read_bytes() == diagnostic_path.read_bytes()
    assert not paths[3].exists()

    assert len(calls) == 2
    for payload, block in zip(calls, schedule["blocks"]):
        assert payload["evaluation_time"] == block["founding_start"]
        assert len(payload["candle_history"]) == 12
        assert all(candle["high"] < 1000 for candle in payload["candle_history"])
        assert parse_timestamp(payload["candle_history"][-1]["timestamp"]) + h4_duration == parse_timestamp(
            block["founding_start"]
        )
    diagnostics = output["h4_diagnostics"]
    assert diagnostics["counts"] == {"UNKNOWN": 1, "CLASSIFIED": 1}
    first, second = diagnostics["blocks"]
    assert first["reason"] == "UNRESOLVED_H4" and first["h4_direction"] is None
    assert second["structure_state"] == "bullish_structure" and second["h4_direction"] == "LONG"
    assert (second["latest_high_relationship"], second["latest_low_relationship"]) == ("HH", "HL")


@pytest.mark.parametrize("rule", ["old", "new", "mixed", "wrong", "duplicate", "foreign"])
def test_four_point_control_rule_compatibility(schedule_inputs, tmp_path, rule):
    _, data, raw, schedule, _ = schedule_inputs
    schedule["blocks"] = schedule["blocks"][-1:]  # Four minutes per direction: 0, 1, 2, 3.
    sealed = scan.prepare_plan(data, raw, schedule=schedule)
    plan = sealed["plan"]
    points = plan["batch_plan"]["points"]
    assert len(points) == 8
    lower = [digest(p) for i,p in enumerate(points) if i//2 in (0,1,3)]
    upper = [digest(p) for i,p in enumerate(points) if i//2 in (0,2,3)]
    assert plan["negative_control_point_ids"] == lower
    if rule == "old": plan["negative_control_point_ids"] = upper
    elif rule == "mixed":
        plan["negative_control_point_ids"] = [digest(p) for i,p in enumerate(points)
            if i//2 in ((0,2,3) if p["run"]["strategy_definition"]["direction"] == "LONG" else (0,1,3))]
    elif rule == "wrong": plan["negative_control_point_ids"] = [digest(p) for i,p in enumerate(points) if i//2 in (0,1,2)]
    elif rule == "duplicate": plan["negative_control_point_ids"].append(lower[0])
    elif rule == "foreign": plan["negative_control_point_ids"][0] = "0"*64
    sealed["plan_sha256"] = digest(plan)
    path = tmp_path/"sealed-v1-plan.json"
    replay.atomic_json(path,sealed,create=True)
    loaded = scan.json_text(path.read_text())
    assert digest(loaded["plan"]) == loaded["plan_sha256"]
    if rule in ("old", "new"):
        assert scan.validate_plan(loaded["plan"],data) == plan
    else:
        with pytest.raises(ValueError,match="control point membership"):
            scan.validate_plan(loaded["plan"],data)


def test_legacy_control_plan_still_requires_original_hash(schedule_inputs,tmp_path):
    paths, data, raw, schedule, _ = schedule_inputs
    schedule["blocks"] = schedule["blocks"][-1:]
    sealed = scan.prepare_plan(data,raw,schedule=schedule)
    points = sealed["plan"]["batch_plan"]["points"]
    sealed["plan"]["negative_control_point_ids"] = [digest(p) for i,p in enumerate(points) if i//2 in (0,2,3)]
    sealed["plan_sha256"] = "0"*64
    path = tmp_path/"tampered-hash.json"
    replay.atomic_json(path,sealed,create=True)
    output = tmp_path/"report.json"
    with pytest.raises(ValueError,match="Scan plan hash mismatch"):
        scan.run_scan(*paths[:2],path,output,paths[3])
    assert not output.exists() and not paths[3].exists()


@pytest.mark.parametrize("change", ["contract","empty","too_many","extra","unordered","duplicate","overlap",
    "grid","naive","offset","seconds","short","long","step","directions","controls","bool_control"])
def test_schedule_invalid_inputs_fail(schedule_inputs,change):
    _,data,raw,schedule,_ = schedule_inputs
    b = schedule["blocks"][0]
    if change == "contract": schedule["contract"] = "unknown"
    elif change == "empty": schedule["blocks"] = []
    elif change == "too_many": schedule["blocks"] *= 9
    elif change == "extra": b["approval"] = True
    elif change == "unordered": schedule["blocks"].reverse()
    elif change == "duplicate": schedule["blocks"][1] = deepcopy(b)
    elif change == "overlap": b["founding_end"] = schedule["blocks"][1]["founding_end"]
    elif change == "grid": b["founding_start"] = "2026-01-02T00:01:00Z"
    elif change == "naive": b["founding_start"] = "2026-01-02T00:00:00"
    elif change == "offset": b["founding_start"] = "2026-01-02T01:00:00+01:00"
    elif change == "seconds": b["founding_end"] = "2026-01-02T00:02:01Z"
    elif change == "short": b["founding_end"] = "2026-01-02T00:01:00Z"
    elif change == "long": b["founding_end"] = "2026-01-02T00:31:00Z"
    elif change == "step": b["measurement_step_seconds"] = True
    elif change == "directions": b["directions"].reverse()
    elif change == "controls": b["control_offsets_minutes"] = [0,2]
    else: b["control_offsets_minutes"][0] = False
    with pytest.raises(ValueError): scan.prepare_plan(data,raw,schedule=schedule)


@pytest.mark.parametrize("tf,open_time", [("H4","2025-12-31T00:00:00Z"),("M1","2026-01-02T00:01:00Z")])
def test_schedule_missing_candidate_reports_exact_open_before_publication(schedule_inputs,tmp_path,monkeypatch,capsys,tf,open_time):
    paths,_,_,_,schedule_path = schedule_inputs
    with paths[0].open() as stream:
        reader = csv.DictReader(stream)
        fields,rows = reader.fieldnames,list(reader)
    with paths[0].open("w",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        writer.writerows(r for r in rows if not (r["timeframe"]==tf and r["timestamp"]==open_time))
    manifest = json.loads(paths[1].read_text())
    manifest["csv_sha256"] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    paths[1].write_text(json.dumps(manifest))
    output = tmp_path/"plan.json"
    monkeypatch.setattr(scan.sys,"argv",["scan","--prepare",str(output),"--dataset",str(paths[0]),
        "--manifest",str(paths[1]),"--run",str(paths[2]),"--schedule",str(schedule_path)])
    assert scan.main() == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "PreparationCoverageError"
    assert error["coverage"][0]["block"] == "2026-01-02T00:00:00Z"
    assert error["coverage"][0]["candidate"][tf]["missing_open_times"] == [open_time]
    assert not output.exists() and not paths[3].exists()


def test_schedule_session_boundary_is_rejected(schedule_inputs):
    from dataclasses import replace
    _,data,raw,schedule,_ = schedule_inputs
    manifest = data.manifest
    manifest["sessions"][0]["close"] = schedule["blocks"][0]["founding_end"]
    with pytest.raises(scan.PreparationCoverageError) as exc:
        scan.prepare_plan(replace(data,manifest_json=json.dumps(manifest)),raw,schedule=schedule)
    assert not exc.value.coverage[0]["within_session"]


@pytest.mark.parametrize("target", ["dataset","manifest","run","schedule","existing_output"])
def test_schedule_cli_input_and_output_protection(schedule_inputs,tmp_path,monkeypatch,target):
    paths,_,_,_,schedule_path = schedule_inputs
    existing = tmp_path/"existing-plan.json"; existing.write_bytes(b"keep")
    protected = [*paths[:3],schedule_path,existing]
    before = {p:p.read_bytes() for p in protected}
    output = dict(zip(["dataset","manifest","run","schedule","existing_output"],protected))[target]
    monkeypatch.setattr(scan.sys,"argv",["scan","--prepare",str(output),"--dataset",str(paths[0]),
        "--manifest",str(paths[1]),"--run",str(paths[2]),"--schedule",str(schedule_path)])
    if target == "existing_output": assert scan.main() == 1
    else:
        with pytest.raises(SystemExit) as exc: scan.main()
        assert exc.value.code == 2
    assert all(p.read_bytes()==before[p] for p in protected)


@pytest.mark.parametrize("mode", ["--scan","--demo"])
@pytest.mark.parametrize("option", ["--schedule", "--h4-diagnostics"])
def test_preparation_options_rejected_in_other_modes(monkeypatch, mode, option):
    option_args = ["unused-schedule.json"] if option == "--schedule" else []
    monkeypatch.setattr(scan.sys, "argv", ["scan", mode, "unused", option, *option_args])
    with pytest.raises(SystemExit) as exc: scan.main()
    assert exc.value.code == 2


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
