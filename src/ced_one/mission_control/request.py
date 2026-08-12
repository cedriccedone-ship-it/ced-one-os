"""Request creation and normalization for Mission Control v0.1."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import MissionRequest, RequestStatus


class MissionRequestBuilder:
    """Create and normalize internal Mission Control request objects."""

    @staticmethod
    def from_user_goal(
        user_goal: str,
        *,
        request_type: str = "general",
        priority: str = "normal",
        source: str = "user",
        business_division: str | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
    ) -> MissionRequest:
        normalized = MissionRequest(
            user_goal=user_goal,
            request_type=request_type,
            priority=priority,
            source=source,
            business_division=business_division,
            context=context or {},
            metadata=metadata or {},
            constraints=constraints or [],
            status=RequestStatus.NORMALIZED,
        )
        return normalized


__all__ = ["MissionRequestBuilder"]
