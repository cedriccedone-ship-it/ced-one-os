"""Local native candidate discovery, followed by fresh governed verification."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import local_historical_replay as replay
from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY, validate_source
from ced_one.business_divisions.trading.historical_market_data import (
    ORDER, digest, exact, json_text, load_dataset, parse_timestamp, read_bytes, stamp,
)
from ced_one.memory.mission_store import ArchiveError, SQLiteMissionArchive, MAX_RECORD_BYTES

CONTRACT = "trading.historical_candidate_scan.v1"
STARTS = ("2026-09-18T12:00:00Z", "2026-09-23T16:00:00Z", "2026-09-25T20:00:00Z")
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)


def seal_plan(dataset, batch, controls):
    plan = dict(contract=CONTRACT, batch_plan=batch, negative_control_point_ids=list(controls),
                diagnostic_contract=strategy.DIAGNOSTIC_CONTRACT)
    validate_plan(plan, dataset)
    return dict(plan=plan, plan_sha256=digest(plan))


def prepare_plan(dataset, profile_text):
    schedule = dict(contract=replay.SCHEDULE_CONTRACT, sessions=[
        dict(founding_start=s, T=stamp(parse_timestamp(s)+timedelta(minutes=30))) for s in STARTS])
    base = replay.scheduled_batch_plan(dataset, profile_text, schedule)
    points, controls = [], []
    for i, start in enumerate(STARTS):
        for minute in range(31):
            for template in base["points"][2*i:2*i+2]:
                point = deepcopy(template)
                point["run"]["T"] = stamp(parse_timestamp(start)+timedelta(minutes=minute))
                points.append(point)
                if minute in (0, 15, 30):
                    controls.append(digest(point))
    return seal_plan(dataset, replay.batch_plan(dataset, profile_text, points), controls)


def validate_plan(plan, dataset):
    exact(plan, {"contract", "batch_plan", "negative_control_point_ids", "diagnostic_contract"}, "Scan plan")
    if plan["contract"] != CONTRACT or plan["diagnostic_contract"] != strategy.DIAGNOSTIC_CONTRACT:
        raise ValueError("Unsupported scan/diagnostic version")
    batch = replay.validate_batch_plan(plan["batch_plan"], dataset)
    ids = [digest(p) for p in batch["points"]]
    controls = plan["negative_control_point_ids"]
    groups = {}
    for point in batch["points"]:
        key = point["session_id"], point["run"]["strategy_definition"]["direction"]
        groups.setdefault(key, []).append(point)
    expected = set()
    for group in groups.values():
        ordered = sorted(group, key=lambda p: parse_timestamp(p["run"]["T"]))
        expected.update(digest(ordered[i]) for i in (0, len(ordered)//2, len(ordered)-1))
    if (type(controls) is not list or any(type(k) is not str or k not in ids for k in controls) or
            len(set(controls)) != len(controls) or set(controls) != expected):
        raise ValueError("Invalid control point membership")
    return deepcopy(plan)


def assessment_input(dataset, point):
    run = point["run"]
    factual = dataset.factual_input(run["T"], run["strategy_definition"], timeframe_starts=point["timeframe_starts"])
    sources = {}
    for tf in ORDER:
        source = validate_source(CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe=tf,
            requested_evaluation_timestamp=run["T"], candle_history=factual["timeframe_histories"][tf])).to_dict())
        if source["source_availability"] == "INVALID":
            raise ValueError("Invalid causal source")
        sources[tf] = source
    native = dict(strategy_definition=strategy.normalize_strategy_definition(run["strategy_definition"]), as_of=run["T"], setup_ordinal=run["setup_ordinal"],
                  sources={tf: deepcopy(sources[tf]) for tf in strategy.TIMEFRAMES})
    return native, sources


def scan_point(dataset, point):
    native, sources = assessment_input(dataset, point)
    diagnosed = strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze_with_diagnostics(native)
    assessment = strategy.validate_strategy_assessment(diagnosed["assessment"], native)
    possible = (assessment["status"] == "COMPLETE" and
                parse_timestamp(assessment["bindings"]["T1"]["available_at"]) == parse_timestamp(point["run"]["T"]))
    return dict(assessment=assessment, diagnostics=diagnosed["diagnostics"], assessment_input_sha256=digest(native),
        source_snapshot_ids={tf: s["source_snapshot_id"] for tf, s in sources.items()},
        source_sha256={tf: digest(s) for tf, s in sources.items()},
        source_availability={tf: s["source_availability"] for tf, s in sources.items()},
        possible_c_eq_t=possible)


def verify_point(dataset, point, scanned, archive_path, *, policy=None):
    # Reconstruct independently; a changed scan result never selects its own truth.
    if digest(scan_point(dataset, point)) != digest(scanned):
        return dict(status="MISMATCH", differences=["SCAN_RECONSTRUCTION"], missions=[])
    report = {"missions": []}
    try:
        report = replay.replay_loaded(dataset, point["run"], archive_path, policy=policy,
                                      timeframe_starts=point["timeframe_starts"], report=report)
    except (ArchiveError, OSError) as error:
        return dict(status="ARCHIVE_FAILED", error_type=type(error).__name__,
                    missions=deepcopy(report["missions"]))
    result = dict(status="VERIFICATION_FAILED", differences=[], missions=report["missions"],
                  official_outcome=report["outcome"], backtest_status=report["backtest_status"], scenario=report["scenario"])
    if report["stopped_reason"] == "ARCHIVE_FAILED":
        result["status"] = "ARCHIVE_FAILED"
        return result
    if isinstance(report["stopped_reason"], dict):
        result["status"] = "VERIFICATION_DENIED" if any(
            m["status"] in ("rejected", "awaiting_approval") for m in report["missions"]) else "VERIFICATION_FAILED"
        return result
    if len(report["missions"]) < 2:
        return result
    try:
        store = SQLiteMissionArchive(archive_path)
        original = store.get(report["missions"][0]["mission_id"])
        record = store.get(report["missions"][1]["mission_id"])
    except (ArchiveError, OSError) as error:
        result.update(status="ARCHIVE_FAILED", error_type=type(error).__name__)
        return result
    if (record.record_sha256 != report["missions"][1]["record_sha256"] or
            original.record_sha256 != report["missions"][0]["record_sha256"]):
        result.update(status="MISMATCH", differences=["ARCHIVE_HASH"])
        return result
    body = record.result.result_payload
    native = body["reconstruction"]["assessment_input"]
    official_sources = {tf: validate_source(s) for tf, s in original.result.result_payload["evidence"]["sources"].items()}
    official = strategy.validate_strategy_assessment(body["strategy_assessment"], native)
    checks = dict(
        assessment=digest(official) == digest(scanned["assessment"]),
        assessment_input_sha256=digest(native) == scanned["assessment_input_sha256"],
        source_snapshot_ids=body["provenance"]["source_snapshot_ids"] == scanned["source_snapshot_ids"],
        source_sha256={tf: digest(s) for tf, s in official_sources.items()} == scanned["source_sha256"],
        archived_predecessor=(body["provenance"]["source_selection"]["source_mission_id"] == original.mission_id and
                              body["provenance"]["source_selection"]["record_sha256"] == original.record_sha256),
        setup_identity=official["setup_identity"] == scanned["assessment"]["setup_identity"],
        completion_identity=official["completion_identity"] == scanned["assessment"]["completion_identity"],
        T1=digest(official["bindings"].get("T1")) == digest(scanned["assessment"]["bindings"].get("T1")),
        authority=body["authority"] == AUTHORITY and all(v is False for v in body["authority"].values()) and body["execution"] is False)
    result["differences"] = [key for key, ok in checks.items() if not ok]
    result["comparison"] = checks
    result["official_assessment_input_sha256"] = digest(native)
    result["candidate"] = body["candidate"]
    result["status"] = ("MISMATCH" if result["differences"] else "MATCH_CANDIDATE" if body["candidate"] is not None
                        else "MATCH_NOT_FORMULATED" if scanned["possible_c_eq_t"] else "MATCH_NO_CANDIDATE")
    return result


def transitions(rows):
    result, previous = [], {}
    for row in rows:
        scanned = row["scan"]
        if scanned is None:
            summary = dict(status=row["status"], phase="ERROR", reason=row.get("error"), evidence={})
            boundary = row["T"]
        else:
            a = scanned["assessment"]
            events = scanned["diagnostics"]["events"]
            event = events[-1]
            if a["status"] == "WAITING" and len(events) > 1:
                event = events[-2]
            summary = dict(status=a["status"], phase=event["phase"], reason=event["reason"], evidence=event["evidence"])
            boundary = event["boundary"]
        key = row["session_id"], row["direction"]
        signature = digest(summary)
        if previous.get(key) != signature:
            result.append(dict(session_id=key[0], direction=key[1], observed_at_T=row["T"],
                               native_boundary=boundary, **summary))
            previous[key] = signature
    return result


def run_scan(csv_path, manifest_path, plan_path, report_path, archive_path, *, policy=None):
    paths = [Path(p).resolve() for p in (csv_path, manifest_path, plan_path, report_path, archive_path)]
    if len(set(paths)) != 5:
        raise ValueError("Scan input/output paths must be distinct")
    dataset = load_dataset(csv_path, manifest_path)
    envelope = json_text(read_bytes(plan_path).decode("utf-8"))
    exact(envelope, {"plan", "plan_sha256"}, "Sealed scan plan")
    plan = validate_plan(envelope["plan"], dataset)
    if digest(plan) != envelope["plan_sha256"]:
        raise ValueError("Scan plan hash mismatch")
    points = plan["batch_plan"]["points"]
    controls = set(plan["negative_control_point_ids"])
    rows = [dict(point_id=digest(p), session_id=p["session_id"], T=p["run"]["T"],
        direction=p["run"]["strategy_definition"]["direction"], control=digest(p) in controls,
        status="PLANNED", scan=None, verification=dict(status="NOT_RUN", missions=[])) for p in points]
    report = dict(contract=CONTRACT, plan=plan, plan_sha256=digest(plan), status="SCANNING", rows=rows,
        authority=deepcopy(AUTHORITY), execution=False, source_authentication="NOT_VERIFIED",
        archive_max_record_bytes=MAX_RECORD_BYTES, transitions=[], elapsed_seconds=0.)
    replay.atomic_json(report_path, report, create=True)
    began = monotonic()
    def checkpoint():
        report["elapsed_seconds"] = monotonic()-began
        report["transitions"] = transitions(rows)
        report["counts"] = dict(points=len(rows), possible_completions=sum(bool(r["scan"] and r["scan"]["possible_c_eq_t"]) for r in rows),
            unique_native_setups=len({r["scan"]["assessment"]["setup_identity"] for r in rows if r["scan"] and r["scan"]["assessment"]["setup_identity"]}),
            unique_native_completions=len({r["scan"]["assessment"]["completion_identity"] for r in rows if r["scan"] and r["scan"]["assessment"]["completion_identity"]}),
            verified_c_eq_t_candidates=sum(bool(r["scan"] and r["scan"]["possible_c_eq_t"] and r["verification"]["status"] == "MATCH_CANDIDATE") for r in rows),
            statuses=dict(Counter(r["status"] for r in rows)), verification=dict(Counter(r["verification"]["status"] for r in rows)))
        replay.atomic_json(report_path, report)
    for point, row in zip(points, rows):
        try:
            row["scan"] = scan_point(dataset, point)
            missing = any(row["scan"]["source_availability"][tf] == "UNAVAILABLE" for tf in strategy.TIMEFRAMES)
            row["status"] = "UNAVAILABLE" if missing else row["scan"]["assessment"]["status"]
        except Exception as error:
            row.update(status="TECHNICAL_ERROR", error="NATIVE_SCAN_ERROR", error_type=type(error).__name__)
        checkpoint()
    report["status"] = "VERIFYING"
    checkpoint()
    aborted = False
    for point, row in zip(points, rows):
        required = row["control"] or bool(row["scan"] and row["scan"]["possible_c_eq_t"])
        if not required:
            row["verification"]["status"] = "NOT_REQUIRED"
        elif aborted:
            row["verification"]["status"] = "NOT_RUN_ABORTED"
        elif row["scan"] is None:
            row["verification"]["status"] = "NOT_RUN_SCAN_ERROR"
        else:
            try:
                row["verification"] = verify_point(dataset, point, row["scan"], archive_path, policy=policy)
            except (ArchiveError, OSError) as error:
                row["verification"] = dict(status="ARCHIVE_FAILED", error_type=type(error).__name__, missions=[])
            except Exception as error:
                row["verification"] = dict(status="VERIFICATION_FAILED", error_type=type(error).__name__, missions=[])
            aborted = row["verification"]["status"] in ("MISMATCH", "ARCHIVE_FAILED", "VERIFICATION_FAILED")
        checkpoint()
    report["status"] = "ABORTED" if aborted else "FINISHED_WITH_ERRORS" if any(
        r["status"] == "TECHNICAL_ERROR" or r["verification"]["status"] == "VERIFICATION_DENIED" for r in rows) else "FINISHED"
    checkpoint()
    return report


def demo(directory):
    root = Path(directory).resolve()
    repo = Path(__file__).resolve().parents[1]
    if root.exists() or root == repo or repo in root.parents:
        raise ValueError("Demo requires a new directory outside the repository")
    sys.path.insert(0, str(repo))
    output = []
    for direction in ("LONG", "SHORT"):
        paths = replay.write_demo_dataset(root/direction, direction)
        dataset = load_dataset(*paths[:2])
        run = json_text(paths[2].read_text())
        at = parse_timestamp(run["T"])
        run["K"] = stamp(at+timedelta(hours=24, minutes=1))
        raw = json.dumps(run)
        starts = {tf: run["strategy_definition"]["configuration"]["history_starts"].get(tf) for tf in ORDER}
        points = []
        for offset in (-1, 0, 1):
            current = deepcopy(run)
            current["T"] = stamp(at+timedelta(minutes=offset))
            points.append(dict(session_id=direction, run=current, timeframe_starts=deepcopy(starts)))
        sealed = seal_plan(dataset, replay.batch_plan(dataset, raw, points), [digest(p) for p in points])
        plan_path, report_path = root/direction/"scan-plan.json", root/direction/"scan-report.json"
        replay.atomic_json(plan_path, sealed, create=True)
        report = run_scan(*paths[:2], plan_path, report_path, paths[3])
        assert [r["scan"]["possible_c_eq_t"] for r in report["rows"]] == [False, True, False]
        assert all(r["verification"]["status"].startswith("MATCH_") for r in report["rows"])
        output.append(dict(direction=direction, counts=report["counts"], elapsed_seconds=report["elapsed_seconds"],
                           report_bytes=report_path.stat().st_size, report=str(report_path)))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", metavar="PLAN")
    modes.add_argument("--scan", metavar="PLAN")
    modes.add_argument("--demo", metavar="NEW_DIRECTORY")
    for name in ("dataset", "manifest", "run", "report", "archive"):
        parser.add_argument("--"+name)
    args = parser.parse_args()
    try:
        if args.demo:
            if any((args.dataset, args.manifest, args.run, args.report, args.archive)):
                parser.error("--demo requires no file inputs")
            result = demo(args.demo)
        elif args.prepare:
            if not all((args.dataset, args.manifest, args.run)) or args.report or args.archive:
                parser.error("--prepare requires only --dataset, --manifest, --run")
            if Path(args.prepare).resolve() in {Path(p).resolve() for p in (args.dataset, args.manifest, args.run)}:
                parser.error("Plan cannot overwrite an input")
            dataset = load_dataset(args.dataset, args.manifest)
            sealed = prepare_plan(dataset, read_bytes(args.run).decode("utf-8"))
            replay.atomic_json(args.prepare, sealed, create=True)
            result = dict(plan=args.prepare, plan_sha256=sealed["plan_sha256"], points=len(sealed["plan"]["batch_plan"]["points"]),
                          controls=len(sealed["plan"]["negative_control_point_ids"]), missions_executed=0)
        else:
            if not all((args.dataset, args.manifest, args.report, args.archive)) or args.run:
                parser.error("--scan requires --dataset, --manifest, --report, --archive; no --run")
            report = run_scan(args.dataset, args.manifest, args.scan, args.report, args.archive)
            result = dict(status=report["status"], counts=report["counts"], elapsed_seconds=report["elapsed_seconds"],
                          report_bytes=Path(args.report).stat().st_size, report=args.report)
        print(json.dumps(result))
        return 0 if not isinstance(result, dict) or result.get("status", "FINISHED") == "FINISHED" else 1
    except (ValueError, OSError, ArchiveError) as error:
        print(json.dumps(dict(error=type(error).__name__)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
