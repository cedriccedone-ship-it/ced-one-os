"""Specialist definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass

from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceSpecialist as _LiquidityIntelligenceSpecialist
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


__all__ = [
    "TradingSpecialist",
    "MarketAnalysisSpecialist",
    "VolatilityRangeSpecialist",
    "LiquidityIntelligenceSpecialist",
    "MARKET_ANALYST",
    "RISK_SPECIALIST",
    "VOLATILITY_ANALYST",
    "LIQUIDITY_ANALYST",
]
