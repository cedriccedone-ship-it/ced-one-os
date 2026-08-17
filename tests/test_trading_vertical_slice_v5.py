from __future__ import annotations

import re

from ced_one.business_divisions.trading.volatility_range import (
    VolatilityRangeAnalyzer,
    VolatilityRangeConfig,
    VolatilityRangeSpecialist,
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


def _series_constant_range_10(count: int, *, start_hour: int = 0):
    candles = []
    for index in range(count):
        hour = start_hour + index
        candles.append(_candle(f"2026-08-16T{hour:02d}:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0))
    return candles


def _series_constant_true_range_100(count: int, *, start_hour: int = 0):
    candles = []
    for index in range(count):
        hour = start_hour + index
        candles.append(_candle(f"2026-08-16T{hour:02d}:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0))
    return candles


def _series_with_true_ranges(ranges: list[float], *, start_hour: int = 0):
    candles = []
    for index, candle_range in enumerate(ranges):
        hour = start_hour + index
        candles.append(_candle(
            f"2026-08-16T{hour:02d}:00:00Z",
            open_price=100.0,
            high=100.0 + candle_range,
            low=100.0,
            close=100.0 + (candle_range / 2.0),
        ))
    return candles


def test_trading_vertical_slice_v5_true_range_rules():
    first = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=112.0, low=100.0, close=106.0),
    ]))
    inside = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=112.0, low=100.0, close=106.0),
        _candle("2026-08-16T11:00:00Z", open_price=106.0, high=114.0, low=104.0, close=110.0),
    ]))
    gap = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=120.0, high=130.0, low=115.0, close=125.0),
    ]))

    assert first.true_range == 12.0
    assert first.candle_range == 12.0
    assert inside.true_range == 10.0
    assert inside.candle_range == 10.0
    assert gap.gap_state == "gap_up"
    assert gap.gap_amount == 5.0
    assert gap.true_range == 25.0


def test_trading_vertical_slice_v5_gap_rules_and_equality():
    gap_up = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=120.0, high=130.0, low=115.0, close=125.0),
    ]))
    gap_down = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=120.0, high=130.0, low=120.0, close=125.0),
        _candle("2026-08-16T11:00:00Z", open_price=100.0, high=105.0, low=90.0, close=95.0),
    ]))
    no_gap = VolatilityRangeAnalyzer().analyze(_payload([
        _candle("2026-08-16T10:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
        _candle("2026-08-16T11:00:00Z", open_price=110.0, high=120.0, low=110.0, close=115.0),
    ]))

    assert gap_up.gap_state == "gap_up"
    assert gap_up.gap_amount == 5.0
    assert gap_down.gap_state == "gap_down"
    assert gap_down.gap_amount == 15.0
    assert no_gap.gap_state == "no_gap"
    assert no_gap.gap_amount == 0.0


def test_trading_vertical_slice_v5_atr_uses_previous_fourteen_only():
    prior = _series_constant_true_range_100(14)
    current_small = _candle("2026-08-16T14:00:00Z", open_price=150.0, high=170.0, low=140.0, close=160.0)
    current_huge = _candle("2026-08-16T14:00:00Z", open_price=150.0, high=260.0, low=140.0, close=240.0)

    small = VolatilityRangeAnalyzer().analyze(_payload(prior + [current_small]))
    huge = VolatilityRangeAnalyzer().analyze(_payload(prior + [current_huge]))

    assert small.atr == 100.0
    assert huge.atr == 100.0
    assert small.current_range_to_atr_ratio == 0.3
    assert huge.current_range_to_atr_ratio == 1.2


def test_trading_vertical_slice_v5_atr_insufficient_history_boundary():
    payload_13 = _payload(_series_constant_true_range_100(13) + [
        _candle("2026-08-16T13:00:00Z", open_price=150.0, high=170.0, low=140.0, close=160.0),
    ])
    payload_14 = _payload(_series_constant_true_range_100(14) + [
        _candle("2026-08-16T14:00:00Z", open_price=150.0, high=170.0, low=140.0, close=160.0),
    ])

    result_13 = VolatilityRangeAnalyzer().analyze(payload_13)
    result_14 = VolatilityRangeAnalyzer().analyze(payload_14)

    assert result_13.atr is None
    assert result_13.current_range_to_atr_ratio is None
    assert result_14.atr == 100.0
    assert result_14.current_range_to_atr_ratio == 0.3


def test_trading_vertical_slice_v5_median_baselines_use_previous_twenty_only():
    prior = [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=100.0 + i, low=100.0, close=100.0 + (i / 2.0))
        for i in range(1, 21)
    ]
    current = _candle("2026-08-16T21:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0)
    result = VolatilityRangeAnalyzer().analyze(_payload(prior + [current]))

    assert result.median_candle_range == 10.5
    assert result.median_true_range == 10.5
    assert result.current_range_to_median_ratio == 100.0 / 10.5
    assert result.current_true_range_to_median_ratio == 100.0 / 10.5


def test_trading_vertical_slice_v5_median_baseline_insufficient_history_boundary():
    result_19 = VolatilityRangeAnalyzer().analyze(_payload(_series_constant_range_10(19) + [
        _candle("2026-08-16T19:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
    ]))
    result_20 = VolatilityRangeAnalyzer().analyze(_payload(_series_constant_range_10(20) + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
    ]))

    assert result_19.median_candle_range is None
    assert result_19.range_state == "insufficient_history"
    assert result_20.median_candle_range == 10.0
    assert result_20.range_state == "normal"


def test_trading_vertical_slice_v5_zero_baseline_and_abnormal_range_context():
    result = VolatilityRangeAnalyzer().analyze(_payload([
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0)
        for i in range(20)
    ] + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=101.0, low=100.0, close=101.0),
    ]))

    assert result.median_candle_range == 0.0
    assert result.median_true_range == 0.0
    assert result.current_range_to_median_ratio is None
    assert result.range_state == "insufficient_context"
    assert result.volatility_state == "insufficient_context"
    assert result.abnormal_range is None


def test_trading_vertical_slice_v5_normalized_ratio_and_state_boundaries():
    prior = _series_constant_true_range_100(20)
    low = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=174.0, low=100.0, close=150.0),
    ]))
    exact_low = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=175.0, low=100.0, close=150.0),
    ]))
    moderate = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=249.0, low=100.0, close=175.0),
    ]))
    exact_high = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=250.0, low=100.0, close=175.0),
    ]))
    elevated = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=251.0, low=100.0, close=175.0),
    ]))

    assert low.volatility_state == "low"
    assert exact_low.volatility_state == "moderate"
    assert moderate.volatility_state == "moderate"
    assert exact_high.volatility_state == "moderate"
    assert elevated.volatility_state == "elevated"

    assert low.range_state == "compressed"
    assert exact_low.range_state == "normal"
    assert moderate.range_state == "expanded"
    assert exact_high.range_state == "expanded"
    assert elevated.range_state == "expanded"


def test_trading_vertical_slice_v5_range_state_boundaries():
    prior = _series_constant_true_range_100(20)
    compressed = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=174.0, low=100.0, close=137.0),
    ]))
    normal = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=175.0, low=100.0, close=137.5),
    ]))
    expanded = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=300.0, low=100.0, close=200.0),
    ]))
    extreme = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=301.0, low=100.0, close=200.5),
    ]))

    assert compressed.range_state == "compressed"
    assert normal.range_state == "normal"
    assert expanded.range_state == "expanded"
    assert extreme.range_state == "extreme"


def test_trading_vertical_slice_v5_volatility_trend_boundaries_and_history():
    contracting_prior = [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0)
        for i in range(15)
    ] + [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=170.0, low=100.0, close=135.0)
        for i in range(15, 20)
    ]
    stable_prior = [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0)
        for i in range(15)
    ] + [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=180.0, low=100.0, close=140.0)
        for i in range(15, 20)
    ]
    stable_upper_prior = [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0)
        for i in range(15)
    ] + [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=220.0, low=100.0, close=160.0)
        for i in range(15, 20)
    ]
    expanding_prior = [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=200.0, low=100.0, close=150.0)
        for i in range(15)
    ] + [
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=230.0, low=100.0, close=165.0)
        for i in range(15, 20)
    ]
    insufficient = VolatilityRangeAnalyzer().analyze(_payload(_series_constant_true_range_100(19) + [
        _candle("2026-08-16T19:00:00Z", open_price=100.0, high=180.0, low=100.0, close=140.0),
    ]))
    zero_long = VolatilityRangeAnalyzer().analyze(_payload([
        _candle(f"2026-08-16T{i:02d}:00:00Z", open_price=100.0, high=100.0, low=100.0, close=100.0)
        for i in range(20)
    ] + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=101.0, low=100.0, close=101.0),
    ]))

    contracting = VolatilityRangeAnalyzer().analyze(_payload(contracting_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=170.0, low=100.0, close=135.0),
    ]))
    stable_low = VolatilityRangeAnalyzer().analyze(_payload(stable_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=180.0, low=100.0, close=140.0),
    ]))
    stable_high = VolatilityRangeAnalyzer().analyze(_payload(stable_upper_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=220.0, low=100.0, close=160.0),
    ]))
    expanding = VolatilityRangeAnalyzer().analyze(_payload(expanding_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=260.0, low=100.0, close=180.0),
    ]))

    assert contracting.volatility_trend == "contracting"
    assert stable_low.volatility_trend == "stable"
    assert stable_high.volatility_trend == "stable"
    assert expanding.volatility_trend == "expanding"
    assert insufficient.volatility_trend == "insufficient_history"
    assert zero_long.volatility_trend == "insufficient_context"


def test_trading_vertical_slice_v5_volatility_baselines_exclude_current_candle_and_exact_trend_boundaries():
    contracting_prior = _series_with_true_ranges([100.0] * 15 + [80.0] * 5)
    expanding_prior = _series_with_true_ranges([100.0] * 15 + [120.0] * 5)

    contracting_a = VolatilityRangeAnalyzer().analyze(_payload(contracting_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=500.0, low=100.0, close=300.0),
    ]))
    contracting_b = VolatilityRangeAnalyzer().analyze(_payload(contracting_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=120.0, low=100.0, close=110.0),
    ]))
    expanding_a = VolatilityRangeAnalyzer().analyze(_payload(expanding_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=500.0, low=100.0, close=300.0),
    ]))
    expanding_b = VolatilityRangeAnalyzer().analyze(_payload(expanding_prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=120.0, low=100.0, close=110.0),
    ]))

    assert contracting_a.short_median_true_range == 80.0
    assert contracting_a.long_median_true_range == 100.0
    assert contracting_b.short_median_true_range == 80.0
    assert contracting_b.long_median_true_range == 100.0
    assert contracting_a.short_to_long_volatility_ratio == 0.8
    assert contracting_a.volatility_trend == "stable"
    assert contracting_b.short_to_long_volatility_ratio == 0.8
    assert contracting_b.volatility_trend == "stable"

    assert expanding_a.short_median_true_range == 120.0
    assert expanding_a.long_median_true_range == 100.0
    assert expanding_b.short_median_true_range == 120.0
    assert expanding_b.long_median_true_range == 100.0
    assert expanding_a.short_to_long_volatility_ratio == 1.2
    assert expanding_a.volatility_trend == "stable"
    assert expanding_b.short_to_long_volatility_ratio == 1.2
    assert expanding_b.volatility_trend == "stable"


def test_trading_vertical_slice_v5_abnormal_range_and_determinism():
    prior = _series_constant_range_10(20)
    below = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=124.0, low=100.0, close=112.0),
    ]))
    exact = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=125.0, low=100.0, close=112.0),
    ]))
    above = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=126.0, low=100.0, close=112.0),
    ]))
    first = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=125.0, low=100.0, close=112.0),
    ]))
    second = VolatilityRangeAnalyzer().analyze(_payload(prior + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=125.0, low=100.0, close=112.0),
    ]))

    assert below.abnormal_range is False
    assert exact.abnormal_range is True
    assert above.abnormal_range is True
    assert first.to_dict() == second.to_dict()


def test_trading_vertical_slice_v5_abnormal_range_insufficient_history_remains_unknown():
    result = VolatilityRangeAnalyzer().analyze(_payload(_series_constant_range_10(19) + [
        _candle("2026-08-16T19:00:00Z", open_price=100.0, high=110.0, low=100.0, close=105.0),
    ]))

    assert result.abnormal_range is None
    assert result.evidence["baseline_states"]["abnormal_range_state"] == "insufficient_history"


def test_trading_vertical_slice_v5_validation_invalid_config_and_safety():
    analyzer = VolatilityRangeAnalyzer()
    invalid_inputs = [
        {
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, {"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}],
        },
        {
            "symbol": "XAUUSD",
            "timeframe": "BAD",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T11:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}],
        },
        {
            "symbol": "XAUUSD",
            "timeframe": "M1",
            "evaluation_time": "2026-08-16T10:00:00Z",
            "candle_history": [{"timestamp": "2026-08-16T11:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}],
            "config": {"atr_window": 0},
        },
    ]
    for payload in invalid_inputs:
        try:
            analyzer.analyze(payload)
            raise AssertionError("Expected invalid input to fail closed.")
        except ValueError:
            pass

    specialist = VolatilityRangeSpecialist()
    result = specialist.analyze_volatility(_payload(_series_constant_range_10(20) + [
        _candle("2026-08-16T20:00:00Z", open_price=100.0, high=125.0, low=100.0, close=112.0),
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
        "setup",
        "breakout_signal",
        "reversal_signal",
        "expected_volatility",
        "forecast",
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
        specialist_name="volatility_analyst",
        capability_name="volatility_range",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False
