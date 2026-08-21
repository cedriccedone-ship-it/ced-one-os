from __future__ import annotations

from ced_one.business_divisions.trading import (
    CANDLE_INTELLIGENCE_CAPABILITY,
    MARKET_STRUCTURE,
    MarketAnalysisSpecialist,
    MarketStructureSpecialist,
)
from ced_one.business_divisions.trading.capabilities import (
    ANALYSIS,
    COORDINATION,
)
from ced_one.business_divisions.trading.division import TradingDivision
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.mission_control.types import MissionRequest


OPERATIONAL_CAPABILITIES = [
    "market_observation",
    "market_structure",
    "candle_intelligence",
    "volatility_range",
    "liquidity_intelligence",
    "liquidity_events",
    "fvg_imbalance_intelligence",
    "displacement_intelligence",
    "order_block_intelligence",
    "structural_dealing_range_intelligence",
    "premium_discount_intelligence",
]

OPERATIONAL_SPECIALISTS = [
    "market_analyst",
    "market_structure_analyst",
    "candle_analyst",
    "volatility_analyst",
    "liquidity_analyst",
    "liquidity_events_analyst",
    "fvg_imbalance_analyst",
    "displacement_analyst",
    "order_block_analyst",
    "structural_dealing_range_analyst",
    "premium_discount_analyst",
]


def request(goal: str) -> MissionRequest:
    return MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")


def test_v17_operational_inventories_are_complete_and_deterministic():
    division = TradingDivision()
    resolver = TradingDivisionResolver()
    assert list(division.get_capability_names()) == OPERATIONAL_CAPABILITIES
    assert list(division.get_specialist_names()) == OPERATIONAL_SPECIALISTS
    assert resolver.get_capability_names() == OPERATIONAL_CAPABILITIES
    assert resolver.get_specialist_names() == OPERATIONAL_SPECIALISTS


def test_v17_internal_slices_and_phantom_entries_are_not_operationally_advertised():
    division = TradingDivision()
    resolver = TradingDivisionResolver()
    text = str(list(division.get_capability_names()) + list(division.get_specialist_names()) + resolver.get_capability_names() + resolver.get_specialist_names())
    for internal in [
        "causal_snapshot_availability", "causal_multi_timeframe_context",
        "causal_factual_intelligence_envelope", "causal_factual_multi_timeframe_context",
        "risk_review", "coordination_specialist", "risk_specialist",
    ]:
        assert internal not in text


def test_v17_generic_architecture_constants_remain_defined_but_are_not_factual_inventory():
    assert COORDINATION.name == "coordination"
    assert ANALYSIS.name == "analysis"
    assert COORDINATION.name not in OPERATIONAL_CAPABILITIES
    assert ANALYSIS.name not in OPERATIONAL_CAPABILITIES


def test_v17_market_context_remains_owned_by_market_analysis_specialist():
    specialist = MarketAnalysisSpecialist()
    assert hasattr(specialist, "observe_market_context")
    assert "market_context" not in TradingDivision().get_capability_names()
    assert "market_context_specialist" not in TradingDivision().get_specialist_names()


def test_v17_market_structure_wrapper_delegates_and_is_read_only():
    specialist = MarketStructureSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="market_structure_analyst",
        capability_name="market_structure",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert specialist.requires_live_market_data() is False
    assert specialist.requires_external_ai() is False
    candles = [
        {"timestamp": "2026-08-16T00:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": "2026-08-16T01:00:00Z", "open": 100, "high": 102, "low": 98, "close": 101},
        {"timestamp": "2026-08-16T02:00:00Z", "open": 101, "high": 101, "low": 97, "close": 99},
    ]
    result = specialist.analyze_market_structure({
        "symbol": "XAUUSD", "timeframe": "H1", "evaluation_time": "2026-08-16T03:00:00Z", "candle_history": candles,
    })
    assert result.to_dict()["timeframe"] == "H1"


def test_v17_candle_capability_and_specialist_are_centrally_represented():
    assert CANDLE_INTELLIGENCE_CAPABILITY.name == "candle_intelligence"
    assert CANDLE_INTELLIGENCE_CAPABILITY.contract == "trading.candle_intelligence.v1"
    assert "candle_intelligence" in TradingDivision().get_capability_names()
    assert "candle_analyst" in TradingDivision().get_specialist_names()


def test_v17_market_structure_capability_is_centrally_represented():
    assert MARKET_STRUCTURE.name == "market_structure"
    assert MARKET_STRUCTURE.contract == "trading.market_structure.v1"
    assert "market_structure" in TradingDivision().get_capability_names()
    assert "market_structure_analyst" in TradingDivision().get_specialist_names()


def test_v17_narrow_new_routes_and_preserved_routes():
    resolver = TradingDivisionResolver()
    for goal in ["market structure intelligence", "swing structure"]:
        assert resolver.resolve_capability(request(goal))["name"] == "market_structure"
        assert resolver.resolve_specialist(request(goal))["name"] == "market_structure_analyst"
    for goal in ["candle intelligence", "candle morphology", "candle analysis"]:
        assert resolver.resolve_capability(request(goal))["name"] == "candle_intelligence"
        assert resolver.resolve_specialist(request(goal))["name"] == "candle_analyst"
    assert resolver.resolve_capability(request("analyze market structure"))["name"] == "market_observation"
    assert resolver.resolve_capability(request("analyze range"))["name"] == "volatility_range"
    assert resolver.resolve_capability(request("premium discount"))["name"] == "premium_discount_intelligence"
    assert resolver.resolve_capability(request("structural dealing range"))["name"] == "structural_dealing_range_intelligence"


def test_v17_internal_infrastructure_has_no_user_routes():
    resolver = TradingDivisionResolver()
    for goal in ["causal snapshot", "causal multi-timeframe context", "factual intelligence envelope", "factual multi-timeframe context"]:
        assert resolver.resolve_capability(request(goal))["name"] == "market_observation"


def test_v17_package_exports_reconciled_user_facing_surfaces_without_internal_layers():
    import ced_one.business_divisions.trading as trading

    assert hasattr(trading, "MARKET_STRUCTURE")
    assert hasattr(trading, "CANDLE_INTELLIGENCE_CAPABILITY")
    assert not hasattr(trading, "CAUSAL_SNAPSHOT_AVAILABILITY")
    assert not hasattr(trading, "CAUSAL_MULTI_TIMEFRAME_CONTEXT")
    assert not hasattr(trading, "CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE")
    assert not hasattr(trading, "CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT")


def test_v17_no_strategy_or_execution_authority_added():
    text = str(TradingDivision().get_capability_names() + list(TradingDivision().get_specialist_names())).lower()
    for forbidden in ["buy", "sell", "signal", "setup", "confidence", "recommendation", "execution"]:
        assert forbidden not in text