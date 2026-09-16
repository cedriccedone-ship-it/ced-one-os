"""Compatibility dispatcher using the governed Mission Control service."""
from ced_one.mission_control.service import MissionControlService


class MissionDispatcher:
    def __init__(self, division_registry=None, *, runtime=None, policy=None):
        self.service = MissionControlService(division_registry, runtime=runtime, policy=policy)

    def dispatch(self, request, division_name):
        return self.service.handle_request(request.user_goal, business_division=division_name,
            request_type=request.request_type, priority=request.priority, source=request.source,
            context=request.context, metadata=request.metadata, constraints=request.constraints)


__all__ = ["MissionDispatcher"]
