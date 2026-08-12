"""Dispatch logic for Mission Control v0.1."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import MissionRequest, MissionResult, RequestStatus


class MissionDispatcher:
    """Route a validated request to a registered business division."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}

    def dispatch(self, request: MissionRequest, division_name: str | None) -> MissionResult:
        if not division_name:
            return MissionResult(
                request_id=request.request_id,
                status=RequestStatus.UNROUTEABLE,
                summary="No valid business division selected for this request.",
                errors=["No routeable division available."],
                success=False,
                metadata={"division_name": None},
            )

        division = self.division_registry.get(division_name)
        if division is None:
            return MissionResult(
                request_id=request.request_id,
                status=RequestStatus.UNROUTEABLE,
                summary=f"Division '{division_name}' is not registered.",
                errors=[f"Division '{division_name}' is not configured."],
                success=False,
                metadata={"division_name": division_name},
            )

        specialist = division.identify_specialist(request)
        capability = division.identify_capability(request)
        result = division.handle_request(request)

        normalized = {
            "request_id": request.request_id,
            "status": RequestStatus.COMPLETED,
            "division": division_name,
            "specialist": specialist.get("name"),
            "capability": capability.get("name"),
            "summary": result.get("summary", "Division processed the request."),
            "result_payload": result.get("result_payload", {}),
            "approval_state": result.get("approval_state", "not_required"),
            "errors": result.get("errors", []),
            "success": result.get("success", True),
            "metadata": result.get("metadata", {}),
        }

        return MissionResult(
            request_id=normalized["request_id"],
            status=normalized["status"],
            division=normalized["division"],
            specialist=normalized["specialist"],
            capability=normalized["capability"],
            summary=normalized["summary"],
            result_payload=normalized["result_payload"],
            approval_state=normalized["approval_state"],
            errors=normalized["errors"],
            success=normalized["success"],
            metadata=normalized["metadata"],
        )


__all__ = ["MissionDispatcher"]
