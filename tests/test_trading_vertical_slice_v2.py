from __future__ import annotations

from datetime import datetime, timezone

from ced_one.business_divisions.trading.market_context import (
    MarketContextAggregator,
    MarketContextInput,
    MarketContextResult,
    MarketContextValidator,
)
from ced_one.business_divisions.trading.market_observation import MarketAnalysisSpecialist


REQUIRED_TIMEFRAMES = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]


def _base_payload(timeframe: str, *, current_price: float = 2341.10, open_price: float = 2339.80, high: float = 2343.20, low: float = 2338.10, close: float = 2341.60, recent_high: float = 2345.50, recent_low: float = 2335.20):
    return {
        "symbol": "XAUUSD",
        "timestamp": "2026-08-16T10:00:00Z",
        "timeframe": timeframe,
        "current_price": current_price,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "session_context": {"session": "london"},
        "source_metadata": {"source": "synthetic_test_contract"},
    }


def _valid_context_payload(**overrides):
    payload = {
        "symbol": "XAUUSD",
        "evaluation_time": "2026-08-16T10:01:00Z",
        "max_age_seconds": 300,
        "timeframes": {
            timeframe: _base_payload(timeframe)
            for timeframe in REQUIRED_TIMEFRAMES
        },
    }
    payload.update(overrides)
    return payload


def test_trading_vertical_slice_v2_requires_exactly_seven_timeframes():
    payload = _valid_context_payload()
    result = MarketContextValidator().validate_input(payload)
    assert not result

    payload_missing = _valid_context_payload(timeframes={k: _base_payload(k) for k in REQUIRED_TIMEFRAMES[:-1]})
    errors = MarketContextValidator().validate_input(payload_missing)
    assert errors
    assert any("missing" in item.lower() or "required" in item.lower() for item in errors)

    payload_extra = _valid_context_payload(timeframes={**{k: _base_payload(k) for k in REQUIRED_TIMEFRAMES}, "M240": _base_payload("M240")})
    errors = MarketContextValidator().validate_input(payload_extra)
    assert errors
    assert any("extra" in item.lower() or "unexpected" in item.lower() for item in errors)


def test_trading_vertical_slice_v2_all_groups_bullish_produce_bullish_aligned_context():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2400.0, open_price=2380.0, high=2405.0, low=2378.0, close=2398.0, recent_high=2410.0, recent_low=2365.0),
            "H4": _base_payload("H4", current_price=2390.0, open_price=2368.0, high=2396.0, low=2360.0, close=2388.0, recent_high=2402.0, recent_low=2355.0),
            "H1": _base_payload("H1", current_price=2385.0, open_price=2365.0, high=2388.0, low=2358.0, close=2383.0, recent_high=2395.0, recent_low=2350.0),
            "M30": _base_payload("M30", current_price=2381.0, open_price=2362.0, high=2385.0, low=2354.0, close=2379.0, recent_high=2390.0, recent_low=2350.0),
            "M15": _base_payload("M15", current_price=2378.0, open_price=2365.0, high=2382.0, low=2358.0, close=2377.0, recent_high=2388.0, recent_low=2352.0),
            "M5": _base_payload("M5", current_price=2374.0, open_price=2360.0, high=2378.0, low=2356.0, close=2371.0, recent_high=2380.0, recent_low=2350.0),
            "M1": _base_payload("M1", current_price=2370.0, open_price=2364.0, high=2375.0, low=2359.0, close=2369.0, recent_high=2381.0, recent_low=2348.0),
        }
    )
    result = specialist.observe_market_context(
        payload,
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )
    assert result.htf_context == "bullish"
    assert result.mtf_context == "bullish"
    assert result.ltf_context == "bullish"
    assert result.overall_context == "bullish_aligned"
    assert result.alignment_metadata["htf_alignment_score"] == 1.0
    assert result.alignment_metadata["mtf_alignment_score"] == 1.0
    assert result.alignment_metadata["ltf_alignment_score"] == 1.0


def test_trading_vertical_slice_v2_all_groups_bearish_produce_bearish_aligned_context():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2280.0, open_price=2340.0, high=2350.0, low=2270.0, close=2285.0, recent_high=2365.0, recent_low=2260.0),
            "H4": _base_payload("H4", current_price=2295.0, open_price=2338.0, high=2348.0, low=2288.0, close=2298.0, recent_high=2355.0, recent_low=2278.0),
            "H1": _base_payload("H1", current_price=2302.0, open_price=2345.0, high=2350.0, low=2294.0, close=2304.0, recent_high=2360.0, recent_low=2288.0),
            "M30": _base_payload("M30", current_price=2309.0, open_price=2352.0, high=2358.0, low=2295.0, close=2310.0, recent_high=2362.0, recent_low=2289.0),
            "M15": _base_payload("M15", current_price=2312.0, open_price=2355.0, high=2362.0, low=2306.0, close=2314.0, recent_high=2368.0, recent_low=2299.0),
            "M5": _base_payload("M5", current_price=2318.0, open_price=2358.0, high=2364.0, low=2310.0, close=2320.0, recent_high=2370.0, recent_low=2305.0),
            "M1": _base_payload("M1", current_price=2324.0, open_price=2360.0, high=2365.0, low=2318.0, close=2326.0, recent_high=2374.0, recent_low=2310.0),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.htf_context == "bearish"
    assert result.mtf_context == "bearish"
    assert result.ltf_context == "bearish"
    assert result.overall_context == "bearish_aligned"


def test_trading_vertical_slice_v2_bullish_htf_and_mtf_with_mixed_ltf_produces_ltf_misalignment():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2400.0, open_price=2380.0, high=2405.0, low=2378.0, close=2398.0, recent_high=2410.0, recent_low=2365.0),
            "H4": _base_payload("H4", current_price=2395.0, open_price=2368.0, high=2399.0, low=2361.0, close=2390.0, recent_high=2405.0, recent_low=2358.0),
            "H1": _base_payload("H1", current_price=2388.0, open_price=2365.0, high=2393.0, low=2358.0, close=2387.0, recent_high=2400.0, recent_low=2352.0),
            "M30": _base_payload("M30", current_price=2382.0, open_price=2362.0, high=2389.0, low=2354.0, close=2381.0, recent_high=2395.0, recent_low=2350.0),
            "M15": _base_payload("M15", current_price=2378.0, open_price=2363.0, high=2384.0, low=2356.0, close=2377.0, recent_high=2391.0, recent_low=2351.0),
            "M5": _base_payload("M5", current_price=2340.0, open_price=2350.0, high=2360.0, low=2335.0, close=2342.0, recent_high=2368.0, recent_low=2333.0),
            "M1": _base_payload("M1", current_price=2368.0, open_price=2358.0, high=2372.0, low=2350.0, close=2367.0, recent_high=2378.0, recent_low=2349.0),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.htf_context == "bullish"
    assert result.mtf_context == "bullish"
    assert result.ltf_context == "mixed"
    assert result.overall_context == "bullish_with_ltf_misalignment"


def test_trading_vertical_slice_v2_htf_bullish_mtf_not_bullish_produces_mtf_misalignment():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2400.0, open_price=2380.0, high=2405.0, low=2378.0, close=2398.0, recent_high=2410.0, recent_low=2365.0),
            "H4": _base_payload("H4", current_price=2395.0, open_price=2368.0, high=2399.0, low=2361.0, close=2390.0, recent_high=2405.0, recent_low=2358.0),
            "H1": _base_payload("H1", current_price=2388.0, open_price=2365.0, high=2392.0, low=2358.0, close=2387.0, recent_high=2400.0, recent_low=2352.0),
            "M30": _base_payload("M30", current_price=2325.0, open_price=2350.0, high=2361.0, low=2320.0, close=2328.0, recent_high=2368.0, recent_low=2310.0),
            "M15": _base_payload("M15", current_price=2338.0, open_price=2347.0, high=2352.0, low=2332.0, close=2339.0, recent_high=2360.0, recent_low=2324.0),
            "M5": _base_payload("M5", current_price=2368.0, open_price=2358.0, high=2372.0, low=2350.0, close=2367.0, recent_high=2378.0, recent_low=2349.0),
            "M1": _base_payload("M1", current_price=2363.0, open_price=2354.0, high=2368.0, low=2349.0, close=2362.0, recent_high=2375.0, recent_low=2342.0),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.htf_context == "bullish"
    assert result.mtf_context != "bullish"
    assert result.overall_context == "bullish_with_mtf_misalignment"


def test_trading_vertical_slice_v2_all_neutral_groups_produce_neutral_context():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2341.0, open_price=2340.0, high=2348.0, low=2334.0, close=2341.5, recent_high=2350.0, recent_low=2325.0),
            "H4": _base_payload("H4", current_price=2341.2, open_price=2341.0, high=2349.0, low=2335.0, close=2341.0, recent_high=2351.0, recent_low=2326.0),
            "H1": _base_payload("H1", current_price=2340.7, open_price=2340.5, high=2347.0, low=2336.0, close=2340.8, recent_high=2349.0, recent_low=2328.0),
            "M30": _base_payload("M30", current_price=2341.3, open_price=2341.4, high=2347.5, low=2337.0, close=2341.1, recent_high=2349.0, recent_low=2329.0),
            "M15": _base_payload("M15", current_price=2340.9, open_price=2340.8, high=2348.2, low=2337.5, close=2341.0, recent_high=2348.5, recent_low=2329.5),
            "M5": _base_payload("M5", current_price=2341.1, open_price=2341.2, high=2348.4, low=2336.8, close=2340.9, recent_high=2349.2, recent_low=2329.4),
            "M1": _base_payload("M1", current_price=2340.8, open_price=2340.9, high=2347.9, low=2336.9, close=2341.0, recent_high=2349.0, recent_low=2329.8),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.htf_context == "neutral"
    assert result.mtf_context == "neutral"
    assert result.ltf_context == "neutral"
    assert result.overall_context == "neutral"


def test_trading_vertical_slice_v2_alignment_scores_are_deterministic_and_non_trade():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2400.0, open_price=2380.0, high=2405.0, low=2378.0, close=2398.0, recent_high=2410.0, recent_low=2365.0),
            "H4": _base_payload("H4", current_price=2395.0, open_price=2368.0, high=2399.0, low=2361.0, close=2390.0, recent_high=2405.0, recent_low=2358.0),
            "H1": _base_payload("H1", current_price=2390.0, open_price=2365.0, high=2393.0, low=2358.0, close=2387.0, recent_high=2400.0, recent_low=2352.0),
            "M30": _base_payload("M30", current_price=2340.0, open_price=2344.0, high=2348.0, low=2336.0, close=2341.0, recent_high=2352.0, recent_low=2330.0),
            "M15": _base_payload("M15", current_price=2382.0, open_price=2362.0, high=2389.0, low=2354.0, close=2381.0, recent_high=2395.0, recent_low=2350.0),
            "M5": _base_payload("M5", current_price=2380.0, open_price=2368.0, high=2388.0, low=2360.0, close=2376.0, recent_high=2390.0, recent_low=2356.0),
            "M1": _base_payload("M1", current_price=2385.0, open_price=2368.0, high=2390.0, low=2362.0, close=2384.0, recent_high=2395.0, recent_low=2358.0),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.alignment_metadata["htf_alignment_score"] == 1.0
    assert result.alignment_metadata["mtf_alignment_score"] == 0.5
    assert result.alignment_metadata["ltf_alignment_score"] == 1.0
    payload_dict = result.to_dict()
    assert "probability" not in str(payload_dict).lower()
    assert "confidence" not in str(payload_dict).lower()
    assert "expected_return" not in str(payload_dict).lower()
    assert "signal" not in str(payload_dict).lower()


def test_trading_vertical_slice_v2_group_structure_and_volatility_are_explicit_and_deterministic():
    specialist = MarketAnalysisSpecialist()
    payload = _valid_context_payload(
        timeframes={
            "D1": _base_payload("D1", current_price=2400.0, open_price=2380.0, high=2405.0, low=2378.0, close=2398.0, recent_high=2410.0, recent_low=2365.0),
            "H4": _base_payload("H4", current_price=2395.0, open_price=2368.0, high=2399.0, low=2361.0, close=2390.0, recent_high=2405.0, recent_low=2358.0),
            "H1": _base_payload("H1", current_price=2388.0, open_price=2365.0, high=2392.0, low=2358.0, close=2387.0, recent_high=2400.0, recent_low=2352.0),
            "M30": _base_payload("M30", current_price=2378.0, open_price=2362.0, high=2384.0, low=2356.0, close=2377.0, recent_high=2391.0, recent_low=2351.0),
            "M15": _base_payload("M15", current_price=2375.0, open_price=2364.0, high=2382.0, low=2357.0, close=2374.0, recent_high=2388.0, recent_low=2352.0),
            "M5": _base_payload("M5", current_price=2365.0, open_price=2355.0, high=2370.0, low=2349.0, close=2364.0, recent_high=2376.0, recent_low=2342.0),
            "M1": _base_payload("M1", current_price=2361.0, open_price=2354.0, high=2368.0, low=2349.0, close=2362.0, recent_high=2375.0, recent_low=2346.0),
        }
    )
    result = specialist.observe_market_context(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.htf_structure in {"uptrend", "range", "mixed", "downtrend"}
    assert result.mtf_structure in {"uptrend", "range", "mixed", "downtrend"}
    assert result.ltf_structure in {"uptrend", "range", "mixed", "downtrend"}
    assert result.htf_volatility in {"low", "moderate", "elevated", "mixed"}
    assert result.mtf_volatility in {"low", "moderate", "elevated", "mixed"}
    assert result.ltf_volatility in {"low", "moderate", "elevated", "mixed"}
    assert "structure_context" not in result.to_dict()
    assert "volatility_context" not in result.to_dict()


def test_trading_vertical_slice_v2_output_has_no_advisory_or_execution_fields():
    specialist = MarketAnalysisSpecialist()
    result = specialist.observe_market_context(
        _valid_context_payload(),
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )
    payload = result.to_dict()
    forbidden = ["buy", "sell", "entry", "stop_loss", "take_profit", "risk", "position_size", "setup_quality", "recommendation", "broker"]
    lower = str(payload).lower()
    for term in forbidden:
        assert term not in lower


def test_trading_vertical_slice_v2_specialist_cannot_mutate_lifecycle_or_issue_execution_commands():
    specialist = MarketAnalysisSpecialist()
    assert specialist.can_mutate_task_lifecycle() is False
    result = specialist.observe_market_context(
        _valid_context_payload(),
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )
    lower = str(result.to_dict()).lower()
    assert "execution" not in lower
    assert "command" not in lower
    assert specialist.is_final_authority() is False
