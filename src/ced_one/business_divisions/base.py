"""Business division abstractions for Ced-One OS.

These contracts are intentionally generic and do not define trading behavior,
provider integrations, market strategies, or mission execution logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable


class BusinessDivision(ABC):
    """Abstract business division boundary.

    A business division sits between Mission Control and specialized operational
    components. It coordinates reusable specialists and capabilities for a domain
    without embedding provider-specific or trade-specific behavior.
    """

    name: str
    scope: str

    @abstractmethod
    def get_name(self) -> str:
        """Return the division's canonical name."""

    @abstractmethod
    def get_scope(self) -> str:
        """Return the business scope in a neutral, generic form."""

    @abstractmethod
    def get_specialist_names(self) -> Iterable[str]:
        """Return the specialist names available to this division."""

    @abstractmethod
    def get_capability_names(self) -> Iterable[str]:
        """Return the capability names available to this division."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return a structured description of the division."""
