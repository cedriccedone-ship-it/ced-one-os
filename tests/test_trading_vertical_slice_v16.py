from __future__ import annotations

import pytest

from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
    CAPABILITY_CONTRACTS,
    CAPABILITY_ORDER,
    CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT,
    TIMEFRAME_ORDER,
)


REQUESTED = "2026-08-17T02:00:00Z"


def source_context(*, source_state="AVAILABLE", completion="COMPLETED", context_id="source_context_1", requested=REQUESTED):
    timeframes = {}
    for index, timeframe in enumerate(TIMEFRAME_ORDER):
        timeframes[timeframe] = {
            "timeframe": timeframe,
            "requested_evaluation_timestamp": requested,
            "effective_causal_cutoff": f"2026-08-17T{index + 1:02d}:00:00Z" if source_state == "AVAILABLE" else None,
            "source_snapshot_id": f"source_{timeframe.lower()}" if source_state == "AVAILABLE" else None,
            "source_availability": source_state,
            "availability_reason": "sufficient_causal_source" if source_state == "AVAILABLE" else source_state.lower(),
            "completion_state": completion,
        }
    return {
        "symbol": "XAUUSD",
        "requested_evaluation_timestamp": requested,
        "context_id": context_id,
        "identity_scope": "snapshot_deterministic",
        "context_state": "COMPLETE",
        "timeframes": timeframes,
        "edges": [],
        "diagnostics": {},
        "evidence": {},
        "metadata": {"contract": "trading.causal_multi_timeframe_context.v1", "identity_scope": "snapshot_deterministic"},
    }


def dependency(capability, source_id, order, *, timeframe="H1", requested=REQUESTED, cutoff="2026-08-17T01:00:00Z"):
    return {
        "dependency_order": order,
        "capability_name": capability,
        "capability_contract": CAPABILITY_CONTRACTS[capability],
        "capability_rule_version": f"{capability}_v1",
        "factual_availability": "AVAILABLE_PRESENT",
        "authoritative_result_id": f"result_{capability}",
        "source_snapshot_id": source_id,
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff,
        "configuration_fingerprint": f"configuration_{capability}",
        "controlled_invocation": True,
        "provenance_validation": "validated_controlled_dependency",
    }


def envelope(timeframe, capability, *, state="AVAILABLE_PRESENT", source_id=None, requested=REQUESTED, cutoff=None, dependencies=None):
    source_id = source_id or f"source_{timeframe.lower()}"
    cutoff = cutoff or f"2026-08-17T{(TIMEFRAME_ORDER.index(timeframe) + 1) if timeframe in TIMEFRAME_ORDER else 1:02d}:00:00Z"
    dependency_map = {
        "liquidity_events": [dependency("liquidity_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "order_block_intelligence": [dependency("displacement_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "structural_dealing_range_intelligence": [dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "premium_discount_intelligence": [
            dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff),
            dependency("structural_dealing_range_intelligence", source_id, 2, timeframe=timeframe, requested=requested, cutoff=cutoff),
        ],
    }
    return {
        "factual_envelope_id": f"envelope_{timeframe.lower()}_{capability}" if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "factual_availability": state,
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff,
        "source_snapshot_id": source_id,
        "source_completion_state": "COMPLETED",
        "context_id": None,
        "capability": {"name": capability, "contract": CAPABILITY_CONTRACTS[capability], "rule_version": f"{capability}_v1", "configuration": {}},
        "authoritative_result": {} if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "authoritative_result_id": f"result_{timeframe.lower()}_{capability}" if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "dependency_provenance": dependency_map.get(capability, []) if dependencies is None else dependencies,
        "availability_reason": "classified",
        "provenance": {"controlled_invocation": True},
        "diagnostics": {},
        "evidence": {},
        "metadata": {"contract": "trading.causal_factual_intelligence_envelope.v1", "identity_scope": "snapshot_deterministic"},
    }


def payload(*, context=None, envelopes=None, symbol="XAUUSD", requested=REQUESTED):
    return {
        "symbol": symbol,
        "requested_evaluation_timestamp": requested,
        "source_context": context or source_context(requested=requested),
        "factual_envelopes": envelopes or {
            timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER}
            for timeframe in TIMEFRAME_ORDER
        },
    }


def analyze(**kwargs):
    return CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(payload(**kwargs))


def test_v16_complete_context_has_exact_canonical_shape():
    result = analyze()
    assert result.context_state == "COMPLETE"
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    assert all(list(result.timeframes[name]["factual_capabilities"]) == list(CAPABILITY_ORDER) for name in TIMEFRAME_ORDER)
    assert result.diagnostics["required_timeframe_count"] == 7
    assert result.diagnostics["required_capability_count_per_timeframe"] == 10
    assert result.diagnostics["complete_timeframe_count"] == 7


@pytest.mark.parametrize("missing", TIMEFRAME_ORDER)
def test_v16_missing_timeframe_is_rejected(missing):
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER if timeframe != missing}
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


def test_v16_extra_timeframe_and_capability_are_rejected():
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    envelopes["W2"] = {capability: envelope("W2", capability) for capability in CAPABILITY_ORDER}
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)
    del envelopes["W2"]
    envelopes["H1"]["unknown"] = envelope("H1", "market_structure")
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


@pytest.mark.parametrize("field", ["source_snapshot_id", "effective_causal_cutoff", "timeframe", "requested_evaluation_timestamp"])
def test_v16_source_envelope_matching_is_exact(field):
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    if field == "source_snapshot_id":
        envelopes["H4"]["market_structure"][field] = "wrong_source"
    elif field == "effective_causal_cutoff":
        envelopes["H4"]["market_structure"][field] = "2026-08-17T99:00:00Z"
    elif field == "timeframe":
        envelopes["H4"]["market_structure"][field] = "H1"
    else:
        envelopes["H4"]["market_structure"][field] = "2026-08-17T03:00:00Z"
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


@pytest.mark.parametrize("state", ["AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"])
def test_v16_factual_states_are_preserved_and_complete_for_absence_only(state):
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    envelopes["H1"]["fvg_imbalance_intelligence"] = envelope("H1", "fvg_imbalance_intelligence", state=state)
    result = analyze(envelopes=envelopes)
    assert result.timeframes["H1"]["factual_capabilities"]["fvg_imbalance_intelligence"]["factual_availability"] == state
    expected = "COMPLETE" if state == "AVAILABLE_ABSENT" else {"UNAVAILABLE": "UNAVAILABLE", "INVALID": "INVALID", "NOT_EVALUATED": "NOT_EVALUATED"}[state]
    assert result.context_state == expected


def test_v16_incomplete_source_is_preserved_and_degrades_context():
    result = analyze(context=source_context(completion="INCOMPLETE"))
    assert result.context_state == "INCOMPLETE"
    assert result.timeframes["D1"]["source_completion_state"] == "INCOMPLETE"


def test_v16_dependent_provenance_is_validated():
    result = analyze()
    premium = result.timeframes["D1"]["factual_capabilities"]["premium_discount_intelligence"]
    assert [item["capability_name"] for item in premium["dependency_provenance"]] == ["market_structure", "structural_dealing_range_intelligence"]

    envelopes = payload()["factual_envelopes"]
    envelopes["D1"]["premium_discount_intelligence"]["dependency_provenance"][0]["source_snapshot_id"] = "wrong"
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


def test_v16_identity_is_deterministic_and_source_or_envelope_sensitive():
    first = analyze()
    second = analyze()
    assert first.to_dict() == second.to_dict()
    changed = payload()["factual_envelopes"]
    changed["M5"]["candle_intelligence"]["factual_envelope_id"] = "changed"
    assert first.factual_context_id != analyze(envelopes=changed).factual_context_id
    assert first.identity_scope == "snapshot_deterministic"


def test_v16_historical_timestamp_requires_consistent_context_and_envelopes():
    historical = "2024-01-02T03:04:05Z"
    context = source_context(requested=historical)
    envelopes = {timeframe: {capability: envelope(timeframe, capability, requested=historical) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    result = analyze(context=context, envelopes=envelopes, requested=historical)
    assert result.requested_evaluation_timestamp == historical
    envelopes["M1"]["market_structure"]["requested_evaluation_timestamp"] = REQUESTED
    with pytest.raises(ValueError):
        analyze(context=context, envelopes=envelopes, requested=historical)


def test_v16_rejects_raw_candles_and_raw_detector_results():
    invalid = payload()
    invalid["candle_history"] = []
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(invalid)
    invalid = payload()
    invalid["factual_envelopes"]["D1"]["market_structure"] = {"structure_state": "bullish_structure"}
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(invalid)


def test_v16_has_no_strategy_or_cross_timeframe_interpretation():
    result = analyze().to_dict()
    text = str(result).lower()
    for forbidden in ["buy", "sell", "signal", "setup", "confidence", "recommendation", "trade_bias", "confirmation", "confluence", "bullish_alignment", "bearish_alignment"]:
        assert forbidden not in text
    assert result["metadata"]["authority_scope"] == "read_only"


def test_v16_public_contract_is_bounded():
    result = analyze().to_dict()
    assert set(result) == {"symbol", "requested_evaluation_timestamp", "source_context_id", "factual_context_id", "identity_scope", "context_state", "timeframes", "diagnostics", "evidence", "metadata"}
    assert "approved_candle_history" not in result["evidence"]