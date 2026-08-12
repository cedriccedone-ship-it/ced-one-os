from __future__ import annotations

from ced_one.mission_control import MissionControlFlow, MissionRequest, RequestStatus


class TradingRouter:
    name = "trading"

    def supports_request(self, request, classification=None):
        text = f"{request.user_goal} {request.request_type} {request.business_division or ''}".lower()
        if "trading" in text or "market" in text or "xauusd" in text:
            return True
        if classification is not None and "trading" in classification.domain_tags:
            return True
        return False

    def resolve_request(self, request, classification=None):
        return {
            "division_name": self.name,
            "is_supported": True,
            "is_routeable": True,
            "confidence": 0.95,
            "rationale": "Trading Division accepted the request for routing.",
            "specialist_name": "market_analyst",
            "capability_name": "coordination",
            "status": "resolved",
        }

    def resolve_specialist(self, request):
        return {
            "name": "market_analyst",
            "division_name": self.name,
            "permission_scope": "read_only",
            "rationale": "Assigned for a domain-specific routing example.",
        }

    def resolve_capability(self, request):
        return {
            "name": "coordination",
            "division_name": self.name,
            "contract": "generic_coordination",
            "rationale": "Selected a reusable capability contract.",
        }


def test_v03_end_to_end_routing_flow():
    flow = MissionControlFlow(division_registry={"trading": TradingRouter()})
    result = flow.handle_request(
        "Route a trading request for XAUUSD analysis",
        business_division="trading",
        metadata={"risk_level": "medium"},
    )

    assert result.status == RequestStatus.COMPLETED
    assert result.division == "trading"
    assert result.specialist == "market_analyst"
    assert result.capability == "coordination"
    assert result.success is True


def test_v03_unrouteable_request_failure():
    flow = MissionControlFlow(division_registry={})
    result = flow.handle_request("This request cannot be matched to a division")

    assert result.status == RequestStatus.UNROUTEABLE
    assert result.success is False
    assert result.errors


def test_v03_authority_violation_is_blocked():
    flow = MissionControlFlow(division_registry={"trading": TradingRouter()})
    result = flow.handle_request(
        "Request with authority override",
        business_division="trading",
        metadata={"authority_override": True},
    )

    assert result.status == RequestStatus.FAILED
    assert any("authority" in error.lower() for error in result.errors)


def test_v03_approval_gate_blocks_high_impact_flow():
    flow = MissionControlFlow(division_registry={"trading": TradingRouter()})
    result = flow.handle_request(
        "Perform a high-impact approval-gated action",
        business_division="trading",
        metadata={"impact_level": "high", "approval_required": True},
    )

    assert result.status == RequestStatus.AWAITING_APPROVAL
    assert result.success is False


def test_v03_execution_history_is_recorded():
    flow = MissionControlFlow(division_registry={"trading": TradingRouter()})
    result = flow.handle_request("Routine routing flow", business_division="trading")

    assert len(flow.execution_history) >= 1
    assert flow.execution_history[-1].request_id == result.request_id
