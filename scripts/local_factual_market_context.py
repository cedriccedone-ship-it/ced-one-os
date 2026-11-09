"""Synthetic historical analysis through the official Mission Control pipeline."""
from datetime import datetime, timedelta, timezone
import json

from ced_one.business_divisions.trading.execution import register_factual_market_context_executor
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control import LocalExecutionRuntime, MissionControlService
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule


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


def main():
    runtime = LocalExecutionRuntime()
    register_factual_market_context_executor(runtime)
    policy = ExecutionPolicy("local_factual_market_context", 1, rules=[PolicyRule(
        "allow_fixed_read_only_composition", 1, 1, PolicyDecision.ALLOW,
        division_name="trading", specialist_name="factual_market_context_analyst",
        capability_name="factual_market_context_composition", permission_scope="read_only",
        adapter_name="local", execution_mode="local", risk_level="low", impact_level="limited",
    )])
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy)
    goal = "Compose factual market context"
    result = service.handle_request(goal, business_division="trading", context=synthetic_payload())
    if not result.success:
        raise RuntimeError(result.errors or result.summary)
    composition = result.result_payload["composition"]
    evidence = result.result_payload["evidence"]
    print(json.dumps({
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
        "interpretation": "Analysis execution completed; factual coverage is reported separately. "
                          "Policy permits local analysis only. No trading or financial-risk approval is granted.",
    }, indent=2))


if __name__ == "__main__":
    main()
