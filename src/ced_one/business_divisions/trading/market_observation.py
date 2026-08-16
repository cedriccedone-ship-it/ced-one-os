"""Market observation capability for the first Trading Ecosystem vertical slice.

This module intentionally implements read-only, synthetic observation logic for the
controlled XAUUSD test path. It is not a trading strategy, market-truth engine,
provider adapter, or execution engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


@dataclass
class MarketObservationInput:
    symbol: str
    timestamp: str
    timeframe: str
    current_price: float
    open: float
    high: float
    low: float
    close: float
    recent_high: float
    recent_low: float
    session_context: dict[str, Any] = field(default_factory=dict)
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MarketObservationInput":
        return cls(
            symbol=str(payload["symbol"]),
            timestamp=str(payload["timestamp"]),
            timeframe=str(payload["timeframe"]),
            current_price=float(payload["current_price"]),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            recent_high=float(payload["recent_high"]),
            recent_low=float(payload["recent_low"]),
            session_context=dict(payload.get("session_context") or {}),
            source_metadata=dict(payload.get("source_metadata") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "current_price": self.current_price,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "recent_high": self.recent_high,
            "recent_low": self.recent_low,
            "session_context": self.session_context,
            "source_metadata": self.source_metadata,
        }


@dataclass
class MarketObservationResult:
    symbol: str
    timestamp: str
    timeframe: str
    market_bias: str
    market_structure: str
    current_price: float
    recent_high: float
    recent_low: float
    volatility_state: str
    session_context: dict[str, Any] = field(default_factory=dict)
    observed_levels: dict[str, Any] = field(default_factory=dict)
    observation_summary: str = ""
    evidence_score: float = 0.0
    source_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "market_bias": self.market_bias,
            "market_structure": self.market_structure,
            "current_price": self.current_price,
            "recent_high": self.recent_high,
            "recent_low": self.recent_low,
            "volatility_state": self.volatility_state,
            "session_context": self.session_context,
            "observed_levels": self.observed_levels,
            "observation_summary": self.observation_summary,
            "evidence_score": self.evidence_score,
            "source_metadata": self.source_metadata,
            "metadata": self.metadata,
        }


class MarketObservationValidator:
    """Validation rules for the controlled XAUUSD observation test path."""

    def validate_input(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> list[str]:
        errors: list[str] = []
        required_fields = [
            "symbol",
            "timestamp",
            "timeframe",
            "current_price",
            "open",
            "high",
            "low",
            "close",
            "recent_high",
            "recent_low",
        ]
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(f"Missing required input field: {field_name}")
        if not errors:
            if str(payload["symbol"]).upper() != "XAUUSD":
                errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")

            timeframe = str(payload["timeframe"]).upper()
            if timeframe not in VALID_TIMEFRAMES:
                errors.append(f"Invalid timeframe: {payload['timeframe']} is not in the allowed deterministic set {sorted(VALID_TIMEFRAMES)}")

            try:
                timestamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
            except ValueError:
                errors.append("Invalid timestamp: timestamp must be parseable ISO 8601.")
                timestamp = None
            else:
                if evaluation_time is not None and timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                if evaluation_time is not None and timestamp.tzinfo is not None:
                    delta_seconds = (evaluation_time - timestamp).total_seconds()
                    if delta_seconds > max_age_seconds:
                        errors.append(
                            "Stale timestamp: evaluation_time - timestamp exceeds the configured max_age_seconds."
                        )

            for key in ["current_price", "open", "high", "low", "close", "recent_high", "recent_low"]:
                value = payload.get(key)
                if value is None:
                    errors.append(f"Missing required numeric price field: {key}")
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    errors.append(f"Non-numeric value for {key}: expected float-like number.")
                    continue
                if numeric <= 0:
                    errors.append(f"Invalid numeric value for {key}: must be greater than 0.")

            try:
                high = float(payload["high"])
                low = float(payload["low"])
                open_price = float(payload["open"])
                close_price = float(payload["close"])
            except (TypeError, ValueError):
                pass
            else:
                if high < max(open_price, close_price):
                    errors.append("Inconsistent OHLC data: high must be greater than or equal to the maximum of open and close.")
                if low > min(open_price, close_price):
                    errors.append("Inconsistent OHLC data: low must be less than or equal to the minimum of open and close.")

            try:
                recent_high = float(payload["recent_high"])
                recent_low = float(payload["recent_low"])
                high = float(payload["high"])
                low = float(payload["low"])
            except (TypeError, ValueError):
                pass
            else:
                if recent_high < high:
                    errors.append("Inconsistent market range: recent_high must be greater than or equal to high.")
                if recent_low > low:
                    errors.append("Inconsistent market range: recent_low must be less than or equal to low.")

        return errors


class TradingMarketObservationCapability:
    """Provider-independent read-only market observation capability.

    This capability intentionally contains no provider identity, connector identity,
    broker logic, external data implementation details, or trade-execution behavior.
    """

    def __init__(self):
        self.name = "market_observation"
        self.contract = "trading.market_observation.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Synthetic read-only market observation for deterministic architecture validation."
        self.metadata = {
            "synthetic_observation_rule": True,
            "deterministic_observation_mode": True,
            "rule_source": "synthetic_test_contract",
            "observation_only": True,
            "advisory_output": False,
        }

    def validate_input(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> list[str]:
        validator = MarketObservationValidator()
        return validator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required = [
            "symbol",
            "timestamp",
            "timeframe",
            "market_bias",
            "market_structure",
            "current_price",
            "recent_high",
            "recent_low",
            "volatility_state",
            "observation_summary",
            "evidence_score",
        ]
        for field_name in required:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")
        if "entry" in payload or "stop_loss" in payload or "take_profit" in payload:
            errors.append("Advisory and execution fields are forbidden in this observation result.")
        if "BUY" in str(payload).upper() or "SELL" in str(payload).upper():
            errors.append("BUY/SELL instructions are forbidden in a market observation result.")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> MarketObservationResult:
        return MarketObservationResult(
            symbol=str(payload["symbol"]),
            timestamp=str(payload["timestamp"]),
            timeframe=str(payload["timeframe"]),
            market_bias=str(payload["market_bias"]),
            market_structure=str(payload["market_structure"]),
            current_price=float(payload["current_price"]),
            recent_high=float(payload["recent_high"]),
            recent_low=float(payload["recent_low"]),
            volatility_state=str(payload["volatility_state"]),
            session_context=dict(payload.get("session_context") or {}),
            observed_levels=dict(payload.get("observed_levels") or {}),
            observation_summary=str(payload.get("observation_summary") or ""),
            evidence_score=float(payload.get("evidence_score", 0.0)),
            source_metadata={
                "rule_source": "synthetic_test_contract",
                "synthetic_observation_rule": True,
                "deterministic_observation_mode": True,
                "observation_only": True,
                "advisory_output": False,
            },
        )


class MarketAnalysisSpecialist:
    """Deterministic market observation specialist for the Trading Division.

    This specialist may validate and describe market state only. It cannot mutate
    lifecycle state, self-approve, or issue trade execution commands.
    """

    def __init__(self):
        self.name = "market_analyst"
        self.division_name = "trading"
        self.capability_name = "market_observation"
        self.permission_scope = "read_only"

    def validate_binding(
        self,
        *,
        division_name: str,
        specialist_name: str,
        capability_name: str,
        permission_scope: str,
    ) -> bool:
        if division_name != "trading":
            return False
        if specialist_name != "market_analyst":
            return False
        if capability_name != "market_observation":
            return False
        if permission_scope != "read_only":
            return False
        return True

    def can_mutate_task_lifecycle(self) -> bool:
        return False

    def is_final_authority(self) -> bool:
        return False

    def requires_external_execution(self) -> bool:
        return False

    def requires_live_market_data(self) -> bool:
        return False

    def requires_external_ai(self) -> bool:
        return False

    def observe_market(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> MarketObservationResult:
        capability = TradingMarketObservationCapability()
        input_errors = capability.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if input_errors:
            return MarketObservationResult(
                symbol=str(payload.get("symbol", "unknown")).upper(),
                timestamp=str(payload.get("timestamp", "unknown")),
                timeframe=str(payload.get("timeframe", "unknown")),
                market_bias="neutral",
                market_structure="range",
                current_price=float(payload.get("current_price", 0.0) or 0.0),
                recent_high=float(payload.get("recent_high", 0.0) or 0.0),
                recent_low=float(payload.get("recent_low", 0.0) or 0.0),
                volatility_state="moderate",
                session_context=dict(payload.get("session_context") or {}),
                observed_levels={},
                observation_summary="Synthetic observation rejected due to invalid controlled market input.",
                evidence_score=0.0,
                source_metadata={
                    "rule_source": "synthetic_test_contract",
                    "synthetic_observation_rule": True,
                    "deterministic_observation_mode": True,
                    "observation_only": True,
                    "advisory_output": False,
                    "validation_errors": input_errors,
                    "status": "rejected",
                    "rejection_reason": "input_validation_failed",
                },
                metadata={"validation_errors": input_errors, "status": "rejected", "rejection_reason": "input_validation_failed"},
            )

        market_df = MarketObservationInput.from_payload(payload)
        market_bias = self._derive_bias(market_df)
        market_structure = self._derive_structure(market_df)
        volatility_state = self._derive_volatility(market_df)
        evidence_score = self._derive_evidence_score(market_df, market_bias, market_structure)
        result_payload = {
            "symbol": market_df.symbol,
            "timestamp": market_df.timestamp,
            "timeframe": market_df.timeframe,
            "market_bias": market_bias,
            "market_structure": market_structure,
            "current_price": market_df.current_price,
            "recent_high": market_df.recent_high,
            "recent_low": market_df.recent_low,
            "volatility_state": volatility_state,
            "session_context": market_df.session_context,
            "observed_levels": {
                "current": market_df.current_price,
                "recent_high": market_df.recent_high,
                "recent_low": market_df.recent_low,
                "range_high": market_df.recent_high,
                "range_low": market_df.recent_low,
            },
            "observation_summary": "Synthetic observation for architecture validation only.",
            "evidence_score": evidence_score,
            "source_metadata": {
                "rule_source": "synthetic_test_contract",
                "synthetic_observation_rule": True,
                "deterministic_observation_mode": True,
                "observation_only": True,
                "advisory_output": False,
            },
        }
        output_errors = capability.validate_output(result_payload)
        if output_errors:
            return MarketObservationResult(
                symbol=market_df.symbol,
                timestamp=market_df.timestamp,
                timeframe=market_df.timeframe,
                market_bias=market_bias,
                market_structure=market_structure,
                current_price=market_df.current_price,
                recent_high=market_df.recent_high,
                recent_low=market_df.recent_low,
                volatility_state=volatility_state,
                session_context=market_df.session_context,
                observed_levels={"current": market_df.current_price},
                observation_summary="Synthetic observation output failed schema validation.",
                evidence_score=evidence_score,
                source_metadata={
                    "rule_source": "synthetic_test_contract",
                    "synthetic_observation_rule": True,
                    "deterministic_observation_mode": True,
                    "observation_only": True,
                    "advisory_output": False,
                },
                metadata={"validation_errors": output_errors, "status": "failed", "rejection_reason": "output_validation_failed"},
            )

        return MarketObservationResult(
            symbol=market_df.symbol,
            timestamp=market_df.timestamp,
            timeframe=market_df.timeframe,
            market_bias=market_bias,
            market_structure=market_structure,
            current_price=market_df.current_price,
            recent_high=market_df.recent_high,
            recent_low=market_df.recent_low,
            volatility_state=volatility_state,
            session_context=market_df.session_context,
            observed_levels={
                "current": market_df.current_price,
                "recent_high": market_df.recent_high,
                "recent_low": market_df.recent_low,
            },
            observation_summary="Synthetic observation for architecture validation only.",
            evidence_score=evidence_score,
            source_metadata={
                "rule_source": "synthetic_test_contract",
                "synthetic_observation_rule": True,
                "deterministic_observation_mode": True,
                "observation_only": True,
                "advisory_output": False,
            },
            metadata={"status": "completed", "validation_errors": [], "source": "synthetic_test_contract"},
        )

    def observe_market_context(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> Any:
        from ced_one.business_divisions.trading.market_context import MarketContextAggregator

        input_payload = dict(payload)
        input_payload.setdefault("symbol", "XAUUSD")
        input_payload.setdefault("max_age_seconds", max_age_seconds)
        if evaluation_time is not None:
            input_payload["evaluation_time"] = evaluation_time.isoformat().replace("+00:00", "Z")
        if "timeframes" not in input_payload:
            input_payload["timeframes"] = {}
        aggregator = MarketContextAggregator()
        return aggregator.aggregate(input_payload)

    def analyze_market_structure(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> Any:
        from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer

        input_payload = dict(payload)
        input_payload.setdefault("symbol", "XAUUSD")
        if evaluation_time is not None:
            input_payload["evaluation_time"] = evaluation_time.isoformat().replace("+00:00", "Z")
        if "candle_history" not in input_payload:
            input_payload["candle_history"] = []
        analyzer = MarketStructureAnalyzer()
        return analyzer.analyze(input_payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    @staticmethod
    def _derive_bias(payload: MarketObservationInput) -> str:
        midpoint = (payload.recent_high + payload.recent_low) / 2.0
        range_size = payload.recent_high - payload.recent_low
        neutral_band = min(5.0, max(2.0, range_size * 0.2))

        if payload.current_price >= payload.recent_high:
            return "bullish"
        if payload.current_price <= payload.recent_low:
            return "bearish"

        if (
            abs(payload.current_price - midpoint) <= neutral_band
            and abs(payload.close - midpoint) <= neutral_band
            and abs(payload.close - payload.open) <= (neutral_band * 2.0)
        ):
            return "neutral"
        if payload.close > payload.open and payload.close > midpoint:
            return "bullish"
        if payload.close < payload.open and payload.close < midpoint:
            return "bearish"
        if payload.current_price > midpoint:
            return "bullish"
        if payload.current_price < midpoint:
            return "bearish"
        return "neutral"

    @staticmethod
    def _derive_structure(payload: MarketObservationInput) -> str:
        if payload.current_price > payload.recent_high and payload.close > payload.open:
            return "uptrend"
        if payload.current_price < payload.recent_low and payload.close < payload.open:
            return "downtrend"
        return "range"

    @staticmethod
    def _derive_volatility(payload: MarketObservationInput) -> str:
        range_size = payload.recent_high - payload.recent_low
        ratio = range_size / max(payload.current_price, 1.0)
        if ratio < 0.002:
            return "low"
        if ratio < 0.006:
            return "moderate"
        return "elevated"

    @staticmethod
    def _derive_evidence_score(payload: MarketObservationInput, bias: str, structure: str) -> float:
        score = 0.5
        if bias in {"bullish", "bearish"}:
            score += 0.2
        if structure in {"uptrend", "downtrend"}:
            score += 0.2
        if payload.recent_high >= payload.high and payload.recent_low <= payload.low:
            score += 0.1
        return min(score, 0.99)


MARKET_OBSERVATION = TradingMarketObservationCapability()
MARKET_ANALYST = MarketAnalysisSpecialist()

__all__ = [
    "MarketAnalysisSpecialist",
    "MarketObservationInput",
    "MarketObservationResult",
    "MarketObservationValidator",
    "MARKET_ANALYST",
    "MARKET_OBSERVATION",
    "TradingMarketObservationCapability",
]
