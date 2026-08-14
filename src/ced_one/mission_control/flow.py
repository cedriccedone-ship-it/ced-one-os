"""End-to-end Mission Control orchestration flow for v0.4."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.execution import ExecutionPlanStep, MissionExecutionPlan
from ced_one.mission_control.guards import MissionGuard
from ced_one.mission_control.request import MissionRequestBuilder
from ced_one.mission_control.resolver import RequestResolver
from ced_one.mission_control.types import ApprovalState, MissionRequest, MissionResult, RequestStatus


class MissionControlFlow:
    """Defines the controlled execution pipeline from intake to MissionResult."""

    def __init__(self, division_registry: dict[str, Any] | None = None):
        self.division_registry = division_registry or {}
        self.resolver = RequestResolver(self.division_registry)
        self.execution_history: list[MissionResult] = []

    @staticmethod
    def _build_execution_plan(request: MissionRequest, division_name: str, specialist: dict[str, Any], capability: dict[str, Any]) -> MissionExecutionPlan:
        approval_required = bool(request.metadata.get("approval_required", False)) or str(request.metadata.get("impact_level", "low")).lower() in {"high", "critical", "irreversible"}
        step_defs = [
            ("validate_authority", "Validate governance and authority boundaries.", False),
            ("resolve_division", "Confirm the registered business division matches the request.", False),
            ("resolve_specialist", "Select the specialist assigned to the request.", False),
            ("resolve_capability", "Bind the reusable capability contract required for the task.", False),
            ("validate_scope", "Confirm the scope and constraints still fit the request.", False),
            ("execute_plan", "Execute the controlled internal orchestration sequence.", approval_required),
        ]

        steps: list[ExecutionPlanStep] = []
        for index, (name, description, approval_required) in enumerate(step_defs, start=1):
            steps.append(
                ExecutionPlanStep(
                    name=name,
                    description=description,
                    order=index,
                    division=division_name,
                    specialist=specialist.get("name"),
                    capability=capability.get("name"),
                    approval_required=approval_required,
                    metadata={
                        "request_id": request.request_id,
                        "request_type": request.request_type,
                        "priority": request.priority,
                    },
                )
            )

        plan = MissionExecutionPlan(
            plan_id=f"plan_{request.request_id}",
            request_id=request.request_id,
            division=division_name,
            specialist=specialist.get("name"),
            capability=capability.get("name"),
            execution_mode="controlled",
            provider=None,
            approved=False,
            steps=steps,
        )
        return plan

    @staticmethod
    def _validate_specialist(specialist: dict[str, Any] | None) -> list[str]:
        if specialist is None:
            return ["No specialist assignment was produced by the selected division."]
        if not specialist.get("name"):
            return ["The selected division did not supply a valid specialist name."]
        return []

    @staticmethod
    def _validate_capability(capability: dict[str, Any] | None) -> list[str]:
        if capability is None:
            return ["No capability assignment was produced by the selected division."]
        if not capability.get("name"):
            return ["The selected division did not supply a valid capability name."]
        return []

    @staticmethod
    def _validate_plan(plan: MissionExecutionPlan) -> list[str]:
        errors: list[str] = []
        if plan.division is None:
            errors.append("Execution plan is missing a valid division.")
        if plan.specialist is None:
            errors.append("Execution plan is missing a valid specialist.")
        if plan.capability is None:
            errors.append("Execution plan is missing a valid capability.")
        if not plan.steps:
            errors.append("Execution plan does not contain any steps.")
        return errors

    @staticmethod
    def _execution_trace(plan: MissionExecutionPlan) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for step in plan.steps:
            trace.append(
                {
                    "step": step.name,
                    "status": step.status,
                    "order": step.order,
                    "division": step.division,
                    "specialist": step.specialist,
                    "capability": step.capability,
                    "approval_required": step.approval_required,
                }
            )
        return trace

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

        specialist_errors = self._validate_specialist(specialist)
        capability_errors = self._validate_capability(capability)
        validation_errors = specialist_errors + capability_errors
        if validation_errors:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.FAILED,
                division=division_resolution.division_name,
                specialist=specialist.get("name") if isinstance(specialist, dict) else None,
                capability=capability.get("name") if isinstance(capability, dict) else None,
                summary="Division returned an invalid specialist or capability assignment.",
                errors=validation_errors,
                success=False,
                metadata={
                    "division_resolution": division_resolution,
                    "specialist": specialist,
                    "capability": capability,
                },
            )
            self.execution_history.append(result)
            return result

        approval = MissionGuard.evaluate_approval(request.metadata)
        if approval.required:
            plan = self._build_execution_plan(request, division_resolution.division_name, specialist, capability)
            plan.approved = False
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.AWAITING_APPROVAL,
                division=division_resolution.division_name,
                specialist=specialist.get("name"),
                capability=capability.get("name"),
                summary="High-impact action requires approval before continuation.",
                approval_state=MissionGuard.approval_state(approval),
                success=False,
                metadata={
                    "division_resolution": division_resolution,
                    "approval_requirement": approval,
                    "execution_plan": plan.as_dict(),
                    "execution_trace": self._execution_trace(plan),
                },
            )
            self.execution_history.append(result)
            return result

        plan = self._build_execution_plan(request, division_resolution.division_name, specialist, capability)
        plan_errors = self._validate_plan(plan)
        if plan_errors:
            result = MissionResult(
                request_id=request.request_id,
                status=RequestStatus.FAILED,
                division=division_resolution.division_name,
                specialist=specialist.get("name"),
                capability=capability.get("name"),
                summary="Execution plan validation failed before orchestration could begin.",
                errors=plan_errors,
                success=False,
                metadata={
                    "division_resolution": division_resolution,
                    "specialist": specialist,
                    "capability": capability,
                    "execution_plan": plan.as_dict(),
                    "execution_trace": self._execution_trace(plan),
                },
            )
            self.execution_history.append(result)
            return result

        for step in plan.steps:
            step.status = "in_progress"
            if step.approval_required and not request.metadata.get("approved", False):
                step.status = "blocked"
                result = MissionResult(
                    request_id=request.request_id,
                    status=RequestStatus.AWAITING_APPROVAL,
                    division=division_resolution.division_name,
                    specialist=specialist.get("name"),
                    capability=capability.get("name"),
                    summary="A protected plan step requires approval before execution.",
                    approval_state=ApprovalState.PENDING,
                    success=False,
                    metadata={
                        "division_resolution": division_resolution,
                        "specialist": specialist,
                        "capability": capability,
                        "execution_plan": plan.as_dict(),
                        "execution_trace": self._execution_trace(plan),
                    },
                )
                self.execution_history.append(result)
                return result
            step.status = "completed"

        plan.approved = True
        result_payload = {
            "request_id": request.request_id,
            "division": division_resolution.division_name,
            "specialist": specialist.get("name"),
            "capability": capability.get("name"),
            "summary": "Division and capability were coordinated through a controlled orchestration plan.",
            "result_payload": {
                "specialist": specialist,
                "capability": capability,
                "plan": plan.as_dict(),
            },
            "approval_state": MissionGuard.approval_state(approval),
            "errors": [],
            "success": True,
            "metadata": {
                "division_resolution": division_resolution,
                "specialist": specialist,
                "capability": capability,
                "execution_plan": plan.as_dict(),
                "execution_trace": self._execution_trace(plan),
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
