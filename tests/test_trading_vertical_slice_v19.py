from __future__ import annotations

from copy import deepcopy

import pytest

from ced_one.business_divisions.trading.causal_factual_event_chronology import (
    CAUSAL_FACTUAL_EVENT_CHRONOLOGY,
    EVENT_FAMILIES,
    MANIFEST_VERSION,
)
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE,
)
from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
    CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT,
)


TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
CAPABILITIES = (
    "market_structure", "candle_intelligence", "volatility_range", "liquidity_intelligence",
    "liquidity_events", "fvg_imbalance_intelligence", "displacement_intelligence",
    "order_block_intelligence", "structural_dealing_range_intelligence", "premium_discount_intelligence",
)
REQUESTED = "2026-08-17T12:00:00Z"


def dependency(capability, source_id, order, *, timeframe, requested=REQUESTED, cutoff):
    return {
        "dependency_order": order,
        "capability_name": capability,
        "capability_contract": f"trading.{capability}.v1",
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


def envelope(timeframe, capability, result=None, *, state="AVAILABLE_PRESENT", source_id=None, cutoff=None, requested=REQUESTED):
    source_id = source_id or f"source_{timeframe.lower()}"
    cutoff = cutoff or f"{requested.split('T')[0]}T{TIMEFRAMES.index(timeframe) + 1:02d}:00:00Z"
    evaluated = state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}
    dependency_chains = {
        "liquidity_events": [dependency("liquidity_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "order_block_intelligence": [dependency("displacement_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "structural_dealing_range_intelligence": [dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "premium_discount_intelligence": [
            dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff),
            dependency("structural_dealing_range_intelligence", source_id, 2, timeframe=timeframe, requested=requested, cutoff=cutoff),
        ],
    }
    return {
        "symbol": "XAUUSD", "timeframe": timeframe, "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff, "source_snapshot_id": source_id,
        "source_completion_state": "COMPLETED",
        "factual_envelope_id": f"envelope_{timeframe.lower()}_{capability}" if evaluated else None,
        "factual_availability": state, "authoritative_result_id": f"result_{timeframe.lower()}_{capability}" if evaluated else None,
        "authoritative_result": ({"diagnostics": {}} if result is None else result) if evaluated else None,
        "capability": {"name": capability, "contract": f"trading.{capability}.v1", "rule_version": f"{capability}_v1", "configuration": {}},
        "dependency_provenance": dependency_chains.get(capability, []), "availability_reason": "classified",
        "provenance": {"controlled_invocation": True, "configuration_fingerprint": f"configuration_{timeframe.lower()}_{capability}"},
        "diagnostics": {},
        "evidence": {"configuration_fingerprint": f"configuration_{timeframe.lower()}_{capability}"},
        "metadata": {"contract": "trading.causal_factual_intelligence_envelope.v1", "identity_scope": "snapshot_deterministic"},
    }


def results():
    return {
        "liquidity_events": {"liquidity_events": [{"event_id": "event_1", "event_type": "liquidity_sweep", "source_interaction_type": "swept", "event_timestamp": "2026-08-17T00:45:00Z", "level_created_at": "2026-08-17T00:40:00Z"}], "diagnostics": {"truncated_event_count": 0}},
        "fvg_imbalance_intelligence": {"fair_value_gaps": [{"fvg_id": "fvg_1", "evidence": {"rule_branch": "bullish_fvg"}, "created_at": "2026-08-17T00:20:00Z", "confirmed_at": "2026-08-17T00:20:00Z", "current_status": "open", "interactions": [{"event_type": "touched_event", "candle_timestamp": "2026-08-17T00:45:00Z", "resulting_status": "open"}]}], "diagnostics": {}},
        "displacement_intelligence": {"displacement_events": [{"event_id": "displacement_1", "direction": "bullish", "source_timestamp": "2026-08-17T00:10:00Z", "confirmed_at": "2026-08-17T00:10:00Z", "created_at": "2026-08-17T00:10:00Z"}], "diagnostics": {"candidate_index_range": {}}},
        "order_block_intelligence": {"order_blocks": [{"order_block_id": "block_1", "direction": "bullish", "source_timestamp": "2026-08-17T00:05:00Z", "confirmed_at": "2026-08-17T00:10:00Z", "created_at": "2026-08-17T00:10:00Z", "current_state": "unvisited", "interactions": [{"interaction_id": "block_event_1", "event_type": "order_block_wick_touch", "candle_timestamp": "2026-08-17T00:45:00Z", "resulting_state": "wick_revisited"}]}], "diagnostics": {"truncated_interaction_count": 0}},
        "structural_dealing_range_intelligence": {"structural_ranges": [{"range_id": "range_1", "chronological_order": "low_to_high", "created_at": "2026-08-17T00:30:00Z", "confirmed_at": "2026-08-17T00:30:00Z"}], "diagnostics": {"truncated_range_count": 0}},
    }


def matrix(*, requested=REQUESTED):
    event_results = results()
    return {timeframe: {capability: envelope(timeframe, capability, event_results.get(capability), requested=requested) for capability in CAPABILITIES} for timeframe in TIMEFRAMES}


def source_context(*, requested=REQUESTED, h1_cutoff=None):
    date = requested.split("T")[0]
    timeframes = {}
    for index, timeframe in enumerate(TIMEFRAMES):
        timeframes[timeframe] = {
            "timeframe": timeframe,
            "requested_evaluation_timestamp": requested,
            "effective_causal_cutoff": h1_cutoff if timeframe == "H1" and h1_cutoff is not None else f"{date}T{index + 1:02d}:00:00Z",
            "source_snapshot_id": f"source_{timeframe.lower()}",
            "source_availability": "AVAILABLE",
            "availability_reason": "sufficient_causal_source",
            "completion_state": "COMPLETED",
        }
    return {
        "symbol": "XAUUSD", "requested_evaluation_timestamp": requested, "context_id": "source_context_v19",
        "identity_scope": "snapshot_deterministic", "context_state": "COMPLETE",
        "timeframes": timeframes, "edges": [], "diagnostics": {}, "evidence": {},
        "metadata": {"contract": "trading.causal_multi_timeframe_context.v1", "identity_scope": "snapshot_deterministic"},
    }


def real_context(envelopes, *, requested=REQUESTED, h1_cutoff=None):
    return CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze({
        "symbol": "XAUUSD", "requested_evaluation_timestamp": requested,
        "source_context": source_context(requested=requested, h1_cutoff=h1_cutoff), "factual_envelopes": envelopes,
    }).to_dict()


def context(envelopes):
    return real_context(envelopes)


def analyze(envelopes=None, factual_context=None):
    envelopes = matrix() if envelopes is None else envelopes
    return CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze({"factual_context": context(envelopes) if factual_context is None else factual_context, "factual_envelopes": envelopes})


INTEGRATION_REQUESTED = "2026-08-17T12:00:00Z"


def integration_candle(index, *, open_price, high, low, close):
    hour = f"{index:02d}"
    return {"timestamp": f"2026-08-17T{hour}:00:00Z", "open": open_price, "high": high, "low": low, "close": close}


def integration_fvg_scenario():
    return [
        integration_candle(0, open_price=98.0, high=100.0, low=97.0, close=99.0),
        integration_candle(1, open_price=99.0, high=101.0, low=98.0, close=100.0),
        integration_candle(2, open_price=102.0, high=104.0, low=101.0, close=103.0),
        integration_candle(3, open_price=101.5, high=102.0, low=101.0, close=101.5),
        integration_candle(4, open_price=101.0, high=101.5, low=100.5, close=101.0),
        integration_candle(5, open_price=100.5, high=101.0, low=100.0, close=100.5),
    ]


def integration_causal_source(candles):
    return {
        "symbol": "XAUUSD", "timeframe": "H1", "requested_evaluation_timestamp": INTEGRATION_REQUESTED,
        "effective_causal_cutoff": "2026-08-17T05:00:00Z", "source_snapshot_id": "source_h1",
        "source_availability": "AVAILABLE", "availability_reason": "sufficient_causal_source",
        "completion_state": "COMPLETED", "approved_candle_history": candles,
        "diagnostics": {}, "evidence": {},
        "metadata": {"contract": "trading.causal_snapshot_availability.v1", "identity_scope": "snapshot_deterministic"},
    }


def integration_fvg_envelope(candles):
    return CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze({
        "symbol": "XAUUSD", "timeframe": "H1", "requested_evaluation_timestamp": INTEGRATION_REQUESTED,
        "causal_source": integration_causal_source(candles),
        "capability": {"name": "fvg_imbalance_intelligence", "contract": "trading.fvg_imbalance_intelligence.v1", "rule_version": "fvg_imbalance_intelligence_v1", "configuration": {}},
    }).to_dict()


def integration_matrix(fvg_envelope_dict):
    grouped = matrix(requested=INTEGRATION_REQUESTED)
    h1 = grouped["H1"]
    for capability in CAPABILITIES:
        h1[capability] = envelope("H1", capability, requested=INTEGRATION_REQUESTED, cutoff=f"{INTEGRATION_REQUESTED.split('T')[0]}T05:00:00Z")
    h1["fvg_imbalance_intelligence"] = fvg_envelope_dict
    return grouped


def integration_payload(candles=None):
    candles = integration_fvg_scenario() if candles is None else candles
    envelopes = integration_matrix(integration_fvg_envelope(candles))
    h1_cutoff = envelopes["H1"]["fvg_imbalance_intelligence"]["effective_causal_cutoff"]
    return {"factual_context": real_context(envelopes, requested=INTEGRATION_REQUESTED, h1_cutoff=h1_cutoff), "factual_envelopes": envelopes}


def test_v19_real_fvg_producer_interactions_reach_chronology():
    payload = integration_payload()
    fvg_result = payload["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]
    source_fvg = fvg_result["authoritative_result"]["fair_value_gaps"][0]
    assert [item["event_type"] for item in source_fvg["interactions"]] == ["touched_event", "partial_fill_event", "fully_filled_event"]

    result = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(payload)

    h1_events = [event for event in result.events if event["timeframe"] == "H1" and event["capability_name"] == "fvg_imbalance_intelligence"]
    assert [event["event_family"] for event in h1_events] == ["fvg_created", "fvg_touched", "fvg_partial_fill", "fvg_fully_filled"]
    expected_sources = [source_fvg["fvg_id"]] + [f"{source_fvg['fvg_id']}:{item['candle_timestamp']}:{item['event_type']}" for item in source_fvg["interactions"]]
    assert [event["source_event_id"] for event in h1_events] == expected_sources
    assert [event["event_timestamp"] for event in h1_events] == [source_fvg["created_at"]] + [item["candle_timestamp"] for item in source_fvg["interactions"]]
    assert all(event["factual_envelope_id"] == fvg_result["factual_envelope_id"] for event in h1_events)
    assert all(event["authoritative_result_id"] == fvg_result["authoritative_result_id"] for event in h1_events)
    assert all(event["source_snapshot_id"] == "source_h1" for event in h1_events)
    assert all(event["effective_causal_cutoff"] == "2026-08-17T05:00:00Z" for event in h1_events)
    assert all(event["configuration_fingerprint"] == fvg_result["provenance"]["configuration_fingerprint"] == fvg_result["evidence"]["configuration_fingerprint"] for event in h1_events)
    assert CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(integration_payload()).to_dict() == result.to_dict()


def corrupted_integration_payload(mutate):
    payload = integration_payload()
    fvg_envelope_dict = deepcopy(payload["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"])
    mutate(fvg_envelope_dict["authoritative_result"]["fair_value_gaps"][0])
    envelopes = integration_matrix(fvg_envelope_dict)
    h1_cutoff = fvg_envelope_dict["effective_causal_cutoff"]
    return {"factual_context": real_context(envelopes, requested=INTEGRATION_REQUESTED, h1_cutoff=h1_cutoff), "factual_envelopes": envelopes}


def test_v19_real_fvg_unknown_interaction_event_type_fails_closed():
    payload = corrupted_integration_payload(lambda fvg: fvg["interactions"][1].update(event_type="unknown_interaction_type"))
    with pytest.raises(ValueError, match="bullish_fvg_1.*missing or unrecognized event_type.*unknown_interaction_type"):
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(payload)


def test_v19_real_fvg_missing_interaction_event_type_fails_closed():
    payload = corrupted_integration_payload(lambda fvg: fvg["interactions"][0].pop("event_type"))
    with pytest.raises(ValueError, match="missing or unrecognized event_type"):
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(payload)


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
    equal_group = next(group for group in result.ordering_groups if group["event_timestamp"] == "2026-08-17T00:45:00Z")
    assert len(equal_group["event_ids"]) > 1


def test_v19_exact_duplicates_are_suppressed_and_conflicts_fail_closed():
    envelopes = matrix()
    duplicate = deepcopy(envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][0])
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"].append(duplicate)
    result = analyze(envelopes)
    assert len([event for event in result.events if event["source_event_id"] == "event_1" and event["timeframe"] == "D1"]) == 1
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][1]["event_timestamp"] = "2026-08-17T00:50:00Z"
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
    envelopes["D1"]["liquidity_events"]["authoritative_result"]["liquidity_events"][0]["event_timestamp"] = "2026-08-17T00:45:00"
    with pytest.raises(ValueError, match="timezone"):
        analyze(envelopes)


def test_v19_is_internal_chronology_only_without_strategy_or_lifecycle_invention():
    result = analyze().to_dict()
    text = str(result).lower()
    for forbidden in ["caused", "confirmation", "disqualification", "confluence", "setup", "buy", "sell", "entry", "execution_command", "retirement", "reactivation", "invalidation"]:
        assert forbidden not in text
    assert result["metadata"]["internal_factual_infrastructure"] is True
    assert result["metadata"]["chronology_only"] is True