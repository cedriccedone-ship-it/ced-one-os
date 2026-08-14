from __future__ import annotations

from ced_one.mission_control import MissionControlFlow, MissionResult, RequestStatus


class GenericDivision:
    name = "generic"

    def supports_request(self, request, classification=None):
        return True

    def resolve_request(self, request, classification=None):
        return {
            "division_name": self.name,
            "is_supported": True,
            "is_routeable": True,
            "confidence": 0.9,
            "rationale": "Generic division accepted the request for orchestration validation.",
            "specialist_name": "operations_specialist",
            "capability_name": "coordination",
            "status": "resolved",
        }

    def resolve_specialist(self, request):
        return {
            "name": "operations_specialist",
            "division_name": self.name,
            "permission_scope": "standard",
            "rationale": "Assigned through the generic division orchestration contract.",
        }

    def resolve_capability(self, request):
        return {
            "name": "coordination",
            "division_name": self.name,
            "contract": "generic_coordination",
            "rationale": "Used a reusable, provider-independent capability contract.",
        }


class InvalidSpecialistDivision(GenericDivision):
    def resolve_specialist(self, request):
        return {"name": None, "division_name": self.name, "permission_scope": "unknown", "rationale": "Missing specialist assignment."}


class InvalidCapabilityDivision(GenericDivision):
    def resolve_capability(self, request):
        return {"name": None, "division_name": self.name, "contract": "unknown", "rationale": "Missing capability assignment."}


def test_v04_builds_execution_plan_for_valid_request():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request("Coordinate a standard internal workflow", business_division="generic")

    assert result.status == RequestStatus.COMPLETED
    assert result.success is True
    assert "execution_plan" in result.metadata
    assert "steps" in result.metadata["execution_plan"]
    assert len(result.metadata["execution_plan"]["steps"]) >= 4


def test_v04_records_execution_trace():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request("Trace a valid orchestration flow", business_division="generic")

    assert "execution_trace" in result.metadata
    assert len(result.metadata["execution_trace"]) >= 2


def test_v04_blocks_authority_override_before_execution():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request(
        "Attempt to override authority during orchestration",
        business_division="generic",
        metadata={"authority_override": True},
    )

    assert result.status == RequestStatus.FAILED
    assert result.success is False
    assert any("authority" in error.lower() for error in result.errors)


def test_v04_blocks_high_impact_plan_until_approval():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request(
        "Execute a high-impact workflow requiring approval",
        business_division="generic",
        metadata={"impact_level": "high", "approval_required": True},
    )

    assert result.status == RequestStatus.AWAITING_APPROVAL
    assert result.success is False
    assert "execution_plan" in result.metadata


def test_v04_rejects_invalid_specialist_assignment():
    flow = MissionControlFlow(division_registry={"generic": InvalidSpecialistDivision()})
    result = flow.handle_request("A request with an invalid specialist assignment", business_division="generic")

    assert result.status == RequestStatus.FAILED
    assert result.success is False
    assert any("specialist" in error.lower() for error in result.errors)


def test_v04_rejects_invalid_capability_assignment():
    flow = MissionControlFlow(division_registry={"generic": InvalidCapabilityDivision()})
    result = flow.handle_request("A request with an invalid capability assignment", business_division="generic")

    assert result.status == RequestStatus.FAILED
    assert result.success is False
    assert any("capability" in error.lower() for error in result.errors)


def test_v04_fails_safely_for_unrouteable_requests():
    flow = MissionControlFlow(division_registry={})
    result = flow.handle_request("A request that cannot be routed to any division")

    assert result.status == RequestStatus.UNROUTEABLE
    assert result.success is False
    assert result.errors


def test_v04_rejects_plan_when_scope_or_capability_mismatch_exists():
    class ScopedDivision(GenericDivision):
        def supports_request(self, request, classification=None):
            return False

    flow = MissionControlFlow(division_registry={"generic": ScopedDivision()})
    result = flow.handle_request("Request outside the allowed scope", business_division="generic")

    assert result.status == RequestStatus.UNROUTEABLE
    assert result.success is False


def test_v04_keeps_execution_history_for_every_request():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request("Keep a complete orchestration history", business_division="generic")

    assert len(flow.execution_history) >= 1
    assert flow.execution_history[-1].request_id == result.request_id


def test_v04_preserves_provider_independence_in_plan_metadata():
    flow = MissionControlFlow(division_registry={"generic": GenericDivision()})
    result = flow.handle_request("Workflow should remain provider-independent", business_division="generic")

    plan = result.metadata["execution_plan"]
    assert plan["provider"] is None
    assert plan["execution_mode"] == "controlled"


def test_v04_rejects_invalid_request_definition_without_division():
    class NoRouteDivision:
        name = "blocked"

        def supports_request(self, request, classification=None):
            return False

        def resolve_request(self, request, classification=None):
            return {"division_name": None, "is_supported": False, "is_routeable": False, "confidence": 0.0, "rationale": "Blocked by division policy.", "status": "unsupported"}

    flow = MissionControlFlow(division_registry={"blocked": NoRouteDivision()})
    result = flow.handle_request("A blocked request should fail safely", business_division="blocked")

    assert result.status in {RequestStatus.UNROUTEABLE, RequestStatus.FAILED}
    assert result.success is False
