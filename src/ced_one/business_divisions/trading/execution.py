"""Explicit local trading composition; Mission Control contains no trading logic."""
from datetime import datetime, timezone

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


def _factual_mission_input(payload):
    """Only raw histories enter this fixed, host-registered workflow."""
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import TIMEFRAME_ORDER
    from ced_one.business_divisions.trading.validation import parse_timestamp

    if type(payload) is not dict or set(payload) != {
        "symbol", "requested_evaluation_timestamp", "timeframe_histories",
    }:
        raise ValueError("Expected symbol, requested_evaluation_timestamp and timeframe_histories only.")
    if payload["symbol"] != "XAUUSD":
        raise ValueError("Only XAUUSD factual analysis is supported.")
    boundary = parse_timestamp(payload["requested_evaluation_timestamp"])
    if boundary > datetime.now(timezone.utc):
        raise ValueError("The evaluation boundary must be historical.")
    histories = payload["timeframe_histories"]
    if type(histories) is not dict or set(histories) != set(TIMEFRAME_ORDER):
        raise ValueError("Exactly D1, H4, H1, M30, M15, M5 and M1 histories are required.")
    for timeframe in TIMEFRAME_ORDER:
        rows = histories[timeframe]
        if type(rows) is not list or any(type(row) is not dict or set(row) != {
            "timestamp", "open", "high", "low", "close",
        } for row in rows):
            raise ValueError(f"{timeframe} must contain raw OHLC candles only.")
    return boundary.isoformat().replace("+00:00", "Z")


def _observation_only(artifact):
    metadata = artifact["metadata"]
    if (metadata.get("authority_scope") != "read_only" or
            metadata.get("observation_only") is not True or
            any(metadata.get(field) is not False for field in (
                "advisory_output", "strategy_output", "execution_output",
            ))):
        raise ValueError("Factual analysis must retain exact read-only authority boundaries.")


def execute_factual_market_context_composition(request):
    """One governed execution; the fixed native dependencies are not separate missions.

    Native validators run before return. A valid unavailable observation is an
    analysis result, while malformed sources or failed invocations fail the task.
    The execution envelope retains full native artifacts without modifying them.
    """
    from ced_one.business_divisions.trading.causal_snapshot_availability import validate_source
    from ced_one.business_divisions.trading.causal_multi_timeframe_context import (
        CAUSAL_MULTI_TIMEFRAME_CONTEXT, validate_source_context,
    )
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
        ADAPTERS, CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE, validate_factual_envelope,
    )
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
        CAPABILITY_ORDER, TIMEFRAME_ORDER, CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT,
        validate_factual_context,
    )
    from ced_one.business_divisions.trading.factual_market_context_composition import (
        FactualMarketContextCompositionAnalyzer, validate_factual_composition,
    )

    payload = request.input_payload
    boundary = _factual_mission_input(payload)
    sources = {}
    for timeframe in TIMEFRAME_ORDER:
        source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze({
            "symbol": "XAUUSD", "timeframe": timeframe,
            "requested_evaluation_timestamp": boundary,
            "candle_history": payload["timeframe_histories"][timeframe],
        }).to_dict()
        validate_source(source)
        _observation_only(source)
        if source["source_availability"] == "INVALID":
            raise ValueError(f"Invalid {timeframe} causal source: {source['availability_reason']}")
        if (source["symbol"], source["timeframe"], source["requested_evaluation_timestamp"]) != (
            "XAUUSD", timeframe, boundary,
        ):
            raise ValueError("Causal source mission binding mismatch.")
        sources[timeframe] = source

    source_context = CAUSAL_MULTI_TIMEFRAME_CONTEXT.analyze({
        "symbol": "XAUUSD", "requested_evaluation_timestamp": boundary,
        "timeframe_sources": sources,
    }).to_dict()
    validate_source_context(source_context)
    _observation_only(source_context)

    envelopes = {}
    for timeframe in TIMEFRAME_ORDER:
        envelopes[timeframe] = {}
        for name in CAPABILITY_ORDER:
            adapter = ADAPTERS[f"trading.{name}.v1"]
            envelope = CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze({
                "symbol": "XAUUSD", "timeframe": timeframe,
                "requested_evaluation_timestamp": boundary,
                "causal_source": sources[timeframe], "context_id": source_context["context_id"],
                "capability": {
                    "name": name, "contract": adapter.contract,
                    "rule_version": adapter.rule_version, "configuration": {},
                },
            }).to_dict()
            validate_factual_envelope(envelope, source_context["timeframes"][timeframe])
            _observation_only(envelope)
            if envelope["factual_availability"] == "INVALID":
                raise ValueError(f"Invalid {timeframe}/{name} factual analysis: {envelope['availability_reason']}")
            envelopes[timeframe][name] = envelope

    factual_context = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze({
        "symbol": "XAUUSD", "requested_evaluation_timestamp": boundary,
        "source_context": source_context, "factual_envelopes": envelopes,
    }).to_dict()
    validate_factual_context(factual_context)
    _observation_only(factual_context)
    composition = FactualMarketContextCompositionAnalyzer().analyze({
        "factual_context": factual_context,
    }).to_dict()
    validate_factual_composition(composition, factual_context)
    _observation_only(composition)
    return {
        "composition": composition,
        "evidence": {
            "sources": sources, "source_context": source_context,
            "factual_envelopes": envelopes, "factual_context": factual_context,
        },
    }


def register_factual_market_context_executor(runtime: LocalExecutionRuntime) -> None:
    """Register analysis execution only; the host must separately supply policy."""
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
        CAPABILITY_ORDER, TIMEFRAME_ORDER,
    )
    from ced_one.business_divisions.trading.factual_market_context_composition import CONTRACT, RULE_VERSION

    runtime.register(CapabilityExecutionContract(
        name="factual_market_context_composition", division_name="trading", contract_id=CONTRACT,
        permission_scope="read_only", retryable=False,
        input_schema={"required_fields": ["symbol", "requested_evaluation_timestamp", "timeframe_histories"]},
        output_schema={"required_fields": ["composition", "evidence"]},
        metadata={
            "risk_level": "low", "impact_level": "limited", "rule_version": RULE_VERSION,
            "timeframe_order": list(TIMEFRAME_ORDER), "capability_order": list(CAPABILITY_ORDER),
            "configuration": "native_defaults", "execution_envelope_version": 1,
        },
    ), execute_factual_market_context_composition)


ARCHIVED_SYNTHESIS_CONTRACT = "trading.archived_market_state_synthesis.v1"
ARCHIVED_SYNTHESIS_RULE = "archived_market_state_synthesis_v1"


def execute_archived_market_state_synthesis(request):
    """Validate the original as-of bundle, then run two existing factual owners."""
    from ced_one.mission_control.service import validate_archived_context_projection
    from ced_one.business_divisions.trading.causal_snapshot_availability import validate_source
    from ced_one.business_divisions.trading.causal_multi_timeframe_context import validate_source_context
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import validate_factual_envelope
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
        CAPABILITY_ORDER, TIMEFRAME_ORDER, validate_factual_context,
    )
    from ced_one.business_divisions.trading.factual_market_context_composition import (
        CONTRACT, RULE_VERSION as COMPOSITION_RULE, validate_factual_composition,
    )
    from ced_one.business_divisions.trading.causal_factual_event_chronology import (
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY, validate_factual_chronology,
    )
    from ced_one.business_divisions.trading.causal_market_state_synthesis import (
        CAUSAL_MARKET_STATE_SYNTHESIS, validate_market_state_synthesis,
    )
    from ced_one.business_divisions.trading.validation import parse_timestamp

    projection = validate_archived_context_projection(request.input_payload)
    ref, original = projection["selection"], projection["original_payload"]
    if (ref["division"], ref["capability"], ref["contract_id"], ref["rule_version"]) != (
            "trading", "factual_market_context_composition", CONTRACT, COMPOSITION_RULE):
        raise ValueError("Unsupported archived source contract/rule.")
    if set(original) != {"composition", "evidence"} or type(original["evidence"]) is not dict or set(original["evidence"]) != {
            "sources", "source_context", "factual_envelopes", "factual_context"}:
        raise ValueError("Expected the complete original factual composition bundle.")
    evidence = original["evidence"]
    sources, matrix = evidence["sources"], evidence["factual_envelopes"]
    if (type(sources) is not dict or set(sources) != set(TIMEFRAME_ORDER) or
            type(matrix) is not dict or set(matrix) != set(TIMEFRAME_ORDER)):
        raise ValueError("Exactly seven original source and envelope slots are required.")
    boundary = parse_timestamp(ref["evaluation_time"])

    def bound(artifact):
        _observation_only(artifact)
        if artifact["symbol"] != "XAUUSD" or parse_timestamp(artifact["requested_evaluation_timestamp"]) != boundary:
            raise ValueError("Original economic boundary or symbol mismatch.")

    source_context = validate_source_context(evidence["source_context"])
    context = validate_factual_context(evidence["factual_context"])
    bound(source_context)
    bound(context)
    if context["source_context_id"] != source_context["context_id"]:
        raise ValueError("Original source/factual context mismatch.")
    source_fields = ("timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff",
                     "source_snapshot_id", "source_availability", "availability_reason", "completion_state")
    for tf in TIMEFRAME_ORDER:
        source = validate_source(sources[tf])
        bound(source)
        if source["source_availability"] == "INVALID" or source["timeframe"] != tf:
            raise ValueError("Invalid original source slot.")
        if source_context["timeframes"][tf] != {key: source[key] for key in source_fields}:
            raise ValueError("Original source/context descriptor mismatch.")
        slot = context["timeframes"][tf]
        if any(slot[k] != source[k] for k in ("source_snapshot_id", "effective_causal_cutoff", "source_availability")) or slot["source_completion_state"] != source["completion_state"]:
            raise ValueError("Original factual source identity mismatch.")
        cutoff = source["effective_causal_cutoff"]
        if cutoff is not None and parse_timestamp(cutoff) > boundary:
            raise ValueError("Original source cutoff exceeds T.")
        if type(matrix[tf]) is not dict or set(matrix[tf]) != set(CAPABILITY_ORDER):
            raise ValueError("Exactly ten original factual envelopes are required per timeframe.")
        for name in CAPABILITY_ORDER:
            envelope = validate_factual_envelope(matrix[tf][name], source_context["timeframes"][tf])
            bound(envelope)
            if envelope["context_id"] != source_context["context_id"] or envelope["factual_availability"] == "INVALID":
                raise ValueError("Original envelope source context mismatch.")
    composition = validate_factual_composition(original["composition"], context)
    bound(composition)
    chronology = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze({
        "factual_context": context, "factual_envelopes": matrix, "composition": composition,
    }).to_dict()
    # The owner's Python manifest uses tuples; its supported JSON wire form uses
    # arrays. Normalize this newly produced field before detached validation/storage.
    chronology["evidence"]["event_source_manifest"] = {
        name: list(families) for name, families in chronology["evidence"]["event_source_manifest"].items()
    }
    validate_factual_chronology(chronology, context, matrix, composition)
    bound(chronology)
    upstream = {"factual_context": context, "factual_envelopes": matrix, "composition": composition,
                "chronology": chronology, "configuration": {}}
    synthesis = CAUSAL_MARKET_STATE_SYNTHESIS.analyze(upstream).to_dict()
    validate_market_state_synthesis(synthesis, upstream)
    bound(synthesis)
    return {
        "synthesis": synthesis, "upstream_bundle": upstream,
        "source_evidence": {"sources": sources, "source_context": source_context},
        "provenance": {
            "source_selection": ref, "new_mission_id": request.mission_id,
            "source_snapshot_ids": {tf: sources[tf]["source_snapshot_id"] for tf in TIMEFRAME_ORDER},
            "source_context_id": source_context["context_id"], "factual_context_id": context["factual_context_id"],
            "composition_id": composition["composition_id"], "chronology_id": chronology["chronology_id"],
            "synthesis_id": synthesis["synthesis_id"],
        },
        "metadata": {"contract": ARCHIVED_SYNTHESIS_CONTRACT, "rule_version": ARCHIVED_SYNTHESIS_RULE,
                     "observation_only": True, "authority_scope": "read_only", "advisory_output": False,
                     "strategy_output": False, "execution_output": False},
    }


def register_archived_market_state_synthesis_executor(runtime: LocalExecutionRuntime) -> None:
    runtime.register(CapabilityExecutionContract(
        name="archived_market_state_synthesis", division_name="trading", contract_id=ARCHIVED_SYNTHESIS_CONTRACT,
        permission_scope="read_only", retryable=False,
        input_schema={"required_fields": ["selection", "original_payload"]},
        output_schema={"required_fields": ["synthesis", "upstream_bundle", "source_evidence", "provenance", "metadata"]},
        metadata={"risk_level": "low", "impact_level": "limited", "rule_version": ARCHIVED_SYNTHESIS_RULE,
                  "requires_archived_context": True, "configuration": "native_defaults"},
    ), execute_archived_market_state_synthesis)
