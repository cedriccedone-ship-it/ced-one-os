"""Decision records for Mission Control v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoutingDecision:
    request_id: str
    division_name: str | None
    classification: str | None
    confidence: float
    rationale: str
    routeable: bool
    supported: bool
    specialist_name: str | None = None
    capability_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["RoutingDecision"]
