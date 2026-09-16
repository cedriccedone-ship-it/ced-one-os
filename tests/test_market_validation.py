from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer
from ced_one.business_divisions.trading.validation import validate_detector_input
from ced_one.business_divisions.trading.candle_intelligence import CandleIntelligenceAnalyzer
from ced_one.business_divisions.trading.volatility_range import VolatilityRangeAnalyzer
from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceAnalyzer
from ced_one.business_divisions.trading.fvg_imbalance_intelligence import FVGImbalanceIntelligenceAnalyzer
from ced_one.business_divisions.trading.displacement_intelligence import DisplacementIntelligenceAnalyzer
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY


def candle(index, high, low, close=100):
    return dict(timestamp=(datetime(2026, 9, 1, tzinfo=timezone.utc)+timedelta(hours=index)).isoformat(), open=100, high=high, low=low, close=close)


def data(candles):
    return dict(symbol="XAUUSD", timeframe="H1", evaluation_time="2026-09-02T00:00:00Z", candle_history=candles)


@pytest.mark.parametrize("analyzer", [MarketStructureAnalyzer, CandleIntelligenceAnalyzer, VolatilityRangeAnalyzer, LiquidityIntelligenceAnalyzer, FVGImbalanceIntelligenceAnalyzer, DisplacementIntelligenceAnalyzer])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, 0])
def test_detectors_reject_invalid_prices(analyzer, value):
    item = candle(0, 103, 98)
    item["close"] = value
    with pytest.raises(ValueError, match="finite"):
        analyzer().analyze(data([item]))


def test_timezone_and_duplicate_instants():
    first = candle(0, 103, 98)
    second = dict(first, timestamp="2026-09-01T02:00:00+02:00")
    assert any("Duplicate" in error for error in validate_detector_input(data([first, second])))
    first["timestamp"] = "2026-09-01T00:00:00"
    assert any("timezone" in error for error in validate_detector_input(data([first])))


def test_only_two_sided_pivots_and_preconfirmed_break_anchor():
    candles = [candle(i, high, low) for i, (high, low) in enumerate([(102,98),(104,99),(102,95),(106,99),(103,97),(104,99)])]
    analyzer = MarketStructureAnalyzer()
    assert analyzer._find_confirmed_swings(candles[:1]) == ([], [])
    result = analyzer.analyze(data(candles))
    assert result.structure_state == "bullish_structure"
    assert result.latest_swing_high["index"] == 3
    assert result.latest_swing_low["index"] == 4
    # Both anchors have already been confirmed before the breakout candle.
    candles.append(candle(6, 108, 99, close=107))
    result = analyzer.analyze(data(candles))
    assert result.continuation_break_confirmed is True
    assert result.broken_anchor_price == 106
    assert result.broken_anchor_timestamp == candles[3]["timestamp"]
    candles[-1]["close"] = 106
    result = analyzer.analyze(data(candles))
    assert result.continuation_break_candidate is True
    assert result.continuation_break_confirmed is False


def test_snapshot_owns_completion_and_future_rejection():
    candles = [candle(0, 102, 98), candle(1, 103, 99)]
    source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp="2026-09-01T01:30:00Z", candle_history=candles))
    assert source.source_availability == "AVAILABLE"
    assert len(source.approved_candle_history) == 1
    future = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp="2026-08-31T00:00:00Z", candle_history=candles))
    assert future.source_availability == "INVALID"
