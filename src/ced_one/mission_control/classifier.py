"""Request classification for Mission Control v0.2."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import MissionRequest, RequestClassification


class RequestClassifier:
    """Classify a request into general routing categories.

    This classifier is intentionally generic and provider-independent. It does not
    encode trading logic, provider behavior, or external integrations.
    """

    @staticmethod
    def classify(request: MissionRequest) -> RequestClassification:
        user_goal = request.user_goal.lower()
        metadata = request.metadata or {}

        tags: list[str] = []
        if "market" in user_goal or "trading" in user_goal:
            tags.append("trading")
        if "sales" in user_goal:
            tags.append("sales")
        if "marketing" in user_goal:
            tags.append("marketing")
        if "development" in user_goal:
            tags.append("development")
        if "support" in user_goal:
            tags.append("support")
        if not tags:
            tags.append("general")

        risk_level = str(metadata.get("risk_level", "low")).lower()
        if risk_level not in {"low", "medium", "high", "critical"}:
            risk_level = "low"

        division_hint = metadata.get("business_division")
        if isinstance(division_hint, str):
            division_hint = division_hint
        else:
            division_hint = None

        confidence = 0.6 if division_hint else 0.5
        if risk_level in {"high", "critical"}:
            confidence = max(confidence, 0.8)

        return RequestClassification(
            domain_tags=tags,
            risk_level=risk_level,
            confidence=confidence,
            division_hint=division_hint,
            rationale="Generic classification based on request metadata and goal content.",
        )


__all__ = ["RequestClassifier"]
