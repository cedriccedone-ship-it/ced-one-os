"""End-to-end Mission Control orchestration flow for v0.3."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.guards import MissionGuard
from ced_one.mission_control.request import MissionRequestBuilder
from ced_one.mission_control.resolver import RequestResolver
from ced_one.mission_control.types import MissionRequest, MissionResult, RequestStatus


class MissionControlFlow:
    """Defines the full request pipeline from intake to MissionResult."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}
        self.resolver = RequestResolver(self.division_registry)
        self.execution_history: list[MissionResult] = []

    def handle_request(
        self,
        user_goal: str,
        *,
        business_division: str | None = None,
        request_type: str = "general",
        priority: str = "normal",
        source: str = "user",
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
    ) -> MissionResult:
        request = MissionRequestBuilder.from_user_goal(
            user_goal,
            request_type=request_type,
            priority=priority,
            source=source,
            business_division=business_division,
            context=context,
            metadata=metadata or {},
            constraints=constraints,
        )

        authority = MissionGuard.validate_authority(request.metadata)
        if not authority.valid:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.FAILED,
                summary="Authority validation failed.",
                errors=list(authority.violations),
                success=False,
                metadata={"authority_validation": authority},
            )
            self.execution_history.append(result)
            return result

        division_resolution = self.resolver.resolve(request)
        if not division_resolution.is_routeable or division_resolution.division_name is None:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.UNROUTEABLE,
                summary=division_resolution.rationale,
                errors=[division_resolution.rationale],
                success=False,
                metadata={"division_resolution": division_resolution},
            )
            self.execution_history.append(result)
            return result

        approval = MissionGuard.evaluate_approval(request.metadata)
        if approval.required:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.AWAITING_APPROVAL,
                division=division_resolution.division_name,
                summary="High-impact action requires approval before continuation.",
                approval_state=MissionGuard.approval_state(approval),
                success=False,
                metadata={
                    "division_resolution": division_resolution,
                    "approval_requirement": approval,
                },
            )
            self.execution_history.append(result)
            return result

        division = self.division_registry.get(division_resolution.division_name)
        if division is None:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.UNROUTEABLE,
                summary=f"Division '{division_resolution.division_name}' is not registered.",
                errors=[f"Division '{division_resolution.division_name}' is not configured."],
                success=False,
                metadata={"division_resolution": division_resolution},
            )
            self.execution_history.append(result)
            return result

        if hasattr(division, "resolve_specialist"):
            specialist = division.resolve_specialist(request)
        else:
            specialist = {"name": None, "permission_scope": "unknown", "rationale": "No specialist resolution provided."}

        if hasattr(division, "resolve_capability"):
            capability = division.resolve_capability(request)
        else:
            capability = {"name": None, "contract": "unknown", "rationale": "No capability resolution provided."}

        result_payload = {
            "request_id": request.request_id,
            "division": division_resolution.division_name,
            "specialist": specialist.get("name"),
            "capability": capability.get("name"),
            "summary": "Division resolved the request successfully.",
            "result_payload": {
                "specialist": specialist,
                "capability": capability,
            },
            "approval_state": MissionGuard.approval_state(approval),
            "errors": [],
            "success": True,
            "metadata": {
                "division_resolution": division_resolution,
                "specialist": specialist,
                "capability": capability,
            },
        }

        result = MissionResult(
            request_id=request.request_id,
            status=RequestStatus.COMPLETED,
            division=division_resolution.division_name,
            specialist=str(specialist.get("name")),
            capability=str(capability.get("name")),
            summary=result_payload["summary"],
            result_payload=result_payload["result_payload"],
            approval_state=result_payload["approval_state"],
            errors=result_payload["errors"],
            success=result_payload["success"],
            metadata=result_payload["metadata"],
        )

        self.execution_history.append(result)
        return result


__all__ = ["MissionControlFlow"]
