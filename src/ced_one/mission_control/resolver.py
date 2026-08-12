"""Generic division resolution for Mission Control v0.3."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import DivisionResolutionResult, MissionRequest, RequestClassification


class RequestResolver:
    """Resolve a request to a business division using a generic registry."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}

    @staticmethod
    def _normalize_result(result: DivisionResolutionResult | dict[str, Any]) -> DivisionResolutionResult:
        if isinstance(result, DivisionResolutionResult):
            return result

        return DivisionResolutionResult(
            division_name=result.get("division_name"),
            is_supported=bool(result.get("is_supported", False)),
            is_routeable=bool(result.get("is_routeable", False)),
            confidence=float(result.get("confidence", 0.0)),
            rationale=str(result.get("rationale", "")),
            specialist_name=result.get("specialist_name"),
            capability_name=result.get("capability_name"),
            status=str(result.get("status", "resolved")),
        )

    def resolve(
        self,
        request: MissionRequest,
        classification: RequestClassification | None = None,
    ) -> DivisionResolutionResult:
        division_name = request.business_division

        if division_name is not None:
            candidates = [division_name]
        else:
            candidates = list(self.division_registry.keys())

        for name in candidates:
            division = self.division_registry.get(name)
            if division is None:
                continue

            if hasattr(division, "supports_request"):
                if not division.supports_request(request, classification):
                    continue

            if hasattr(division, "resolve_request"):
                return self._normalize_result(division.resolve_request(request, classification))

            return DivisionResolutionResult(
                division_name=name,
                is_supported=True,
                is_routeable=True,
                confidence=0.7,
                rationale=f"Resolved request to registered division '{name}'.",
                specialist_name=None,
                capability_name=None,
                status="resolved",
            )

        return DivisionResolutionResult(
            division_name=None,
            is_supported=False,
            is_routeable=False,
            confidence=0.0,
            rationale="No registered business division can support this request.",
            specialist_name=None,
            capability_name=None,
            status="unsupported",
        )


__all__ = ["RequestResolver"]
