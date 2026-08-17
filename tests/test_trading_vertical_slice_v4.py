from __future__ import annotations

from ced_one.business_divisions.trading.candle_intelligence import (
    CandleIntelligenceAnalyzer,
    CandleIntelligenceConfig,
    CandleIntelligenceSpecialist,
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


def test_trading_vertical_slice_v4_bullish_bearish_neutral_and_raw_metrics():
    bullish = CandleIntelligenceAnalyzer().analyze(
        _payload([
            _candle("2026-08-16T10:00:00Z", open_price=100.0, high=130.0, low=90.0, close=115.0),
        ])
    )
    assert bullish.candle_direction == "bullish"
    assert bullish.range == 40.0
    assert bullish.body_size == 15.0
    assert bullish.upper_wick_size == 15.0
    assert bullish.lower_wick_size == 10.0
    assert bullish.body_to_range_ratio == 15.0 / 40.0
    assert bullish.upper_wick_to_range_ratio == 15.0 / 40.0
    assert bullish.lower_wick_to_range_ratio == 10.0 / 40.0
    assert bullish.close_location_ratio == 25.0 / 40.0

    bearish = CandleIntelligenceAnalyzer().analyze(
        _payload([
            _candle("2026-08-16T10:00:00Z", open_price=115.0, high=130.0, low=90.0, close=100.0),
        ])
    )
    assert bearish.candle_direction == "bearish"

    neutral = CandleIntelligenceAnalyzer().analyze(
        _payload([
            _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=90.0, close=100.0),
        ])
    )
    assert neutral.candle_direction == "neutral"


def test_trading_vertical_slice_v4_zero_range_contract():
    result = CandleIntelligenceAnalyzer().analyze(
        _payload([
            _candle("2026-08-16T10:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        ])
    )
    assert result.range == 0.0
    assert result.body_size == 0.0
    assert result.upper_wick_size == 0.0
    assert result.lower_wick_size == 0.0
    assert result.body_to_range_ratio is None
    assert result.upper_wick_to_range_ratio is None
    assert result.lower_wick_to_range_ratio is None
    assert result.close_location_ratio is None
    assert result.candle_direction == "neutral"
    assert result.body_classification == "zero_range"
    assert result.wick_classification == "zero_range"
    assert result.close_location_classification == "zero_range"
    assert result.rejection_classification == "none"
    assert result.engulfing_classification == "none"


def test_trading_vertical_slice_v4_body_threshold_boundaries():
    small = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=150.0, low=50.0, close=125.0),
    ]))
    medium_low = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=150.0, low=50.0, close=126.0),
    ]))
    medium_high = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=200.0, low=100.0, close=159.0),
    ]))
    large = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=200.0, low=100.0, close=160.0),
    ]))

    assert small.body_to_range_ratio == 0.25
    assert small.body_classification == "small_body"
    assert medium_low.body_to_range_ratio == 0.26
    assert medium_low.body_classification == "medium_body"
    assert medium_high.body_to_range_ratio == 0.59
    assert medium_high.body_classification == "medium_body"
    assert large.body_to_range_ratio == 0.60
    assert large.body_classification == "large_body"


def test_trading_vertical_slice_v4_wick_classifications_and_precedence():
    dominant_upper = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=57.0, high=152.0, low=52.0, close=100.0),
    ]))
    dominant_lower = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=62.0, high=105.0, low=10.0, close=100.0),
    ]))
    minimal = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=91.0, low=49.0, close=90.0),
    ]))
    balanced = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=45.0, high=62.0, low=38.0, close=55.0),
    ]))
    mixed = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=56.0, high=124.0, low=24.0, close=80.0),
    ]))

    assert dominant_upper.wick_classification == "dominant_upper_wick"
    assert dominant_lower.wick_classification == "dominant_lower_wick"
    assert minimal.wick_classification == "minimal_wicks"
    assert balanced.wick_classification == "balanced_wicks"
    assert mixed.wick_classification == "mixed_wicks"

    precedence = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=91.0, low=49.0, close=90.0),
    ]))
    assert precedence.wick_classification == "minimal_wicks"


def test_trading_vertical_slice_v4_close_location_boundaries():
    near_low = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=30.0),
    ]))
    lower = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=50.0),
    ]))
    upper = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=70.0),
    ]))
    near_high = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=90.0),
    ]))

    assert near_low.close_location_classification == "close_near_low"
    assert lower.close_location_classification == "close_lower_region"
    assert upper.close_location_classification == "close_upper_region"
    assert near_high.close_location_classification == "close_near_high"


def test_trading_vertical_slice_v4_rejection_boundaries():
    bullish = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=85.0),
    ]))
    bullish_fail = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=84.0),
    ]))
    bearish = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=35.0),
    ]))
    bearish_fail = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=36.0),
    ]))

    assert bullish.rejection_classification == "bullish_rejection"
    assert bullish_fail.rejection_classification == "none"
    assert bearish.rejection_classification == "bearish_rejection"
    assert bearish_fail.rejection_classification == "none"


def test_trading_vertical_slice_v4_engulfing_requires_opposite_previous_direction_and_strict_boundaries():
    bullish = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=105.0, low=85.0, close=90.0),
        _candle("2026-08-16T11:00:00Z", open_price=88.0, high=112.0, low=80.0, close=110.0),
    ]))
    bearish = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=90.0, high=110.0, low=80.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=108.0, high=115.0, low=70.0, close=85.0),
    ]))
    boundary_fail = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=105.0, low=85.0, close=90.0),
        _candle("2026-08-16T11:00:00Z", open_price=90.0, high=112.0, low=80.0, close=110.0),
    ]))

    assert bullish.engulfing_classification == "bullish_engulfing"
    assert bearish.engulfing_classification == "bearish_engulfing"
    assert boundary_fail.engulfing_classification == "none"


def test_trading_vertical_slice_v4_inside_outside_strict_boundaries():
    inside = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=90.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=102.0, high=109.0, low=91.0, close=100.0),
    ]))
    outside = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=90.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=95.0, high=111.0, low=89.0, close=100.0),
    ]))
    equality = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=90.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=102.0, high=110.0, low=90.0, close=100.0),
    ]))

    assert inside.bar_relationship == "inside_bar"
    assert outside.bar_relationship == "outside_bar"
    assert equality.bar_relationship == "none"


def test_trading_vertical_slice_v4_relative_range_and_baseline_excludes_current():
    candles = [
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=50.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=75.0, low=55.0, close=65.0),
        _candle("2026-08-16T12:00:00Z", open_price=65.0, high=95.0, low=65.0, close=80.0),
        _candle("2026-08-16T13:00:00Z", open_price=80.0, high=120.0, low=80.0, close=100.0),
        _candle("2026-08-16T14:00:00Z", open_price=100.0, high=150.0, low=100.0, close=125.0),
        _candle("2026-08-16T15:00:00Z", open_price=125.0, high=149.0, low=125.0, close=137.0),
    ]
    result = CandleIntelligenceAnalyzer().analyze(_payload(candles))
    baseline = result.evidence["relative_range_rule"]["baseline_ranges"]
    assert baseline == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert result.relative_range_classification == "normal"

    compressed = CandleIntelligenceAnalyzer().analyze(_payload(candles[:-1] + [
        _candle("2026-08-16T15:00:00Z", open_price=125.0, high=148.0, low=125.0, close=136.0),
    ]))
    expanded = CandleIntelligenceAnalyzer().analyze(_payload(candles[:-1] + [
        _candle("2026-08-16T15:00:00Z", open_price=125.0, high=187.0, low=125.0, close=155.0),
    ]))
    assert compressed.relative_range_classification == "compressed"
    assert expanded.relative_range_classification == "expanded"


def test_trading_vertical_slice_v4_relative_range_boundaries_and_zero_baseline():
    normal_low = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=50.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=65.0, low=55.0, close=60.0),
        _candle("2026-08-16T12:00:00Z", open_price=60.0, high=70.0, low=60.0, close=65.0),
        _candle("2026-08-16T13:00:00Z", open_price=65.0, high=75.0, low=65.0, close=70.0),
        _candle("2026-08-16T14:00:00Z", open_price=70.0, high=80.0, low=70.0, close=75.0),
        _candle("2026-08-16T15:00:00Z", open_price=75.0, high=83.0, low=75.0, close=79.0),
    ]))
    normal_high = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=50.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=65.0, low=55.0, close=60.0),
        _candle("2026-08-16T12:00:00Z", open_price=60.0, high=70.0, low=60.0, close=65.0),
        _candle("2026-08-16T13:00:00Z", open_price=65.0, high=75.0, low=65.0, close=70.0),
        _candle("2026-08-16T14:00:00Z", open_price=70.0, high=80.0, low=70.0, close=75.0),
        _candle("2026-08-16T15:00:00Z", open_price=75.0, high=86.0, low=75.0, close=80.0),
    ]))
    zero_baseline = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        _candle("2026-08-16T11:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        _candle("2026-08-16T12:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        _candle("2026-08-16T13:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        _candle("2026-08-16T14:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0),
        _candle("2026-08-16T15:00:00Z", open_price=100.0, high=101.0, low=100.0, close=101.0),
    ]))

    assert normal_low.relative_range_classification == "normal"
    assert normal_high.relative_range_classification == "normal"
    assert zero_baseline.relative_range_classification == "insufficient_sequence_context"


def test_trading_vertical_slice_v4_sequence_evidence():
    counts = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=45.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=65.0, low=50.0, close=60.0),
        _candle("2026-08-16T12:00:00Z", open_price=60.0, high=70.0, low=55.0, close=60.0),
        _candle("2026-08-16T13:00:00Z", open_price=60.0, high=62.0, low=52.0, close=54.0),
        _candle("2026-08-16T14:00:00Z", open_price=54.0, high=64.0, low=50.0, close=60.0),
    ]))
    alternating = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=45.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=65.0, low=50.0, close=50.0),
        _candle("2026-08-16T12:00:00Z", open_price=50.0, high=60.0, low=45.0, close=55.0),
        _candle("2026-08-16T13:00:00Z", open_price=55.0, high=65.0, low=50.0, close=50.0),
    ]))
    neutral_breaks_alternation = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=45.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=65.0, low=50.0, close=55.0),
        _candle("2026-08-16T12:00:00Z", open_price=55.0, high=60.0, low=50.0, close=50.0),
        _candle("2026-08-16T13:00:00Z", open_price=50.0, high=60.0, low=45.0, close=55.0),
    ]))

    assert counts.consecutive_bullish_count == 1
    assert counts.consecutive_bearish_count == 0
    assert alternating.alternating_sequence is True
    assert neutral_breaks_alternation.alternating_sequence is False


def test_trading_vertical_slice_v4_range_sequences():
    expansion = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=50.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=70.0, low=55.0, close=65.0),
        _candle("2026-08-16T12:00:00Z", open_price=65.0, high=85.0, low=65.0, close=75.0),
    ]))
    compression = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=80.0, low=50.0, close=70.0),
        _candle("2026-08-16T11:00:00Z", open_price=70.0, high=90.0, low=70.0, close=80.0),
        _candle("2026-08-16T12:00:00Z", open_price=80.0, high=90.0, low=80.0, close=85.0),
    ]))
    equality_breaks = CandleIntelligenceAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=50.0, high=60.0, low=50.0, close=55.0),
        _candle("2026-08-16T11:00:00Z", open_price=55.0, high=70.0, low=55.0, close=65.0),
        _candle("2026-08-16T12:00:00Z", open_price=65.0, high=70.0, low=55.0, close=60.0),
    ]))

    assert expansion.range_expansion_sequence is True
    assert compression.range_compression_sequence is True
    assert equality_breaks.range_expansion_sequence is False
    assert equality_breaks.range_compression_sequence is False


def test_trading_vertical_slice_v4_validation_and_invalid_configuration():
    analyzer = CandleIntelligenceAnalyzer()
    invalid_inputs = [
        {
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, {"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}],
        },
        {
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T11:00:00Z", "open": 100.0, "high": 99.0, "low": 101.0, "close": 100.0}],
        },
        {
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T11:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}],
            "config": {"small_body_ratio_max": 0.70, "large_body_ratio_min": 0.60},
        },
    ]
    for payload in invalid_inputs:
        try:
            analyzer.analyze(payload)
            raise AssertionError("Expected invalid input to fail closed.")
        except ValueError:
            pass


def test_trading_vertical_slice_v4_safety_and_final_authority_boundary():
    specialist = CandleIntelligenceSpecialist()
    result = specialist.analyze_candles(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=60.0, high=110.0, low=10.0, close=85.0),
    ]))
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
        "setup_quality",
        "trading_confidence",
        "trade_recommendation",
        "broker_instruction",
        "execution_command",
    ]:
        assert forbidden not in text

    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="candle_analyst",
        capability_name="candle_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False
