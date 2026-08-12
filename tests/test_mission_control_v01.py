from __future__ import annotations

from ced_one.mission_control import (
    ApprovalState,
    MissionControlService,
    MissionRequest,
    RequestStatus,
)


class DummyDivision:
    name = "trading"

    def classify_request(self, request):
        return {
            "division_name": self.name,
            "status": "routeable",
            "rationale": "Division selected for test routing.",
            "confidence": 1.0,
            "is_supported": True,
            "is_routeable": True,
        }

    def identify_specialist(self, request):
        return {
            "name": "market_analyst",
            "division_name": self.name,
            "permission_scope": "read_only",
            "rationale": "Assigned for testing.",
        }

    def identify_capability(self, request):
        return {
            "name": "coordination",
            "division_name": self.name,
            "contract": "generic_coordination",
            "rationale": "Assigned for testing.",
        }

    def handle_request(self, request):
        return {
            "request_id": request.request_id,
            "status": "completed",
            "division": self.name,
            "specialist": "market_analyst",
            "capability": "coordination",
            "summary": "Division processed the request successfully.",
            "result_payload": {"ok": True},
            "approval_state": "not_required",
            "errors": [],
            "success": True,
            "metadata": {"division": self.name},
        }


def test_request_creation_and_status_defaults():
    request = MissionRequest(user_goal="Assess a business objective")

    assert request.request_id
    assert request.status == RequestStatus.RECEIVED
    assert request.user_goal == "Assess a business objective"
    assert request.business_division is None


def test_router_routes_registered_division():
    service = MissionControlService(division_registry={"trading": DummyDivision()})
    result = service.handle_request(
        "Assess a business objective",
        business_division="trading",
    )

    assert result.status in {RequestStatus.COMPLETED, RequestStatus.APPROVED}
    assert result.division == "trading"


def test_unrouteable_request_returns_safe_failure():
    service = MissionControlService(division_registry={})
    result = service.handle_request("Request with no division mapping")

    assert result.status == RequestStatus.UNROUTEABLE
    assert result.success is False
    assert result.errors


def test_high_impact_request_requires_approval():
    service = MissionControlService(division_registry={"trading": DummyDivision()})

    result = service.handle_request(
        "Finalize a high-impact action",
        business_division="trading",
        metadata={"impact_level": "high", "approval_required": True},
    )

    assert result.status == RequestStatus.AWAITING_APPROVAL
    assert result.approval_state == ApprovalState.PENDING


def test_authority_validator_blocks_lower_layer_override():
    service = MissionControlService(division_registry={"trading": DummyDivision()})
    result = service.handle_request(
        "Request with improper override",
        business_division="trading",
        metadata={"authority_override": True},
    )

    assert result.status == RequestStatus.FAILED
    assert any("authority" in error.lower() for error in result.errors)


def test_service_tracks_request_history():
    service = MissionControlService(division_registry={"trading": DummyDivision()})
    result = service.handle_request("Track a routine request", business_division="trading")

    assert len(service.execution_history) >= 1
    assert service.execution_history[-1].request_id == result.request_id
