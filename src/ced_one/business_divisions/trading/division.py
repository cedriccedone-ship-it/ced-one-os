"""Trading Division contract for Ced-One OS.

This module defines the first business division without implementing strategy,
execution, live market behavior, or provider-specific integrations.
"""

from __future__ import annotations

from typing import Any, Iterable

from ced_one.business_divisions.base import BusinessDivision


class TradingDivision(BusinessDivision):
    """First concrete business division.

    The division is generic enough to support multiple trading scenarios, while
    establishing XAUUSD as the initial market scope for the first architecture
    iteration.
    """

    name = "trading"
    scope = "XAUUSD"

    def get_name(self) -> str:
        return self.name

    def get_scope(self) -> str:
        return self.scope

    def get_specialist_names(self) -> Iterable[str]:
        return ["market_analyst", "volatility_analyst"]

    def get_capability_names(self) -> Iterable[str]:
        return ["market_observation", "volatility_range"]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "business_division",
            "scope": self.scope,
            "market_scope": "XAUUSD",
            "notes": (
                "Initial division scope for architecture scaffolding only. "
                "No execution, strategy, or live market integration is implemented."
            ),
        }
