"""Trading Division resolution logic for Ced-One OS v0.3.

This is the first concrete Business Division example. It defines how a request is
routed within the trading domain without implementing live execution or external
provider logic.
"""

from __future__ import annotations

from typing import Any

from ced_one.business_divisions.base import BusinessDivision
from ced_one.mission_control.types import DivisionResolutionResult, MissionRequest, RequestClassification


class TradingDivisionResolver(BusinessDivision):
    """Concrete Trading Division router and resolver."""

    name = "trading"
    scope = "XAUUSD"

    def get_name(self) -> str:
        return self.name

    def get_scope(self) -> str:
        return self.scope

    def get_specialist_names(self) -> list[str]:
        return [
            "market_analyst",
            "volatility_analyst",
            "liquidity_analyst",
            "fvg_imbalance_analyst",
            "risk_specialist",
            "coordination_specialist",
        ]

    def get_capability_names(self) -> list[str]:
        return [
            "coordination",
            "analysis",
            "market_observation",
            "volatility_range",
            "liquidity_intelligence",
            "fvg_imbalance_intelligence",
            "risk_review",
        ]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "business_division",
            "scope": self.scope,
            "market_scope": "XAUUSD",
            "notes": "Initial domain-specific routing example for architecture validation only.",
        }

    def supports_request(self, request: MissionRequest, classification: RequestClassification | None = None) -> bool:
        text = f"{request.user_goal} {request.request_type} {request.business_division or ''}".lower()
        if "trading" in text or "market" in text or "xauusd" in text:
            return True
        if classification is not None and "trading" in classification.domain_tags:
            return True
        return False

    def resolve_request(
        self,
        request: MissionRequest,
        classification: RequestClassification | None = None,
    ) -> DivisionResolutionResult:
        if not self.supports_request(request, classification):
            return DivisionResolutionResult(
                division_name=None,
                is_supported=False,
                is_routeable=False,
                confidence=0.0,
                rationale="Request does not fall within the trading business division scope.",
                specialist_name=None,
                capability_name=None,
                status="unsupported",
            )

        text = f"{request.user_goal} {request.request_type} {request.business_division or ''}".lower()
        specialist_name = "market_analyst"
        capability_name = "market_observation"
        if "volatility" in text or "range" in text:
            specialist_name = "volatility_analyst"
            capability_name = "volatility_range"
        elif "liquidity" in text:
            specialist_name = "liquidity_analyst"
            capability_name = "liquidity_intelligence"
        elif "imbalance" in text or "fair value gap" in text or "fvg" in text:
            specialist_name = "fvg_imbalance_analyst"
            capability_name = "fvg_imbalance_intelligence"

        return DivisionResolutionResult(
            division_name=self.name,
            is_supported=True,
            is_routeable=True,
            confidence=0.9,
            rationale="Trading Division accepted the request for domain-specific routing.",
            specialist_name=specialist_name,
            capability_name=capability_name,
            status="resolved",
        )

    def resolve_specialist(self, request: MissionRequest) -> dict[str, Any]:
        text = f"{request.user_goal} {request.request_type} {request.business_division or ''}".lower()
        if "volatility" in text or "range" in text:
            return {
                "name": "volatility_analyst",
                "division_name": self.name,
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the volatility analyst for the realized range test.",
            }
        if "liquidity" in text:
            return {
                "name": "liquidity_analyst",
                "division_name": self.name,
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the liquidity analyst for the deterministic liquidity test.",
            }
        if "imbalance" in text or "fair value gap" in text or "fvg" in text:
            return {
                "name": "fvg_imbalance_analyst",
                "division_name": self.name,
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the fvg and imbalance analyst for deterministic imbalance intelligence.",
            }
        return {
            "name": "market_analyst",
            "division_name": self.name,
            "permission_scope": "read_only",
            "rationale": "Trading Division selected the market analyst for the routing test.",
        }

    def resolve_capability(self, request: MissionRequest) -> dict[str, Any]:
        text = f"{request.user_goal} {request.request_type} {request.business_division or ''}".lower()
        if "volatility" in text or "range" in text:
            return {
                "name": "volatility_range",
                "division_name": self.name,
                "contract": "trading.volatility_range.v1",
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the volatility and range capability for the controlled XAUUSD volatility slice.",
            }
        if "liquidity" in text:
            return {
                "name": "liquidity_intelligence",
                "division_name": self.name,
                "contract": "trading.liquidity_intelligence.v1",
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the liquidity intelligence capability for the controlled XAUUSD liquidity slice.",
            }
        if "imbalance" in text or "fair value gap" in text or "fvg" in text:
            return {
                "name": "fvg_imbalance_intelligence",
                "division_name": self.name,
                "contract": "trading.fvg_imbalance_intelligence.v1",
                "permission_scope": "read_only",
                "rationale": "Trading Division selected the fvg and imbalance intelligence capability for the controlled XAUUSD imbalance slice.",
            }
        return {
            "name": "market_observation",
            "division_name": self.name,
            "contract": "trading.market_observation.v1",
            "permission_scope": "read_only",
            "rationale": "Trading Division selected the market observation capability for the controlled XAUUSD observation slice.",
        }


__all__ = ["TradingDivisionResolver"]
