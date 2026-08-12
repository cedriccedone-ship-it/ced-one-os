"""Authority validation for Mission Control v0.1."""

from __future__ import annotations

from typing import Any

from ced_one.mission_control.types import AuthorityValidationResult


class AuthorityValidator:
    """Ensure lower layers cannot override constitutional or core authority."""

    @staticmethod
    def validate(request_metadata: dict[str, Any] | None = None) -> AuthorityValidationResult:
        metadata = request_metadata or {}
        violations: list[str] = []
        blocked_by: list[str] = []

        if metadata.get("authority_override") is True:
            violations.append("A lower layer attempted to override the governing authority.")
            blocked_by.append("constitution")

        if metadata.get("core_override") is True:
            violations.append("A lower layer attempted to override Ced-One Core authority.")
            blocked_by.append("core")

        if not violations:
            return AuthorityValidationResult(
                valid=True,
                violations=[],
                blocked_by=[],
                message="Authority validation passed.",
            )

        return AuthorityValidationResult(
            valid=False,
            violations=violations,
            blocked_by=blocked_by,
            message="Authority validation failed; governance and core boundaries must be preserved.",
        )


__all__ = ["AuthorityValidator"]
