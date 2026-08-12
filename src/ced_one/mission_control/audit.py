"""Basic execution audit support for Mission Control v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuditEntry:
    request_id: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionAudit:
    """Stores lightweight execution history for Mission Control operations."""

    def __init__(self):
        self.entries: list[AuditEntry] = []

    def record(self, request_id: str, status: str, summary: str = "", metadata: dict[str, Any] | None = None) -> AuditEntry:
        entry = AuditEntry(
            request_id=request_id,
            status=status,
            summary=summary,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry


__all__ = ["AuditEntry", "ExecutionAudit"]
