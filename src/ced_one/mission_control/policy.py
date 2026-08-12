"""Safety and policy rules for Mission Control v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SafetyCheck:
    passed: bool
    reason: str = ""
    policy_name: str = "generic"
    metadata: dict[str, Any] = field(default_factory=dict)


class SafetyPolicy:
    """Minimal safety wrapper to enforce built-in constraints."""

    @staticmethod
    def evaluate(metadata: dict[str, Any] | None = None) -> SafetyCheck:
        data = metadata or {}
        if data.get("authority_override") is True:
            return SafetyCheck(
                passed=False,
                reason="A lower layer attempted to override authority.",
                policy_name="authority",
                metadata=data,
            )
        if data.get("core_override") is True:
            return SafetyCheck(
                passed=False,
                reason="A lower layer attempted to override Ced-One Core authority.",
                policy_name="core",
                metadata=data,
            )
        return SafetyCheck(
            passed=True,
            reason="No authority violation detected.",
            policy_name="authority",
            metadata=data,
        )


__all__ = ["SafetyCheck", "SafetyPolicy"]
