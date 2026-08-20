from __future__ import annotations

import re

import pytest

from ced_one.business_divisions.trading.capabilities import LIQUIDITY_EVENTS
from ced_one.business_divisions.trading.liquidity_events import (
    LiquidityEventsAnalyzer,
    LiquidityEventsConfig,
    LiquidityEventsSpecialist,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control.types import MissionRequest


def candle(timestamp: str, *, open_price: float, high: float, low: float, close: float):
    return {"timestamp": timestamp, "open": open_price, "high": high, "low": low, "close": close}


def payload(candles, *, config=None):
    result = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "evaluation_time": "2026-08-16T10:00:00Z",
        "candle_history": candles,
    }
    if config is not None:
        result["config"] = config
    return result


def high_history():
    return [
        candle("2026-08-16T00:00:00Z", open_price=100, high=104, low=98, close=102),
        candle("2026-08-16T01:00:00Z", open_price=102, high=110, low=99, close=108),
        candle("2026-08-16T02:00:00Z", open_price=108, high=109, low=100, close=104),
        candle("2026-08-16T03:00:00Z", open_price=104, high=110, low=101, close=105),
        candle("2026-08-16T04:00:00Z", open_price=105, high=112, low=102, close=109),
        candle("2026-08-16T05:00:00Z", open_price=109, high=112, low=104, close=111),
    ]


def low_history():
    return [
        candle("2026-08-16T00:00:00Z", open_price=110, high=113, low=104, close=111),
        candle("2026-08-16T01:00:00Z", open_price=111, high=112, low=100, close=102),
        candle("2026-08-16T02:00:00Z", open_price=102, high=114, low=101, close=110),
        candle("2026-08-16T03:00:00Z", open_price=110, high=112, low=99.9, close=108),
        candle("2026-08-16T04:00:00Z", open_price=108, high=111, low=98.5, close=100.1),
        candle("2026-08-16T05:00:00Z", open_price=100.1, high=106, low=98.5, close=98.5),
    ]


def events_for(result, level_type):
    return [event for event in result.liquidity_events if event["level_type"] == level_type]


def test_v9_capability_and_specialist_are_read_only_and_non_authoritative():
    assert LIQUIDITY_EVENTS.name == "liquidity_events"
    assert LIQUIDITY_EVENTS.contract == "trading.liquidity_events.v1"
    assert LIQUIDITY_EVENTS.permission_scope == "read_only"
    specialist = LiquidityEventsSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="liquidity_events_analyst",
        capability_name="liquidity_events",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False


def test_v9_maps_touch_sweep_and_close_beyond_from_slice6():
    result = LiquidityEventsAnalyzer().analyze(payload(high_history()))
    events = events_for(result, "confirmed_swing_high_level")
    assert [event["event_type"] for event in events] == [
        "liquidity_touch",
        "liquidity_sweep",
        "liquidity_close_beyond",
    ]
    assert [event["source_interaction_type"] for event in events] == ["touched", "breached", "closed_beyond"]
    assert events[1]["source_wick_breach_without_close"] is True
    assert events[2]["closed_beyond_boundary"] is True
    assert events[1]["observed_open"] == 105.0
    assert events[1]["lower_boundary"] == 110.0
    assert events[1]["upper_boundary"] == 110.0


def test_v9_low_side_sweep_and_close_beyond_are_symmetric():
    result = LiquidityEventsAnalyzer().analyze(payload(low_history(), config={"liquidity_config": {"interaction_tolerance": 0.2}}))
    events = events_for(result, "confirmed_swing_low_level")
    assert [event["event_type"] for event in events] == [
        "liquidity_touch",
        "liquidity_sweep",
        "liquidity_close_beyond",
    ]
    assert events[1]["boundary_excursion"] == pytest.approx(1.3)
    assert events[2]["boundary_excursion"] == pytest.approx(1.3)


def test_v9_cluster_uses_slice6_outer_applied_boundary():
    candles = [
        candle("2026-08-16T00:00:00Z", open_price=100, high=105, low=99, close=103),
        candle("2026-08-16T01:00:00Z", open_price=103, high=110, low=98, close=106),
        candle("2026-08-16T02:00:00Z", open_price=103, high=104, low=97, close=102),
        candle("2026-08-16T03:00:00Z", open_price=102, high=110.4, low=96, close=109),
        candle("2026-08-16T04:00:00Z", open_price=103, high=104, low=95, close=100),
        candle("2026-08-16T05:00:00Z", open_price=100, high=110.2, low=94, close=108),
        candle("2026-08-16T06:00:00Z", open_price=101, high=103, low=93, close=99),
        candle("2026-08-16T07:00:00Z", open_price=99, high=111, low=98, close=109),
    ]
    result = LiquidityEventsAnalyzer().analyze(payload(candles, config={"liquidity_config": {"interaction_tolerance": 0.1}}))
    sweep = [event for event in result.liquidity_events if event["source_interaction_type"] == "breached"][0]
    assert sweep["level_type"] == "equal_high_cluster"
    assert sweep["upper_boundary"] == 110.5
    assert sweep["boundary_excursion"] == 0.5


def test_v9_causality_excludes_confirming_candle_and_preserves_repeated_history():
    candles = [
        candle("2026-08-16T00:00:00Z", open_price=100, high=104, low=98, close=102),
        candle("2026-08-16T01:00:00Z", open_price=102, high=110, low=99, close=108),
        candle("2026-08-16T02:00:00Z", open_price=108, high=109, low=100, close=104),
        candle("2026-08-16T03:00:00Z", open_price=104, high=110, low=101, close=105),
        candle("2026-08-16T04:00:00Z", open_price=105, high=112, low=102, close=109),
        candle("2026-08-16T05:00:00Z", open_price=109, high=110, low=104, close=105),
        candle("2026-08-16T06:00:00Z", open_price=105, high=112, low=104, close=111),
    ]
    result = LiquidityEventsAnalyzer().analyze(payload(candles))
    events = [
        item
        for item in events_for(result, "confirmed_swing_high_level")
        if item["level_id"] == "high_confirmed_swing_high_level_1"
    ]
    assert [item["event_timestamp"] for item in events] == [
        "2026-08-16T03:00:00Z",
        "2026-08-16T04:00:00Z",
        "2026-08-16T05:00:00Z",
        "2026-08-16T06:00:00Z",
    ]
    assert events[0]["event_timestamp"] > events[0]["level_created_at"]
    assert events[0]["event_type"] == "liquidity_touch"
    assert events[1]["event_type"] == "liquidity_sweep"
    assert events[2]["event_type"] == "liquidity_touch"


def test_v9_state_is_calculated_before_touch_exclusion_and_retention():
    result = LiquidityEventsAnalyzer().analyze(
        payload(high_history(), config={"maximum_events": 1, "include_touch_events": False})
    )
    assert result.diagnostics["candidate_interaction_count"] == 3
    assert result.diagnostics["excluded_touch_count"] == 1
    assert result.diagnostics["pre_truncation_event_count"] == 2
    assert result.diagnostics["emitted_event_count"] == 1
    assert result.diagnostics["truncated_event_count"] == 1
    assert result.level_event_states[next(iter(result.level_event_states))] == "closed_beyond"
    assert result.summary["total_event_count"] == 1


def test_v9_diagnostics_accounting_and_chronological_retention():
    result = LiquidityEventsAnalyzer().analyze(payload(high_history(), config={"maximum_events": 2}))
    diagnostics = result.diagnostics
    assert diagnostics["touch_candidate_count"] + diagnostics["sweep_candidate_count"] + diagnostics["close_beyond_candidate_count"] == diagnostics["candidate_interaction_count"]
    assert diagnostics["pre_truncation_event_count"] == diagnostics["candidate_interaction_count"]
    assert diagnostics["truncated_event_count"] == diagnostics["pre_truncation_event_count"] - diagnostics["emitted_event_count"]
    assert [event["event_timestamp"] for event in result.liquidity_events] == sorted(event["event_timestamp"] for event in result.liquidity_events)


def test_v9_configuration_composition_and_nested_lookback_rejection():
    result = LiquidityEventsAnalyzer().analyze(
        payload(high_history(), config={
            "lookback_candles": 6,
            "liquidity_config": {"equal_level_tolerance": 0.75, "interaction_tolerance": 0.2},
        })
    )
    assert result.evidence["requested_source_lookback_candles"] == 6
    assert result.evidence["effective_source_lookback_candles"] == 6
    assert result.evidence["effective_liquidity_config"]["equal_level_tolerance"] == 0.75
    with pytest.raises(ValueError, match="lookback_candles"):
        LiquidityEventsAnalyzer().analyze(payload(high_history(), config={"liquidity_config": {"lookback_candles": 4}}))


def test_v9_event_ids_are_snapshot_deterministic_and_source_level_ids_are_copied():
    first = LiquidityEventsAnalyzer().analyze(payload(high_history()))
    second = LiquidityEventsAnalyzer().analyze(payload(high_history()))
    assert first.to_dict() == second.to_dict()
    assert all(event["level_id"].startswith("high_confirmed_swing_high_level_") for event in first.liquidity_events)
    assert first.evidence["identity_scope"] == "snapshot_deterministic"
    assert first.metadata["identity_scope"] == "snapshot_deterministic"


def test_v9_fail_closed_source_validation():
    analyzer = LiquidityEventsAnalyzer()
    with pytest.raises(ValueError, match="wick_breach_without_close"):
        analyzer._map_interaction(
            {"level_id": "high_test", "side": "high", "level_type": "confirmed_swing_high_level", "source_timestamp": "t0", "created_at": "t1", "representative_price": 100},
            {"event_type": "breached", "wick_breach_without_close": False, "candle_timestamp": "t2", "observed_high": 101, "observed_low": 99, "observed_close": 100, "applied_boundary": {"lower_boundary": 100, "upper_boundary": 100}},
            {"t2": {"open": 100, "high": 101, "low": 99, "close": 100}},
        )
    with pytest.raises(ValueError, match="unknown event_type"):
        analyzer._map_interaction(
            {"level_id": "high_test", "side": "high", "level_type": "confirmed_swing_high_level", "source_timestamp": "t0", "created_at": "t1", "representative_price": 100},
            {"event_type": "unknown", "wick_breach_without_close": False, "candle_timestamp": "t2", "observed_high": 101, "observed_low": 99, "observed_close": 100, "applied_boundary": {"lower_boundary": 100, "upper_boundary": 100}},
            {"t2": {"open": 100, "high": 101, "low": 99, "close": 100}},
        )


def test_v9_resolver_specific_terms_precede_generic_liquidity():
    resolver = TradingDivisionResolver()
    for goal, expected in [
        ("analyze liquidity", "liquidity_intelligence"),
        ("map liquidity", "liquidity_intelligence"),
        ("analyze liquidity sweep", "liquidity_events"),
        ("analyze liquidity events", "liquidity_events"),
        ("find sweeps", "liquidity_events"),
        ("analyze close beyond liquidity", "liquidity_events"),
    ]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == expected
        assert resolver.resolve_specialist(request)["name"] == ("liquidity_events_analyst" if expected == "liquidity_events" else "liquidity_analyst")


def test_v9_safety_boundary_contains_no_advisory_or_execution_terms():
    result = LiquidityEventsAnalyzer().analyze(payload(high_history()))
    text = str(result.to_dict()).lower()
    for forbidden in ["buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "target", "signal", "confidence", "recommendation", "stop_hunt", "manipulation", "execution_command"]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None
