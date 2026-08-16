"""Trading division package for Ced-One OS.

This is the first concrete business division. It is intentionally generic in
shape and does not implement any trading execution behavior.
"""

from ced_one.business_divisions.trading.capabilities import ANALYSIS, COORDINATION, MARKET_OBSERVATION, TradingCapability
from ced_one.business_divisions.trading.division import TradingDivision
from ced_one.business_divisions.trading.market_context import MarketContextAggregator, MarketContextInput, MarketContextResult, MarketContextValidator
from ced_one.business_divisions.trading.market_observation import (
    MarketAnalysisSpecialist,
    MarketObservationInput,
    MarketObservationResult,
    MarketObservationValidator,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.specialists import MARKET_ANALYST, RISK_SPECIALIST, TradingSpecialist

__all__ = [
    "TradingDivision",
    "TradingDivisionResolver",
    "TradingSpecialist",
    "TradingCapability",
    "MarketAnalysisSpecialist",
    "MarketObservationInput",
    "MarketObservationResult",
    "MarketObservationValidator",
    "MarketContextInput",
    "MarketContextResult",
    "MarketContextValidator",
    "MarketContextAggregator",
    "MARKET_ANALYST",
    "RISK_SPECIALIST",
    "COORDINATION",
    "ANALYSIS",
    "MARKET_OBSERVATION",
]
