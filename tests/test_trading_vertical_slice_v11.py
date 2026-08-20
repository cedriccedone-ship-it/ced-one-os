from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from ced_one.business_divisions.trading.capabilities import STRUCTURAL_DEALING_RANGE_INTELLIGENCE
from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.structural_dealing_range_intelligence import (
    StructuralDealingRangeAnalyzer,
    StructuralDealingRangeIntelligenceSpecialist,
)
from ced_one.mission_control.types import MissionRequest


def candle(index: int, *, high: float, low: float, open_price: float | None = None, close: float | None = None):
    open_value = high - 1 if open_price is None else open_price
    close_value = open_value if close is None else close
    return {
        "timestamp": (datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(hours=index)).isoformat().replace("+00:00", "Z"),
        "open": open_value,
        "high": high,
        "low": low,
        "close": close_value,
    }


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


def pivot_history():
    return [
        candle(0, high=105, low=100),
        candle(1, high=110, low=99),
        candle(2, high=104, low=95),
        candle(3, high=108, low=97),
        candle(4, high=112, low=96),
        candle(5, high=107, low=94),
        candle(6, high=111, low=98),
        candle(7, high=109, low=97),
        candle(8, high=108, low=98),
    ]


def analyze(candles=None, *, config=None):
    return StructuralDealingRangeAnalyzer().analyze(payload(candles or pivot_history(), config=config))


def test_v11_capability_and_specialist_boundary():
    assert STRUCTURAL_DEALING_RANGE_INTELLIGENCE.name == "structural_dealing_range_intelligence"
    assert STRUCTURAL_DEALING_RANGE_INTELLIGENCE.contract == "trading.structural_dealing_range_intelligence.v1"
    assert STRUCTURAL_DEALING_RANGE_INTELLIGENCE.permission_scope == "read_only"
    specialist = StructuralDealingRangeIntelligenceSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="structural_dealing_range_analyst",
        capability_name="structural_dealing_range_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False


def test_v11_reuses_slice3_swing_evidence_and_causal_counts():
    candles = pivot_history()
    source = MarketStructureAnalyzer().analyze(payload(candles))
    result = analyze(candles)
    assert result.diagnostics["source_swing_high_count"] == len(source.evidence["swing_highs"])
    assert result.diagnostics["source_swing_low_count"] == len(source.evidence["swing_lows"])
    assert result.diagnostics["source_pivot_count"] == result.diagnostics["confirmed_pivot_count"] + result.diagnostics["terminal_unconfirmed_pivot_count"]
    assert result.diagnostics["confirmed_pivot_count"] == result.diagnostics["confirmed_high_pivot_count"] + result.diagnostics["confirmed_low_pivot_count"]
    assert all(item["identity_scope"] == "snapshot_deterministic" for item in result.evidence["confirmed_pivots"])


def test_v11_terminal_pivot_is_excluded_without_fabricated_confirmation():
    candles = pivot_history()[:-1]
    source = MarketStructureAnalyzer().analyze(payload(candles))
    result = analyze(candles)
    terminal_indices = {item["index"] for item in source.evidence["swing_highs"] + source.evidence["swing_lows"] if item["index"] + 1 >= len(candles)}
    assert terminal_indices
    assert result.diagnostics["terminal_unconfirmed_pivot_count"] == len(terminal_indices)
    assert all(item["confirmed_index"] < len(candles) for item in result.evidence["confirmed_pivots"])
    assert "evaluation_time" not in str(result.evidence["confirmed_pivots"])


def test_v11_confirmed_pivots_use_index_plus_one_and_local_reference_fields():
    result = analyze()
    pivot = result.evidence["confirmed_pivots"][0]
    assert pivot["confirmed_index"] == pivot["source_index"] + 1
    assert pivot["confirmed_at"] == pivot["source_timestamp"].replace("00:00:00Z", "01:00:00Z") or pivot["confirmed_at"]
    assert set(pivot) >= {
        "pivot_reference_id", "pivot_type", "source_index", "source_timestamp", "price",
        "confirmed_index", "confirmed_at", "source_structure_rule_version", "identity_scope",
    }


def test_v11_low_to_high_and_high_to_low_ranges_are_adjacent_and_geometric():
    result = analyze()
    orders = [item["chronological_order"] for item in result.structural_ranges]
    assert "low_to_high" in orders
    assert "high_to_low" in orders
    assert all(item["range_high"] > item["range_low"] for item in result.structural_ranges)
    assert all(item["range_width"] == item["range_high"] - item["range_low"] for item in result.structural_ranges)
    assert all(item["created_at"] == item["confirmed_at"] for item in result.structural_ranges)


def test_v11_same_type_runs_collapse_to_extreme_real_pivot():
    candles = [
        candle(0, high=105, low=98),
        candle(1, high=110, low=99),
        candle(2, high=108, low=100),
        candle(3, high=112, low=98),
        candle(4, high=107, low=95),
        candle(5, high=109, low=96),
        candle(6, high=108, low=97),
    ]
    result = analyze(candles)
    assert result.diagnostics["same_type_run_count"] >= 1
    assert result.diagnostics["collapsed_pivot_count"] <= result.diagnostics["confirmed_pivot_count"]
    assert all(item["first_pivot_source_timestamp"] != item["second_pivot_source_timestamp"] or item["first_pivot_type"] != item["second_pivot_type"] for item in result.structural_ranges)


def test_v11_incomplete_final_leg_does_not_fabricate_range_or_replace_current():
    result = analyze(pivot_history() + [candle(9, high=115, low=100)])
    assert result.current_range is not None
    assert result.current_range in result.structural_ranges or result.current_range["range_id"] not in {item["range_id"] for item in result.structural_ranges}
    assert all(item["first_pivot_type"] != item["second_pivot_type"] for item in result.structural_ranges)


def test_v11_current_range_is_selected_before_retention():
    full = analyze(config={"maximum_ranges": 1000})
    limited = analyze(config={"maximum_ranges": 1})
    assert full.current_range is not None
    assert limited.current_range == full.current_range
    assert len(limited.structural_ranges) == 1
    assert limited.diagnostics["truncated_range_count"] == limited.diagnostics["pre_retention_range_count"] - 1


def test_v11_range_ids_and_order_are_deterministic():
    first = analyze()
    second = analyze()
    assert first.to_dict() == second.to_dict()
    assert [item["range_id"] for item in first.structural_ranges] == [item["range_id"] for item in second.structural_ranges]
    assert first.evidence["identity_scope"] == "snapshot_deterministic"
    assert [item["created_at"] for item in first.structural_ranges] == sorted(item["created_at"] for item in first.structural_ranges)


def test_v11_zero_width_pairs_are_omitted_and_diagnosed():
    candles = [
        candle(0, high=105, low=100),
        candle(1, high=110, low=99),
        candle(2, high=104, low=95),
        candle(3, high=108, low=97),
        candle(4, high=110, low=96),
        candle(5, high=107, low=94),
        candle(6, high=109, low=98),
    ]
    result = analyze(candles)
    assert result.diagnostics["zero_width_range_count"] >= 0
    assert all(item["range_width"] > 0 for item in result.structural_ranges)


def test_v11_configuration_is_integer_only_bounded_and_has_no_structure_pass_through():
    for value in [1.5, True, False, "50"]:
        with pytest.raises(ValueError, match="maximum_ranges"):
            analyze(config={"maximum_ranges": value})
    for value in [0, 1001]:
        with pytest.raises(ValueError, match="maximum_ranges"):
            analyze(config={"maximum_ranges": value})
    with pytest.raises(ValueError, match="unknown fields"):
        analyze(config={"structure_config": {}})


def test_v11_evidence_excludes_later_zone_and_directional_semantics():
    result = analyze()
    evidence_text = str(result.evidence).lower()
    assert "structure_state" in evidence_text
    assert "hh/hl/lh/ll" in evidence_text
    assert "premium" not in result.to_dict()
    assert "discount" not in result.to_dict()
    assert "equilibrium" not in result.to_dict()
    assert "range_position" not in result.to_dict()


def test_v11_resolver_precedence_preserves_generic_range_and_structure_routing():
    resolver = TradingDivisionResolver()
    for goal in ["structural dealing range", "dealing range structure", "structural range", "market structure range"]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == "structural_dealing_range_intelligence"
        assert resolver.resolve_specialist(request)["name"] == "structural_dealing_range_analyst"
    generic_range = MissionRequest(user_goal="analyze range", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(generic_range)["name"] == "volatility_range"
    generic_structure = MissionRequest(user_goal="analyze market structure", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(generic_structure)["name"] == "market_observation"


def test_v11_no_advisory_or_premium_discount_output():
    result = analyze()
    text = str(result.to_dict()).lower()
    for forbidden in ["buy", "sell", "entry", "exit", "signal", "setup", "probability", "confidence", "recommendation", "premium", "discount", "equilibrium", "execution_command"]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None
