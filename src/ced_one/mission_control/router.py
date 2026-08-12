"""Division routing logic for Mission Control v0.1."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import MissionRequest, RouteDecision


class RequestRouter:
    """Select the appropriate business division for a request."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}

    def route(self, request: MissionRequest) -> RouteDecision:
        if request.business_division:
            division_name = request.business_division
            division = self.division_registry.get(division_name)
            if division is None:
                return RouteDecision(
                    division_name=None,
                    is_supported=False,
                    is_routeable=False,
                    confidence=0.0,
                    rationale=f"Business division '{division_name}' is not registered.",
                    status="unrouteable",
                )
            return RouteDecision(
                division_name=division_name,
                is_supported=True,
                is_routeable=True,
                confidence=0.9,
                rationale=f"Request routed to registered division '{division_name}'.",
                status="routed",
            )

        if not self.division_registry:
            return RouteDecision(
                division_name=None,
                is_supported=False,
                is_routeable=False,
                confidence=0.0,
                rationale="No business divisions are registered for routing.",
                status="unsupported",
            )

        primary_division_name = next(iter(self.division_registry.keys()))
        return RouteDecision(
            division_name=primary_division_name,
            is_supported=True,
            is_routeable=True,
            confidence=0.5,
            rationale=(
                "No explicit division specified; selected the first available registered "
                "division for generic routing."
            ),
            status="routed",
        )


__all__ = ["RequestRouter"]
