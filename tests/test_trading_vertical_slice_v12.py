from __future__ import annotations

import re

import pytest

from ced_one.business_divisions.trading.capabilities import PREMIUM_DISCOUNT_INTELLIGENCE
from ced_one.business_divisions.trading.division import TradingDivision
from ced_one.business_divisions.trading.premium_discount_intelligence import (
    PremiumDiscountAnalyzer,
    PremiumDiscountIntelligenceSpecialist,
    PremiumDiscountResult,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.specialists import PREMIUM_DISCOUNT_ANALYST
from ced_one.business_divisions.trading.structural_dealing_range_intelligence import (
    StructuralDealingRangeResult,
)
from ced_one.mission_control.types import MissionRequest


TIMESTAMP = "2026-08-16T08:00:00Z"


def current_range(**overrides):
    result = {
        "range_id": "range_authoritative_1",
        "range_low": 100.0,
        "range_high": 120.0,
        "range_width": 20.0,
        "chronological_order": "low_to_high",
        "first_pivot_type": "low",
        "first_pivot_source_index": 1,
        "first_pivot_source_timestamp": "2026-08-16T01:00:00Z",
        "first_pivot_confirmed_at": "2026-08-16T02:00:00Z",
        "first_pivot_price": 100.0,
        "second_pivot_type": "high",
        "second_pivot_source_index": 5,
        "second_pivot_source_timestamp": "2026-08-16T05:00:00Z",
        "second_pivot_confirmed_at": "2026-08-16T06:00:00Z",
        "second_pivot_price": 120.0,
        "confirmed_at": "2026-08-16T06:00:00Z",
        "created_at": "2026-08-16T06:00:00Z",
        "source_structure_rule_version": "market_structure_v1",
        "identity_scope": "snapshot_deterministic",
        "evidence": {
            "first_pivot_reference_id": "pivot_low_1",
            "second_pivot_reference_id": "pivot_high_1",
            "pairing_rule": "adjacent_opposite_pivot_pair_after_same_type_run_collapse",
        },
    }
    result.update(overrides)
    return result


def source_result(*, range_record=None, timestamp=TIMESTAMP, structural_ranges=None):
    return StructuralDealingRangeResult(
        symbol="XAUUSD",
        timeframe="H1",
        evaluation_time="2026-08-16T09:00:00Z",
        timestamp=timestamp,
        scanned_candle_count=8,
        structural_ranges=[] if structural_ranges is None else structural_ranges,
        current_range=range_record,
        summary={"total_returned_range_count": 0 if range_record is None else 1, "current_range_id": 0 if range_record is None else 1},
        diagnostics={},
        evidence={
            "structural_range_rule_version": "structural_dealing_range_intelligence_v1",
            "identity_scope": "snapshot_deterministic",
        },
        metadata={"identity_scope": "snapshot_deterministic"},
    )


def payload(price, *, timestamp=TIMESTAMP, range_record=None, source=None, **observation_fields):
    return {
        "source_result": source or source_result(range_record=current_range() if range_record is None else range_record, timestamp=timestamp),
        "observation": {"timestamp": timestamp, "close": price, **observation_fields},
    }


def analyze(price, **kwargs):
    return PremiumDiscountAnalyzer().analyze(payload(price, **kwargs))


def test_v12_capability_specialist_and_division_boundary():
    assert PREMIUM_DISCOUNT_INTELLIGENCE.name == "premium_discount_intelligence"
    assert PREMIUM_DISCOUNT_INTELLIGENCE.contract == "trading.premium_discount_intelligence.v1"
    assert PREMIUM_DISCOUNT_INTELLIGENCE.permission_scope == "read_only"
    assert PREMIUM_DISCOUNT_ANALYST.name == "premium_discount_analyst"
    specialist = PremiumDiscountIntelligenceSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="premium_discount_analyst",
        capability_name="premium_discount_intelligence",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False
    assert "premium_discount_analyst" in TradingDivision().get_specialist_names()
    assert "premium_discount_intelligence" in TradingDivision().get_capability_names()


@pytest.mark.parametrize(
    ("price", "classification"),
    [
        (99.0, "below_range"),
        (100.0, "discount"),
        (105.0, "discount"),
        (110.0, "equilibrium"),
        (115.0, "premium"),
        (120.0, "premium"),
        (121.0, "above_range"),
    ],
)
def test_v12_exact_boundary_classification(price, classification):
    result = analyze(price).observation
    assert result is not None
    assert result["classification"] == classification


@pytest.mark.parametrize(
    ("price", "expected_position"),
    [(99.0, -0.05), (100.0, 0.0), (110.0, 0.5), (120.0, 1.0), (121.0, 1.05)],
)
def test_v12_normalized_position_is_unclamped(price, expected_position):
    result = analyze(price).observation
    assert result is not None
    assert result["range_position"] == expected_position


def test_v12_consumes_supplied_current_range_without_using_retained_ranges():
    authoritative = current_range(range_id="range_current")
    retained = current_range(range_id="range_unrelated", range_low=1.0, range_high=2.0, range_width=1.0)
    result = analyze(110.0, source=source_result(range_record=authoritative, structural_ranges=[retained]))
    assert result.observation["range_id"] == "range_current"
    assert result.observation["range_low"] == 100.0
    assert result.observation["range_high"] == 120.0
    assert "observations" not in result.to_dict()


def test_v12_close_is_authoritative_and_other_ohlc_fields_are_ignored():
    result = analyze(105.0, open=119.0, high=119.5, low=101.0)
    assert result.observation["observation_price"] == 105.0
    assert result.observation["classification"] == "discount"


def test_v12_no_current_range_emits_no_observation():
    result = analyze(110.0, source=source_result(range_record=None))
    assert result.observation is None
    assert result.diagnostics["range_available"] is False
    assert result.diagnostics["observation_emitted"] is False
    assert result.diagnostics["source_range_id"] is None


def test_v12_requires_exact_source_snapshot_pairing():
    with pytest.raises(ValueError, match="exactly match"):
        analyze(110.0, timestamp="2026-08-16T08:01:00Z", source=source_result(timestamp=TIMESTAMP))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item.update(range_id=""),
        lambda item: item.update(range_low="invalid"),
        lambda item: item.update(range_low=float("nan")),
        lambda item: item.update(range_high=100.0),
        lambda item: item.update(range_width=21.0),
        lambda item: item.update(confirmed_at="invalid"),
        lambda item: item.update(created_at="2026-08-16T07:00:00Z"),
        lambda item: item.update(identity_scope="persistent"),
        lambda item: item.update(source_structure_rule_version="unknown"),
        lambda item: item.update(evidence={}),
    ],
)
def test_v12_malformed_source_fails_closed(mutation):
    range_record = current_range()
    mutation(range_record)
    with pytest.raises(ValueError):
        analyze(110.0, range_record=range_record)


def test_v12_rejects_confirmation_after_observation_timestamp():
    range_record = current_range(confirmed_at="2026-08-16T09:00:00Z", created_at="2026-08-16T09:00:00Z")
    with pytest.raises(ValueError, match="causally available"):
        analyze(110.0, range_record=range_record)


def test_v12_rejects_unsupported_source_result_rule_version():
    source = source_result(range_record=current_range())
    source.evidence["structural_range_rule_version"] = "unknown"
    with pytest.raises(ValueError, match="unsupported structural range rule version"):
        analyze(110.0, source=source)


def test_v12_equilibrium_and_evidence_are_reproducible():
    result = analyze(110.0)
    assert result.observation["equilibrium"] == 110.0
    assert result.observation["range_position"] == 0.5
    assert result.evidence["equilibrium_formula"] == "range_low + ((range_high - range_low) / 2)"
    assert result.evidence["range_position_formula"] == "(observation_price - range_low) / (range_high - range_low)"
    assert result.evidence["source_range_id"] == "range_authoritative_1"


def test_v12_identity_is_snapshot_deterministic():
    first = analyze(115.0)
    second = analyze(115.0)
    assert first.to_dict() == second.to_dict()
    assert first.observation["identity_scope"] == "snapshot_deterministic"
    assert first.metadata["identity_scope"] == "snapshot_deterministic"
    assert not first.observation["observation_id"].startswith("persistent_")


def test_v12_has_no_configuration_or_advisory_semantics():
    result = analyze(110.0).to_dict()
    assert "config" not in result
    text = str(result).lower()
    for forbidden in [
        "buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "target",
        "risk_reward", "position_size", "signal", "setup", "confidence", "probability", "recommendation",
        "expected_direction", "preferred_trade", "high_probability", "trade_bias", "bullish_opportunity",
        "bearish_opportunity", "execution_command",
    ]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None


def test_v12_resolver_precedence_and_generic_range_compatibility():
    resolver = TradingDivisionResolver()
    for goal in ["premium discount", "premium/discount", "range position", "price in range", "premium", "discount", "equilibrium"]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == "premium_discount_intelligence"
        assert resolver.resolve_specialist(request)["name"] == "premium_discount_analyst"
    for goal in ["structural dealing range", "dealing range structure", "structural range", "market structure range"]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == "structural_dealing_range_intelligence"
    generic = MissionRequest(user_goal="analyze range", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(generic)["name"] == "volatility_range"


def test_v12_result_is_the_declared_public_shape():
    result = analyze(110.0)
    assert isinstance(result, PremiumDiscountResult)
    assert set(result.to_dict()) == {"symbol", "timeframe", "timestamp", "observation", "diagnostics", "evidence", "metadata"}
    assert set(result.observation) == {
        "observation_id", "observation_timestamp", "observation_price", "price_source",
        "range_id", "range_low", "equilibrium", "range_high", "range_position", "classification", "identity_scope",
    }