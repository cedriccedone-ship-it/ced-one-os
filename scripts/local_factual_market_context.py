"""Synthetic historical analysis through the official Mission Control pipeline."""
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
import sys

from ced_one.mission_control import LocalExecutionRuntime, MissionControlService
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule
from ced_one.memory.mission_store import SQLiteMissionArchive


def synthetic_payload():
    """Aggregate one invented minute-price path into seven historical OHLC series.

    This is test data, with no provider or real-market authenticity claim. Each
    timeframe also supplies one open candle to demonstrate causal exclusion.
    """
    boundary = datetime(2026, 9, 1, tzinfo=timezone.utc)
    minutes = 32 * 1440
    start = boundary - timedelta(minutes=minutes)
    prices = [2500 + (i % 97 - 48) * .03 + ((i // 97) % 11 - 5) * .2
              for i in range(minutes + 1)]
    histories = {}
    for timeframe, width in (("D1", 1440), ("H4", 240), ("H1", 60), ("M30", 30),
                             ("M15", 15), ("M5", 5), ("M1", 1)):
        rows = []
        for offset in range(minutes - 32 * width, minutes, width):
            values = prices[offset:offset + width + 1]
            rows.append({
                "timestamp": (start + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
                "open": values[0], "high": max(values) + .1,
                "low": min(values) - .1, "close": values[-1],
            })
        rows.append({"timestamp": boundary.isoformat().replace("+00:00", "Z"),
                     "open": prices[-1], "high": prices[-1] + .1,
                     "low": prices[-1] - .1, "close": prices[-1]})
        histories[timeframe] = rows
    return {"symbol": "XAUUSD", "requested_evaluation_timestamp": boundary.isoformat().replace("+00:00", "Z"),
            "timeframe_histories": histories}


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", help="Explicit local SQLite path; use a private directory outside the repository.")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--read", metavar="MISSION_ID", help="Read a historical mission without execution.")
    operation.add_argument("--synthesize", metavar="MISSION_ID", help="Select one archived composition for a new governed mission.")
    parser.add_argument("--record-sha256", help="Required expected source record hash for --synthesize.")
    parser.add_argument("--evaluation-time", help="Required original economic boundary T for --synthesize.")
    parser.add_argument("--created-not-after", help="Required upper bound on original request creation; not archive availability.")
    args = parser.parse_args(list(argv))
    if args.read and not args.archive:
        parser.error("--read requires --archive")
    if args.synthesize and not all((args.archive, args.record_sha256, args.evaluation_time, args.created_not_after)):
        parser.error("--synthesize requires --archive, --record-sha256, --evaluation-time and --created-not-after")
    if not args.synthesize and any((args.record_sha256, args.evaluation_time, args.created_not_after)):
        parser.error("Selection constraints require --synthesize")
    archive = SQLiteMissionArchive(args.archive) if args.archive else None
    if args.read:
        # No division, executor or allow policy is registered for this operation.
        record = MissionControlService(archive=archive).get_archived_mission(args.read)
        goal, result = record.request.user_goal, record.result
    else:
        from ced_one.business_divisions.trading.execution import (
            register_factual_market_context_executor, register_archived_market_state_synthesis_executor,
        )
        from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
        runtime = LocalExecutionRuntime()
        capability = "archived_market_state_synthesis" if args.synthesize else "factual_market_context_composition"
        (register_archived_market_state_synthesis_executor if args.synthesize else register_factual_market_context_executor)(runtime)
        policy = ExecutionPolicy("local_factual_market_context", 1, rules=[PolicyRule(
            "allow_fixed_read_only_composition", 1, 1, PolicyDecision.ALLOW,
            division_name="trading", specialist_name="factual_market_context_analyst",
            capability_name=capability, permission_scope="read_only",
            adapter_name="local", execution_mode="local", risk_level="low", impact_level="limited",
        )])
        service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy, archive=archive)
        if args.synthesize:
            from ced_one.business_divisions.trading.factual_market_context_composition import CONTRACT, RULE_VERSION
            goal = "Archived market state synthesis"
            result = service.handle_request(goal, business_division="trading", archive_selection={
                "mission_id": args.synthesize, "record_sha256": args.record_sha256,
                "division": "trading", "capability": "factual_market_context_composition",
                "contract_id": CONTRACT, "rule_version": RULE_VERSION,
                "evaluation_time": args.evaluation_time, "created_not_after": args.created_not_after,
            })
        else:
            goal = "Compose factual market context"
            result = service.handle_request(goal, business_division="trading", context=synthetic_payload())
        if not result.success:
            raise RuntimeError(result.errors or result.summary)
    body = result.result_payload
    synthesis = body.get("synthesis")
    if synthesis is not None:
        composition = body["upstream_bundle"]["composition"]
        evidence = {**body["source_evidence"], "factual_envelopes": body["upstream_bundle"]["factual_envelopes"]}
    else:
        composition, evidence = body["composition"], body["evidence"]
    output = {
        "operation": "archive_read" if args.read else "synthesize" if args.synthesize else "execute",
        "process_id": os.getpid(),
        "execution_performed_now": not bool(args.read),
        "temporal_scope": "HISTORICAL_RECORD_ONLY" if args.read else "SYNTHETIC_HISTORICAL_ANALYSIS",
        "archive": result.metadata.get("archive"),
        "record_sha256": archive.get(result.request_id).record_sha256 if archive and result.metadata.get("archive") == {"status": "stored"} else None,
        "requested_evaluation_timestamp": composition["requested_evaluation_timestamp"],
        "user_request": goal, "input_kind": "synthetic historical OHLC",
        "mission_id": result.request_id, "status": result.status.value, "summary": result.summary,
        "division": result.division, "specialist": result.specialist, "capability": result.capability,
        "execution_performed": result.metadata["execution_performed"],
        "execution_outcome": result.metadata["execution_result"]["outcome"],
        "validation_errors": result.metadata["execution_result"]["validation_errors"],
        "composition_id": composition["composition_id"], "composition_state": composition["composition_state"],
        "factual_envelope_count": sum(len(group) for group in evidence["factual_envelopes"].values()),
        "relationship_count": len(composition["adjacent_relationships"]),
        "sources": {tf: {key: source[key] for key in (
            "source_snapshot_id", "effective_causal_cutoff", "completion_state", "diagnostics",
        )} for tf, source in evidence["sources"].items()},
        "policy": result.metadata["policy_decision"], "audit_reference": result.metadata["audit_reference"],
        "audit_events": [{key: event[key] for key in (
            "event_type", "task_id", "mission_id", "timestamp",
        )} for event in result.metadata["task_graph"]["audit_events"]],
        "interpretation": ("Historical archive read; no execution or renewed authorization. " if args.read else "") +
                          "Analysis execution completed; factual coverage is reported separately. "
                          "Policy permits local analysis only. No trading or financial-risk approval is granted.",
    }
    if synthesis is not None:
        chronology = body["upstream_bundle"]["chronology"]
        output.update({
            "source_mission_id": body["provenance"]["source_selection"]["source_mission_id"],
            "source_record_sha256": body["provenance"]["source_selection"]["record_sha256"],
            "source_selection": body["provenance"]["source_selection"],
            "chronology_id": chronology["chronology_id"], "chronology_state": chronology["chronology_state"],
            "event_count": len(chronology["events"]), "synthesis_id": synthesis["synthesis_id"],
            "validation_scope": "archived_execution" if args.read else "current_analysis_execution",
            "native_validation": "passed", "source_snapshot_ids": body["provenance"]["source_snapshot_ids"],
        })
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
