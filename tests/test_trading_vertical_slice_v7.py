from __future__ import annotations

import re

from ced_one.business_divisions.trading.fvg_imbalance_intelligence import (
    FVGImbalanceIntelligenceAnalyzer,
    FVGImbalanceIntelligenceSpecialist,
    FVGIntelligenceConfig,
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


def _fvgs_by_side(result, side: str):
    return [item for item in result.fair_value_gaps if item["side"] == side]


def test_trading_vertical_slice_v7_bullish_and_bearish_detection_strict_valid_rules():
    bullish_candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
    ]
    bearish_candles = [
        _candle("2026-08-16T00:00:00Z", open_price=112.0, high=115.0, low=110.0, close=114.0),
        _candle("2026-08-16T01:00:00Z", open_price=114.0, high=116.0, low=111.0, close=112.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=105.0, low=100.0, close=101.0),
    ]

    bullish = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(bullish_candles))
    bearish = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(bearish_candles))

    assert len(_fvgs_by_side(bullish, "bullish")) == 1
    assert len(_fvgs_by_side(bearish, "bearish")) == 1


def test_trading_vertical_slice_v7_equality_and_zero_width_not_emitted():
    bullish_equal = [
        _candle("2026-08-16T00:00:00Z", open_price=95.0, high=100.0, low=94.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=102.0, low=97.0, close=101.0),
        _candle("2026-08-16T02:00:00Z", open_price=101.0, high=103.0, low=100.0, close=102.0),
    ]
    bearish_equal = [
        _candle("2026-08-16T00:00:00Z", open_price=110.0, high=113.0, low=105.0, close=112.0),
        _candle("2026-08-16T01:00:00Z", open_price=112.0, high=114.0, low=108.0, close=109.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=105.0, low=101.0, close=102.0),
    ]

    result_bull = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(bullish_equal))
    result_bear = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(bearish_equal))

    assert result_bull.fair_value_gaps == []
    assert result_bear.fair_value_gaps == []


def test_trading_vertical_slice_v7_minimum_gap_size_equality_qualifies_and_below_excludes():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=102.0, high=104.0, low=101.0, close=103.0),
    ]

    equal_result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"minimum_gap_size": 1.0}))
    below_result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"minimum_gap_size": 1.01}))

    assert len(equal_result.fair_value_gaps) == 1
    assert below_result.fair_value_gaps == []


def test_trading_vertical_slice_v7_anti_lookahead_created_at_and_confirming_candle_not_interaction():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.0, close=108.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert fvg["source_timestamp"] == "2026-08-16T01:00:00Z"
    assert fvg["confirmed_at"] == "2026-08-16T02:00:00Z"
    assert fvg["created_at"] == "2026-08-16T02:00:00Z"
    assert fvg["first_interaction_at"] == "2026-08-16T03:00:00Z"
    assert all(event["candle_timestamp"] != "2026-08-16T02:00:00Z" for event in fvg["interactions"])


def test_trading_vertical_slice_v7_lookback_exact_index_contract_and_scanned_count():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=101.0, low=96.0, close=100.0),
        _candle("2026-08-16T02:00:00Z", open_price=100.0, high=102.0, low=97.0, close=101.0),
        _candle("2026-08-16T03:00:00Z", open_price=101.0, high=103.0, low=98.0, close=102.0),
        _candle("2026-08-16T04:00:00Z", open_price=105.0, high=106.0, low=104.0, close=105.5),
        _candle("2026-08-16T05:00:00Z", open_price=106.0, high=107.0, low=105.0, close=106.0),
        _candle("2026-08-16T06:00:00Z", open_price=107.0, high=108.0, low=106.0, close=107.0),
        _candle("2026-08-16T07:00:00Z", open_price=108.0, high=109.0, low=107.0, close=108.0),
    ]

    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 4}))

    assert result.scanned_candle_count == 3
    assert result.evidence["candidate_source_index_range"] == {"b_min": 4, "b_max": 6}
    assert result.evidence["scanned_candle_count_basis"] == "middle_candle_candidates"
    assert all(item["source_timestamp"] != "2026-08-16T03:00:00Z" for item in result.fair_value_gaps)
    assert any(item["source_timestamp"] == "2026-08-16T04:00:00Z" for item in result.fair_value_gaps)


def test_trading_vertical_slice_v7_tolerance_only_touch_cannot_create_artificial_fill_bullish():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.5, close=109.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"interaction_tolerance": 1.0}))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert fvg["interactions"][0]["event_type"] == "touched_event"
    assert fvg["interactions"][0]["fill_depth"] == 0.0
    assert fvg["interactions"][0]["fill_percentage"] == 0.0
    assert fvg["current_status"] == "open"
    assert fvg["current_fill_depth"] == 0.0
    assert fvg["current_fill_percentage"] == 0.0


def test_trading_vertical_slice_v7_tolerance_only_touch_cannot_create_artificial_fill_bearish():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=112.0, high=115.0, low=110.0, close=114.0),
        _candle("2026-08-16T01:00:00Z", open_price=114.0, high=116.0, low=111.0, close=112.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=105.0, low=100.0, close=101.0),
        _candle("2026-08-16T03:00:00Z", open_price=101.0, high=104.5, low=100.0, close=101.5),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"interaction_tolerance": 1.0}))
    fvg = _fvgs_by_side(result, "bearish")[0]

    assert fvg["interactions"][0]["event_type"] == "touched_event"
    assert fvg["interactions"][0]["fill_depth"] == 0.0
    assert fvg["interactions"][0]["fill_percentage"] == 0.0
    assert fvg["current_status"] == "open"


def test_trading_vertical_slice_v7_bullish_fill_progression_precedence_and_clamp():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.0, close=108.0),
        _candle("2026-08-16T04:00:00Z", open_price=108.0, high=109.0, low=103.0, close=104.0),
        _candle("2026-08-16T05:00:00Z", open_price=104.0, high=108.0, low=100.0, close=101.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=107.0, low=95.0, close=96.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert [event["event_type"] for event in fvg["interactions"]] == [
        "touched_event",
        "partial_fill_event",
        "fully_filled_event",
        "fully_filled_event",
    ]
    assert fvg["current_status"] == "fully_filled"
    assert fvg["current_fill_depth"] == fvg["gap_width"]
    assert fvg["current_fill_percentage"] == 100.0
    assert fvg["full_fill_at"] == "2026-08-16T05:00:00Z"


def test_trading_vertical_slice_v7_one_primary_event_per_candle_and_precedence():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=111.0, low=99.0, close=100.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert fvg["interaction_count"] == 1
    assert fvg["interactions"][0]["event_type"] == "fully_filled_event"
    timestamps = [event["candle_timestamp"] for event in fvg["interactions"]]
    assert len(timestamps) == len(set(timestamps))


def test_trading_vertical_slice_v7_status_and_fill_metrics_are_monotonic():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.0, close=108.0),
        _candle("2026-08-16T04:00:00Z", open_price=108.0, high=109.0, low=103.0, close=104.0),
        _candle("2026-08-16T05:00:00Z", open_price=104.0, high=108.0, low=100.0, close=101.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=107.0, low=95.0, close=96.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    status_rank = {"open": 0, "partially_filled": 1, "fully_filled": 2}
    statuses = [event["resulting_status"] for event in fvg["interactions"]]
    depths = [event["fill_depth"] for event in fvg["interactions"]]
    percentages = [event["fill_percentage"] for event in fvg["interactions"]]

    assert all(status_rank[statuses[i]] <= status_rank[statuses[i + 1]] for i in range(len(statuses) - 1))
    assert all(depths[i] <= depths[i + 1] for i in range(len(depths) - 1))
    assert all(percentages[i] <= percentages[i + 1] for i in range(len(percentages) - 1))
    assert fvg["full_fill_at"] == "2026-08-16T05:00:00Z"


def test_trading_vertical_slice_v7_bearish_fill_progression_and_status_monotonicity():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=112.0, high=115.0, low=110.0, close=114.0),
        _candle("2026-08-16T01:00:00Z", open_price=114.0, high=116.0, low=111.0, close=112.0),
        _candle("2026-08-16T02:00:00Z", open_price=103.0, high=105.0, low=100.0, close=101.0),
        _candle("2026-08-16T03:00:00Z", open_price=101.0, high=105.0, low=100.0, close=102.0),
        _candle("2026-08-16T04:00:00Z", open_price=102.0, high=107.0, low=101.0, close=103.0),
        _candle("2026-08-16T05:00:00Z", open_price=103.0, high=110.0, low=102.0, close=109.0),
        _candle("2026-08-16T06:00:00Z", open_price=109.0, high=111.0, low=105.0, close=106.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bearish")[0]

    assert fvg["current_status"] == "fully_filled"
    assert fvg["current_fill_percentage"] == 100.0
    assert fvg["full_fill_at"] == "2026-08-16T05:00:00Z"
    assert fvg["interactions"][-1]["resulting_status"] == "fully_filled"


def test_trading_vertical_slice_v7_first_last_full_fill_timestamps_and_recency():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.0, close=108.0),
        _candle("2026-08-16T04:00:00Z", open_price=108.0, high=109.0, low=103.0, close=104.0),
        _candle("2026-08-16T05:00:00Z", open_price=104.0, high=108.0, low=100.0, close=101.0),
        _candle("2026-08-16T06:00:00Z", open_price=101.0, high=107.0, low=101.0, close=104.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert fvg["first_interaction_at"] == "2026-08-16T03:00:00Z"
    assert fvg["last_interaction_at"] == "2026-08-16T06:00:00Z"
    assert fvg["full_fill_at"] == "2026-08-16T05:00:00Z"
    assert fvg["bars_since_creation"] == 4
    assert fvg["bars_since_last_interaction"] == 0


def test_trading_vertical_slice_v7_no_interaction_recency_none():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=112.0, low=106.0, close=111.0),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    fvg = _fvgs_by_side(result, "bullish")[0]

    assert fvg["interaction_count"] == 0
    assert fvg["first_interaction_at"] is None
    assert fvg["last_interaction_at"] is None
    assert fvg["bars_since_last_interaction"] is None


def test_trading_vertical_slice_v7_include_fully_filled_is_final_output_filter_only():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=109.0, low=100.0, close=101.0),
    ]

    include_true = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"include_fully_filled": True}))
    include_false = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, config={"include_fully_filled": False}))

    assert include_true.evidence["totals_pre_filter"] == include_false.evidence["totals_pre_filter"]
    assert include_true.evidence["totals_pre_filter"]["fully_filled_count"] == 1
    assert include_true.summary["fully_filled_count"] == 1
    assert include_false.summary["fully_filled_count"] == 0
    assert include_false.fair_value_gaps == []
    assert include_false.evidence["filtered_out_fully_filled_count"] == 1


def test_trading_vertical_slice_v7_empty_result_contract():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.5, low=99.2, close=100.8),
        _candle("2026-08-16T02:00:00Z", open_price=100.8, high=101.6, low=99.4, close=100.2),
        _candle("2026-08-16T03:00:00Z", open_price=100.2, high=101.7, low=99.5, close=100.6),
        _candle("2026-08-16T04:00:00Z", open_price=100.6, high=101.8, low=99.6, close=100.3),
        _candle("2026-08-16T05:00:00Z", open_price=100.3, high=101.6, low=99.4, close=100.7),
        _candle("2026-08-16T06:00:00Z", open_price=100.7, high=101.7, low=99.5, close=100.4),
        _candle("2026-08-16T07:00:00Z", open_price=100.4, high=101.5, low=99.3, close=100.6),
    ]
    result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))

    assert result.fair_value_gaps == []
    assert result.summary == {
        "bullish_fvg_count": 0,
        "bearish_fvg_count": 0,
        "open_count": 0,
        "partially_filled_count": 0,
        "fully_filled_count": 0,
    }


def test_trading_vertical_slice_v7_config_validation_and_unknown_fields_fail_closed():
    analyzer = FVGImbalanceIntelligenceAnalyzer()
    base = [
        _candle("2026-08-16T00:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        _candle("2026-08-16T01:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        _candle("2026-08-16T02:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
    ]
    invalid_payloads = [
        _payload(base, config={"lookback_candles": 2}),
        _payload(base, config={"interaction_tolerance": -0.1}),
        _payload(base, config={"include_fully_filled": "false"}),
        _payload(base, config={"minimum_gap_size": -0.1}),
        _payload(base, config={"unknown": 1}),
    ]

    for payload in invalid_payloads:
        try:
            analyzer.analyze(payload)
            raise AssertionError("Expected invalid config to fail closed.")
        except ValueError:
            pass


def test_trading_vertical_slice_v7_determinism_and_safety_boundary():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
        _candle("2026-08-16T03:00:00Z", open_price=107.0, high=110.0, low=105.0, close=108.0),
    ]

    first = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    second = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles))
    assert first.to_dict() == second.to_dict()

    specialist = FVGImbalanceIntelligenceSpecialist()
    result = specialist.analyze_imbalance(_payload(candles))
    text = str(result.to_dict()).lower()
    for forbidden in [
        "buy",
        "sell",
        "entry",
        "exit",
        "stop_loss",
        "take_profit",
        "risk_reward",
        "setup",
        "setup_quality",
        "probability",
        "forecast",
        "prediction",
        "expected_direction",
        "trade_recommendation",
        "position_size",
        "broker_instruction",
        "execution_command",
        "stop_hunt",
        "manipulation",
        "smart_money_intent",
    ]:
        assert re.search(rf"\\b{re.escape(forbidden)}\\b", text) is None

    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="fvg_imbalance_analyst",
        capability_name="fvg_imbalance_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False


def test_trading_vertical_slice_v7_seven_timeframes_supported():
    candles = [
        _candle("2026-08-16T00:00:00Z", open_price=96.0, high=100.0, low=95.0, close=99.0),
        _candle("2026-08-16T01:00:00Z", open_price=99.0, high=103.0, low=96.0, close=102.0),
        _candle("2026-08-16T02:00:00Z", open_price=106.0, high=108.0, low=105.0, close=107.0),
    ]
    for timeframe in ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]:
        result = FVGImbalanceIntelligenceAnalyzer().analyze(_payload(candles, timeframe=timeframe))
        assert result.timeframe == timeframe


def test_trading_vertical_slice_v7_config_is_immutable():
    config = FVGIntelligenceConfig()
    try:
        config.lookback_candles = 10
        raise AssertionError("Expected frozen config to reject mutation.")
    except Exception:
        pass
