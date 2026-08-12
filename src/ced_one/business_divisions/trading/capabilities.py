"""Capability definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingCapability:
    name: str
    contract: str
    responsibility: str


COORDINATION = TradingCapability(
    name="coordination",
    contract="generic_coordination",
    responsibility="Coordinate a request within the trading domain without external execution behavior.",
)

ANALYSIS = TradingCapability(
    name="analysis",
    contract="domain_analysis",
    responsibility="Interpret domain context while remaining provider-independent.",
)


__all__ = ["TradingCapability", "COORDINATION", "ANALYSIS"]
