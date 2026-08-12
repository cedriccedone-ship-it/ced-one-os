"""Business-division registry for Mission Control v0.2."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class DivisionRegistry:
    """A minimal registry for business divisions.

    Mission Control remains generic by not hard-coding any domain-specific
    division logic here. Divisions are registered explicitly by the caller.
    """

    def __init__(self, divisions: dict[str, Any] | None = None):
        self._divisions = dict(divisions or {})

    def register(self, name: str, division: Any) -> None:
        self._divisions[name] = division

    def unregister(self, name: str) -> None:
        self._divisions.pop(name, None)

    def get(self, name: str) -> Any | None:
        return self._divisions.get(name)

    def names(self) -> Iterable[str]:
        return list(self._divisions.keys())

    def as_dict(self) -> dict[str, Any]:
        return dict(self._divisions)


__all__ = ["DivisionRegistry"]
