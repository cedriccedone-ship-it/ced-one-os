"""Capability definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingCapability:
    name: str
    contract: str
    responsibility: str
    permission_scope: str = "standard"
    division_name: str = "trading"


COORDINATION = TradingCapability(
    name="coordination",
    contract="generic_coordination",
    responsibility="Coordinate a request within the trading domain without external execution behavior.",
    permission_scope="read_only",
    division_name="trading",
)

ANALYSIS = TradingCapability(
    name="analysis",
    contract="domain_analysis",
    responsibility="Interpret domain context while remaining provider-independent.",
    permission_scope="read_only",
    division_name="trading",
)

MARKET_OBSERVATION = TradingCapability(
    name="market_observation",
    contract="trading.market_observation.v1",
    responsibility="Perform deterministic synthetic XAUUSD market observation for architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

VOLATILITY_RANGE = TradingCapability(
    name="volatility_range",
    contract="trading.volatility_range.v1",
    responsibility="Perform deterministic realized volatility and range intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

LIQUIDITY_INTELLIGENCE = TradingCapability(
    name="liquidity_intelligence",
    contract="trading.liquidity_intelligence.v1",
    responsibility="Perform deterministic factual liquidity intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

FVG_IMBALANCE_INTELLIGENCE = TradingCapability(
    name="fvg_imbalance_intelligence",
    contract="trading.fvg_imbalance_intelligence.v1",
    responsibility="Perform deterministic factual fair value gap and imbalance intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

DISPLACEMENT_INTELLIGENCE = TradingCapability(
    name="displacement_intelligence",
    contract="trading.displacement_intelligence.v1",
    responsibility="Perform deterministic factual displacement intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

LIQUIDITY_EVENTS = TradingCapability(
    name="liquidity_events",
    contract="trading.liquidity_events.v1",
    responsibility="Perform deterministic factual liquidity touch, sweep, and close-beyond event intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

ORDER_BLOCK_INTELLIGENCE = TradingCapability(
    name="order_block_intelligence",
    contract="trading.order_block_intelligence.v1",
    responsibility="Perform deterministic factual order block origin and subsequent interaction intelligence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

STRUCTURAL_DEALING_RANGE_INTELLIGENCE = TradingCapability(
    name="structural_dealing_range_intelligence",
    contract="trading.structural_dealing_range_intelligence.v1",
    responsibility="Perform deterministic factual structural dealing range construction from confirmed market-structure pivot evidence for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

PREMIUM_DISCOUNT_INTELLIGENCE = TradingCapability(
    name="premium_discount_intelligence",
    contract="trading.premium_discount_intelligence.v1",
    responsibility="Perform deterministic factual current-close classification within the authoritative structural dealing range for XAUUSD architecture validation only.",
    permission_scope="read_only",
    division_name="trading",
)

__all__ = [
    "TradingCapability",
    "COORDINATION",
    "ANALYSIS",
    "MARKET_OBSERVATION",
    "VOLATILITY_RANGE",
    "LIQUIDITY_INTELLIGENCE",
    "FVG_IMBALANCE_INTELLIGENCE",
    "DISPLACEMENT_INTELLIGENCE",
    "LIQUIDITY_EVENTS",
    "ORDER_BLOCK_INTELLIGENCE",
    "STRUCTURAL_DEALING_RANGE_INTELLIGENCE",
    "PREMIUM_DISCOUNT_INTELLIGENCE",
]
