"""Mission Control orchestration workflow for v0.2."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.approval import ApprovalGate
from ced_one.mission_control.classifier import RequestClassifier
from ced_one.mission_control.dispatcher import MissionDispatcher
from ced_one.mission_control.request import MissionRequestBuilder
from ced_one.mission_control.router import RequestRouter
from ced_one.mission_control.types import AuthorityValidationResult, MissionResult, RequestStatus
from ced_one.mission_control.validator import AuthorityValidator


class MissionControlOrchestrator:
    """Coordinates the v0.2 lifecycle from request to result."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}
        self.router = RequestRouter(self.division_registry)
        self.dispatcher = MissionDispatcher(self.division_registry)
        self.classifier = RequestClassifier()
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

        request.status = RequestStatus.CLASSIFIED
        classification = self.classifier.classify(request)
        request.metadata.setdefault("classification", classification)

        authority_check: AuthorityValidationResult = AuthorityValidator.validate(request.metadata)
        if not authority_check.valid:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.FAILED,
                summary="Authority validation failed.",
                errors=[*authority_check.violations],
                success=False,
                metadata={
                    "classification": classification,
                    "authority_validation": authority_check,
                },
            )
            self.execution_history.append(result)
            return result

        route = self.router.route(request)
        if not route.is_routeable or route.division_name is None:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.UNROUTEABLE,
                summary=route.rationale,
                errors=[route.rationale],
                success=False,
                metadata={
                    "classification": classification,
                    "route_decision": route.__dict__,
                },
            )
            self.execution_history.append(result)
            return result

        approval_requirement = ApprovalGate.evaluate(request.metadata)
        if approval_requirement.required:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.AWAITING_APPROVAL,
                division=route.division_name,
                summary="High-impact action requires approval before proceeding.",
                approval_state=ApprovalGate.status_for(approval_requirement),
                success=False,
                metadata={
                    "classification": classification,
                    "route_decision": route.__dict__,
                    "approval_requirement": approval_requirement,
                },
            )
            self.execution_history.append(result)
            return result

        dispatch_result = self.dispatcher.dispatch(request, route.division_name)
        dispatch_result.metadata.setdefault("classification", classification)
        dispatch_result.metadata.setdefault("route_decision", route.__dict__)
        self.execution_history.append(dispatch_result)
        return dispatch_result


__all__ = ["MissionControlOrchestrator"]
