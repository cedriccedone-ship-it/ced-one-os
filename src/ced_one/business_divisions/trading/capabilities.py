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


__all__ = ["TradingCapability", "COORDINATION", "ANALYSIS", "MARKET_OBSERVATION"]
