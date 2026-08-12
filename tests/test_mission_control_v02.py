from __future__ import annotations

from ced_one.mission_control import (
    ApprovalState,
    MissionControlOrchestrator,
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
            "confidence": 0.97,
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


def test_v02_request_is_classified_and_routed():
    orchestrator = MissionControlOrchestrator(division_registry={"trading": DummyDivision()})
    result = orchestrator.handle_request(
        "Assess a market outcome for a business objective",
        business_division="trading",
        metadata={"risk_level": "medium"},
    )

    assert result.status in {RequestStatus.COMPLETED, RequestStatus.APPROVED}
    assert result.division == "trading"
    assert result.success is True


def test_v02_unsupported_request_fails_safely():
    service = MissionControlService(division_registry={})
    result = service.handle_request("No valid division mapping")

    assert result.status == RequestStatus.UNROUTEABLE
    assert result.success is False
    assert result.errors


def test_v02_approval_gate_requires_pending_status():
    service = MissionControlService(division_registry={"trading": DummyDivision()})
    result = service.handle_request(
        "Perform a high-impact action",
        business_division="trading",
        metadata={"impact_level": "high", "approval_required": True},
    )

    assert result.status == RequestStatus.AWAITING_APPROVAL
    assert result.approval_state == ApprovalState.PENDING


def test_v02_authority_violation_is_blocked():
    service = MissionControlService(division_registry={"trading": DummyDivision()})
    result = service.handle_request(
        "Attempt to override hierarchy",
        business_division="trading",
        metadata={"authority_override": True},
    )

    assert result.status == RequestStatus.FAILED
    assert any("authority" in error.lower() for error in result.errors)


def test_v02_orchestrator_tracks_execution_history():
    orchestrator = MissionControlOrchestrator(division_registry={"trading": DummyDivision()})
    result = orchestrator.handle_request("Routine orchestration request", business_division="trading")

    assert len(orchestrator.execution_history) >= 1
    assert orchestrator.execution_history[-1].request_id == result.request_id


def test_v02_generic_classifier_tags_requests():
    from ced_one.mission_control.classifier import RequestClassifier
    request = MissionRequest(user_goal="Support a new development initiative")
    classification = RequestClassifier.classify(request)

    assert "development" in classification.domain_tags
    assert classification.risk_level in {"low", "medium", "high", "critical"}
