"""Unsupported and unrouteable request handling for Mission Control v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnsupportedRequest:
    request_id: str
    reason: str
    supported: bool = False
    routeable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class UnsupportedRequestHandler:
    """Return structured result metadata for unsupported or unrouteable requests."""

    @staticmethod
    def build(request_id: str, reason: str, metadata: dict[str, Any] | None = None) -> UnsupportedRequest:
        return UnsupportedRequest(
            request_id=request_id,
            reason=reason,
            supported=False,
            routeable=False,
            metadata=metadata or {},
        )


__all__ = ["UnsupportedRequest", "UnsupportedRequestHandler"]
