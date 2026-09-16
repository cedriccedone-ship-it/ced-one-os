"""Run with an installed package: python scripts/local_candle_analysis.py."""
import json
from ced_one.business_divisions.trading.execution import register_candle_executor
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control import MissionControlService, LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule


def main():
    runtime = LocalExecutionRuntime()
    register_candle_executor(runtime)
    policy = ExecutionPolicy("local_candle_analysis", 1, rules=[PolicyRule(
        "allow_read_only_candles", 1, 1, PolicyDecision.ALLOW,
        division_name="trading", specialist_name="candle_analyst", capability_name="candle_intelligence",
        permission_scope="read_only", adapter_name="local", execution_mode="local",
        risk_level="low", impact_level="limited",
    )])
    service = MissionControlService({"trading": TradingDivisionResolver()}, runtime=runtime, policy=policy)
    result = service.handle_request("Analyze candle intelligence", business_division="trading", context={
        "symbol": "XAUUSD", "timeframe": "H1", "evaluation_time": "2026-09-01T02:30:00Z",
        "candle_history": [
            {"timestamp": "2026-09-01T00:00:00Z", "open": 2500, "high": 2505, "low": 2498, "close": 2503},
            {"timestamp": "2026-09-01T01:00:00Z", "open": 2503, "high": 2510, "low": 2501, "close": 2508},
            {"timestamp": "2026-09-01T02:00:00Z", "open": 2508, "high": 2511, "low": 2504, "close": 2505},
        ],
    })
    if not result.success:
        raise RuntimeError(result.errors or result.summary)
    print(json.dumps({
        "status": result.status.value, "execution_performed": result.metadata["execution_performed"],
        "candle_timestamp": result.result_payload["timestamp"],
        "candle_direction": result.result_payload["candle_direction"],
        "provenance": result.result_payload["provenance"],
        "policy": result.metadata["policy_decision"], "audit_reference": result.metadata["audit_reference"],
    }, indent=2))


if __name__ == "__main__":
    main()
