"""Specialist definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass

from ced_one.business_divisions.trading.market_observation import MarketAnalysisSpecialist as _MarketAnalysisSpecialist


@dataclass(frozen=True)
class TradingSpecialist:
    name: str
    permission_scope: str
    responsibility: str


class MarketAnalysisSpecialist(_MarketAnalysisSpecialist):
    """Compatibility wrapper around the deterministic XAUUSD market observation implementation."""

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


__all__ = ["TradingSpecialist", "MarketAnalysisSpecialist", "MARKET_ANALYST", "RISK_SPECIALIST"]
