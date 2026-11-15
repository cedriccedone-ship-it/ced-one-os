"""One local export, three independently governed historical research missions."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
from ced_one.business_divisions.trading import factual_market_context_composition as composition
from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY, validate_source
from ced_one.business_divisions.trading.historical_market_data import (
    CONTRACT, ORDER, digest, exact, json_text, load_dataset, parse_timestamp, read_bytes, stamp,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.memory.mission_store import SQLiteMissionArchive, ArchiveError, serialize_mission, MAX_RECORD_BYTES
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule


def local_policy():
    return ExecutionPolicy("explicit_local_historical_research", 1, rules=[PolicyRule(
        "local_"+name, 1, i, PolicyDecision.ALLOW, division_name="trading",
        specialist_name="factual_market_context_analyst", capability_name=name, permission_scope="read_only",
        adapter_name="local", execution_mode="local", risk_level="low", impact_level="limited")
        for i, name in enumerate(("factual_market_context_composition", execution.STRATEGY_REPLAY_CAPABILITY,
                                 execution.REFERENCE_BACKTEST_CAPABILITY), 1)])


def selection(record, at, capability, contract, rule):
    return dict(mission_id=record.mission_id, record_sha256=record.record_sha256, division="trading",
        capability=capability, contract_id=contract, rule_version=rule, evaluation_time=at,
        created_not_after=stamp(datetime.now(timezone.utc)))


def observation_profile(dataset, candidate_record, run):
    """Bind the original candidate and distinct export observations; never infer availability."""
    body = candidate_record.result.result_payload
    formulation, native_input = body["candidate_formulation"], body["reconstruction"]["candidate_input"]
    candidate = formulation["candidate"]
    at = parse_timestamp(run["T"])
    if parse_timestamp(candidate["valid_from"]) != at:
        raise ValueError("C = T is required")
    horizon = at+timedelta(hours=24)
    m = dataset.manifest
    if "M1" not in m["timeframes"]:
        raise ValueError("Observation export has no M1 specification")
    m1 = validate_source(CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="M1",
        requested_evaluation_timestamp=run["K"], candle_history=dataset.observation_rows(run["T"]))).to_dict())
    def ref(source):
        return dict(contract=source["metadata"]["contract"], rule_version=source["metadata"]["rule_version"],
            symbol=source["symbol"], timeframe=source["timeframe"], source_snapshot_id=source["source_snapshot_id"],
            full_artifact_sha256=digest(source))
    spec = m["timeframes"]["M1"]
    declaration = dict(contract=reference.DATASET_RELATIONSHIP_CONTRACT, rule_version=reference.RELATIONSHIP_RULE_VERSION,
        declaration_id=m["dataset_id"], declaration_revision=1, relationship_type=reference.BASE_RELATIONSHIP,
        source_namespace=m["source_namespace"], dataset_revision=m["dataset_revision"], price_domain=m["price_basis"],
        available_at=run["relationship_available_at"],
        subject_bindings=dict(candidate_origin=dict(contract=formulation["contract"], rule_version=formulation["rule_version"],
            candidate_identity=candidate["candidate_identity"], full_artifact_sha256=digest(formulation),
            reconstruction_input_sha256=digest(native_input), original_m1_source=ref(formulation["m1_origin_source"]),
            price_references=["entry_reference", "stop_reference"]), m1=ref(m1)),
        timeframe_grid_bindings=dict(M1=dict(timeframe="M1", anchor_open=stamp(parse_timestamp(spec["anchor"])), duration_seconds=60)),
        coverage_declarations=dict(M1=dict(requested_start=stamp(at-timedelta(minutes=1)), requested_end=stamp(horizon),
            declared_coverage_start=stamp(parse_timestamp(spec["coverage_start"])),
            declared_coverage_end=stamp(parse_timestamp(spec["coverage_end"])), dataset_end=m["dataset_end"])),
        declaration_provenance=dict(declarant_namespace=m["source_namespace"], record_id=dataset.dataset_sha256),
        authority=dict(authenticated_source_truth=False, trade_decision=False, financial_risk=False, execution=False))
    return dict(research_boundary=run["K"], m1=m1, declarations=[declaration])


def validate_run(value):
    run = deepcopy(value)
    exact(run, {"contract", "T", "K", "strategy_definition", "setup_ordinal", "entry_validity_duration_seconds",
                "relationship_available_at"}, "Replay run")
    if run["contract"] != CONTRACT:
        raise ValueError("Unsupported replay run")
    for key in ("T", "K", "relationship_available_at"):
        run[key] = stamp(parse_timestamp(run[key]))
    t, k = parse_timestamp(run["T"]), parse_timestamp(run["K"])
    if not t+timedelta(hours=24) <= k <= datetime.now(timezone.utc) or parse_timestamp(run["relationship_available_at"]) > k:
        raise ValueError("Invalid T/H/K or declaration availability")
    run["strategy_definition"] = strategy.normalize_strategy_definition(run["strategy_definition"])
    if t < parse_timestamp(run["strategy_definition"]["configuration"]["founding_start"]):
        raise ValueError("T precedes founding")
    if type(run["setup_ordinal"]) is not int or run["setup_ordinal"] < 0:
        raise ValueError("Invalid setup ordinal")
    if type(run["entry_validity_duration_seconds"]) is not int or run["entry_validity_duration_seconds"] <= 0:
        raise ValueError("Invalid candidate duration")
    try:
        timedelta(seconds=run["entry_validity_duration_seconds"])
    except OverflowError:
        raise ValueError("Candidate duration is not representable") from None
    return run


def run_replay(csv_path, manifest_path, run_path, archive_path, *, policy=None):
    dataset = load_dataset(csv_path, manifest_path)
    run = validate_run(json_text(read_bytes(run_path).decode("utf-8")))
    return replay_loaded(dataset, run, archive_path, policy=policy)


def replay_loaded(dataset, run, archive_path, *, policy=None, timeframe_starts=None, report=None, checkpoint=None):
    """The existing three missions, with fresh governance for every invocation."""
    run = validate_run(run)
    t = parse_timestamp(run["T"])
    runtime = LocalExecutionRuntime()
    # Registration validates the real strategy configuration before the first mission.
    execution.register_governed_strategy_candidate_replay_executor(runtime, strategy_definition=run["strategy_definition"],
        setup_ordinal=run["setup_ordinal"], entry_validity_duration_seconds=run["entry_validity_duration_seconds"])
    factual = dataset.factual_input(run["T"], run["strategy_definition"], timeframe_starts=timeframe_starts)
    binding = dataset.binding(factual)
    execution.register_factual_market_context_executor(runtime, import_binding=binding)
    store = SQLiteMissionArchive(archive_path)
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=local_policy() if policy is None else policy, archive=store)
    if report is None:
        report = {}
    report.update(dict(import_contract=CONTRACT, dataset_sha256=binding["dataset_sha256"],
        manifest_sha256=binding["manifest_sha256"], imported_at=binding["imported_at"],
        T=run["T"], H=stamp(t+timedelta(hours=24)), K=run["K"],
        source_authentication="NOT_VERIFIED", availability_model="CANDLE_CLOSE_RESEARCH_ASSUMPTION",
        missions=[], candidate=None, scenario=None, assessment=None, authority=None,
        outcome=None, backtest_status="NOT_RUN", stopped_reason=None, execution=False))
    def completed(result):
        step = dict(mission_id=result.request_id, capability=result.capability, status=result.status.value,
            archive=result.metadata.get("archive"), record_sha256=None)
        report["missions"].append(step)
        if checkpoint:
            checkpoint()
        if result.metadata.get("archive") != {"status": "stored"}:
            report["stopped_reason"] = "ARCHIVE_FAILED"
            return None
        record = store.get(result.request_id)
        step["record_sha256"] = record.record_sha256
        step["record_bytes"] = len(serialize_mission(record.request, record.result, record.policy).encode("utf-8"))
        if checkpoint:
            checkpoint()
        if not result.success:
            report["stopped_reason"] = dict(reason="MISSION_FAILED", errors=result.errors,
                execution_failure=result.metadata.get("execution_result", {}).get("failure_reason"))
            return None
        return record
    original = completed(service.handle_request("Compose factual market context", business_division="trading", context=factual))
    if original is None:
        return report
    candidate_record = completed(service.handle_request("Governed strategy candidate replay", business_division="trading",
        archive_selection=selection(original, run["T"], "factual_market_context_composition", composition.CONTRACT, composition.RULE_VERSION)))
    if candidate_record is None:
        return report
    body = candidate_record.result.result_payload
    report["outcome"] = body["outcome"]
    report["assessment"] = body["strategy_assessment"]
    report["authority"] = body["authority"]
    if body["candidate"] is None:
        report["backtest_status"] = "NOT_RUN_NO_CANDIDATE"
        report["stopped_reason"] = body["outcome"]
        report["assessment"] = body["strategy_assessment"]
        return report
    report["candidate"] = body["candidate"]
    if parse_timestamp(body["candidate"]["valid_from"]) != t:
        report["backtest_status"] = "SKIPPED_C_NE_T"
        report["stopped_reason"] = "SKIPPED_C_NE_T"
        return report
    profile = observation_profile(dataset, candidate_record, run)
    execution.register_governed_reference_backtest_executor(runtime, observation_profile=profile, import_binding=dataset.binding(profile))
    backtest = completed(service.handle_request("Governed reference backtest", business_division="trading",
        archive_selection=selection(candidate_record, run["T"], execution.STRATEGY_REPLAY_CAPABILITY,
            execution.STRATEGY_REPLAY_CONTRACT, execution.STRATEGY_REPLAY_RULE)))
    if backtest is not None:
        report["scenario"] = backtest.result.result_payload["scenario"]
        report["backtest_status"] = report["scenario"]["completion_status"]
        report["authority"] = backtest.result.result_payload["authority"]
    return report


BATCH_CONTRACT = "trading.historical_batch_replay.v1"
FIRST_DATES = ("2026-09-16", "2026-09-17", "2026-09-24")
WARMUP = {"H4": 12, "H1": 12, "M30": 8, "M15": 32, "M5": 30, "M1": 60}


def native_versions():
    from ced_one.business_divisions.trading import (
        causal_snapshot_availability as source, causal_multi_timeframe_context as source_context,
        causal_factual_intelligence_envelope as envelope, causal_factual_multi_timeframe_context as context,
        causal_trading_policy_strategy_action_formulation as action, xauusd_technical_trade_candidate as candidate,
    )
    return dict(strategy=strategy.RULE_VERSION, factual_rules=dict(strategy.FACTUAL_RULES),
                source=source.RULE_VERSION, source_context=source_context.RULE_VERSION,
                envelope=envelope.RULE_VERSION, context=context.RULE_VERSION,
                adapters={key: dict(contract=value.contract, rule_version=value.rule_version)
                          for key, value in envelope.ADAPTERS.items()},
                action=action.RULE_VERSION, candidate=candidate.RULE_VERSION,
                composition=composition.RULE_VERSION, reference=reference.RULE_VERSION,
                replay=execution.STRATEGY_REPLAY_RULE, backtest=execution.REFERENCE_BACKTEST_RULE)


def batch_plan(dataset, profile_text, points):
    """Seal an explicit plan; no analyzer, outcome or archive lookup participates."""
    return dict(contract=BATCH_CONTRACT, dataset_sha256=dataset.dataset_sha256,
        manifest_sha256=hashlib.sha256(dataset.manifest_json.encode()).hexdigest(),
        profile_json=profile_text, profile_sha256=hashlib.sha256(profile_text.encode()).hexdigest(),
        native_versions=native_versions(), points=deepcopy(points))


def first_batch_plan(dataset, profile_text):
    profile = validate_run(json_text(profile_text))
    points = []
    for date in FIRST_DATES:
        founding = parse_timestamp(date+"T12:00:00Z")
        starts = {"D1": None, **{tf: stamp(founding-n*execution_duration(tf)) for tf, n in WARMUP.items()}}
        for minute in range(5):
            for direction in ("LONG", "SHORT"):
                run = deepcopy(profile)
                run.update(T=date+f"T13:0{minute}:00Z", setup_ordinal=0, entry_validity_duration_seconds=120)
                definition = run["strategy_definition"]
                definition["direction"] = direction
                definition["configuration"].update(history_starts={tf: starts[tf] for tf in strategy.TIMEFRAMES},
                    founding_start=stamp(founding), founding_end=date+"T13:04:00Z")
                points.append(dict(session_id=date, run=run, timeframe_starts=deepcopy(starts)))
    plan = batch_plan(dataset, profile_text, points)
    validate_batch_plan(plan, dataset)
    return plan


def validate_batch_plan(plan, dataset):
    exact(plan, {"contract", "dataset_sha256", "manifest_sha256", "profile_json", "profile_sha256",
                 "native_versions", "points"}, "Batch plan")
    if (plan["contract"] != BATCH_CONTRACT or plan["dataset_sha256"] != dataset.dataset_sha256 or
            plan["manifest_sha256"] != hashlib.sha256(dataset.manifest_json.encode()).hexdigest() or
            plan["native_versions"] != native_versions() or type(plan["profile_json"]) is not str or
            plan["profile_sha256"] != hashlib.sha256(plan["profile_json"].encode()).hexdigest()):
        raise ValueError("Batch source/profile/version mismatch")
    profile = validate_run(json_text(plan["profile_json"]))
    if type(plan["points"]) is not list or not 1 <= len(plan["points"]) <= 1000:
        raise ValueError("Batch requires 1..1000 explicit points")
    seen, domains = set(), {}
    def invariant(definition):
        value = deepcopy(definition)
        value.pop("direction")
        for key in ("history_starts", "founding_start", "founding_end"):
            value["configuration"].pop(key)
        return digest(value)
    for point in plan["points"]:
        exact(point, {"session_id", "run", "timeframe_starts"}, "Batch point")
        if type(point["session_id"]) is not str or not point["session_id"].strip():
            raise ValueError("Invalid session identity")
        run = validate_run(point["run"])
        if (invariant(run["strategy_definition"]) != invariant(profile["strategy_definition"]) or
                run["K"] != profile["K"] or run["relationship_available_at"] != profile["relationship_available_at"]):
            raise ValueError("Batch must preserve source profile and declaration availability")
        # Also validates auxiliary windows and exact strategy-domain agreement.
        dataset.factual_input(run["T"], run["strategy_definition"], timeframe_starts=point["timeframe_starts"])
        key = (point["session_id"], run["T"], run["strategy_definition"]["direction"], run["setup_ordinal"])
        if key in seen:
            raise ValueError("Duplicate batch point")
        seen.add(key)
        domain = digest(dict(configuration=run["strategy_definition"]["configuration"],
            timeframe_starts=point["timeframe_starts"], duration=run["entry_validity_duration_seconds"]))
        if point["session_id"] in domains and domains[point["session_id"]] != domain:
            raise ValueError("Session windows/profile must remain fixed")
        domains[point["session_id"]] = domain
    return deepcopy(plan)


def atomic_json(path, value, *, create=False):
    """Publish complete external evidence; never silently replace an initial plan/report."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix="."+path.name+"-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if create:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def point_coverage(dataset, point):
    run = point["run"]
    at = parse_timestamp(run["T"])
    histories = dataset.histories
    coverage = {}
    for tf in ORDER:
        left = point["timeframe_starts"][tf]
        if left is None:
            coverage[tf] = dict(absent_by_plan=True)
            continue
        start = parse_timestamp(left)
        duration = execution_duration(tf)
        expected = max(0, (at-start)//duration)
        actual = sum(start <= parse_timestamp(c["timestamp"]) and parse_timestamp(c["timestamp"])+duration <= at
                     for c in histories[tf])
        coverage[tf] = dict(expected=expected, actual=actual, missing=expected-actual)
    coverage["observation_M1"] = dict(expected=1441, actual=len(dataset.observation_rows(run["T"])))
    coverage["declared_sessions_at_T"] = [s for s in dataset.manifest["sessions"]
        if parse_timestamp(s["open"]) <= at < parse_timestamp(s["close"])]
    return coverage


def batch_counts(rows):
    setups, completions, backtests = {}, {}, set()
    statuses = {}
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0)+1
        assessment = row.get("result", {}).get("assessment") or {}
        for key, collection in (("setup_identity", setups), ("completion_identity", completions)):
            if assessment.get(key) is not None:
                identity = assessment[key]
                collection[identity] = collection.get(identity, 0)+1
        if row.get("result", {}).get("scenario") is not None:
            backtests.add(assessment["completion_identity"])
    return dict(planned=len(rows), statuses=statuses, unique_setups=len(setups), unique_completions=len(completions),
        setup_observations=setups, completion_observations=completions, unique_backtests=len(backtests))


def run_batch(csv_path, manifest_path, plan_path, archive_path, report_path, *, policy=None):
    paths = [Path(p).resolve() for p in (csv_path, manifest_path, plan_path, archive_path, report_path)]
    if len(set(paths)) != len(paths):
        raise ValueError("Batch input/output paths must be distinct")
    dataset = load_dataset(csv_path, manifest_path)
    envelope = json_text(read_bytes(plan_path).decode("utf-8"))
    exact(envelope, {"plan", "plan_sha256"}, "Sealed batch")
    plan = validate_batch_plan(envelope["plan"], dataset)
    if digest(plan) != envelope["plan_sha256"]:
        raise ValueError("Batch plan hash mismatch")
    rows = [dict(point_id=digest(p), session_id=p["session_id"], T=p["run"]["T"],
        direction=p["run"]["strategy_definition"]["direction"], setup_ordinal=p["run"]["setup_ordinal"],
        coverage=point_coverage(dataset, p), status="PLANNED", result={}) for p in plan["points"]]
    report = dict(contract=BATCH_CONTRACT, plan_sha256=digest(plan), plan=plan, rows=rows,
        imported_at=dataset.imported_at, archive_max_record_bytes=MAX_RECORD_BYTES,
        source_authentication="NOT_VERIFIED", execution=False, status="PLANNED", counts=batch_counts(rows))
    atomic_json(report_path, report, create=True)  # The entire plan is durable before the first mission.
    def checkpoint():
        report["counts"] = batch_counts(rows)
        atomic_json(report_path, report)
    aborted = False
    for point, row in zip(plan["points"], rows):
        if aborted:
            row["status"] = "NOT_RUN_ABORTED"
        else:
            row["status"] = "RUNNING"
            atomic_json(report_path, report)
            try:
                replay_loaded(dataset, point["run"], archive_path, policy=policy,
                    timeframe_starts=point["timeframe_starts"], report=row["result"], checkpoint=checkpoint)
                result = row["result"]
                if result["stopped_reason"] == "ARCHIVE_FAILED":
                    row["status"], aborted = "ARCHIVE_FAILED", True
                elif isinstance(result["stopped_reason"], dict):
                    row["status"] = "MISSION_FAILED"
                elif result["scenario"] is not None:
                    row["status"] = result["scenario"]["completion_status"]
                elif result["backtest_status"] == "SKIPPED_C_NE_T":
                    row["status"] = "SKIPPED_C_NE_T"
                elif result["outcome"] == "UNAVAILABLE":
                    row["status"] = "UNAVAILABLE"
                else:
                    row["status"] = result["assessment"]["status"] if result["assessment"] else "UNAVAILABLE"
            except ArchiveError as error:
                row.update(status="ARCHIVE_FAILED", error=error.code)
                aborted = True
            except OSError:
                row.update(status="TECHNICAL_ERROR", error="IO_ERROR")
                aborted = True  # Storage/read failure has no safe automatic retry.
            except (ValueError, TypeError, KeyError):
                row.update(status="TECHNICAL_ERROR", error="INVALID_REPLAY_DATA")
            except Exception:
                row.update(status="TECHNICAL_ERROR", error="UNEXPECTED_REPLAY_ERROR")
        report["counts"] = batch_counts(rows)
        atomic_json(report_path, report)
    report["status"] = "ABORTED" if aborted else "FINISHED"
    atomic_json(report_path, report)
    return report


def write_demo_dataset(directory, direction="LONG", case="target"):
    """Explicit synthetic producer fixture; normal CSV runs never import tests."""
    import csv
    import hashlib
    from tests.test_xauusd_causal_liquidity_reversal import scenario, ts
    definition, histories = scenario(direction)
    at, horizon = parse_timestamp(ts(31)), parse_timestamp(ts(31))+timedelta(hours=24)
    histories = {tf: [c for c in rows if parse_timestamp(c["timestamp"])+execution_duration(tf) <= at]
                 for tf, rows in histories.items()}
    entry, stop = (124., 107.) if direction == "LONG" else (176., 193.)
    sign = 1 if direction == "LONG" else -1
    mark = stop if case == "stop" else entry+sign*3*abs(entry-stop)
    histories["M1"].append(dict(timestamp=stamp(at), open=entry,
        high=max(entry, mark), low=min(entry, mark), close=entry))
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    dataset = directory / "candles.csv"
    with dataset.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timeframe", "timestamp", "open", "high", "low", "close"])
        writer.writeheader()
        for tf in ORDER:
            for candle in histories.get(tf, []):
                writer.writerow(dict(timeframe=tf, **candle))
    specs = {tf: dict(anchor=rows[0]["timestamp"], coverage_start=rows[0]["timestamp"],
        coverage_end=stamp(horizon if tf == "M1" else parse_timestamp(rows[-1]["timestamp"])+execution_duration(tf)))
        for tf, rows in histories.items() if rows}
    manifest = dict(contract=CONTRACT, symbol="XAUUSD", source_namespace="synthetic-producer-fixture", dataset_id="demo",
        dataset_revision="v1", price_basis="MID", csv_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(), timeframes=specs,
        sessions=[dict(open=min(s["coverage_start"] for s in specs.values()), close=stamp(horizon))], dataset_end=None)
    run = dict(contract=CONTRACT, T=stamp(at), K=stamp(horizon), strategy_definition=definition, setup_ordinal=0,
        entry_validity_duration_seconds=120, relationship_available_at=stamp(at))
    for name, value in (("manifest", manifest), ("replay", run)):
        (directory/(name+".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")
    return dataset, directory/"manifest.json", directory/"replay.json", directory/"missions.sqlite3"


def execution_duration(tf):
    from ced_one.business_divisions.trading.causal_snapshot_availability import VALID_TIMEFRAME_DURATIONS
    return VALID_TIMEFRAME_DURATIONS[tf]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset")
    parser.add_argument("--manifest")
    parser.add_argument("--run")
    parser.add_argument("--archive")
    parser.add_argument("--prepare-batch", metavar="PLAN", help="Seal the fixed September 30-point plan without executing missions")
    parser.add_argument("--batch", metavar="PLAN", help="Execute an explicit sealed batch plan")
    parser.add_argument("--report", help="New external JSON report; never overwrite a previous run")
    parser.add_argument("--demo-batch", metavar="DIRECTORY", help="One positive synthetic batch point, outside the repository")
    parser.add_argument("--demo", metavar="DIRECTORY", help="Generate and execute labelled synthetic LONG/SHORT fixtures outside the repository")
    args = parser.parse_args()
    try:
        if sum(bool(v) for v in (args.demo, args.demo_batch, args.prepare_batch, args.batch)) > 1:
            parser.error("Select only one demo/prepare/batch mode")
        if args.demo_batch:
            if any((args.dataset, args.manifest, args.run, args.archive, args.report)):
                parser.error("--demo-batch cannot be combined with file inputs")
            root = Path(args.demo_batch).resolve()
            repo = Path(__file__).resolve().parents[1]
            if root == repo or repo in root.parents or root.exists():
                parser.error("Demo requires a new directory outside the repository")
            sys.path.insert(0, str(repo))
            paths = write_demo_dataset(root)
            dataset = load_dataset(*paths[:2])
            profile_text = paths[2].read_text(encoding="utf-8")
            run = validate_run(json_text(profile_text))
            starts = {tf: run["strategy_definition"]["configuration"]["history_starts"].get(tf) for tf in ORDER}
            plan = batch_plan(dataset, profile_text, [dict(session_id="synthetic-positive", run=run, timeframe_starts=starts)])
            validate_batch_plan(plan, dataset)
            atomic_json(root/"batch.json", dict(plan=plan, plan_sha256=digest(plan)), create=True)
            report = run_batch(*paths[:2], root/"batch.json", paths[3], root/"report.json")
            row = report["rows"][0]
            if (row["status"] != "RESOLVED" or row["result"]["scenario"]["reference_result"]["lower_r"] !=
                    dict(numerator=3, denominator=1) or len(row["result"]["missions"]) != 3 or
                    any(v is not False for v in row["result"]["authority"].values())):
                raise ValueError("Synthetic batch did not establish the expected read-only reference result")
            print(json.dumps(dict(synthetic=True, plan_sha256=report["plan_sha256"], counts=report["counts"],
                reference_result=row["result"]["scenario"]["reference_result"],
                missions=row["result"]["missions"], report=str(root/"report.json"), execution=False)))
        elif args.prepare_batch:
            if not all((args.dataset, args.manifest, args.run)) or args.archive or args.report:
                parser.error("--prepare-batch requires only --dataset, --manifest and --run")
            if Path(args.prepare_batch).resolve() in {Path(p).resolve() for p in (args.dataset, args.manifest, args.run)}:
                parser.error("Plan must not overwrite an input")
            dataset = load_dataset(args.dataset, args.manifest)
            plan = first_batch_plan(dataset, read_bytes(args.run).decode("utf-8"))
            atomic_json(args.prepare_batch, dict(plan=plan, plan_sha256=digest(plan)), create=True)
            print(json.dumps(dict(plan=str(args.prepare_batch), plan_sha256=digest(plan), points=len(plan["points"]),
                profile_sha256=plan["profile_sha256"], missions_executed=0,
                coverage=[point_coverage(dataset, point) for point in plan["points"]])))
        elif args.batch:
            if not all((args.dataset, args.manifest, args.archive, args.report)) or args.run:
                parser.error("--batch requires --dataset, --manifest, --archive and --report; no --run")
            report = run_batch(args.dataset, args.manifest, args.batch, args.archive, args.report)
            print(json.dumps(dict(status=report["status"], plan_sha256=report["plan_sha256"], counts=report["counts"], report=args.report)))
            if report["status"] == "ABORTED" or any(r["status"] in ("TECHNICAL_ERROR", "MISSION_FAILED") for r in report["rows"]):
                return 1
        elif args.demo:
            if any((args.dataset, args.manifest, args.run, args.archive, args.report)):
                parser.error("--demo cannot be combined with file inputs")
            root = Path(args.demo).resolve()
            repo = Path(__file__).resolve().parents[1]
            if root == repo or repo in root.parents:
                parser.error("Demo directory must be outside the repository")
            sys.path.insert(0, str(repo))
            for direction in ("LONG", "SHORT"):
                results = []
                for case in ("target", "stop"):
                    paths = write_demo_dataset(root/direction/case, direction, case)
                    result = run_replay(*paths)
                    if result["stopped_reason"] is not None or result["scenario"] is None:
                        raise ValueError("Synthetic replay did not complete: " + str(result["stopped_reason"]))
                    assert all(v is False for v in result["authority"].values()) and result["execution"] is False
                    results.append(result)
                    print(json.dumps(dict(synthetic=True, direction=direction, case=case, missions=result["missions"],
                        dataset_sha256=result["dataset_sha256"], manifest_sha256=result["manifest_sha256"],
                        T=result["T"], H=result["H"], K=result["K"],
                        candidate_identity=result["candidate"]["candidate_identity"],
                        entry=result["candidate"]["entry_reference"], stop=result["candidate"]["stop_reference"],
                        outcome=result["scenario"]["completion_status"], reference_result=result["scenario"]["reference_result"],
                        authority=result["authority"], execution=result["execution"])))
                assert results[0]["candidate"] == results[1]["candidate"]
                assert results[0]["scenario"]["reference_result"] != results[1]["scenario"]["reference_result"]
        else:
            if args.report:
                parser.error("--report requires --batch")
            if not all((args.dataset, args.manifest, args.run, args.archive)):
                parser.error("--dataset, --manifest, --run and --archive are required")
            result = run_replay(args.dataset, args.manifest, args.run, args.archive)
            print(json.dumps(result, indent=2))
            if result["stopped_reason"] is not None:
                return 1
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
