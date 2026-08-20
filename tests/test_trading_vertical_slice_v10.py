from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from ced_one.business_divisions.trading.capabilities import ORDER_BLOCK_INTELLIGENCE
from ced_one.business_divisions.trading.order_block_intelligence import (
    OrderBlockIntelligenceAnalyzer,
    OrderBlockIntelligenceSpecialist,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control.types import MissionRequest


def candle(index: int, *, open_price: float, high: float, low: float, close: float):
    return {
        "timestamp": (datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(hours=index)).isoformat().replace("+00:00", "Z"),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def history():
    quiet = [candle(index, open_price=100, high=101, low=99, close=100) for index in range(20)]
    quiet.append(candle(20, open_price=101, high=103, low=99, close=100))
    quiet.append(candle(21, open_price=100, high=106, low=99, close=105))
    return quiet


def payload(candles, *, config=None):
    result = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "evaluation_time": "2026-08-17T10:00:00Z",
        "candle_history": candles,
    }
    if config is not None:
        result["config"] = config
    return result


def analyze(candles=None, *, config=None):
    return OrderBlockIntelligenceAnalyzer().analyze(payload(candles or history(), config=config))


def test_v10_capability_specialist_and_safety_boundary():
    assert ORDER_BLOCK_INTELLIGENCE.name == "order_block_intelligence"
    assert ORDER_BLOCK_INTELLIGENCE.contract == "trading.order_block_intelligence.v1"
    assert ORDER_BLOCK_INTELLIGENCE.permission_scope == "read_only"
    specialist = OrderBlockIntelligenceSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="order_block_analyst",
        capability_name="order_block_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False
    text = str(analyze().to_dict()).lower()
    for forbidden in ["buy", "sell", "entry", "exit", "signal", "setup", "confidence", "recommendation", "mitigated", "invalidated", "execution_command"]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None


def test_v10_bullish_event_sources_nearest_preceding_bearish_candle():
    result = analyze()
    assert len(result.order_blocks) == 1
    block = result.order_blocks[0]
    assert block["direction"] == "bullish"
    assert block["source_timestamp"] == "2026-08-16T20:00:00Z"
    assert block["confirmed_at"] == "2026-08-16T21:00:00Z"
    assert block["created_at"] == block["confirmed_at"]
    assert block["source_displacement_event_id"] == "bullish_displacement_1"
    assert block["source_open"] == 101.0
    assert block["source_high"] == 103.0
    assert block["source_low"] == 99.0
    assert block["source_close"] == 100.0
    assert block["body_low"] == 100.0
    assert block["body_high"] == 101.0
    assert block["range_low"] == 99.0
    assert block["range_high"] == 103.0
    assert block["source_timestamp"] < block["confirmed_at"]


def test_v10_bearish_event_sources_nearest_preceding_bullish_candle():
    candles = [candle(index, open_price=100, high=101, low=99, close=100) for index in range(20)]
    candles.append(candle(20, open_price=99, high=103, low=98, close=102))
    candles.append(candle(21, open_price=102, high=103, low=96, close=97))
    result = analyze(candles)
    block = result.order_blocks[0]
    assert block["direction"] == "bearish"
    assert block["source_timestamp"] == "2026-08-16T20:00:00Z"
    assert block["source_displacement_event_id"] == "bearish_displacement_1"


def test_v10_neutral_candles_are_skipped_and_origin_search_is_bounded():
    candles = [candle(index, open_price=100, high=101, low=99, close=100) for index in range(20)]
    candles.extend([
        candle(20, open_price=100, high=101, low=99, close=100),
        candle(21, open_price=100, high=101, low=99, close=100),
        candle(22, open_price=100, high=106, low=99, close=105),
    ])
    result = analyze(candles, config={"origin_search_lookback": 2})
    assert result.order_blocks == []
    assert result.diagnostics["origin_search_count"] == 1
    assert result.diagnostics["origin_not_found_count"] == 1
    search = result.evidence["origin_searches"][0]
    assert search["displacement_source_index"] == 22
    assert search["origin_search_start_index"] == 21
    assert search["inspected_candle_count"] == 2


def test_v10_origin_search_can_cross_displacement_candidate_boundary():
    candles = [candle(index, open_price=100, high=101, low=99, close=100) for index in range(20)]
    candles.extend([
        candle(20, open_price=101, high=103, low=99, close=100),
        candle(21, open_price=100, high=106, low=99, close=105),
    ])
    result = analyze(candles, config={"lookback_candles": 1})
    assert len(result.order_blocks) == 1
    assert result.evidence["origin_searches"][0]["crossed_source_candidate_boundary"] is True


def test_v10_interaction_precedence_and_state_progression():
    candles = history() + [
        candle(22, open_price=99.5, high=100.5, low=98, close=99.5),
        candle(23, open_price=99.5, high=101, low=99, close=100.5),
        candle(24, open_price=100, high=102, low=99.5, close=101),
        candle(25, open_price=98, high=100, low=97, close=98),
    ]
    result = analyze(candles)
    block = result.order_blocks[0]
    assert [item["event_type"] for item in block["interactions"]] == [
        "order_block_wick_touch",
        "order_block_body_revisit",
        "order_block_body_revisit",
        "order_block_close_through",
    ]
    assert block["current_state"] == "closed_through"
    assert block["interactions"][0]["prior_state"] == "unvisited"
    assert block["interactions"][-1]["resulting_state"] == "closed_through"


def test_v10_exact_body_equality_is_body_revisit_not_wick_touch():
    candles = history() + [
        candle(22, open_price=99, high=100.5, low=98.5, close=100),
        candle(23, open_price=99.5, high=100.5, low=98.5, close=100),
    ]
    result = analyze(candles)
    assert result.order_blocks[0]["interactions"][0]["event_type"] == "order_block_body_revisit"
    assert result.order_blocks[0]["interactions"][1]["event_type"] == "order_block_body_revisit"


def test_v10_close_through_is_strict_at_range_boundary():
    equality = analyze(history() + [candle(22, open_price=98, high=100, low=97, close=99)])
    assert equality.order_blocks[0]["interactions"][0]["event_type"] != "order_block_close_through"
    strict = analyze(history() + [candle(22, open_price=98, high=100, low=96, close=98)])
    assert strict.order_blocks[0]["interactions"][0]["event_type"] == "order_block_close_through"


def test_v10_displacement_confirmation_candle_cannot_revisit_own_block():
    result = analyze()
    block = result.order_blocks[0]
    assert all(item["candle_timestamp"] != "2026-08-16T21:00:00Z" for item in block["interactions"])


def test_v10_duplicate_candidates_preserve_contributing_ids_and_are_deterministic():
    candles = history() + [candle(22, open_price=100, high=106, low=99, close=105)]
    result = analyze(candles)
    assert len(result.order_blocks) == 1
    block = result.order_blocks[0]
    assert block["evidence"]["contributing_displacement_event_ids"] == ["bullish_displacement_1", "bullish_displacement_2"]
    assert result.diagnostics["duplicate_candidate_count"] == 1
    assert result.to_dict() == analyze(candles).to_dict()


def test_v10_state_is_calculated_before_interaction_retention():
    candles = history() + [
        candle(22, open_price=98.5, high=100.5, low=98, close=98.5),
        candle(23, open_price=99.5, high=101, low=99, close=100.5),
        candle(24, open_price=98, high=100, low=97, close=98),
    ]
    result = analyze(candles, config={"maximum_interactions_per_block": 1})
    block = result.order_blocks[0]
    assert block["current_state"] == "closed_through"
    assert len(block["interactions"]) == 1
    assert result.diagnostics["pre_retention_interaction_count"] == 3
    assert result.diagnostics["truncated_interaction_count"] == 2
    assert result.diagnostics["blocks_with_earliest_interaction_omitted"] == 1


def test_v10_integer_validation_rejects_non_integer_and_boolean_values():
    fields = ["lookback_candles", "origin_search_lookback", "maximum_order_blocks", "maximum_interactions_per_block"]
    for field_name in fields:
        with pytest.raises(ValueError, match=field_name):
            analyze(config={field_name: 1.5})
        with pytest.raises(ValueError, match=field_name):
            analyze(config={field_name: True})


def test_v10_configuration_bounds_and_nested_lookback_rejection():
    for field_name, value in [
        ("lookback_candles", 0),
        ("origin_search_lookback", 0),
        ("origin_search_lookback", 11),
        ("maximum_order_blocks", 0),
        ("maximum_order_blocks", 1001),
        ("maximum_interactions_per_block", 0),
        ("maximum_interactions_per_block", 1001),
    ]:
        with pytest.raises(ValueError, match=field_name):
            analyze(config={field_name: value})
    with pytest.raises(ValueError, match="lookback_candles"):
        analyze(config={"displacement_config": {"lookback_candles": 2}})
    result = analyze(config={"lookback_candles": 1, "displacement_config": {"baseline_window": 20}})
    assert result.evidence["requested_source_lookback_candles"] == 1
    assert result.evidence["effective_source_lookback_candles"] == 1


def test_v10_resolver_precedence_and_generic_displacement_routing():
    resolver = TradingDivisionResolver()
    for goal in ["order block", "orderblock intelligence", "displacement origin", "order block after displacement"]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == "order_block_intelligence"
        assert resolver.resolve_specialist(request)["name"] == "order_block_analyst"
    request = MissionRequest(user_goal="analyze displacement", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(request)["name"] == "displacement_intelligence"
    assert resolver.resolve_specialist(request)["name"] == "displacement_analyst"


def test_v10_retention_order_is_deterministic():
    candles = history() + [candle(22, open_price=98.5, high=100.5, low=98, close=98.5)]
    first = analyze(candles, config={"maximum_order_blocks": 1})
    second = analyze(candles, config={"maximum_order_blocks": 1})
    assert first.to_dict() == second.to_dict()
    assert first.order_blocks == sorted(first.order_blocks, key=lambda item: (item["created_at"], item["source_timestamp"], item["direction"], item["order_block_id"]))
