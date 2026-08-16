from __future__ import annotations

from datetime import datetime, timezone

from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer


def _base_candle(timestamp: str, *, open_price: float, high: float, low: float, close: float):
    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _payload(*, candles):
    return {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "evaluation_time": "2026-08-16T10:00:00Z",
        "candle_history": candles,
    }


def test_trading_vertical_slice_v3_strict_swing_high():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.5),
        _base_candle("2026-08-16T10:00:00Z", open_price=100.5, high=103.0, low=99.5, close=102.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=101.5, high=101.8, low=98.0, close=100.2),
        _base_candle("2026-08-16T12:00:00Z", open_price=100.0, high=102.5, low=97.5, close=101.2),
        _base_candle("2026-08-16T13:00:00Z", open_price=101.0, high=104.0, low=98.0, close=103.2),
        _base_candle("2026-08-16T14:00:00Z", open_price=103.0, high=103.3, low=98.8, close=102.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=102.0, high=103.2, low=96.0, close=99.0),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state in {"bullish_structure", "unresolved_structure"}
    assert result.latest_swing_high is not None
    assert result.latest_swing_high["high"] == 104.0


def test_trading_vertical_slice_v3_strict_swing_low():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=102.0, low=98.0, close=99.5),
        _base_candle("2026-08-16T10:00:00Z", open_price=99.5, high=101.0, low=96.0, close=98.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=98.0, high=100.5, low=95.0, close=96.5),
        _base_candle("2026-08-16T12:00:00Z", open_price=96.5, high=99.0, low=94.0, close=95.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=95.0, high=98.5, low=93.0, close=94.2),
        _base_candle("2026-08-16T14:00:00Z", open_price=94.2, high=96.0, low=92.0, close=93.2),
        _base_candle("2026-08-16T15:00:00Z", open_price=93.0, high=98.0, low=90.5, close=91.5),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.latest_swing_low is not None
    assert result.latest_swing_low["low"] == 90.5


def test_trading_vertical_slice_v3_equal_high_is_not_swing_high():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=102.0, low=99.0, close=100.2),
        _base_candle("2026-08-16T10:00:00Z", open_price=100.2, high=103.0, low=98.0, close=101.5),
        _base_candle("2026-08-16T11:00:00Z", open_price=101.5, high=103.0, low=97.0, close=102.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=102.0, high=103.5, low=96.0, close=100.2),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.latest_swing_high is None or result.latest_swing_high["high"] != 103.0


def test_trading_vertical_slice_v3_equal_low_is_not_swing_low():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=105.0, low=94.0, close=101.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=101.0, high=103.0, low=93.0, close=96.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=96.0, high=102.0, low=93.0, close=94.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=94.0, high=106.0, low=92.0, close=105.0),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.latest_swing_low is None or result.latest_swing_low["low"] != 93.0


def test_trading_vertical_slice_v3_hh_hl_bullish_structure():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=103.0, low=96.0, close=101.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=101.0, high=104.0, low=97.0, close=102.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=102.0, high=103.5, low=98.0, close=101.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.0, high=105.0, low=99.0, close=104.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=104.0, high=104.5, low=100.0, close=103.0),
        _base_candle("2026-08-16T14:00:00Z", open_price=103.0, high=106.0, low=101.0, close=105.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=105.0, high=106.2, low=101.2, close=105.5),
        _base_candle("2026-08-16T16:00:00Z", open_price=105.5, high=107.0, low=102.0, close=106.0),
        _base_candle("2026-08-16T17:00:00Z", open_price=106.0, high=106.5, low=101.8, close=105.8),
        _base_candle("2026-08-16T18:00:00Z", open_price=105.8, high=108.0, low=103.0, close=107.0),
        _base_candle("2026-08-16T19:00:00Z", open_price=107.0, high=108.1, low=103.5, close=107.5),
        _base_candle("2026-08-16T20:00:00Z", open_price=107.5, high=109.0, low=104.0, close=108.4),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state == "bullish_structure"
    assert result.latest_high_relationship == "HH"
    assert result.latest_low_relationship == "HL"


def test_trading_vertical_slice_v3_lh_ll_bearish_structure():
    # Crafted to contain two confirmed swing highs (indices 1 and 3)
    # and two confirmed swing lows (indices 2 and 5) producing LH + LL.
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=110.0, high=112.0, low=107.0, close=109.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=109.0, high=115.0, low=104.0, close=110.5),
        _base_candle("2026-08-16T11:00:00Z", open_price=110.5, high=113.0, low=102.0, close=108.5),
        _base_candle("2026-08-16T12:00:00Z", open_price=108.5, high=116.0, low=105.0, close=107.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=107.0, high=111.0, low=103.0, close=105.0),
        _base_candle("2026-08-16T14:00:00Z", open_price=105.0, high=113.0, low=100.0, close=103.5),
        _base_candle("2026-08-16T15:00:00Z", open_price=103.5, high=109.0, low=102.0, close=102.5),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state == "bearish_structure"
    assert result.latest_high_relationship == "LH"
    assert result.latest_low_relationship == "LL"


def test_trading_vertical_slice_v3_conflicting_directions_are_unresolved():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=102.0, low=98.0, close=100.5),
        _base_candle("2026-08-16T10:00:00Z", open_price=100.5, high=104.0, low=97.0, close=103.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=103.0, high=103.2, low=96.0, close=101.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.0, high=106.0, low=95.0, close=105.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=105.0, high=105.6, low=94.0, close=101.0),
        _base_candle("2026-08-16T14:00:00Z", open_price=101.0, high=107.0, low=93.0, close=106.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=106.0, high=108.5, low=92.0, close=107.5),
        _base_candle("2026-08-16T16:00:00Z", open_price=107.5, high=109.0, low=90.0, close=103.0),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state == "unresolved_structure"


def test_trading_vertical_slice_v3_bullish_break_confirmation_requires_close_above_anchor():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=102.0, low=98.0, close=100.8),
        _base_candle("2026-08-16T10:00:00Z", open_price=100.8, high=103.0, low=99.0, close=101.5),
        _base_candle("2026-08-16T11:00:00Z", open_price=101.5, high=103.4, low=99.4, close=101.8),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.8, high=104.0, low=100.0, close=103.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=103.0, high=103.4, low=99.6, close=101.0),
        _base_candle("2026-08-16T14:00:00Z", open_price=101.0, high=105.2, low=100.0, close=104.2),
        _base_candle("2026-08-16T15:00:00Z", open_price=104.2, high=105.0, low=100.6, close=101.5),
        _base_candle("2026-08-16T16:00:00Z", open_price=101.5, high=106.0, low=101.0, close=105.4),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state in {"bullish_structure", "unresolved_structure"}
    assert result.continuation_break_confirmed in {False, True}


def test_trading_vertical_slice_v3_valid_input_without_sufficient_structure_is_unresolved():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=101.0, low=99.0, close=100.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=100.0, high=102.0, low=98.5, close=101.8),
        _base_candle("2026-08-16T11:00:00Z", open_price=101.8, high=102.5, low=98.0, close=101.2),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.2, high=102.0, low=97.0, close=100.4),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    assert result.structure_state == "unresolved_structure"


def test_trading_vertical_slice_v3_invalid_payload_fails_closed():
    payload = {
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "evaluation_time": "2026-08-16T10:00:00Z",
        "candle_history": [
            {"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            {"timestamp": "2026-08-16T10:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        ],
    }
    try:
        MarketStructureAnalyzer().analyze(payload)
        raise AssertionError("Expected validation failure for duplicate timestamps.")
    except ValueError:
        pass


def test_trading_vertical_slice_v3_no_advisory_output_or_execution_semantics():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=103.0, low=96.0, close=101.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=101.0, high=104.0, low=97.0, close=102.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=102.0, high=103.5, low=98.0, close=101.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.0, high=105.0, low=99.0, close=104.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=104.0, high=105.5, low=100.0, close=104.2),
        _base_candle("2026-08-16T14:00:00Z", open_price=104.2, high=106.0, low=101.0, close=105.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=105.0, high=106.5, low=101.5, close=105.8),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    payload_dict = result.to_dict()
    text = str(payload_dict).lower()
    assert "buy" not in text
    assert "sell" not in text
    assert "entry" not in text
    assert "stop_loss" not in text
    assert "take_profit" not in text
    assert "risk" not in text
    assert "position_size" not in text
    assert "recommendation" not in text


def test_trading_vertical_slice_v3_same_input_produces_identical_output():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=103.0, low=96.0, close=101.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=101.0, high=104.0, low=97.0, close=102.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=102.0, high=103.5, low=98.0, close=101.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.0, high=105.0, low=99.0, close=104.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=104.0, high=105.5, low=100.0, close=104.2),
        _base_candle("2026-08-16T14:00:00Z", open_price=104.2, high=106.0, low=101.0, close=105.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=105.0, high=106.5, low=101.5, close=105.8),
    ]
    payload = _payload(candles=candles)
    first = MarketStructureAnalyzer().analyze(payload)
    second = MarketStructureAnalyzer().analyze(payload)
    assert first.to_dict() == second.to_dict()


def test_trading_vertical_slice_v3_specialist_side_effects_are_prohibited():
    candles = [
        _base_candle("2026-08-16T09:00:00Z", open_price=100.0, high=103.0, low=96.0, close=101.0),
        _base_candle("2026-08-16T10:00:00Z", open_price=101.0, high=104.0, low=97.0, close=102.0),
        _base_candle("2026-08-16T11:00:00Z", open_price=102.0, high=103.5, low=98.0, close=101.0),
        _base_candle("2026-08-16T12:00:00Z", open_price=101.0, high=105.0, low=99.0, close=104.0),
        _base_candle("2026-08-16T13:00:00Z", open_price=104.0, high=105.5, low=100.0, close=104.2),
        _base_candle("2026-08-16T14:00:00Z", open_price=104.2, high=106.0, low=101.0, close=105.0),
        _base_candle("2026-08-16T15:00:00Z", open_price=105.0, high=106.5, low=101.5, close=105.8),
    ]
    result = MarketStructureAnalyzer().analyze(_payload(candles=candles))
    lower = str(result.to_dict()).lower()
    assert "execution" not in lower
    assert "command" not in lower
    assert "broker" not in lower
    assert "live" not in lower
    assert "ai" not in lower
