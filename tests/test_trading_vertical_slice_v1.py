from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ced_one.business_divisions.trading.capabilities import MARKET_OBSERVATION, TradingCapability
from ced_one.business_divisions.trading.market_observation import (
    MarketObservationInput,
    MarketObservationResult,
    MarketObservationValidator,
    TradingMarketObservationCapability,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.specialists import MARKET_ANALYST, MarketAnalysisSpecialist
from ced_one.mission_control.types import MissionRequest, RequestClassification


def _xauusd_payload(**overrides):
    payload = {
        "symbol": "XAUUSD",
        "timestamp": "2026-08-16T10:00:00Z",
        "timeframe": "M5",
        "current_price": 2341.10,
        "open": 2339.80,
        "high": 2343.20,
        "low": 2338.10,
        "close": 2341.60,
        "recent_high": 2345.50,
        "recent_low": 2335.20,
        "session_context": {"session": "london"},
        "source_metadata": {"source": "synthetic_test_contract"},
    }
    payload.update(overrides)
    return payload


def test_trading_vertical_slice_routes_xauusd_market_observation():
    request = MissionRequest(
        user_goal="Analyze the supplied XAUUSD market data and return a structured market observation.",
        request_type="analysis",
        business_division="trading",
        context={"symbol": "XAUUSD"},
    )
    classification = RequestClassification(domain_tags=["trading", "market", "xauusd"], confidence=0.95)
    resolver = TradingDivisionResolver()
    result = resolver.resolve_request(request, classification)

    assert result.division_name == "trading"
    assert result.specialist_name == "market_analyst"
    assert result.capability_name == "market_observation"
    assert result.is_supported is True
    assert result.is_routeable is True
    assert result.confidence >= 0.9


def test_trading_vertical_slice_market_observation_capability_exists():
    assert MARKET_OBSERVATION.name == "market_observation"
    assert MARKET_OBSERVATION.permission_scope == "read_only"
    assert MARKET_OBSERVATION.contract == "trading.market_observation.v1"
    assert isinstance(MARKET_OBSERVATION, TradingCapability)


def test_trading_vertical_slice_market_analyst_executes_deterministic_observation():
    specialist = MarketAnalysisSpecialist()
    payload = _xauusd_payload()
    result = specialist.observe_market(
        payload,
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )

    assert result.symbol == "XAUUSD"
    assert result.market_bias in {"bullish", "bearish", "neutral"}
    assert result.market_structure in {"uptrend", "downtrend", "range"}
    assert result.volatility_state in {"low", "moderate", "elevated"}
    assert result.source_metadata.get("rule_source") == "synthetic_test_contract"
    assert result.source_metadata.get("synthetic_observation_rule") is True


def test_trading_vertical_slice_stale_timestamp_uses_injected_evaluation_time():
    specialist = MarketAnalysisSpecialist()
    stale_payload = _xauusd_payload(timestamp="2026-08-16T09:50:00Z")
    result = specialist.observe_market(
        stale_payload,
        evaluation_time=datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc),
        max_age_seconds=60,
    )

    assert result.metadata.get("validation_errors")
    assert any("stale" in item.lower() for item in result.metadata["validation_errors"])


def test_trading_vertical_slice_unsupported_symbol_is_rejected():
    specialist = MarketAnalysisSpecialist()
    payload = _xauusd_payload(symbol="EURUSD")
    result = specialist.observe_market(
        payload,
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )

    assert result.metadata.get("status") == "rejected"
    assert result.metadata.get("rejection_reason")


def test_trading_vertical_slice_wrong_specialist_binding_is_rejected():
    specialist = MarketAnalysisSpecialist()
    result = specialist.validate_binding(
        division_name="trading",
        specialist_name="risk_specialist",
        capability_name="market_observation",
        permission_scope="read_only",
    )
    assert result is False


def test_trading_vertical_slice_wrong_capability_binding_is_rejected():
    specialist = MarketAnalysisSpecialist()
    result = specialist.validate_binding(
        division_name="trading",
        specialist_name="market_analyst",
        capability_name="risk_review",
        permission_scope="read_only",
    )
    assert result is False


def test_trading_vertical_slice_permission_mismatch_is_rejected():
    specialist = MarketAnalysisSpecialist()
    result = specialist.validate_binding(
        division_name="trading",
        specialist_name="market_analyst",
        capability_name="market_observation",
        permission_scope="write",
    )
    assert result is False


def test_trading_vertical_slice_missing_required_field_produces_validation_failure():
    validator = MarketObservationValidator()
    payload = _xauusd_payload()
    del payload["current_price"]
    errors = validator.validate_input(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert any("current_price" in item for item in errors)


def test_trading_vertical_slice_non_numeric_price_produces_validation_failure():
    validator = MarketObservationValidator()
    payload = _xauusd_payload(current_price="not-a-number")
    errors = validator.validate_input(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert any("numeric" in item.lower() or "current_price" in item.lower() for item in errors)


def test_trading_vertical_slice_invalid_timeframe_produces_validation_failure():
    validator = MarketObservationValidator()
    payload = _xauusd_payload(timeframe="MN1")
    errors = validator.validate_input(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert any("timeframe" in item.lower() for item in errors)


def test_trading_vertical_slice_inconsistent_ohlc_produces_validation_failure():
    validator = MarketObservationValidator()
    payload = _xauusd_payload(high=100.0, low=200.0)
    errors = validator.validate_input(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert any("high" in item.lower() or "low" in item.lower() or "ohlc" in item.lower() for item in errors)


def test_trading_vertical_slice_bullish_synthetic_input_produces_bullish_observation():
    payload = _xauusd_payload(
        current_price=2400.00,
        open=2380.00,
        high=2405.00,
        low=2378.00,
        close=2398.00,
        recent_high=2410.00,
        recent_low=2365.00,
    )
    specialist = MarketAnalysisSpecialist()
    result = specialist.observe_market(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.market_bias == "bullish"


def test_trading_vertical_slice_bearish_synthetic_input_produces_bearish_observation():
    payload = _xauusd_payload(
        current_price=2310.00,
        open=2340.00,
        high=2348.00,
        low=2305.00,
        close=2315.00,
        recent_high=2360.00,
        recent_low=2290.00,
    )
    specialist = MarketAnalysisSpecialist()
    result = specialist.observe_market(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.market_bias == "bearish"


def test_trading_vertical_slice_neutral_synthetic_input_produces_neutral_observation():
    payload = _xauusd_payload(
        current_price=2340.00,
        open=2341.00,
        high=2348.00,
        low=2334.00,
        close=2340.50,
        recent_high=2350.00,
        recent_low=2325.00,
    )
    specialist = MarketAnalysisSpecialist()
    result = specialist.observe_market(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert result.market_bias == "neutral"


def test_trading_vertical_slice_observation_rules_are_deterministic():
    payload = _xauusd_payload(
        current_price=2400.00,
        open=2380.00,
        high=2405.00,
        low=2378.00,
        close=2398.00,
        recent_high=2410.00,
        recent_low=2365.00,
    )
    specialist = MarketAnalysisSpecialist()
    first = specialist.observe_market(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    second = specialist.observe_market(payload, evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc), max_age_seconds=300)
    assert first.market_bias == second.market_bias
    assert first.market_structure == second.market_structure
    assert first.volatility_state == second.volatility_state


def test_trading_vertical_slice_output_schema_rejects_invalid_output():
    capability = TradingMarketObservationCapability()
    invalid = {"symbol": "XAUUSD", "entry": 2345.0, "side": "buy"}
    errors = capability.validate_output(invalid)
    assert errors
    assert any("entry" in item.lower() for item in errors) or any("advisory" in item.lower() for item in errors)


def test_trading_vertical_slice_output_contains_no_advisory_fields():
    specialist = MarketAnalysisSpecialist()
    result = specialist.observe_market(
        _xauusd_payload(),
        evaluation_time=datetime(2026, 8, 16, 10, 1, 0, tzinfo=timezone.utc),
        max_age_seconds=300,
    )
    payload = result.to_dict()
    assert "entry" not in payload
    assert "stop_loss" not in payload
    assert "take_profit" not in payload
    assert "buy" not in str(payload).lower()
    assert "sell" not in str(payload).lower()


def test_trading_vertical_slice_specialist_cannot_mutate_task_lifecycle():
    specialist = MarketAnalysisSpecialist()
    assert specialist.can_mutate_task_lifecycle() is False


def test_trading_vertical_slice_mission_control_remains_final_completion_authority():
    specialist = MarketAnalysisSpecialist()
    assert specialist.is_final_authority() is False


def test_trading_vertical_slice_has_no_broker_or_external_live_integration():
    specialist = MarketAnalysisSpecialist()
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False


def test_trading_vertical_slice_market_observation_input_model():
    input_model = MarketObservationInput.from_payload(_xauusd_payload())
    assert input_model.symbol == "XAUUSD"
    assert input_model.timeframe == "M5"
    assert input_model.current_price > 0
    assert input_model.recent_high >= input_model.high
    assert input_model.recent_low <= input_model.low


def test_trading_vertical_slice_market_observation_result_model():
    result = MarketObservationResult(
        symbol="XAUUSD",
        timestamp="2026-08-16T10:00:00Z",
        timeframe="M5",
        market_bias="bullish",
        market_structure="uptrend",
        current_price=2341.10,
        recent_high=2345.50,
        recent_low=2335.20,
        volatility_state="moderate",
        session_context={"session": "london"},
        observed_levels={"current": 2341.10, "recent_high": 2345.50, "recent_low": 2335.20},
        observation_summary="Synthetic observation for architecture validation only.",
        evidence_score=0.82,
        source_metadata={"rule_source": "synthetic_test_contract"},
    )
    payload = result.to_dict()
    assert payload["market_bias"] == "bullish"
    assert payload["market_structure"] == "uptrend"
    assert payload["evidence_score"] == 0.82
    assert "entry" not in payload
