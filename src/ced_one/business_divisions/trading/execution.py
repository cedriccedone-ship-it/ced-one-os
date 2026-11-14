"""Explicit local trading composition; Mission Control contains no trading logic."""
from datetime import datetime, timezone
from copy import deepcopy

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


def _import_binding(binding, payload):
    if binding is None:
        return None
    from ced_one.business_divisions.trading.historical_market_data import validate_binding
    return validate_binding(binding, payload)


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
    _import_binding(request.metadata["capability_contract"]["metadata"].get("import_binding"), payload)
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


def register_factual_market_context_executor(runtime: LocalExecutionRuntime, *, import_binding=None) -> None:
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
            **({"import_binding": deepcopy(import_binding)} if import_binding is not None else {}),
        },
    ), execute_factual_market_context_composition)


ARCHIVED_SYNTHESIS_CONTRACT = "trading.archived_market_state_synthesis.v1"
ARCHIVED_SYNTHESIS_RULE = "archived_market_state_synthesis_v1"


def _validated_archived_composition(payload):
    """Shared original-evidence validation for governed archive consumers."""
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
    from ced_one.business_divisions.trading.validation import parse_timestamp

    projection = validate_archived_context_projection(payload)
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
    return ref, sources, source_context, context, matrix, composition


def execute_archived_market_state_synthesis(request):
    """Validate the original as-of bundle, then run two existing factual owners."""
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import TIMEFRAME_ORDER
    from ced_one.business_divisions.trading.causal_factual_event_chronology import (
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY, validate_factual_chronology,
    )
    from ced_one.business_divisions.trading.causal_market_state_synthesis import (
        CAUSAL_MARKET_STATE_SYNTHESIS, validate_market_state_synthesis,
    )
    from ced_one.business_divisions.trading.validation import parse_timestamp

    ref, sources, source_context, context, matrix, composition = _validated_archived_composition(request.input_payload)

    def bound(artifact):
        _observation_only(artifact)
        if artifact["symbol"] != "XAUUSD" or parse_timestamp(artifact["requested_evaluation_timestamp"]) != parse_timestamp(ref["evaluation_time"]):
            raise ValueError("Original economic boundary or symbol mismatch.")

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


STRATEGY_REPLAY_CAPABILITY = "governed_strategy_candidate_replay"
STRATEGY_REPLAY_CONTRACT = "trading.governed_strategy_candidate_replay.v1"
STRATEGY_REPLAY_RULE = "governed_strategy_candidate_replay_v1"


def _strategy_replay_versions():
    from ced_one.business_divisions.trading import (
        causal_snapshot_availability as source, causal_multi_timeframe_context as context,
        causal_factual_intelligence_envelope as envelope, causal_factual_multi_timeframe_context as factual,
        factual_market_context_composition as composition, xauusd_causal_liquidity_reversal as strategy,
        causal_trading_policy_strategy_action_formulation as action, xauusd_technical_trade_candidate as candidate,
    )
    return {
        "source": {"contract": source.CONTRACT, "rule_version": source.RULE_VERSION},
        "source_context": {"contract": context.CONTRACT, "rule_version": context.RULE_VERSION},
        "envelope": {"contract": envelope.CONTRACT, "rule_version": envelope.RULE_VERSION},
        "factual_context": {"contract": "trading.causal_factual_multi_timeframe_context.v1", "rule_version": factual.RULE_VERSION},
        "composition": {"contract": composition.CONTRACT, "rule_version": composition.RULE_VERSION},
        "strategy": {"contract": strategy.CONTRACT, "rule_version": strategy.RULE_VERSION,
                     "strategy_version": strategy.STRATEGY_VERSION, "factual_rules": dict(strategy.FACTUAL_RULES)},
        "action": {"contract": action.CONTRACT, "rule_version": action.RULE_VERSION},
        "candidate": {"contract": candidate.CONTRACT, "rule_version": candidate.RULE_VERSION},
    }


def _strategy_replay_profile(strategy_definition, setup_ordinal, entry_validity_duration_seconds):
    from datetime import timedelta
    from ced_one.business_divisions.trading.xauusd_causal_liquidity_reversal import normalize_strategy_definition
    from ced_one.mission_control.policy import validate_context_data

    if type(setup_ordinal) is not int or setup_ordinal < 0:
        raise ValueError("setup_ordinal must be an explicit nonnegative integer.")
    if type(entry_validity_duration_seconds) is not int or entry_validity_duration_seconds <= 0:
        raise ValueError("Entry validity must be explicit positive integer elapsed seconds.")
    try:
        timedelta(seconds=entry_validity_duration_seconds)
    except OverflowError as exc:
        raise ValueError("Entry validity duration is not representable.") from exc
    definition = normalize_strategy_definition(strategy_definition)
    if (definition["strategy_version"], definition["rule_version"]) != ("0.2", "revision_2.1"):
        raise ValueError("Only Strategy #1 v0.2 revision_2.1 is supported.")
    profile = {"strategy_definition": definition, "setup_ordinal": setup_ordinal,
               "entry_validity_duration_seconds": entry_validity_duration_seconds,
               "native_versions": _strategy_replay_versions()}
    if validate_context_data(profile):
        raise ValueError("Replay profile must contain supported finite JSON data only.")
    return profile


def execute_governed_strategy_candidate_replay(request):
    """Reconstruct historical technical references; never authorize a trade."""
    from copy import deepcopy
    from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
    from ced_one.business_divisions.trading import causal_trading_policy_strategy_action_formulation as actions
    from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as candidates

    contract = request.metadata["capability_contract"]
    if (contract["name"], contract["contract_id"], contract["permission_scope"]) != (
            STRATEGY_REPLAY_CAPABILITY, STRATEGY_REPLAY_CONTRACT, "read_only"):
        raise ValueError("Replay execution contract mismatch.")
    metadata = contract["metadata"]
    profile = metadata["replay_profile"]
    strategy.exact(profile, {"strategy_definition", "setup_ordinal", "entry_validity_duration_seconds", "native_versions"}, "Replay profile")
    expected = _strategy_replay_profile(profile["strategy_definition"], profile["setup_ordinal"], profile["entry_validity_duration_seconds"])
    if (strategy.identity("", profile) != strategy.identity("", expected) or
            metadata["profile_sha256"] != strategy.identity("", expected) or metadata["rule_version"] != STRATEGY_REPLAY_RULE):
        raise ValueError("Replay profile or native version mismatch.")
    ref, sources, _, _, _, _ = _validated_archived_composition(request.input_payload)
    for tf in strategy.TIMEFRAMES:
        source = sources[tf]
        if {k: source["metadata"][k] for k in ("contract", "rule_version")} != profile["native_versions"]["source"]:
            raise ValueError("Unsupported strategy source version.")
    assessment_input = {"strategy_definition": deepcopy(profile["strategy_definition"]), "as_of": ref["evaluation_time"],
                        "sources": {tf: deepcopy(sources[tf]) for tf in strategy.TIMEFRAMES}, "setup_ordinal": profile["setup_ordinal"]}
    assessment = strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(assessment_input).to_dict()
    assessment = strategy.validate_strategy_assessment(assessment, assessment_input)
    action_policy = {
        "contract": actions.DEFINITION_CONTRACT, "policy_id": STRATEGY_REPLAY_CAPABILITY + ".intent", "policy_version": 1,
        "strategy_definition": deepcopy(profile["strategy_definition"]),
        "configuration_fingerprint": strategy.identity("configuration_", profile["strategy_definition"]["configuration"]),
        "declared_action": {"action_type": "DIRECTIONAL_ENTRY_INTENT", "direction": profile["strategy_definition"]["direction"]},
    }
    action_input = {"action_policy_definition": action_policy, "strategy_assessment": assessment, "assessment_input": assessment_input}
    # The public action analyzer itself reconstructs through the strategy validator.
    action = actions.STRATEGY_ACTION_FORMULATION.analyze(action_input).to_dict()
    candidate_input = formulation = candidate = None
    outcome = "UNAVAILABLE" if any(sources[tf]["source_availability"] == "UNAVAILABLE" for tf in strategy.TIMEFRAMES) else assessment["status"]
    if assessment["status"] == "COMPLETE" and outcome != "UNAVAILABLE":
        candidate_input = {
            "candidate_policy_definition": {"contract": candidates.POLICY_CONTRACT,
                "policy_id": STRATEGY_REPLAY_CAPABILITY + ".candidate", "policy_version": 1,
                "configuration": {"entry_validity_duration_seconds": profile["entry_validity_duration_seconds"]}},
            "strategy_assessment": assessment, "action_formulation": action, "action_formulation_input": action_input,
        }
        formulation = candidates.XAUUSD_TECHNICAL_TRADE_CANDIDATE.analyze(candidate_input).to_dict()
        formulation = candidates.validate_technical_candidate_formulation(formulation, candidate_input)
        candidate = formulation["candidate"]
        outcome = "CANDIDATE_FORMULATED" if candidate is not None else "NOT_FORMULATED"
    return {
        "outcome": outcome, "strategy_assessment": assessment, "action_formulation": action,
        "candidate_formulation": formulation, "candidate": candidate,
        "reconstruction": {"assessment_input": assessment_input, "action_input": action_input, "candidate_input": candidate_input},
        "provenance": {"source_selection": ref, "new_mission_id": request.mission_id, "evaluation_time": ref["evaluation_time"],
            "source_snapshot_ids": {tf: source["source_snapshot_id"] for tf, source in sources.items()},
            "strategy_source_snapshot_ids": {tf: sources[tf]["source_snapshot_id"] for tf in strategy.TIMEFRAMES},
            "replay_profile": deepcopy(profile), "profile_sha256": metadata["profile_sha256"]},
        "metadata": {"contract": STRATEGY_REPLAY_CONTRACT, "rule_version": STRATEGY_REPLAY_RULE,
                     "authority_scope": "read_only", "candidate_scope": "HISTORICAL_TECHNICAL_REFERENCE_ONLY",
                     "source_authentication": "NOT_VERIFIED", "execution_output": False},
        "authority": dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                                    "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False),
        "execution": False,
    }


def register_governed_strategy_candidate_replay_executor(runtime: LocalExecutionRuntime, *, strategy_definition,
                                                        setup_ordinal, entry_validity_duration_seconds) -> None:
    """Host-selected profile, isolated and bound by the existing authorization snapshot."""
    from ced_one.business_divisions.trading.xauusd_causal_liquidity_reversal import identity

    profile = _strategy_replay_profile(strategy_definition, setup_ordinal, entry_validity_duration_seconds)
    runtime.register(CapabilityExecutionContract(
        name=STRATEGY_REPLAY_CAPABILITY, division_name="trading", contract_id=STRATEGY_REPLAY_CONTRACT,
        permission_scope="read_only", retryable=False,
        input_schema={"required_fields": ["selection", "original_payload"]},
        output_schema={"required_fields": ["outcome", "strategy_assessment", "action_formulation", "candidate_formulation",
                                          "candidate", "reconstruction", "provenance", "metadata", "authority", "execution"]},
        metadata={"risk_level": "low", "impact_level": "limited", "rule_version": STRATEGY_REPLAY_RULE,
                  "requires_archived_context": True, "replay_profile": profile, "profile_sha256": identity("", profile)},
    ), execute_governed_strategy_candidate_replay)


REFERENCE_BACKTEST_CAPABILITY = "governed_reference_backtest"
REFERENCE_BACKTEST_CONTRACT = "trading.governed_reference_backtest.v1"
REFERENCE_BACKTEST_RULE = "governed_reference_backtest_v1"
_REFERENCE_AUTHORITY_FIELDS = ("quantity_selection", "budget_approval", "position_effect_compliance",
                             "margin_capital_approval", "trade_decision", "financial_risk", "execution")


def _reference_hash(value):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _reference_time(value):
    from ced_one.business_divisions.trading.validation import parse_timestamp
    if type(value) is not str:
        raise ValueError("Reference time must be canonical UTC text.")
    at = parse_timestamp(value)
    if value != at.isoformat().replace("+00:00", "Z"):
        raise ValueError("Reference time must be canonical UTC text.")
    return at


def _reference_profile(observation_profile):
    from copy import deepcopy
    from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
    from ced_one.business_divisions.trading.xauusd_causal_liquidity_reversal import exact
    from ced_one.mission_control.policy import validate_context_data
    exact(observation_profile, {"research_boundary", "m1", "declarations"}, "Observation profile")
    if validate_context_data(observation_profile) or type(observation_profile["m1"]) is not dict or type(observation_profile["declarations"]) is not list:
        raise ValueError("Observation profile must contain finite JSON evidence.")
    if _reference_time(observation_profile["research_boundary"]) > datetime.now(timezone.utc):
        raise ValueError("Research boundary is in the future.")
    # Registration binds data only. Public owner replay remains behind governance.
    profile = deepcopy(observation_profile)
    profile["native_versions"] = {"candidate_replay": _strategy_replay_versions(),
        "reference": {"scenario_contract": reference.SCENARIO_CONTRACT, "policy_contract": reference.POLICY_CONTRACT,
            "rule_version": reference.RULE_VERSION, "relationship_contract": reference.DATASET_RELATIONSHIP_CONTRACT,
            "relationship_rule_version": reference.RELATIONSHIP_RULE_VERSION}}
    return profile


def _validated_reference_candidate(payload):
    from copy import deepcopy
    from ced_one.mission_control.service import validate_archived_context_projection
    from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
    from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as candidates
    from ced_one.business_divisions.trading import factual_market_context_composition as composition
    from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import TIMEFRAME_ORDER

    projection = validate_archived_context_projection(payload)
    ref, body = projection["selection"], projection["original_payload"]
    if (ref["division"], ref["capability"], ref["contract_id"], ref["rule_version"]) != (
            "trading", STRATEGY_REPLAY_CAPABILITY, STRATEGY_REPLAY_CONTRACT, STRATEGY_REPLAY_RULE):
        raise ValueError("Unsupported archived candidate contract/rule.")
    strategy.exact(body, {"outcome", "strategy_assessment", "action_formulation", "candidate_formulation", "candidate",
                         "reconstruction", "provenance", "metadata", "authority", "execution"}, "Candidate replay")
    expected_metadata = {"contract": STRATEGY_REPLAY_CONTRACT, "rule_version": STRATEGY_REPLAY_RULE,
        "authority_scope": "read_only", "candidate_scope": "HISTORICAL_TECHNICAL_REFERENCE_ONLY",
        "source_authentication": "NOT_VERIFIED", "execution_output": False}
    if _reference_hash(body["metadata"]) != _reference_hash(expected_metadata):
        raise ValueError("Candidate replay metadata mismatch.")
    strategy.exact(body["authority"], _REFERENCE_AUTHORITY_FIELDS, "Candidate replay authority")
    if body["execution"] is not False or any(v is not False for v in body["authority"].values()):
        raise ValueError("Candidate replay cannot grant authority.")
    if body["outcome"] != "CANDIDATE_FORMULATED" or body["candidate"] is None:
        raise ValueError("NO_CANDIDATE")
    provenance = body["provenance"]
    strategy.exact(provenance, {"source_selection", "new_mission_id", "evaluation_time", "source_snapshot_ids",
                              "strategy_source_snapshot_ids", "replay_profile", "profile_sha256"}, "Candidate provenance")
    profile = provenance["replay_profile"]
    strategy.exact(profile, {"strategy_definition", "setup_ordinal", "entry_validity_duration_seconds", "native_versions"}, "Candidate profile")
    expected = _strategy_replay_profile(profile["strategy_definition"], profile["setup_ordinal"], profile["entry_validity_duration_seconds"])
    if _reference_hash(profile) != _reference_hash(expected) or provenance["profile_sha256"] != strategy.identity("", expected):
        raise ValueError("Candidate profile or native version mismatch.")
    reconstruction = body["reconstruction"]
    strategy.exact(reconstruction, {"assessment_input", "action_input", "candidate_input"}, "Candidate reconstruction")
    assessment = strategy.validate_strategy_assessment(body["strategy_assessment"], reconstruction["assessment_input"])
    formulation = candidates.validate_technical_candidate_formulation(body["candidate_formulation"], reconstruction["candidate_input"])
    action = formulation["upstream_formulation"]
    same_pairs = [(body["candidate"], formulation["candidate"]), (body["action_formulation"], action),
        (assessment, action["strategy_assessment"]),
        (reconstruction["action_input"], reconstruction["candidate_input"]["action_formulation_input"]),
        (reconstruction["assessment_input"], reconstruction["action_input"]["assessment_input"]),
        (assessment["strategy_definition"], profile["strategy_definition"]),
        (assessment["setup_ordinal"], profile["setup_ordinal"])]
    for supplied, native in same_pairs:
        if _reference_hash(supplied) != _reference_hash(native):
            raise ValueError("Candidate replay differs from native reconstruction.")
    if formulation["candidate"] is None:
        raise ValueError("NO_CANDIDATE")
    from ced_one.business_divisions.trading import causal_trading_policy_strategy_action_formulation as actions
    expected_action_policy = {"contract": actions.DEFINITION_CONTRACT, "policy_id": STRATEGY_REPLAY_CAPABILITY + ".intent",
        "policy_version": 1, "strategy_definition": profile["strategy_definition"],
        "configuration_fingerprint": strategy.identity("configuration_", profile["strategy_definition"]["configuration"]),
        "declared_action": {"action_type": "DIRECTIONAL_ENTRY_INTENT", "direction": profile["strategy_definition"]["direction"]}}
    expected_policy = {"contract": candidates.POLICY_CONTRACT, "policy_id": STRATEGY_REPLAY_CAPABILITY + ".candidate",
        "policy_version": 1, "configuration": {"entry_validity_duration_seconds": profile["entry_validity_duration_seconds"]}}
    if (_reference_hash(formulation["candidate_policy_definition"]) != _reference_hash(expected_policy) or
            _reference_hash(action["action_policy_definition"]) != _reference_hash(expected_action_policy)):
        raise ValueError("Candidate policy differs from original replay profile.")
    strategy.exact(provenance["source_snapshot_ids"], TIMEFRAME_ORDER, "Original source identities")
    strategy.exact(provenance["strategy_source_snapshot_ids"], strategy.TIMEFRAMES, "Strategy source identities")
    if any(v is not None and (type(v) is not str or not v) for v in provenance["source_snapshot_ids"].values()):
        raise ValueError("Malformed original source identity.")
    for tf, source in reconstruction["assessment_input"]["sources"].items():
        if source["source_snapshot_id"] != provenance["source_snapshot_ids"][tf] or source["source_snapshot_id"] != provenance["strategy_source_snapshot_ids"][tf]:
            raise ValueError("Original candidate source identity mismatch.")
    parent = provenance["source_selection"]
    strategy.exact(parent, set(ref), "Original factual selection")
    if any(type(v) is not str or not v for v in parent.values()):
        raise ValueError("Malformed original factual selection.")
    if (parent["schema_version"], parent["division"], parent["capability"], parent["contract_id"], parent["rule_version"], parent["temporal_scope"]) != (
            "mission_control.archived_context.v1", "trading", "factual_market_context_composition", composition.CONTRACT,
            composition.RULE_VERSION, "HISTORICAL_RECORD_ONLY"):
        raise ValueError("Original factual selection contract mismatch.")
    for key in ("record_sha256", "payload_sha256"):
        if len(parent[key]) != 64 or any(c not in "0123456789abcdef" for c in parent[key]):
            raise ValueError("Malformed original factual hash.")
    times = [_reference_time(parent[k]) for k in ("evaluation_time", "source_request_created_at", "created_not_after", "selected_at")]
    if times != sorted(times) or times[-1] > _reference_time(ref["selected_at"]):
        raise ValueError("Original factual selection chronology mismatch.")
    t = _reference_time(ref["evaluation_time"])
    if (provenance["new_mission_id"] != ref["source_mission_id"] or parent["source_mission_id"] == ref["source_mission_id"] or
            any(_reference_time(v) != t for v in (provenance["evaluation_time"], parent["evaluation_time"],
                assessment["evaluation_boundary"], action["knowledge_boundary"], formulation["candidate"]["valid_from"]))):
        raise ValueError("Candidate origin or C = T boundary mismatch.")
    return ref, deepcopy(body), formulation


def execute_governed_reference_backtest(request):
    """Variant A descriptive reference research; never fills or trade eligibility."""
    from copy import deepcopy
    from datetime import timedelta
    from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as reference
    from ced_one.business_divisions.trading.causal_snapshot_availability import validate_source
    from ced_one.business_divisions.trading.xauusd_causal_liquidity_reversal import exact

    contract = request.metadata["capability_contract"]
    if (contract["name"], contract["contract_id"], contract["permission_scope"]) != (
            REFERENCE_BACKTEST_CAPABILITY, REFERENCE_BACKTEST_CONTRACT, "read_only"):
        raise ValueError("Reference execution contract mismatch.")
    metadata = contract["metadata"]
    profile = metadata["observation_profile"]
    exact(profile, {"research_boundary", "m1", "declarations", "native_versions"}, "Registered observation profile")
    _import_binding(metadata.get("import_binding"), {k: profile[k] for k in ("research_boundary", "m1", "declarations")})
    expected = _reference_profile({k: profile[k] for k in ("research_boundary", "m1", "declarations")})
    if (_reference_hash(profile) != _reference_hash(expected) or metadata["profile_sha256"] != _reference_hash(expected) or
            metadata["rule_version"] != REFERENCE_BACKTEST_RULE or metadata["variant"] != "A"):
        raise ValueError("Reference profile or native version mismatch.")
    ref, body, formulation = _validated_reference_candidate(request.input_payload)
    start = _reference_time(formulation["candidate"]["valid_from"])
    horizon = start + timedelta(minutes=1440)
    boundary = _reference_time(profile["research_boundary"])
    if boundary < horizon:
        raise ValueError("Research boundary precedes 24-hour horizon.")
    source = validate_source(deepcopy(profile["m1"]))
    if source["symbol"] != "XAUUSD" or source["timeframe"] != "M1" or _reference_time(source["requested_evaluation_timestamp"]) != boundary:
        raise ValueError("Observation source must be XAUUSD M1 at K.")
    native_request = {"contract": reference.SCENARIO_CONTRACT, "rule_version": reference.RULE_VERSION, "variant": "A",
        "candidate_formulation": formulation, "formulation_input": body["reconstruction"]["candidate_input"],
        "research_boundary": profile["research_boundary"],
        "evidence": {"m1": source, "m5": None, "declarations": deepcopy(profile["declarations"])}}
    scenario = reference.evaluate_reference_scenario(native_request)
    scenario = reference.validate_reference_scenario(scenario, native_request)
    return {"outcome": scenario["completion_status"], "scenario": scenario, "reconstruction": native_request,
        "provenance": {"source_selection": ref, "new_mission_id": request.mission_id,
            "candidate_provenance": body["provenance"], "candidate_identity": formulation["candidate"]["candidate_identity"],
            "evaluation_time": ref["evaluation_time"], "candidate_start": formulation["candidate"]["valid_from"],
            "observation_horizon": horizon.isoformat().replace("+00:00", "Z"), "research_boundary": profile["research_boundary"],
            "observation_profile_sha256": metadata["profile_sha256"], "native_versions": deepcopy(profile["native_versions"])},
        "metadata": {"contract": REFERENCE_BACKTEST_CONTRACT, "rule_version": REFERENCE_BACKTEST_RULE,
            "authority_scope": "read_only", "research_scope": "RETROSPECTIVE_REFERENCE_RESEARCH",
            "source_authentication": "NOT_VERIFIED", "execution_output": False},
        "authority": dict.fromkeys(_REFERENCE_AUTHORITY_FIELDS, False), "execution": False}


def register_governed_reference_backtest_executor(runtime: LocalExecutionRuntime, *, observation_profile, import_binding=None) -> None:
    profile = _reference_profile(observation_profile)
    runtime.register(CapabilityExecutionContract(
        name=REFERENCE_BACKTEST_CAPABILITY, division_name="trading", contract_id=REFERENCE_BACKTEST_CONTRACT,
        permission_scope="read_only", retryable=False,
        input_schema={"required_fields": ["selection", "original_payload"]},
        output_schema={"required_fields": ["outcome", "scenario", "reconstruction", "provenance", "metadata", "authority", "execution"]},
        metadata={"risk_level": "low", "impact_level": "limited", "requires_archived_context": True,
            "rule_version": REFERENCE_BACKTEST_RULE, "variant": "A", "observation_profile": profile,
            "profile_sha256": _reference_hash(profile),
            **({"import_binding": _import_binding(import_binding, observation_profile)} if import_binding is not None else {})},
    ), execute_governed_reference_backtest)
