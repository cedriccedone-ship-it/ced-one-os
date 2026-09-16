"""Explicit local trading composition; Mission Control contains no trading logic."""
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY
from ced_one.business_divisions.trading.candle_intelligence import CandleIntelligenceAnalyzer, CandleIntelligenceCapability, RULE_VERSION
from ced_one.mission_control.runtime import CapabilityExecutionContract, LocalExecutionRuntime


def execute_candle_intelligence(request):
    payload = request.input_payload
    source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze({
        "symbol": payload["symbol"], "timeframe": payload["timeframe"],
        "requested_evaluation_timestamp": payload["evaluation_time"],
        "candle_history": payload["candle_history"],
    })
    if source.source_availability != "AVAILABLE":
        raise ValueError(f"Causal source {source.source_availability}: {source.availability_reason}")
    result = CandleIntelligenceAnalyzer().analyze({
        "symbol": source.symbol, "timeframe": source.timeframe,
        "evaluation_time": source.requested_evaluation_timestamp,
        "candle_history": source.approved_candle_history, "config": payload.get("config"),
    }).to_dict()
    errors = CandleIntelligenceCapability().validate_output(result)
    if errors:
        raise ValueError("; ".join(errors))
    result["provenance"] = {
        "source_snapshot_id": source.source_snapshot_id,
        "effective_causal_cutoff": source.effective_causal_cutoff,
        "source_completion_state": source.completion_state,
        "contract": "trading.candle_intelligence.v1", "rule_version": RULE_VERSION,
        "approved_candle_count": len(source.approved_candle_history),
    }
    return result


def register_candle_executor(runtime: LocalExecutionRuntime) -> None:
    runtime.register(CapabilityExecutionContract(
        name="candle_intelligence", division_name="trading", contract_id="trading.candle_intelligence.v1",
        permission_scope="read_only", retryable=False,
        input_schema={"required_fields": ["symbol", "timeframe", "evaluation_time", "candle_history"]},
        output_schema={"required_fields": ["symbol", "timeframe", "timestamp", "candle_direction", "evidence", "metadata", "provenance"]},
        metadata={"risk_level": "low", "impact_level": "limited", "rule_version": RULE_VERSION},
    ), execute_candle_intelligence)
