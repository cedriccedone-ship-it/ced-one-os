"""Specialist definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass

from ced_one.business_divisions.trading.displacement_intelligence import DisplacementIntelligenceSpecialist as _DisplacementIntelligenceSpecialist
from ced_one.business_divisions.trading.fvg_imbalance_intelligence import FVGImbalanceIntelligenceSpecialist as _FVGImbalanceIntelligenceSpecialist
from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceSpecialist as _LiquidityIntelligenceSpecialist
from ced_one.business_divisions.trading.liquidity_events import LiquidityEventsSpecialist as _LiquidityEventsSpecialist
from ced_one.business_divisions.trading.order_block_intelligence import OrderBlockIntelligenceSpecialist as _OrderBlockIntelligenceSpecialist
from ced_one.business_divisions.trading.premium_discount_intelligence import PremiumDiscountIntelligenceSpecialist as _PremiumDiscountIntelligenceSpecialist
from ced_one.business_divisions.trading.structural_dealing_range_intelligence import StructuralDealingRangeIntelligenceSpecialist as _StructuralDealingRangeIntelligenceSpecialist
from ced_one.business_divisions.trading.market_observation import MarketAnalysisSpecialist as _MarketAnalysisSpecialist
from ced_one.business_divisions.trading.volatility_range import VolatilityRangeSpecialist as _VolatilityRangeSpecialist


@dataclass(frozen=True)
class TradingSpecialist:
    name: str
    permission_scope: str
    responsibility: str


class MarketAnalysisSpecialist(_MarketAnalysisSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD market observation implementation."""

    pass


class VolatilityRangeSpecialist(_VolatilityRangeSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD volatility and range implementation."""

    pass


class LiquidityIntelligenceSpecialist(_LiquidityIntelligenceSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD liquidity implementation."""

    pass


class FVGImbalanceIntelligenceSpecialist(_FVGImbalanceIntelligenceSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD FVG and imbalance implementation."""

    pass


class DisplacementIntelligenceSpecialist(_DisplacementIntelligenceSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD displacement implementation."""

    pass


class LiquidityEventsSpecialist(_LiquidityEventsSpecialist):
    """Compatibility wrapper around deterministic liquidity event intelligence."""

    pass


class OrderBlockIntelligenceSpecialist(_OrderBlockIntelligenceSpecialist):
    """Compatibility wrapper around deterministic order block intelligence."""

    pass


class StructuralDealingRangeIntelligenceSpecialist(_StructuralDealingRangeIntelligenceSpecialist):
    """Compatibility wrapper around deterministic structural dealing ranges."""

    pass


class PremiumDiscountIntelligenceSpecialist(_PremiumDiscountIntelligenceSpecialist):
    """Compatibility wrapper around deterministic current premium/discount geometry."""

    pass


MARKET_ANALYST = TradingSpecialist(
    name="market_analyst",
    permission_scope="read_only",
    responsibility="Review and route domain-specific information for the trading business division.",
)

RISK_SPECIALIST = TradingSpecialist(
    name="risk_specialist",
    permission_scope="review_only",
    responsibility="Assess risk boundaries without executing external actions.",
)

VOLATILITY_ANALYST = TradingSpecialist(
    name="volatility_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic realized volatility and range context for the trading business division.",
)

LIQUIDITY_ANALYST = TradingSpecialist(
    name="liquidity_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual liquidity context for the trading business division.",
)

FVG_IMBALANCE_ANALYST = TradingSpecialist(
    name="fvg_imbalance_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual fair value gap and imbalance context for the trading business division.",
)

DISPLACEMENT_ANALYST = TradingSpecialist(
    name="displacement_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual displacement context for the trading business division.",
)

LIQUIDITY_EVENTS_ANALYST = TradingSpecialist(
    name="liquidity_events_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual liquidity touch, sweep, and close-beyond events for the trading business division.",
)

ORDER_BLOCK_ANALYST = TradingSpecialist(
    name="order_block_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual order block origin and interaction context for the trading business division.",
)

STRUCTURAL_DEALING_RANGE_ANALYST = TradingSpecialist(
    name="structural_dealing_range_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual structural dealing range context for the trading business division.",
)

PREMIUM_DISCOUNT_ANALYST = TradingSpecialist(
    name="premium_discount_analyst",
    permission_scope="read_only",
    responsibility="Review deterministic factual current premium and discount geometry for the trading business division.",
)


__all__ = [
    "TradingSpecialist",
    "MarketAnalysisSpecialist",
    "VolatilityRangeSpecialist",
    "LiquidityIntelligenceSpecialist",
    "FVGImbalanceIntelligenceSpecialist",
    "DisplacementIntelligenceSpecialist",
    "MARKET_ANALYST",
    "RISK_SPECIALIST",
    "VOLATILITY_ANALYST",
    "LIQUIDITY_ANALYST",
    "FVG_IMBALANCE_ANALYST",
    "DISPLACEMENT_ANALYST",
    "LIQUIDITY_EVENTS_ANALYST",
    "OrderBlockIntelligenceSpecialist",
    "ORDER_BLOCK_ANALYST",
    "StructuralDealingRangeIntelligenceSpecialist",
    "STRUCTURAL_DEALING_RANGE_ANALYST",
    "PremiumDiscountIntelligenceSpecialist",
    "PREMIUM_DISCOUNT_ANALYST",
]
