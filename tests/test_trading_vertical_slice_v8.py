from __future__ import annotations

import re
from datetime import datetime, timedelta

from ced_one.business_divisions.trading.displacement_intelligence import (
    DisplacementIntelligenceAnalyzer,
    DisplacementIntelligenceConfig,
    DisplacementIntelligenceSpecialist,
)


def _ts(index: int) -> str:
    return (datetime(2026, 8, 16, 0, 0, 0) + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _candle(timestamp: str, *, open_price: float, high: float, low: float, close: float):
    return {"timestamp": timestamp, "open": open_price, "high": high, "low": low, "close": close}


def _quiet_candles(count: int, *, start_index: int = 0):
    return [_candle(_ts(start_index + i), open_price=100.0, high=101.0, low=99.0, close=100.0) for i in range(count)]


def _flat_candles(count: int, *, start_index: int = 0):
    return [_candle(_ts(start_index + i), open_price=100.0, high=100.0, low=100.0, close=100.0) for i in range(count)]


def _bullish_strong(index: int):
    return _candle(_ts(index), open_price=100.0, high=105.0, low=100.0, close=104.0)


def _bearish_strong(index: int):
    return _candle(_ts(index), open_price=104.0, high=104.0, low=99.0, close=99.5)


def _payload(candles, *, config=None, timeframe="H1"):
    payload = {
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "evaluation_time": "2026-08-17T10:00:00Z",
        "candle_history": candles,
    }
    if config is not None:
        payload["config"] = config
    return payload


def _events_by_direction(result, direction: str):
    return [item for item in result.displacement_events if item["direction"] == direction]


# ---------------------------------------------------------------------------
# SINGLE EVENT
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_bullish_qualifying_event():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bullish")
    assert len(events) == 1
    assert events[0]["source_timestamp"] == _ts(20)


def test_trading_vertical_slice_v8_bearish_qualifying_event():
    candles = _quiet_candles(20) + [_bearish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bearish")
    assert len(events) == 1
    assert events[0]["source_timestamp"] == _ts(20)


def test_trading_vertical_slice_v8_neutral_candle_excluded():
    neutral = _candle(_ts(20), open_price=100.0, high=105.0, low=100.0, close=100.0)
    candles = _quiet_candles(20) + [neutral]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []


def test_trading_vertical_slice_v8_body_ratio_below_threshold_excluded():
    candle = _candle(_ts(20), open_price=101.0, high=103.0, low=100.0, close=102.4)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []


def test_trading_vertical_slice_v8_exact_body_threshold_qualifies():
    candle = _candle(_ts(20), open_price=102.0, high=110.0, low=100.0, close=109.0)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bullish")
    assert len(events) == 1
    assert events[0]["body_to_range_ratio"] == 0.70


def test_trading_vertical_slice_v8_bullish_close_location_exact_threshold_qualifies():
    candle = _candle(_ts(20), open_price=100.25, high=105.0, low=100.0, close=104.0)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bullish")
    assert len(events) == 1
    assert events[0]["close_location_ratio"] == 0.80


def test_trading_vertical_slice_v8_bearish_close_location_exact_threshold_qualifies():
    candle = _candle(_ts(20), open_price=104.75, high=105.0, low=100.0, close=101.0)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bearish")
    assert len(events) == 1
    assert events[0]["close_location_ratio"] == 0.20


def test_trading_vertical_slice_v8_close_location_outside_boundary_excluded():
    candle = _candle(_ts(20), open_price=100.2, high=105.0, low=100.0, close=103.95)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []


def test_trading_vertical_slice_v8_range_expansion_below_threshold_excluded():
    candle = _candle(_ts(20), open_price=100.145, high=102.9, low=100.0, close=102.465)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []


def test_trading_vertical_slice_v8_exact_range_expansion_threshold_qualifies():
    candle = _candle(_ts(20), open_price=100.3, high=103.0, low=100.0, close=102.55)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bullish")
    assert len(events) == 1
    assert events[0]["range_expansion_ratio"] == 1.50


def test_trading_vertical_slice_v8_all_gates_exact_boundary_qualifies():
    wide_quiet = [
        _candle(_ts(i), open_price=100.0, high=110.0, low=90.0, close=100.0) for i in range(20)
    ]
    candle = _candle(_ts(20), open_price=103.0, high=130.0, low=100.0, close=124.0)
    candles = wide_quiet + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    events = _events_by_direction(result, "bullish")
    assert len(events) == 1
    assert events[0]["body_to_range_ratio"] == 0.70
    assert events[0]["close_location_ratio"] == 0.80
    assert events[0]["range_expansion_ratio"] == 1.50


# ---------------------------------------------------------------------------
# BASELINE
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_current_candle_excluded_from_own_baseline():
    candle = _bullish_strong(20)
    candles = _quiet_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    event = _events_by_direction(result, "bullish")[0]
    assert event["evidence"]["median_true_range"] == 2.0
    assert len(event["evidence"]["baseline_values"]) == 20
    assert candle["high"] - candle["low"] not in event["evidence"]["baseline_values"]


def test_trading_vertical_slice_v8_insufficient_history_explicit():
    shaped = [
        _candle(_ts(5 + i), open_price=100.0, high=105.0, low=100.0, close=104.0) for i in range(4)
    ]
    candles = _quiet_candles(5) + shaped + _quiet_candles(11, start_index=9) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.evidence["insufficient_history_count"] == 20
    assert len(result.displacement_events) == 1
    assert result.displacement_events[0]["source_timestamp"] == _ts(20)


def test_trading_vertical_slice_v8_zero_median_baseline_is_insufficient_context():
    candle = _candle(_ts(20), open_price=100.0, high=105.0, low=100.0, close=104.0)
    candles = _flat_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []
    assert result.evidence["insufficient_context_count"] == 1
    assert result.evidence["insufficient_history_count"] == 20


def test_trading_vertical_slice_v8_baseline_beginning_at_index_zero_uses_candle_range():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.evidence["evaluable_candidate_count"] == 1
    event = result.displacement_events[0]
    assert event["evidence"]["baseline_values"] == [2.0] * 20


# ---------------------------------------------------------------------------
# CAUSALITY
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_source_confirmed_created_timestamps_equal():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    event = result.displacement_events[0]
    assert event["source_timestamp"] == event["confirmed_at"] == event["created_at"] == _ts(20)


def test_trading_vertical_slice_v8_event_requires_no_future_candle():
    base_candles = _quiet_candles(20) + [_bullish_strong(20)]
    extended_candles = base_candles + [
        _candle(_ts(21), open_price=100.0, high=101.0, low=99.0, close=100.0),
        _bearish_strong(22),
    ]
    base_result = DisplacementIntelligenceAnalyzer().analyze(_payload(base_candles))
    extended_result = DisplacementIntelligenceAnalyzer().analyze(_payload(extended_candles))

    base_event = base_result.displacement_events[0]
    extended_event = [item for item in extended_result.displacement_events if item["source_timestamp"] == _ts(20)][0]

    for key in ["source_timestamp", "confirmed_at", "created_at", "body_size", "candle_range", "true_range", "range_expansion_ratio"]:
        assert base_event[key] == extended_event[key]


# ---------------------------------------------------------------------------
# LOOKBACK
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_candidate_boundary_inclusion_and_exclusion():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 2}))
    timestamps = [item["source_timestamp"] for item in result.displacement_events]
    assert _ts(20) not in timestamps
    assert _ts(21) in timestamps
    assert _ts(22) in timestamps
    assert result.scanned_candle_count == 2


def test_trading_vertical_slice_v8_baseline_may_reach_outside_candidate_window():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 1}))
    assert result.scanned_candle_count == 1
    assert len(result.displacement_events) == 1
    assert result.displacement_events[0]["evidence"]["median_true_range"] == 2.0


def test_trading_vertical_slice_v8_scanned_candle_count_l_less_than_n():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 100}))
    assert len(candles) == 21
    assert result.scanned_candle_count == 21
    assert result.evidence["candidate_index_range"] == {"candidate_index_min": 0, "candidate_index_max": 20}


def test_trading_vertical_slice_v8_scanned_candle_count_l_equals_n():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 21}))
    assert result.scanned_candle_count == 21
    assert result.evidence["candidate_index_range"]["candidate_index_min"] == 0


def test_trading_vertical_slice_v8_scanned_candle_count_l_greater_than_n():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 3}))
    assert result.scanned_candle_count == 3
    assert result.evidence["candidate_index_range"] == {"candidate_index_min": 19, "candidate_index_max": 21}


def test_trading_vertical_slice_v8_empty_candle_history_rejected():
    analyzer = DisplacementIntelligenceAnalyzer()
    try:
        analyzer.analyze(_payload([]))
        raise AssertionError("Expected empty candle_history to fail closed.")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# DIAGNOSTICS
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_diagnostic_accounting_identities():
    candles = _quiet_candles(20) + [_bullish_strong(20)] + _quiet_candles(4, start_index=21)
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))

    assert result.evidence["evaluated_candidate_count"] == result.scanned_candle_count == 25
    assert result.evidence["insufficient_history_count"] == 20
    assert result.evidence["insufficient_context_count"] == 0
    assert result.evidence["evaluable_candidate_count"] == 5
    assert result.evidence["qualifying_event_count"] == 1
    assert (
        result.evidence["insufficient_history_count"]
        + result.evidence["insufficient_context_count"]
        + result.evidence["evaluable_candidate_count"]
        == result.scanned_candle_count
    )
    assert result.evidence["qualifying_event_count"] <= result.evidence["evaluable_candidate_count"]


def test_trading_vertical_slice_v8_insufficient_context_diagnostic_count():
    candle = _candle(_ts(20), open_price=100.0, high=105.0, low=100.0, close=104.0)
    candles = _flat_candles(20) + [candle]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.evidence["insufficient_history_count"] == 20
    assert result.evidence["insufficient_context_count"] == 1
    assert result.evidence["evaluable_candidate_count"] == 0
    assert result.evidence["qualifying_event_count"] == 0


# ---------------------------------------------------------------------------
# SEQUENCE
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_single_event_alone_no_sequence():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_sequences == []


def test_trading_vertical_slice_v8_second_same_direction_creates_sequence():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert len(result.displacement_sequences) == 1
    sequence = result.displacement_sequences[0]
    assert sequence["member_count"] == 2
    assert sequence["created_at"] == _ts(21)
    assert sequence["source_timestamp"] == _ts(20)


def test_trading_vertical_slice_v8_third_extends_without_moving_created_at():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    sequence = result.displacement_sequences[0]
    assert sequence["created_at"] == _ts(21)
    assert sequence["member_count"] == 3
    assert sequence["end_timestamp"] == _ts(22)


def test_trading_vertical_slice_v8_opposite_direction_breaks_sequence():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bearish_strong(21), _bullish_strong(22)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_sequences == []
    assert len(result.displacement_events) == 3


def test_trading_vertical_slice_v8_non_qualifying_candle_breaks_sequence():
    quiet_break = _candle(_ts(21), open_price=100.0, high=101.0, low=99.0, close=100.0)
    candles = _quiet_candles(20) + [_bullish_strong(20), quiet_break, _bullish_strong(22)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_sequences == []


def test_trading_vertical_slice_v8_neutral_candle_breaks_sequence():
    neutral_break = _candle(_ts(21), open_price=100.0, high=105.0, low=100.0, close=100.0)
    candles = _quiet_candles(20) + [_bullish_strong(20), neutral_break, _bullish_strong(22)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_sequences == []


def test_trading_vertical_slice_v8_no_gap_bridging():
    candles = _quiet_candles(20) + [
        _bullish_strong(20),
        _candle(_ts(21), open_price=100.0, high=101.0, low=99.0, close=100.0),
        _bullish_strong(22),
        _bullish_strong(23),
    ]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert len(result.displacement_sequences) == 1
    sequence = result.displacement_sequences[0]
    assert sequence["member_timestamps"] == [_ts(22), _ts(23)]


def test_trading_vertical_slice_v8_cumulative_metrics_exact():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    sequence = result.displacement_sequences[0]
    assert sequence["cumulative_body_move"] == 8.0
    assert sequence["cumulative_range"] == 10.0
    assert sequence["maximum_range_expansion_ratio"] == 2.5


# ---------------------------------------------------------------------------
# BOUNDARY SEQUENCE
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_pre_existing_run_excluded_from_sequence_emission():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22), _bullish_strong(23)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 3}))

    assert result.evidence["boundary_continuation_checked"] is True
    assert result.evidence["boundary_continuation_source_index"] == 20
    assert result.evidence["boundary_continuation_excluded"] is True
    assert result.displacement_sequences == []
    timestamps = [item["source_timestamp"] for item in result.displacement_events]
    assert timestamps == [_ts(21), _ts(22), _ts(23)]


def test_trading_vertical_slice_v8_minimum_sequence_events_three_still_excludes_boundary_continuation():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22), _bullish_strong(23)]
    result = DisplacementIntelligenceAnalyzer().analyze(
        _payload(candles, config={"lookback_candles": 3, "minimum_sequence_events": 3})
    )
    assert result.evidence["boundary_continuation_excluded"] is True
    assert result.displacement_sequences == []


def test_trading_vertical_slice_v8_break_then_fresh_run_emits_normally():
    quiet_break = _candle(_ts(24), open_price=100.0, high=101.0, low=99.0, close=100.0)
    candles = _quiet_candles(20) + [
        _bullish_strong(20),
        _bullish_strong(21),
        _bullish_strong(22),
        _bullish_strong(23),
        quiet_break,
        _bullish_strong(25),
        _bullish_strong(26),
    ]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 6}))

    assert result.evidence["boundary_continuation_excluded"] is True
    assert len(result.displacement_sequences) == 1
    sequence = result.displacement_sequences[0]
    assert sequence["member_timestamps"] == [_ts(25), _ts(26)]
    assert sequence["created_at"] == _ts(26)


def test_trading_vertical_slice_v8_candidate_index_min_zero_no_continuation_check():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22), _bullish_strong(23)]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 100}))

    assert result.evidence["boundary_continuation_checked"] is False
    assert result.evidence["boundary_continuation_source_index"] is None
    assert result.evidence["boundary_continuation_excluded"] is False
    assert len(result.displacement_sequences) == 1
    sequence = result.displacement_sequences[0]
    assert sequence["member_count"] == 4
    assert sequence["created_at"] == _ts(21)


def test_trading_vertical_slice_v8_emitted_sequences_reference_only_emitted_events():
    quiet_break = _candle(_ts(24), open_price=100.0, high=101.0, low=99.0, close=100.0)
    candles = _quiet_candles(20) + [
        _bullish_strong(20),
        _bullish_strong(21),
        _bullish_strong(22),
        _bullish_strong(23),
        quiet_break,
        _bullish_strong(25),
        _bullish_strong(26),
    ]
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, config={"lookback_candles": 6}))
    emitted_ids = {item["event_id"] for item in result.displacement_events}
    for sequence in result.displacement_sequences:
        for event_id in sequence["member_event_ids"]:
            assert event_id in emitted_ids


# ---------------------------------------------------------------------------
# RECENCY
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_bars_since_event_exact():
    candles = _quiet_candles(20) + [_bullish_strong(20)] + _quiet_candles(3, start_index=21)
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    event = result.displacement_events[0]
    assert event["bars_since_event"] == 3


def test_trading_vertical_slice_v8_bars_since_creation_and_end_exact():
    candles = (
        _quiet_candles(20)
        + [_bullish_strong(20), _bullish_strong(21), _bullish_strong(22)]
        + _quiet_candles(2, start_index=23)
    )
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    sequence = result.displacement_sequences[0]
    assert sequence["bars_since_creation"] == 3
    assert sequence["bars_since_end"] == 2


# ---------------------------------------------------------------------------
# EMPTY
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_valid_no_event_result():
    candles = _quiet_candles(25)
    result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert result.displacement_events == []
    assert result.displacement_sequences == []
    assert result.summary == {
        "bullish_event_count": 0,
        "bearish_event_count": 0,
        "bullish_sequence_count": 0,
        "bearish_sequence_count": 0,
    }


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_config_validation_and_unknown_fields_fail_closed():
    analyzer = DisplacementIntelligenceAnalyzer()
    base = _quiet_candles(20) + [_bullish_strong(20)]
    invalid_payloads = [
        _payload(base, config={"minimum_body_ratio": 1.5}),
        _payload(base, config={"minimum_body_ratio": -0.1}),
        _payload(base, config={"bullish_close_location_min": 1.5}),
        _payload(base, config={"bearish_close_location_max": 0.5, "bullish_close_location_min": 0.5}),
        _payload(base, config={"minimum_range_expansion_ratio": 0}),
        _payload(base, config={"minimum_range_expansion_ratio": -1.0}),
        _payload(base, config={"lookback_candles": 0}),
        _payload(base, config={"baseline_window": 0}),
        _payload(base, config={"minimum_sequence_events": 1}),
        _payload(base, config={"unknown": 1}),
    ]
    for payload in invalid_payloads:
        try:
            analyzer.analyze(payload)
            raise AssertionError("Expected invalid config to fail closed.")
        except ValueError:
            pass


def test_trading_vertical_slice_v8_config_is_immutable():
    config = DisplacementIntelligenceConfig()
    try:
        config.minimum_body_ratio = 0.9
        raise AssertionError("Expected frozen config to reject mutation.")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# DETERMINISM
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_repeated_output_identical():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21)]
    first = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    second = DisplacementIntelligenceAnalyzer().analyze(_payload(candles))
    assert first.to_dict() == second.to_dict()


# ---------------------------------------------------------------------------
# SAFETY
# ---------------------------------------------------------------------------


def test_trading_vertical_slice_v8_non_advisory_boundary_and_authority():
    candles = _quiet_candles(20) + [_bullish_strong(20), _bullish_strong(21)]
    specialist = DisplacementIntelligenceSpecialist()
    result = specialist.analyze_displacement(_payload(candles))
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
        "probability",
        "prediction",
        "forecast",
        "expected_direction",
        "trade_recommendation",
        "position_size",
        "broker_instruction",
        "execution_command",
        "stop_hunt",
        "manipulation",
        "smart_money_intent",
        "bos",
        "choch",
        "mss",
    ]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None

    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="displacement_analyst",
        capability_name="displacement_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False

    assert result.metadata["deterministic_displacement_intelligence"] is True
    assert result.metadata["observation_only"] is True
    assert result.metadata["advisory_output"] is False
    assert result.metadata["strategy_output"] is False
    assert result.metadata["execution_output"] is False


def test_trading_vertical_slice_v8_seven_timeframes_supported():
    candles = _quiet_candles(20) + [_bullish_strong(20)]
    for timeframe in ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]:
        result = DisplacementIntelligenceAnalyzer().analyze(_payload(candles, timeframe=timeframe))
        assert result.timeframe == timeframe
