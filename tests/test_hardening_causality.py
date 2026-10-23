"""Approved H1-H5 regressions use real producers, not asserted identity labels."""
from copy import deepcopy
import pytest
from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceAnalyzer
from ced_one.business_divisions.trading.liquidity_events import LiquidityEventsAnalyzer


def liquidity_payload(highs, *, mirrored=False, lookback=100):
    candles = [dict(timestamp=f"2026-08-16T{i:02d}:00:00Z", open=100, high=h, low=99, close=100)
               for i, h in enumerate(highs)]
    if mirrored:
        candles = [{**c, "open": 200-c["open"], "close": 200-c["close"],
                    "high": 200-c["low"], "low": 200-c["high"]} for c in candles]
    return dict(symbol="XAUUSD", timeframe="H1", evaluation_time="2026-08-17T12:00:00Z",
                candle_history=candles, config={"lookback_candles": lookback})


@pytest.mark.parametrize("mirrored", [False, True])
def test_h2_prefix_invariance_including_later_membership(mirrored):
    payload = liquidity_payload([105,110,104,110.2,104,110.3,110.4,104], mirrored=mirrored)
    short = deepcopy(payload); short["candle_history"] = short["candle_history"][:6]
    earlier = LiquidityIntelligenceAnalyzer().analyze(short)
    later = LiquidityIntelligenceAnalyzer().analyze(payload)
    assert earlier.historical_interactions == [r for r in later.historical_interactions if r["candle_index"] < 6]
    row = next(r for r in earlier.historical_interactions if r["candle_index"] == 5 and "cluster" in r["level_type"])
    assert row["event_type"] == "breached"
    assert all(m["confirmed_at_index"] < row["candle_index"] for m in row["causal_boundary"]["members"])
    assert later.evidence["historical_reporting_domain"]["retention_limit"] is None
    mapped = LiquidityEventsAnalyzer().analyze(payload)
    event = next(e for e in mapped.liquidity_events if e["event_timestamp"] == row["candle_timestamp"] and e["level_id"] == row["causal_boundary_id"])
    assert event["event_type"] == "liquidity_sweep"
    assert event["causal_boundary"] == row["causal_boundary"]


def test_h2_later_member_does_not_delete_interaction_and_lookback_is_historical():
    payload = liquidity_payload([105,110,104,110.2,104,110.3,104,104,104,104], lookback=3)
    result = LiquidityIntelligenceAnalyzer().analyze(payload)
    assert result.liquidity_levels == []  # Current candidate domain has moved on.
    assert result.historical_interactions
    for row in result.historical_interactions:
        i = row["candle_index"]
        assert all(max(0,i-3) <= m["pivot_index"] and m["confirmed_at_index"] < i
                   for m in row["causal_boundary"]["members"])
    assert any(r["candle_index"] == 3 for r in result.historical_interactions)
    limited = LiquidityEventsAnalyzer().analyze({**payload, "config": {"lookback_candles": 3, "maximum_events": 1}})
    assert limited.diagnostics["truncated_event_count"] > 0


def test_h2_confirmation_candle_excluded_next_candle_eligible():
    result = LiquidityIntelligenceAnalyzer().analyze(liquidity_payload([105,110,109,110]))
    assert [r["candle_index"] for r in result.historical_interactions] == [3]


def test_h2_candidate_window_includes_i_minus_lookback_and_excludes_older_pivots():
    result = LiquidityIntelligenceAnalyzer().analyze(liquidity_payload([105,110,104,109,110,110], lookback=3))
    at_four = [r for r in result.historical_interactions if r["candle_index"] == 4]
    assert any(m["pivot_index"] == 1 for r in at_four for m in r["causal_boundary"]["members"])
    assert all(m["pivot_index"] >= 2 for r in result.historical_interactions if r["candle_index"] == 5
               for m in r["causal_boundary"]["members"])


def test_h2_later_cluster_member_retains_its_earlier_interaction():
    payload = liquidity_payload([105,110,104,110.2,104,110.3,104])
    result = LiquidityIntelligenceAnalyzer().analyze(payload)
    current = next(level for level in result.liquidity_levels if level["level_type"] == "equal_high_cluster")
    assert payload["candle_history"][5]["timestamp"] in current["member_timestamps"]
    prior = next(r for r in result.historical_interactions if r["candle_index"] == 5 and "cluster" in r["level_type"])
    assert prior["event_type"] == "breached"
    assert prior["causal_boundary_id"] != current["causal_boundary_id"]
    assert [m["pivot_index"] for m in prior["causal_boundary"]["members"]] == [1,3]
