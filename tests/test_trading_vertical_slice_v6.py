from __future__ import annotations

import re

from ced_one.business_divisions.trading.liquidity_intelligence import (
    LiquidityIntelligenceAnalyzer,
    LiquidityIntelligenceConfig,
    LiquidityIntelligenceSpecialist,
)


def _candle(timestamp: str, *, open_price: float, high: float, low: float, close: float):
    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _payload(candles, *, config=None, timeframe="H1"):
    payload = {
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "evaluation_time": "2026-08-16T10:00:00Z",
        "candle_history": candles,
    }
    if config is not None:
        payload["config"] = config
    return payload


def _find_levels(result, level_type: str):
    return [item for item in result.liquidity_levels if item["level_type"] == level_type]


def test_trading_vertical_slice_v6_confirmed_pivots_map_to_levels_and_non_confirmed_excluded():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=106.0, low=98.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=112.0, low=99.0, close=110.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=108.0, low=94.0, close=97.0),
        _candle("2026-08-16T03:00:00Z", open_price=97.0, high=109.0, low=96.0, close=104.0),
        _candle("2026-08-16T04:00:00Z", open_price=104.0, high=109.5, low=97.0, close=103.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))

    highs = _find_levels(result, "confirmed_swing_high_level")
    lows = _find_levels(result, "confirmed_swing_low_level")
    assert any(item["representative_price"] == 112.0 for item in highs)
    assert any(item["representative_price"] == 94.0 for item in lows)
    assert not any(item["representative_price"] == 109.0 for item in highs)


def test_trading_vertical_slice_v6_anti_lookahead_and_confirming_candle_exclusion():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=98.0, close=102.0),
        _candle("2026-08-16T01:00:00Z", open_price=102.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=109.0, low=97.0, close=106.0),
        _candle("2026-08-16T03:00:00Z", open_price=106.0, high=110.0, low=100.0, close=105.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(
        _payload(candles, config={"minimum_cluster_members": 3, "include_single_swing_levels": True})
    )
    levels = _find_levels(result, "confirmed_swing_high_level")
    level_110 = [item for item in levels if item["representative_price"] == 110.0][0]

    assert level_110["source_timestamp"] == "2026-08-16T01:00:00Z"
    assert level_110["created_at"] == "2026-08-16T02:00:00Z"
    assert level_110["interaction_count"] == 1
    assert level_110["interactions"][0]["candle_timestamp"] == "2026-08-16T03:00:00Z"


def test_trading_vertical_slice_v6_equal_high_cluster_membership_and_causal_creation():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.4, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
        _candle("2026-08-16T05:00:00Z", open_price=100.0, high=110.2, low=94.0, close=108.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=103.0, low=93.0, close=99.0),
        _candle("2026-08-16T07:00:00Z", open_price=99.0, high=110.3, low=98.0, close=109.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))
    clusters = _find_levels(result, "equal_high_cluster")

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["member_count"] == 3
    assert cluster["member_prices"] == [110.0, 110.4, 110.2]
    assert cluster["member_timestamps"] == ["2026-08-16T01:00:00Z", "2026-08-16T03:00:00Z", "2026-08-16T05:00:00Z"]
    assert cluster["member_confirmed_at"] == ["2026-08-16T02:00:00Z", "2026-08-16T04:00:00Z", "2026-08-16T06:00:00Z"]
    assert cluster["created_at"] == "2026-08-16T04:00:00Z"
    assert cluster["latest_member_at"] == "2026-08-16T05:00:00Z"


def test_trading_vertical_slice_v6_equal_high_exact_tolerance_clusters_and_outside_tolerance_does_not():
    inside = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.5, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
    ]
    outside = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.6, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
    ]
    inside_result = LiquidityIntelligenceAnalyzer().analyze(_payload(inside))
    outside_result = LiquidityIntelligenceAnalyzer().analyze(_payload(outside))

    assert len(_find_levels(inside_result, "equal_high_cluster")) == 1
    assert len(_find_levels(outside_result, "equal_high_cluster")) == 0


def test_trading_vertical_slice_v6_equal_low_cluster_and_no_multi_cluster_membership():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=110.0, high=114.0, low=102.0, close=108.0),
        _candle("2026-08-16T01:00:00Z", open_price=108.0, high=113.0, low=100.0, close=103.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=115.0, low=101.0, close=111.0),
        _candle("2026-08-16T03:00:00Z", open_price=111.0, high=116.0, low=100.4, close=113.0),
        _candle("2026-08-16T04:00:00Z", open_price=113.0, high=117.0, low=106.0, close=116.0),
        _candle("2026-08-16T05:00:00Z", open_price=116.0, high=118.0, low=100.2, close=117.0),
        _candle("2026-08-16T06:00:00Z", open_price=117.0, high=119.0, low=107.0, close=118.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))
    clusters = _find_levels(result, "equal_low_cluster")

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["member_count"] == 3
    assert cluster["cluster_low"] == 100.0
    assert cluster["cluster_high"] == 100.4
    member_keys = [(ts, price) for ts, price in zip(cluster["member_timestamps"], cluster["member_prices"])]
    assert len(member_keys) == len(set(member_keys))


def test_trading_vertical_slice_v6_cluster_zone_uses_low_high_not_median_and_member_candles_not_interactions():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.4, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
        _candle("2026-08-16T05:00:00Z", open_price=100.0, high=110.2, low=94.0, close=108.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=103.0, low=93.0, close=99.0),
        _candle("2026-08-16T07:00:00Z", open_price=99.0, high=110.3, low=98.0, close=108.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))
    cluster = _find_levels(result, "equal_high_cluster")[0]

    assert cluster["representative_price"] == 110.2
    assert cluster["cluster_low"] == 110.0
    assert cluster["cluster_high"] == 110.4
    assert cluster["interaction_count"] == 1
    assert cluster["interactions"][0]["event_type"] == "touched"


def test_trading_vertical_slice_v6_single_level_interaction_precedence_and_wick_metadata_high():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=98.0, close=102.0),
        _candle("2026-08-16T01:00:00Z", open_price=102.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=109.0, low=100.0, close=104.0),
        _candle("2026-08-16T03:00:00Z", open_price=104.0, high=110.0, low=101.0, close=105.0),
        _candle("2026-08-16T04:00:00Z", open_price=105.0, high=111.0, low=102.0, close=109.0),
        _candle("2026-08-16T05:00:00Z", open_price=109.0, high=112.0, low=104.0, close=111.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(
        _payload(candles, config={"minimum_cluster_members": 3, "include_single_swing_levels": True})
    )
    level = [
        item for item in _find_levels(result, "confirmed_swing_high_level")
        if item["representative_price"] == 110.0
    ][0]

    assert [event["event_type"] for event in level["interactions"]] == ["touched", "breached", "closed_beyond"]
    assert level["interactions"][1]["wick_breach_without_close"] is True
    assert level["interactions"][2]["wick_breach_without_close"] is False
    assert level["interaction_count"] == 3
    assert level["current_status"] == "closed_beyond"


def test_trading_vertical_slice_v6_status_non_downgrade_and_single_primary_event_per_candle():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=98.0, close=102.0),
        _candle("2026-08-16T01:00:00Z", open_price=102.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=109.0, low=100.0, close=104.0),
        _candle("2026-08-16T03:00:00Z", open_price=104.0, high=112.0, low=101.0, close=111.0),
        _candle("2026-08-16T04:00:00Z", open_price=105.0, high=110.0, low=102.0, close=105.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(
        _payload(candles, config={"minimum_cluster_members": 3, "include_single_swing_levels": True})
    )
    level = [
        item for item in _find_levels(result, "confirmed_swing_high_level")
        if item["representative_price"] == 110.0
    ][0]

    assert len(level["interactions"]) == 2
    assert [event["event_type"] for event in level["interactions"]] == ["closed_beyond", "touched"]
    assert level["interactions"][0]["candle_timestamp"] == "2026-08-16T03:00:00Z"
    assert level["interactions"][1]["candle_timestamp"] == "2026-08-16T04:00:00Z"
    assert level["interactions"][1]["resulting_status"] == "closed_beyond"
    assert level["current_status"] == "closed_beyond"


def test_trading_vertical_slice_v6_single_level_interactions_low_side_and_tolerance_boundary():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=110.0, high=113.0, low=104.0, close=111.0),
        _candle("2026-08-16T01:00:00Z", open_price=111.0, high=112.0, low=100.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=110.0, high=114.0, low=101.0, close=110.0),
        _candle("2026-08-16T03:00:00Z", open_price=110.0, high=112.0, low=99.9, close=108.0),
        _candle("2026-08-16T04:00:00Z", open_price=108.0, high=111.0, low=99.7, close=100.1),
        _candle("2026-08-16T05:00:00Z", open_price=100.1, high=106.0, low=99.7, close=99.7),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={
        "minimum_cluster_members": 3,
        "interaction_tolerance": 0.2,
    }))
    level = [
        item for item in _find_levels(result, "confirmed_swing_low_level")
        if item["representative_price"] == 100.0
    ][0]

    assert [event["event_type"] for event in level["interactions"]] == ["touched", "breached", "closed_beyond"]
    assert level["interactions"][1]["wick_breach_without_close"] is True
    assert level["current_status"] == "closed_beyond"


def test_trading_vertical_slice_v6_cluster_interaction_zone_and_wick_metadata():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.4, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
        _candle("2026-08-16T05:00:00Z", open_price=100.0, high=110.2, low=94.0, close=108.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=103.0, low=93.0, close=99.0),
        _candle("2026-08-16T07:00:00Z", open_price=99.0, high=110.5, low=98.0, close=109.0),
        _candle("2026-08-16T08:00:00Z", open_price=109.0, high=111.0, low=108.0, close=110.3),
        _candle("2026-08-16T09:00:00Z", open_price=110.3, high=111.5, low=109.0, close=111.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={"interaction_tolerance": 0.1}))
    cluster = _find_levels(result, "equal_high_cluster")[0]

    assert [event["event_type"] for event in cluster["interactions"]] == ["touched", "breached", "closed_beyond"]
    assert cluster["interactions"][1]["wick_breach_without_close"] is True
    assert cluster["interactions"][2]["wick_breach_without_close"] is False


def test_trading_vertical_slice_v6_bars_since_and_last_interaction_semantics():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=98.0, close=102.0),
        _candle("2026-08-16T01:00:00Z", open_price=102.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=109.0, low=100.0, close=104.0),
        _candle("2026-08-16T03:00:00Z", open_price=104.0, high=110.0, low=101.0, close=105.0),
        _candle("2026-08-16T04:00:00Z", open_price=105.0, high=108.0, low=103.0, close=106.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={"minimum_cluster_members": 3}))
    level = [
        item for item in _find_levels(result, "confirmed_swing_high_level")
        if item["representative_price"] == 110.0
    ][0]

    assert level["created_at"] == "2026-08-16T02:00:00Z"
    assert level["last_interaction_at"] == "2026-08-16T03:00:00Z"
    assert level["bars_since_creation"] == 2
    assert level["bars_since_last_interaction"] == 1


def test_trading_vertical_slice_v6_no_interaction_yields_none_last_interaction_and_active():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=98.0, close=102.0),
        _candle("2026-08-16T01:00:00Z", open_price=102.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=108.0, high=109.0, low=100.0, close=104.0),
        _candle("2026-08-16T03:00:00Z", open_price=104.0, high=107.0, low=101.0, close=105.0),
        _candle("2026-08-16T04:00:00Z", open_price=105.0, high=108.0, low=102.0, close=106.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={"minimum_cluster_members": 3}))
    level = [
        item for item in _find_levels(result, "confirmed_swing_high_level")
        if item["representative_price"] == 110.0
    ][0]

    assert level["current_status"] == "active"
    assert level["interaction_count"] == 0
    assert level["last_interaction_at"] is None
    assert level["bars_since_last_interaction"] is None


def test_trading_vertical_slice_v6_lookback_filters_candidates_without_manufacturing_boundary_pivots():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=106.0, low=97.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=109.0, low=98.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=105.0, high=106.0, low=97.0, close=101.0),
        _candle("2026-08-16T03:00:00Z", open_price=101.0, high=120.0, low=96.0, close=118.0),
        _candle("2026-08-16T04:00:00Z", open_price=109.0, high=110.0, low=97.0, close=108.0),
        _candle("2026-08-16T05:00:00Z", open_price=108.0, high=108.0, low=95.0, close=100.0),
        _candle("2026-08-16T06:00:00Z", open_price=100.0, high=111.0, low=96.0, close=109.0),
        _candle("2026-08-16T07:00:00Z", open_price=106.0, high=107.0, low=94.0, close=100.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 4, "minimum_cluster_members": 3}))

    prices = [item["representative_price"] for item in result.liquidity_levels]
    assert 120.0 not in prices
    assert 110.0 not in prices
    assert 111.0 in prices


def test_trading_vertical_slice_v6_lookback_allows_outside_context_for_inside_pivot_confirmation():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=104.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=106.0, low=100.0, close=105.0),
        _candle("2026-08-16T02:00:00Z", open_price=104.0, high=104.5, low=101.0, close=103.0),
        _candle("2026-08-16T03:00:00Z", open_price=103.0, high=109.0, low=102.0, close=108.0),
        _candle("2026-08-16T04:00:00Z", open_price=108.0, high=111.0, low=101.0, close=110.0),
        _candle("2026-08-16T05:00:00Z", open_price=107.0, high=108.0, low=100.0, close=102.0),
        _candle("2026-08-16T06:00:00Z", open_price=102.0, high=107.0, low=99.0, close=101.0),
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 3, "minimum_cluster_members": 3}))

    highs = _find_levels(result, "confirmed_swing_high_level")
    assert any(item["representative_price"] == 111.0 for item in highs)


def test_trading_vertical_slice_v6_valid_empty_result_on_insufficient_confirmed_pivots():
    candles = [
        _candle(f"2026-08-16T{hour:02d}:00:00Z", open_price=100.0 + hour, high=101.0 + hour, low=99.5 + hour, close=100.5 + hour)
        for hour in range(6)
    ]
    result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))

    assert result.liquidity_levels == []
    assert result.summary == {
        "active_high_levels": 0,
        "active_low_levels": 0,
        "equal_high_clusters": 0,
        "equal_low_clusters": 0,
        "touched_levels": 0,
        "breached_levels": 0,
        "closed_beyond_levels": 0,
        "wick_breach_without_close_levels": 0,
    }
    assert result.evidence["reason"] == "insufficient_confirmed_pivots"


def test_trading_vertical_slice_v6_config_validation_and_unknown_fields_fail_closed():
    analyzer = LiquidityIntelligenceAnalyzer()
    invalid_payloads = [
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"equal_level_tolerance": 0.0}),
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"lookback_candles": 2}),
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"minimum_cluster_members": 1}),
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"interaction_tolerance": -0.1}),
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"include_single_swing_levels": "yes"}),
        _payload([
            _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
            _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        ], config={"unknown": 1}),
    ]

    for payload in invalid_payloads:
        try:
            analyzer.analyze(payload)
            raise AssertionError("Expected invalid config to fail closed.")
        except ValueError:
            pass


def test_trading_vertical_slice_v6_deterministic_and_safety_boundary():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=105.0, low=99.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=98.0, close=106.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=104.0, low=97.0, close=102.0),
        _candle("2026-08-16T03:00:00Z", open_price=102.0, high=110.4, low=96.0, close=109.0),
        _candle("2026-08-16T04:00:00Z", open_price=103.0, high=104.0, low=95.0, close=100.0),
        _candle("2026-08-16T05:00:00Z", open_price=100.0, high=110.2, low=94.0, close=108.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=103.0, low=93.0, close=99.0),
        _candle("2026-08-16T07:00:00Z", open_price=99.0, high=111.0, low=98.0, close=110.0),
    ]

    first = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))
    second = LiquidityIntelligenceAnalyzer().analyze(_payload(candles))
    assert first.to_dict() == second.to_dict()

    specialist = LiquidityIntelligenceSpecialist()
    result = specialist.analyze_liquidity(_payload(candles))
    text = str(result.to_dict()).lower()
    for forbidden in [
        "buy",
        "sell",
        "long",
        "short",
        "entry",
        "exit",
        "stop_loss",
        "take_profit",
        "risk_reward",
        "setup",
        "setup_quality",
        "trade_target",
        "profit_target",
        "stop_hunt",
        "manipulation",
        "smart_money_intent",
        "expected_direction",
        "probability",
        "trading_confidence",
        "trade_recommendation",
        "position_size",
        "broker_instruction",
        "execution_command",
    ]:
        assert re.search(rf"\\b{re.escape(forbidden)}\\b", text) is None

    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="liquidity_analyst",
        capability_name="liquidity_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False


def test_trading_vertical_slice_v6_seven_timeframes_supported():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=106.0, low=98.0, close=103.0),
        _candle("2026-08-16T01:00:00Z", open_price=103.0, high=110.0, low=99.0, close=108.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=107.0, low=96.0, close=100.0),
    ]
    for timeframe in ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]:
        result = LiquidityIntelligenceAnalyzer().analyze(_payload(candles, timeframe=timeframe))
        assert result.timeframe == timeframe


def test_trading_vertical_slice_v6_config_object_is_immutable():
    config = LiquidityIntelligenceConfig()
    try:
        config.lookback_candles = 50
        raise AssertionError("Expected frozen config to reject mutation.")
    except Exception:
        pass
