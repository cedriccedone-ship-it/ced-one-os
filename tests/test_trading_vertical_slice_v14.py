from __future__ import annotations

from copy import deepcopy
import re

import pytest

from ced_one.business_divisions.trading.causal_multi_timeframe_context import (
    EDGE_ALIGNMENT_STATES,
    TIMEFRAME_ORDER,
    CausalMultiTimeframeContextAnalyzer,
)


REQUESTED = "2026-08-16T12:00:00Z"


def source(timeframe: str, *, availability: str = "AVAILABLE", completion: str = "COMPLETED", snapshot_id: str | None = None, symbol: str = "XAUUSD", requested: str = REQUESTED, cutoff: str | None = "2026-08-16T11:00:00Z", reason: str = "sufficient_causal_source"):
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff,
        "source_snapshot_id": snapshot_id if snapshot_id is not None else (f"causal_snapshot_{timeframe.lower()}" if availability == "AVAILABLE" else None),
        "source_availability": availability,
        "availability_reason": reason,
        "completion_state": completion,
        "approved_candle_history": [] if availability != "AVAILABLE" else [{"timestamp": "2026-08-16T10:00:00Z"}],
        "diagnostics": {},
        "evidence": {},
        "metadata": {},
    }


def payload(*, sources=None, symbol: str = "XAUUSD", requested: str = REQUESTED):
    return {
        "symbol": symbol,
        "requested_evaluation_timestamp": requested,
        "timeframe_sources": {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER} if sources is None else sources,
    }


def analyze(**kwargs):
    return CausalMultiTimeframeContextAnalyzer().analyze(payload(**kwargs))


def test_v14_complete_context_has_exact_ordered_slots_and_edges():
    result = analyze()
    assert result.context_state == "COMPLETE"
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    assert [(edge["parent_timeframe"], edge["child_timeframe"]) for edge in result.edges] == list(zip(TIMEFRAME_ORDER, TIMEFRAME_ORDER[1:]))
    assert len(result.edges) == 6
    assert all(edge["alignment_status"] == "ALIGNED" for edge in result.edges)


def test_v14_preserves_each_source_record_and_cutoff():
    sources = {timeframe: source(timeframe, cutoff=f"2026-08-16T{index + 1:02d}:00:00Z") for index, timeframe in enumerate(TIMEFRAME_ORDER)}
    result = analyze(sources=sources)
    assert [result.timeframes[item]["effective_causal_cutoff"] for item in TIMEFRAME_ORDER] == [
        "2026-08-16T01:00:00Z", "2026-08-16T02:00:00Z", "2026-08-16T03:00:00Z",
        "2026-08-16T04:00:00Z", "2026-08-16T05:00:00Z", "2026-08-16T06:00:00Z", "2026-08-16T07:00:00Z",
    ]
    assert [result.timeframes[item]["source_snapshot_id"] for item in TIMEFRAME_ORDER] == [f"causal_snapshot_{item.lower()}" for item in TIMEFRAME_ORDER]


@pytest.mark.parametrize("missing", TIMEFRAME_ORDER)
def test_v14_missing_required_slot_is_rejected(missing):
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER if timeframe != missing}
    with pytest.raises(ValueError, match="Missing required timeframe sources"):
        analyze(sources=sources)


def test_v14_extra_slot_is_rejected():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["W2"] = source("W2")
    with pytest.raises(ValueError, match="Unsupported timeframe sources"):
        analyze(sources=sources)


def test_v14_slot_must_match_embedded_source_timeframe():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["H1"] = source("H4")
    with pytest.raises(ValueError, match="embedded timeframe does not match slot"):
        analyze(sources=sources)


@pytest.mark.parametrize("field,value", [("symbol", "EURUSD"), ("requested", "2026-08-16T12:01:00Z")])
def test_v14_rejects_mixed_symbol_or_requested_timestamp(field, value):
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    if field == "symbol":
        sources["H1"]["symbol"] = value
    else:
        sources["H1"]["requested_evaluation_timestamp"] = value
    with pytest.raises(ValueError):
        analyze(sources=sources)


def test_v14_authoritative_invalid_source_is_preserved_and_invalidates_context():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["H4"] = source("H4", availability="INVALID", completion="UNKNOWN", reason="invalid_source")
    result = analyze(sources=sources)
    assert result.context_state == "INVALID"
    assert result.timeframes["H4"]["source_availability"] == "INVALID"
    assert result.timeframes["H4"]["source_snapshot_id"] is None
    assert result.edges[0]["alignment_status"] == "CHILD_INVALID"
    assert result.edges[1]["alignment_status"] == "PARENT_INVALID"


def test_v14_unknown_source_state_is_malformed_input():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["H4"]["source_availability"] = "UNKNOWN"
    with pytest.raises(ValueError, match="unknown source availability"):
        analyze(sources=sources)


def test_v14_available_incomplete_source_produces_incomplete_context():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["M15"] = source("M15", completion="INCOMPLETE")
    result = analyze(sources=sources)
    assert result.context_state == "INCOMPLETE"
    assert result.timeframes["M15"]["completion_state"] == "INCOMPLETE"
    assert result.timeframes["M15"]["source_availability"] == "AVAILABLE"


def test_v14_available_unknown_completion_is_fail_closed_to_unavailable():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["H1"] = source("H1", completion="UNKNOWN")
    result = analyze(sources=sources)
    assert result.context_state == "UNAVAILABLE"
    assert result.timeframes["H1"]["completion_state"] == "UNKNOWN"
    assert result.edges[1]["alignment_status"] == "CHILD_UNAVAILABLE"


@pytest.mark.parametrize(
    ("availability", "completion", "expected"),
    [
        ("UNAVAILABLE", "UNKNOWN", "UNAVAILABLE"),
        ("NOT_EVALUATED", "UNKNOWN", "NOT_EVALUATED"),
    ],
)
def test_v14_context_state_for_authoritative_degraded_sources(availability, completion, expected):
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["M1"] = source("M1", availability=availability, completion=completion, reason=availability.lower())
    result = analyze(sources=sources)
    assert result.context_state == expected
    assert result.timeframes["M1"]["source_availability"] == availability


def test_v14_precedence_is_invalid_then_unavailable_then_not_evaluated_then_incomplete():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["D1"] = source("D1", completion="INCOMPLETE")
    sources["H4"] = source("H4", availability="NOT_EVALUATED", completion="UNKNOWN")
    sources["H1"] = source("H1", availability="UNAVAILABLE", completion="UNKNOWN")
    sources["M30"] = source("M30", availability="INVALID", completion="UNKNOWN", reason="invalid_source")
    assert analyze(sources=sources).context_state == "INVALID"
    sources["M30"] = source("M30", availability="AVAILABLE", completion="COMPLETED")
    assert analyze(sources=sources).context_state == "UNAVAILABLE"
    sources["H1"] = source("H1", availability="AVAILABLE", completion="COMPLETED")
    assert analyze(sources=sources).context_state == "NOT_EVALUATED"
    sources["H4"] = source("H4", availability="AVAILABLE", completion="COMPLETED")
    assert analyze(sources=sources).context_state == "INCOMPLETE"


def test_v14_intermediate_gap_remains_explicit():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["H4"] = source("H4", availability="UNAVAILABLE", completion="UNKNOWN", reason="incomplete_current_candle")
    result = analyze(sources=sources)
    assert result.context_state == "UNAVAILABLE"
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    assert result.edges[0]["alignment_status"] == "CHILD_UNAVAILABLE"
    assert result.edges[1]["alignment_status"] == "PARENT_UNAVAILABLE"
    assert not any(edge["parent_timeframe"] == "D1" and edge["child_timeframe"] == "H1" for edge in result.edges)


def test_v14_edge_alignment_vocabulary_is_source_only():
    sources = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    sources["D1"] = source("D1", availability="INVALID", completion="UNKNOWN", reason="invalid_source")
    sources["H4"] = source("H4", availability="UNAVAILABLE", completion="UNKNOWN", reason="incomplete_current_candle")
    result = analyze(sources=sources)
    assert {edge["alignment_status"] for edge in result.edges} <= EDGE_ALIGNMENT_STATES
    assert result.edges[0]["alignment_status"] == "PARENT_INVALID"
    assert result.edges[1]["alignment_status"] == "PARENT_UNAVAILABLE"
    text = str(result.to_dict()).lower()
    for forbidden in ["bullish", "bearish", "confirmation", "confluence", "trade_bias"]:
        assert forbidden not in text


def test_v14_identity_is_deterministic_and_all_source_descriptors_participate():
    first = analyze()
    second = analyze()
    changed_id = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    changed_id["M5"]["source_snapshot_id"] = "causal_snapshot_changed"
    changed_state = {timeframe: source(timeframe) for timeframe in TIMEFRAME_ORDER}
    changed_state["M5"] = source("M5", availability="UNAVAILABLE", completion="UNKNOWN", reason="incomplete_current_candle")
    assert first.to_dict() == second.to_dict()
    assert first.context_id == second.context_id
    assert first.context_id != analyze(sources=changed_id).context_id
    assert first.context_id != analyze(sources=changed_state).context_id
    assert first.identity_scope == "snapshot_deterministic"


def test_v14_history_is_not_accepted_and_source_histories_are_not_duplicated():
    invalid = payload()
    invalid["candle_history"] = []
    with pytest.raises(ValueError, match="Unsupported input fields"):
        CausalMultiTimeframeContextAnalyzer().analyze(invalid)
    result = analyze()
    assert all("approved_candle_history" not in record for record in result.timeframes.values())
    assert "approved_candle_history" not in result.evidence


def test_v14_historical_common_timestamp_is_accepted():
    historical = "2024-01-02T03:04:05Z"
    sources = {timeframe: source(timeframe, requested=historical) for timeframe in TIMEFRAME_ORDER}
    result = analyze(sources=sources, requested=historical)
    assert result.requested_evaluation_timestamp == historical


def test_v14_public_shape_and_diagnostics_are_bounded():
    result = analyze()
    assert set(result.to_dict()) == {
        "symbol", "requested_evaluation_timestamp", "context_id", "identity_scope", "context_state",
        "timeframes", "edges", "diagnostics", "evidence", "metadata",
    }
    assert result.diagnostics == {
        "required_timeframe_count": 7,
        "available_timeframe_count": 7,
        "unavailable_timeframe_count": 0,
        "invalid_timeframe_count": 0,
        "not_evaluated_timeframe_count": 0,
        "completed_timeframe_count": 7,
        "incomplete_timeframe_count": 0,
        "complete_edge_count": 6,
        "incomplete_edge_count": 0,
    }
    assert result.evidence["timeframe_order"] == list(TIMEFRAME_ORDER)
    assert result.evidence["rule_version"] == "causal_multi_timeframe_context_v1"


def test_v14_source_only_boundary_has_no_detector_or_strategy_semantics():
    result = analyze().to_dict()
    assert result["metadata"]["source_context_only"] is True
    assert result["metadata"]["authority_scope"] == "read_only"
    text = str(result).lower()
    for forbidden in [
        "market_structure", "candle_intelligence", "liquidity", "fvg", "displacement", "order_block",
        "premium", "discount", "buy", "sell", "signal", "setup", "recommendation", "execution_command",
    ]:
        assert forbidden not in text


def test_v14_does_not_add_specialist_or_resolver_behavior():
    result = analyze()
    assert "specialist" not in result.metadata
    assert "resolver" not in result.metadata
    assert "registry" not in result.metadata