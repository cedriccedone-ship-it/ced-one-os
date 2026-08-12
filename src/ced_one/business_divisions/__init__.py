"""Business division package for Ced-One OS.

This module defines the generic business-division abstraction that sits between
Mission Control and the specialist/capability layers.
"""

from ced_one.business_divisions.base import BusinessDivision
from ced_one.business_divisions.trading import TradingDivision

__all__ = ["BusinessDivision", "TradingDivision"]
