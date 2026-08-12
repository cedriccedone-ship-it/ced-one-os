"""Specialist definitions for the Trading Division v0.3 example."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingSpecialist:
    name: str
    permission_scope: str
    responsibility: str


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


__all__ = ["TradingSpecialist", "MARKET_ANALYST", "RISK_SPECIALIST"]
