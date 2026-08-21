"""Deterministic current close classification within the Slice #11 range."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from ced_one.business_divisions.trading.structural_dealing_range_intelligence import (
    RULE_VERSION as STRUCTURAL_RANGE_RULE_VERSION,
)

RULE_VERSION = "premium_discount_intelligence_v1"
CONTRACT = "trading.premium_discount_intelligence.v1"
PRICE_SOURCE = "close"
VALID_CLASSIFICATIONS = {"below_range", "discount", "equilibrium", "premium", "above_range"}


@dataclass(frozen=True)
class PremiumDiscountObservationInput:
    source_result: Any
    timestamp: str
    close: float

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PremiumDiscountObservationInput":
        observation = payload.get("observation")
        if not isinstance(observation, dict):
            raise ValueError("Invalid premium discount input: observation must be a dictionary.")
        if "timestamp" not in observation or "close" not in observation:
            raise ValueError("Invalid premium discount input: observation requires timestamp and close.")
        try:
            close = float(observation["close"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid premium discount input: close must be numeric.") from exc
        if not math.isfinite(close):
            raise ValueError("Invalid premium discount input: close must be finite.")
        return cls(
            source_result=payload.get("source_result"),
            timestamp=str(observation["timestamp"]),
            close=close,
        )


@dataclass
class PremiumDiscountResult:
    symbol: str
    timeframe: str
    timestamp: str
    observation: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "observation": self.observation,
            "diagnostics": self.diagnostics,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class PremiumDiscountValidator:
    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @classmethod
    def _source_dict(cls, source_result: Any) -> dict[str, Any]:
        if hasattr(source_result, "to_dict"):
            source_result = source_result.to_dict()
        if not isinstance(source_result, dict):
            raise ValueError("Invalid premium discount source: expected a StructuralDealingRangeResult or dictionary.")
        required = [
            "symbol", "timeframe", "timestamp", "structural_ranges", "current_range",
            "summary", "diagnostics", "evidence", "metadata",
        ]
        missing = [name for name in required if name not in source_result]
        if missing:
            raise ValueError(f"Invalid premium discount source: missing fields {missing}.")
        if not isinstance(source_result["structural_ranges"], list):
            raise ValueError("Invalid premium discount source: structural_ranges must be a list.")
        if not isinstance(source_result["evidence"], dict) or not isinstance(source_result["metadata"], dict):
            raise ValueError("Invalid premium discount source: evidence and metadata must be dictionaries.")
        cls._parse_timestamp(source_result["timestamp"])
        if source_result["evidence"].get("structural_range_rule_version") != STRUCTURAL_RANGE_RULE_VERSION:
            raise ValueError("Invalid premium discount source: unsupported structural range rule version.")
        return source_result

    @classmethod
    def _range_dict(cls, current_range: Any, observation_timestamp: str) -> dict[str, Any]:
        if not isinstance(current_range, dict):
            raise ValueError("Invalid premium discount source: current_range must be a dictionary or None.")
        required = [
            "range_id", "range_low", "range_high", "range_width", "confirmed_at", "created_at",
            "source_structure_rule_version", "identity_scope", "evidence",
        ]
        missing = [name for name in required if name not in current_range]
        if missing:
            raise ValueError(f"Invalid premium discount source: current_range missing fields {missing}.")
        range_id = current_range["range_id"]
        if not isinstance(range_id, str) or not range_id:
            raise ValueError("Invalid premium discount source: current_range range_id must be non-empty.")
        try:
            range_low = float(current_range["range_low"])
            range_high = float(current_range["range_high"])
            range_width = float(current_range["range_width"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid premium discount source: range geometry must be numeric.") from exc
        if not all(math.isfinite(value) for value in [range_low, range_high, range_width]):
            raise ValueError("Invalid premium discount source: range geometry must be finite.")
        if range_high <= range_low:
            raise ValueError("Invalid premium discount source: range_high must be greater than range_low.")
        if range_width != range_high - range_low:
            raise ValueError("Invalid premium discount source: range_width is inconsistent with range boundaries.")
        if current_range["source_structure_rule_version"] != "market_structure_v1":
            raise ValueError("Invalid premium discount source: unsupported source structure rule version.")
        if current_range["identity_scope"] != "snapshot_deterministic":
            raise ValueError("Invalid premium discount source: unsupported identity scope.")
        if not isinstance(current_range["evidence"], dict):
            raise ValueError("Invalid premium discount source: current_range evidence must be a dictionary.")
        for evidence_field in ["first_pivot_reference_id", "second_pivot_reference_id", "pairing_rule"]:
            if not current_range["evidence"].get(evidence_field):
                raise ValueError(f"Invalid premium discount source: current_range evidence missing {evidence_field}.")
        confirmed_at = cls._parse_timestamp(current_range["confirmed_at"])
        created_at = cls._parse_timestamp(current_range["created_at"])
        observation_at = cls._parse_timestamp(observation_timestamp)
        if created_at != confirmed_at or confirmed_at > observation_at:
            raise ValueError("Invalid premium discount source: range confirmation is not causally available.")
        return current_range

    @classmethod
    def validate_input(cls, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        if "source_result" not in payload:
            return ["Missing required input field: source_result."]
        try:
            input_model = PremiumDiscountObservationInput.from_payload(payload)
            source = cls._source_dict(input_model.source_result)
            if str(source["timestamp"]) != input_model.timestamp:
                raise ValueError("Observation timestamp must exactly match source_result timestamp.")
            cls._parse_timestamp(input_model.timestamp)
            if source["current_range"] is not None:
                cls._range_dict(source["current_range"], input_model.timestamp)
        except (TypeError, ValueError) as exc:
            return [str(exc)]
        return []


class PremiumDiscountIntelligenceCapability:
    def __init__(self):
        self.name = "premium_discount_intelligence"
        self.contract = CONTRACT
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual classification of a current candle close within the authoritative structural dealing range."
        self.metadata = {
            "deterministic_premium_discount_intelligence": True,
            "current_observation_only": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "identity_scope": "snapshot_deterministic",
        }

    def validate_input(self, payload: Any, **_: Any) -> list[str]:
        return PremiumDiscountValidator.validate_input(payload)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        required = ["symbol", "timeframe", "timestamp", "observation", "diagnostics", "evidence", "metadata"]
        return [f"Missing required output field: {name}" for name in required if name not in payload]


class PremiumDiscountIntelligenceSpecialist:
    def __init__(self):
        self.name = "premium_discount_analyst"
        self.division_name = "trading"
        self.capability_name = "premium_discount_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == self.name
            and capability_name == self.capability_name
            and permission_scope == "read_only"
        )

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

    def analyze_premium_discount(self, payload: dict[str, Any], **_: Any) -> PremiumDiscountResult:
        return PremiumDiscountAnalyzer().analyze(payload)


class PremiumDiscountAnalyzer:
    @staticmethod
    def _hash_id(parts: list[Any]) -> str:
        encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
        return "premium_discount_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _classify(price: float, range_low: float, equilibrium: float, range_high: float) -> str:
        if price < range_low:
            return "below_range"
        if price < equilibrium:
            return "discount"
        if price == equilibrium:
            return "equilibrium"
        if price <= range_high:
            return "premium"
        return "above_range"

    def analyze(self, payload: dict[str, Any]) -> PremiumDiscountResult:
        errors = PremiumDiscountValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid premium discount input: " + "; ".join(errors))
        input_model = PremiumDiscountObservationInput.from_payload(payload)
        source = PremiumDiscountValidator._source_dict(input_model.source_result)
        current_range = source["current_range"]
        source_range_count = len(source["structural_ranges"])
        base_diagnostics = {
            "range_available": current_range is not None,
            "observation_emitted": False,
            "classification": None,
            "source_range_id": None if current_range is None else current_range["range_id"],
            "source_range_count": source_range_count,
            "identity_scope": "snapshot_deterministic",
        }
        base_evidence = {
            "source_capability_contract": "trading.structural_dealing_range_intelligence.v1",
            "source_structural_range_rule_version": STRUCTURAL_RANGE_RULE_VERSION,
            "source_range_id": None if current_range is None else current_range["range_id"],
            "observation_timestamp": input_model.timestamp,
            "observation_price": input_model.close,
            "price_source": PRICE_SOURCE,
            "equilibrium_formula": "range_low + ((range_high - range_low) / 2)",
            "range_position_formula": "(observation_price - range_low) / (range_high - range_low)",
            "classification_boundaries": {
                "below_range": "price < range_low",
                "discount": "range_low <= price < equilibrium",
                "equilibrium": "price == equilibrium",
                "premium": "equilibrium < price <= range_high",
                "above_range": "price > range_high",
            },
            "identity_scope": "snapshot_deterministic",
        }
        if current_range is None:
            return PremiumDiscountResult(
                symbol=str(source["symbol"]),
                timeframe=str(source["timeframe"]),
                timestamp=input_model.timestamp,
                diagnostics=base_diagnostics,
                evidence=base_evidence,
                metadata={
                    "deterministic_premium_discount_intelligence": True,
                    "current_observation_only": True,
                    "observation_only": True,
                    "advisory_output": False,
                    "strategy_output": False,
                    "execution_output": False,
                    "identity_scope": "snapshot_deterministic",
                },
            )

        PremiumDiscountValidator._range_dict(current_range, input_model.timestamp)
        range_low = float(current_range["range_low"])
        range_high = float(current_range["range_high"])
        equilibrium = range_low + ((range_high - range_low) / 2)
        range_position = (input_model.close - range_low) / (range_high - range_low)
        classification = self._classify(input_model.close, range_low, equilibrium, range_high)
        observation_id = self._hash_id([current_range["range_id"], input_model.timestamp, PRICE_SOURCE, RULE_VERSION])
        observation = {
            "observation_id": observation_id,
            "observation_timestamp": input_model.timestamp,
            "observation_price": input_model.close,
            "price_source": PRICE_SOURCE,
            "range_id": current_range["range_id"],
            "range_low": range_low,
            "equilibrium": equilibrium,
            "range_high": range_high,
            "range_position": range_position,
            "classification": classification,
            "identity_scope": "snapshot_deterministic",
        }
        base_diagnostics.update(
            observation_emitted=True,
            classification=classification,
        )
        base_evidence.update(
            source_range_identity_scope=current_range["identity_scope"],
            range_low=range_low,
            equilibrium=equilibrium,
            range_high=range_high,
            range_position=range_position,
            classification=classification,
        )
        return PremiumDiscountResult(
            symbol=str(source["symbol"]),
            timeframe=str(source["timeframe"]),
            timestamp=input_model.timestamp,
            observation=observation,
            diagnostics=base_diagnostics,
            evidence=base_evidence,
            metadata={
                "deterministic_premium_discount_intelligence": True,
                "current_observation_only": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "identity_scope": "snapshot_deterministic",
            },
        )


PREMIUM_DISCOUNT_INTELLIGENCE = PremiumDiscountAnalyzer()

__all__ = [
    "PremiumDiscountAnalyzer",
    "PremiumDiscountObservationInput",
    "PremiumDiscountResult",
    "PremiumDiscountValidator",
    "PremiumDiscountIntelligenceCapability",
    "PremiumDiscountIntelligenceSpecialist",
    "PREMIUM_DISCOUNT_INTELLIGENCE",
    "RULE_VERSION",
]