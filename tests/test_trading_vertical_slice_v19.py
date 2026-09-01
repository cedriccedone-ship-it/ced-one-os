from __future__ import annotations

from copy import deepcopy

import pytest

from ced_one.business_divisions.trading.causal_factual_event_chronology import (
    CAUSAL_FACTUAL_EVENT_CHRONOLOGY,
    EVENT_FAMILIES,
    MANIFEST_VERSION,
)


TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
CAPABILITIES = (
    "market_structure", "candle_intelligence", "volatility_range", "liquidity_intelligence",
    "liquidity_events", "fvg_imbalance_intelligence", "displacement_intelligence",
    "order_block_intelligence", "structural_dealing_range_intelligence", "premium_discount_intelligence",
)
REQUESTED = "2026-08-17T12:00:00Z"


def envelope(timeframe, capability, result=None, *, state="AVAILABLE_PRESENT", source_id=None, cutoff="2026-08-17T11:00:00Z"):
    source_id = source_id or f"source_{timeframe.lower()}"
    return {
        "symbol": "XAUUSD", "timeframe": timeframe, "requested_evaluation_timestamp": REQUESTED,
        "effective_causal_cutoff": cutoff, "source_snapshot_id": source_id,
        "factual_envelope_id": f"envelope_{timeframe.lower()}_{capability}",
        "factual_availability": state, "authoritative_result_id": f"result_{timeframe.lower()}_{capability}",
        "authoritative_result": {} if result is None else result,
        "capability": {"name": capability, "contract": f"trading.{capability}.v1", "rule_version": f"{capability}_v1", "configuration": {}},
        "dependency_provenance": [], "availability_reason": "classified",
        "provenance": {"configuration_fingerprint": f"configuration_{timeframe.lower()}_{capability}"},
        "evidence": {"configuration_fingerprint": f"configuration_{timeframe.lower()}_{capability}"},
        "metadata": {"contract": "trading.causal_factual_intelligence_envelope.v1"},
    }


def results():
    return {
        "liquidity_events": {"liquidity_events": [{"event_id": "event_1", "event_type": "liquidity_sweep", "source_interaction_type": "swept", "event_timestamp": "2026-08-17T09:00:00Z", "level_created_at": "2026-08-17T08:00:00Z"}], "diagnostics": {"truncated_event_count": 0}},
        "fvg_imbalance_intelligence": {"fair_value_gaps": [{"fvg_id": "fvg_1", "rule_branch": "bullish_fvg", "created_at": "2026-08-17T08:00:00Z", "confirmed_at": "2026-08-17T08:00:00Z", "current_status": "open", "interactions": [{"event_type": "fvg_wick_touch", "candle_timestamp": "2026-08-17T09:00:00Z", "resulting_status": "partially_filled"}]}], "diagnostics": {}},
        "displacement_intelligence": {"displacement_events": [{"event_id": "displacement_1", "direction": "bullish", "source_timestamp": "2026-08-17T07:00:00Z", "confirmed_at": "2026-08-17T07:00:00Z", "created_at": "2026-08-17T07:00:00Z"}], "diagnostics": {"candidate_index_range": {}}},
        "order_block_intelligence": {"order_blocks": [{"order_block_id": "block_1", "direction": "bullish", "source_timestamp": "2026-08-17T06:00:00Z", "confirmed_at": "2026-08-17T07:00:00Z", "created_at": "2026-08-17T07:00:00Z", "current_state": "unvisited", "interactions": [{"interaction_id": "block_event_1", "event_type": "order_block_wick_touch", "candle_timestamp": "2026-08-17T09:00:00Z", "resulting_state": "wick_revisited"}]}], "diagnostics": {"truncated_interaction_count": 0}},
        "structural_dealing_range_intelligence": {"structural_ranges": [{"range_id": "range_1", "chronological_order": "low_to_high", "created_at": "2026-08-17T08:00:00Z", "confirmed_at": "2026-08-17T08:00:00Z"}], "diagnostics": {"truncated_range_count": 0}},
    }


def matrix():
    event_results = results()
    return {timeframe: {capability: envelope(timeframe, capability, event_results.get(capability)) for capability in CAPABILITIES} for timeframe in TIMEFRAMES}


def context(envelopes):
    return {
        "symbol": "XAUUSD", "requested_evaluation_timestamp": REQUESTED, "factual_context_id": "factual_context_1",
        "identity_scope": "snapshot_deterministic", "context_state": "COMPLETE",
        "timeframes": {
            timeframe: {"timeframe": timeframe, "source_snapshot_id": f"source_{timeframe.lower()}", "effective_causal_cutoff": "2026-08-17T11:00:00Z", "factual_context_state": "COMPLETE", "factual_capabilities": {capability: {"factual_envelope_id": envelopes[timeframe][capability]["factual_envelope_id"], "authoritative_result_id": envelopes[timeframe][capability]["authoritative_result_id"], "factual_availability": envelopes[timeframe][capability]["factual_availability"]} for capability in CAPABILITIES}} for timeframe in TIMEFRAMES
        },
        "metadata": {"contract": "trading.causal_factual_multi_timeframe_context.v1"},
    }


def analyze(envelopes=None, factual_context=None):
    envelopes = matrix() if envelopes is None else envelopes
    return CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze({"factual_context": context(envelopes) if factual_context is None else factual_context, "factual_envelopes": envelopes})


def test_v19_fixed_manifest_and_all_timeframes_are_preserved():
    result = analyze()
    assert result.event_source_manifest_version == MANIFEST_VERSION
    assert result.chronology_state == "COMPLETE"
    assert list(result.timeframes) == list(TIMEFRAMES)
    assert set(EVENT_FAMILIES) == {"liquidity_events", "fvg_imbalance_intelligence", "displacement_intelligence", "order_block_intelligence", "structural_dealing_range_intelligence"}


def test_v19_normalizes_only_fixed_source_families_with_terminal_fingerprints():
    result = analyze()
    families = {event["event_family"] for event in result.events}
    assert {"liquidity_sweep", "fvg_created", "fvg_touched", "displacement", "order_block_created", "order_block_wick_touch", "structural_range_created"} <= families
    assert all(event["configuration_fingerprint"].startswith("configuration_") for event in result.events)
    assert all(event["factual_envelope_id"] and event["authoritative_result_id"] for event in result.events)
    assert "premium_discount_intelligence" not in {event["capability_name"] for event in result.events}


def test_v19_orders_distinct_times_and_groups_equal_times_without_factual_tie_claims():
    result = analyze()
    assert [group["event_timestamp"] for group in result.ordering_groups] == sorted(group["event_timestamp"] for group in result.ordering_groups)
    assert all(edge["ordering"] == "BEFORE" for edge in result.chronology_edges)
    equal_group = next(group for group in result.ordering_groups if group["event_timestamp"] == "2026-08-17T09:00:00Z")
    assert len(equal_group["event_ids"]) > 1


def test_v19_exact_duplicates_are_suppressed_and_conflicts_fail_closed():
    envelopes = matrix()
    duplicate = deepcopy(envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][0])
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"].append(duplicate)
    result = analyze(envelopes)
    assert len([event for event in result.events if event["source_event_id"] == "event_1" and event["timeframe"] == "D1"]) == 1
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][1]["event_timestamp"] = "2026-08-17T10:00:00Z"
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        analyze(envelopes)


def test_v19_rejects_mismatched_context_envelope_and_future_event():
    envelopes = matrix()
    envelopes["H4"]["fvg_imbalance_intelligence"]["source_snapshot_id"] = "wrong"
    with pytest.raises(ValueError):
        analyze(envelopes)
    envelopes = matrix()
    envelopes["M1"]["displacement_intelligence"]["authoritative_result"]["displacement_events"][0]["created_at"] = "2026-08-17T12:00:00Z"
    with pytest.raises(ValueError, match="causal cutoff"):
        analyze(envelopes)


def test_v19_evaluated_empty_is_complete_and_coverage_is_explicit():
    envelopes = matrix()
    for timeframe in TIMEFRAMES:
        envelopes[timeframe]["liquidity_events"] = envelope(timeframe, "liquidity_events", {"liquidity_events": [], "diagnostics": {}}, state="AVAILABLE_ABSENT")
    result = analyze(envelopes)
    coverage = result.timeframes["D1"]["coverage"]["liquidity_events"]
    assert result.chronology_state == "COMPLETE"
    assert coverage["evaluated_empty_event_set"] is True
    assert coverage["coverage_state"] == "FULLY_COVERED"


@pytest.mark.parametrize(("state", "expected"), [("UNAVAILABLE", "UNAVAILABLE"), ("INVALID", "INVALID"), ("NOT_EVALUATED", "NOT_EVALUATED")])
def test_v19_degraded_event_source_state_propagates_without_event_inference(state, expected):
    envelopes = matrix()
    envelopes["H4"]["order_block_intelligence"] = envelope("H4", "order_block_intelligence", None, state=state)
    result = analyze(envelopes)
    assert result.chronology_state == expected
    assert result.timeframes["H4"]["event_ids"]["order_block_intelligence"] == []


def test_v19_identity_is_deterministic_and_no_extra_truncation_is_applied():
    first = analyze()
    second = analyze()
    assert first.to_dict() == second.to_dict()
    assert first.chronology_id == second.chronology_id
    assert first.diagnostics["chronology_truncated_count"] == 0
    assert first.identity_scope == "snapshot_deterministic"


def test_v19_rejects_raw_inputs_naive_timestamps_and_missing_terminal_fingerprint():
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze({"candle_history": []})
    envelopes = matrix()
    envelopes["D1"]["fvg_imbalance_intelligence"]["provenance"].pop("configuration_fingerprint")
    with pytest.raises(ValueError, match="fingerprint"):
        analyze(envelopes)
    envelopes = matrix()
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][0]["event_timestamp"] = "2026-08-17T09:00:00"
    with pytest.raises(ValueError, match="timezone"):
        analyze(envelopes)


def test_v19_is_internal_chronology_only_without_strategy_or_lifecycle_invention():
    result = analyze().to_dict()
    text = str(result).lower()
    for forbidden in ["caused", "confirmation", "disqualification", "confluence", "setup", "buy", "sell", "entry", "execution_command", "retirement", "reactivation", "invalidation"]:
        assert forbidden not in text
    assert result["metadata"]["internal_factual_infrastructure"] is True
    assert result["metadata"]["chronology_only"] is True