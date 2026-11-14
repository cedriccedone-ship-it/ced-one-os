"""One local export, three independently governed historical research missions."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from ced_one.business_divisions.trading import execution
from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
from ced_one.business_divisions.trading import factual_market_context_composition as composition
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY, validate_source
from ced_one.business_divisions.trading.historical_market_data import (
    CONTRACT, ORDER, digest, exact, json_text, load_dataset, parse_timestamp, read_bytes, stamp,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.memory.mission_store import SQLiteMissionArchive
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


def run_replay(csv_path, manifest_path, run_path, archive_path, *, policy=None):
    dataset = load_dataset(csv_path, manifest_path)
    run = json_text(read_bytes(run_path).decode("utf-8"))
    exact(run, {"contract", "T", "K", "strategy_definition", "setup_ordinal", "entry_validity_duration_seconds",
                "relationship_available_at"}, "Replay run")
    if run["contract"] != CONTRACT:
        raise ValueError("Unsupported replay run")
    for key in ("T", "K", "relationship_available_at"):
        run[key] = stamp(parse_timestamp(run[key]))
    t, k = parse_timestamp(run["T"]), parse_timestamp(run["K"])
    if not t+timedelta(hours=24) <= k <= datetime.now(timezone.utc) or parse_timestamp(run["relationship_available_at"]) > k:
        raise ValueError("Invalid T/H/K or declaration availability")
    runtime = LocalExecutionRuntime()
    # Registration validates the real strategy configuration before the first mission.
    execution.register_governed_strategy_candidate_replay_executor(runtime, strategy_definition=run["strategy_definition"],
        setup_ordinal=run["setup_ordinal"], entry_validity_duration_seconds=run["entry_validity_duration_seconds"])
    factual = dataset.factual_input(run["T"], run["strategy_definition"])
    binding = dataset.binding(factual)
    execution.register_factual_market_context_executor(runtime, import_binding=binding)
    store = SQLiteMissionArchive(archive_path)
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime,
        policy=local_policy() if policy is None else policy, archive=store)
    report = dict(import_contract=CONTRACT, dataset_sha256=binding["dataset_sha256"],
        manifest_sha256=binding["manifest_sha256"], imported_at=binding["imported_at"],
        T=run["T"], H=stamp(t+timedelta(hours=24)), K=run["K"],
        source_authentication="NOT_VERIFIED", availability_model="CANDLE_CLOSE_RESEARCH_ASSUMPTION",
        missions=[], candidate=None, scenario=None, stopped_reason=None, execution=False)
    def completed(result):
        step = dict(mission_id=result.request_id, capability=result.capability, status=result.status.value,
            archive=result.metadata.get("archive"), record_sha256=None)
        report["missions"].append(step)
        if result.metadata.get("archive") != {"status": "stored"}:
            report["stopped_reason"] = "ARCHIVE_FAILED"
            return None
        record = store.get(result.request_id)
        step["record_sha256"] = record.record_sha256
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
    if body["candidate"] is None:
        report["stopped_reason"] = body["outcome"]
        report["assessment"] = body["strategy_assessment"]
        return report
    report["candidate"] = body["candidate"]
    profile = observation_profile(dataset, candidate_record, run)
    execution.register_governed_reference_backtest_executor(runtime, observation_profile=profile, import_binding=dataset.binding(profile))
    backtest = completed(service.handle_request("Governed reference backtest", business_division="trading",
        archive_selection=selection(candidate_record, run["T"], execution.STRATEGY_REPLAY_CAPABILITY,
            execution.STRATEGY_REPLAY_CONTRACT, execution.STRATEGY_REPLAY_RULE)))
    if backtest is not None:
        report["scenario"] = backtest.result.result_payload["scenario"]
        report["authority"] = backtest.result.result_payload["authority"]
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
    parser.add_argument("--demo", metavar="DIRECTORY", help="Generate and execute labelled synthetic LONG/SHORT fixtures outside the repository")
    args = parser.parse_args()
    try:
        if args.demo:
            if any((args.dataset, args.manifest, args.run, args.archive)):
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
