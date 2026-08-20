"""Deterministic structural dealing ranges composed from Slice #3 pivots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re
from typing import Any

from ced_one.business_divisions.trading.market_structure import (
    MarketStructureAnalyzer,
    MarketStructureValidator,
)

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
STRUCTURE_RULE_VERSION = "market_structure_v1"
RULE_VERSION = "structural_dealing_range_intelligence_v1"


@dataclass(frozen=True)
class StructuralDealingRangeConfig:
    maximum_ranges: int = 50

    def validate(self) -> list[str]:
        if isinstance(self.maximum_ranges, bool) or not isinstance(self.maximum_ranges, int):
            return ["Invalid config field maximum_ranges: must be an integer."]
        if not 1 <= self.maximum_ranges <= 1000:
            return ["Invalid config field maximum_ranges: must be between 1 and 1000."]
        return []

    @classmethod
    def from_payload(cls, payload: Any | None) -> "StructuralDealingRangeConfig":
        if payload is None:
            return cls()
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid structural dealing range config: config must be a dictionary or StructuralDealingRangeConfig.")
        unknown = sorted(set(payload) - {"maximum_ranges"})
        if unknown:
            raise ValueError(f"Invalid structural dealing range config: unknown fields {unknown}.")
        config = cls(maximum_ranges=payload.get("maximum_ranges", cls.maximum_ranges))
        errors = config.validate()
        if errors:
            raise ValueError("Invalid structural dealing range config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, int]:
        return {"maximum_ranges": self.maximum_ranges}


@dataclass
class StructuralDealingRangeInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: StructuralDealingRangeConfig = field(default_factory=StructuralDealingRangeConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StructuralDealingRangeInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=StructuralDealingRangeConfig.from_payload(payload.get("config")),
        )


@dataclass
class StructuralDealingRangeResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    structural_ranges: list[dict[str, Any]] = field(default_factory=list)
    current_range: dict[str, Any] | None = None
    summary: dict[str, int] = field(default_factory=dict)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_time": self.evaluation_time,
            "timestamp": self.timestamp,
            "scanned_candle_count": self.scanned_candle_count,
            "structural_ranges": self.structural_ranges,
            "current_range": self.current_range,
            "summary": self.summary,
            "diagnostics": self.diagnostics,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class StructuralDealingRangeValidator:
    @staticmethod
    def validate_input(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        if str(payload.get("symbol", "")).upper() != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")
        timeframe = str(payload.get("timeframe", "")).upper()
        if timeframe not in VALID_TIMEFRAMES:
            errors.append(f"Unsupported timeframe: {timeframe or '<missing>'} is not in the allowed deterministic set {sorted(VALID_TIMEFRAMES)}")
        if payload.get("evaluation_time") is None:
            errors.append("Missing required evaluation_time.")
        else:
            try:
                datetime.fromisoformat(str(payload["evaluation_time"]).replace("Z", "+00:00"))
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")
        try:
            StructuralDealingRangeConfig.from_payload(payload.get("config"))
        except ValueError as exc:
            errors.append(str(exc))
        errors.extend(MarketStructureValidator.validate_input(payload))
        return errors


class StructuralDealingRangeIntelligenceCapability:
    def __init__(self):
        self.name = "structural_dealing_range_intelligence"
        self.contract = "trading.structural_dealing_range_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual structural dealing range construction from confirmed Slice #3 pivot evidence."
        self.metadata = {
            "deterministic_structural_dealing_range_intelligence": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "identity_scope": "snapshot_deterministic",
        }

    def validate_input(self, payload: dict[str, Any], **_: Any) -> list[str]:
        return StructuralDealingRangeValidator.validate_input(payload)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        required = [
            "symbol", "timeframe", "evaluation_time", "timestamp", "scanned_candle_count",
            "structural_ranges", "current_range", "summary", "diagnostics", "evidence", "metadata",
        ]
        errors = [f"Missing required output field: {name}" for name in required if name not in payload]
        forbidden = [
            "buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "target",
            "signal", "setup", "probability", "confidence", "recommendation", "expected_direction",
            "equilibrium", "premium", "discount", "range_position", "distance_to_equilibrium",
            "bullish_setup", "bearish_setup", "execution_command",
        ]
        text = str(payload).lower()
        errors.extend(f"Forbidden advisory or later-slice term detected: {term}" for term in forbidden if re.search(rf"\b{re.escape(term)}\b", text))
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> StructuralDealingRangeResult:
        return StructuralDealingRangeAnalyzer().analyze(payload)


class StructuralDealingRangeIntelligenceSpecialist:
    def __init__(self):
        self.name = "structural_dealing_range_analyst"
        self.division_name = "trading"
        self.capability_name = "structural_dealing_range_intelligence"
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

    def analyze_structural_ranges(self, payload: dict[str, Any], **_: Any) -> StructuralDealingRangeResult:
        return StructuralDealingRangeAnalyzer().analyze(payload)


class StructuralDealingRangeAnalyzer:
    @staticmethod
    def _hash_id(parts: list[Any], prefix: str) -> str:
        encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
        return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def _pivot_reference(cls, pivot_type: str, source_index: int, source_timestamp: str, price: float, rule_version: str) -> str:
        return cls._hash_id([rule_version, pivot_type, source_index, source_timestamp, price], "pivot_")

    @staticmethod
    def _pivot_price(pivot_type: str, source: dict[str, Any]) -> float:
        return float(source["high"] if pivot_type == "high" else source["low"])

    @classmethod
    def _confirmed_pivots(
        cls,
        source_result: Any,
        candle_history: list[dict[str, Any]],
        rule_version: str,
    ) -> tuple[list[dict[str, Any]], int, int, int, int]:
        all_sources = [("high", item) for item in source_result.evidence.get("swing_highs", [])]
        all_sources.extend(("low", item) for item in source_result.evidence.get("swing_lows", []))
        confirmed: list[dict[str, Any]] = []
        terminal_count = 0
        confirmed_high_count = 0
        confirmed_low_count = 0
        for pivot_type, source in all_sources:
            source_index = int(source["index"])
            source_timestamp = str(source["timestamp"])
            confirmed_index = source_index + 1
            if confirmed_index >= len(candle_history):
                terminal_count += 1
                continue
            price = cls._pivot_price(pivot_type, source)
            confirmed_pivot = {
                "pivot_reference_id": cls._pivot_reference(pivot_type, source_index, source_timestamp, price, rule_version),
                "pivot_type": pivot_type,
                "source_index": source_index,
                "source_timestamp": source_timestamp,
                "price": price,
                "confirmed_index": confirmed_index,
                "confirmed_at": str(candle_history[confirmed_index]["timestamp"]),
                "source_structure_rule_version": rule_version,
                "identity_scope": "snapshot_deterministic",
            }
            confirmed.append(confirmed_pivot)
            if pivot_type == "high":
                confirmed_high_count += 1
            else:
                confirmed_low_count += 1
        return confirmed, terminal_count, confirmed_high_count, confirmed_low_count, len(all_sources)

    @staticmethod
    def _collapse(ordered: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        collapsed: list[dict[str, Any]] = []
        same_type_run_count = 0
        index = 0
        while index < len(ordered):
            pivot_type = ordered[index]["pivot_type"]
            end = index + 1
            while end < len(ordered) and ordered[end]["pivot_type"] == pivot_type:
                end += 1
            run = ordered[index:end]
            if len(run) > 1:
                same_type_run_count += 1
            if pivot_type == "high":
                retained = max(run, key=lambda item: (item["price"], item["source_index"], item["source_timestamp"], item["pivot_reference_id"]))
            else:
                retained = min(run, key=lambda item: (item["price"], -item["source_index"], item["source_timestamp"], item["pivot_reference_id"]))
            collapsed.append(retained)
            index = end
        return collapsed, same_type_run_count

    @classmethod
    def _range_record(cls, first: dict[str, Any], second: dict[str, Any], rule_version: str) -> dict[str, Any] | None:
        if first["pivot_type"] == second["pivot_type"]:
            return None
        range_low = min(first["price"], second["price"])
        range_high = max(first["price"], second["price"])
        range_width = range_high - range_low
        if range_width <= 0:
            return None
        chronological_order = "low_to_high" if first["pivot_type"] == "low" else "high_to_low"
        range_id = cls._hash_id(
            [first["pivot_reference_id"], second["pivot_reference_id"], chronological_order, rule_version],
            "range_",
        )
        confirmed_at = max(first["confirmed_at"], second["confirmed_at"])
        return {
            "range_id": range_id,
            "range_low": range_low,
            "range_high": range_high,
            "range_width": range_width,
            "chronological_order": chronological_order,
            "first_pivot_type": first["pivot_type"],
            "first_pivot_source_index": first["source_index"],
            "first_pivot_source_timestamp": first["source_timestamp"],
            "first_pivot_confirmed_at": first["confirmed_at"],
            "first_pivot_price": first["price"],
            "second_pivot_type": second["pivot_type"],
            "second_pivot_source_index": second["source_index"],
            "second_pivot_source_timestamp": second["source_timestamp"],
            "second_pivot_confirmed_at": second["confirmed_at"],
            "second_pivot_price": second["price"],
            "confirmed_at": confirmed_at,
            "created_at": confirmed_at,
            "source_structure_rule_version": rule_version,
            "identity_scope": "snapshot_deterministic",
            "evidence": {
                "first_pivot_reference_id": first["pivot_reference_id"],
                "second_pivot_reference_id": second["pivot_reference_id"],
                "pairing_rule": "adjacent_opposite_pivots_after_same_type_run_collapse",
            },
        }

    def analyze(self, payload: dict[str, Any]) -> StructuralDealingRangeResult:
        errors = StructuralDealingRangeValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid structural dealing range input: " + "; ".join(errors))
        input_model = StructuralDealingRangeInput.from_payload(payload)
        config = input_model.config
        source_result = MarketStructureAnalyzer().analyze(payload)
        rule_version = str(source_result.metadata.get("structure_rule_version", STRUCTURE_RULE_VERSION))
        confirmed, terminal_count, confirmed_high_count, confirmed_low_count, source_count = self._confirmed_pivots(
            source_result, input_model.candle_history, rule_version
        )
        ordered = sorted(
            confirmed,
            key=lambda item: (item["source_index"], item["source_timestamp"], item["pivot_type"], item["pivot_reference_id"]),
        )
        collapsed, same_type_run_count = self._collapse(ordered)
        ranges: list[dict[str, Any]] = []
        zero_width_count = 0
        completed_candidate_count = 0
        for first, second in zip(collapsed, collapsed[1:]):
            if first["pivot_type"] == second["pivot_type"]:
                continue
            completed_candidate_count += 1
            range_record = self._range_record(first, second, rule_version)
            if range_record is None:
                zero_width_count += 1
                continue
            ranges.append(range_record)
        sort_key = lambda item: (item["created_at"], item["second_pivot_source_index"], item["range_id"])
        ranges.sort(key=sort_key)
        current_range = ranges[-1] if ranges else None
        pre_retention_count = len(ranges)
        retained = ranges[-config.maximum_ranges:]
        retained.sort(key=sort_key)
        diagnostics = {
            "source_swing_high_count": len(source_result.evidence.get("swing_highs", [])),
            "source_swing_low_count": len(source_result.evidence.get("swing_lows", [])),
            "source_pivot_count": source_count,
            "terminal_unconfirmed_pivot_count": terminal_count,
            "confirmed_high_pivot_count": confirmed_high_count,
            "confirmed_low_pivot_count": confirmed_low_count,
            "confirmed_pivot_count": len(confirmed),
            "same_type_run_count": same_type_run_count,
            "collapsed_pivot_count": len(collapsed),
            "completed_range_candidate_count": completed_candidate_count,
            "valid_range_count": len(ranges),
            "zero_width_range_count": zero_width_count,
            "pre_retention_range_count": pre_retention_count,
            "emitted_range_count": len(retained),
            "truncated_range_count": pre_retention_count - len(retained),
        }
        summary = {
            "total_returned_range_count": len(retained),
            "current_range_id": 0 if current_range is None else 1,
        }
        result = StructuralDealingRangeResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=input_model.candle_history[-1]["timestamp"],
            scanned_candle_count=len(input_model.candle_history),
            structural_ranges=retained,
            current_range=current_range,
            summary=summary,
            diagnostics=diagnostics,
            evidence={
                "structure_rule_version": rule_version,
                "structural_range_rule_version": RULE_VERSION,
                "source_role": "Slice #3 remains pivot detector",
                "causal_filter": "Slice #11 excludes pivots without a following candle",
                "terminal_pivot_handling": "terminal Slice #3 observations without next candle are excluded",
                "composition_rules": ["same_type_run_collapse", "adjacent_opposite_pivot_pairing"],
                "confirmed_pivots": confirmed,
                "unused_structure_fields": ["structure_state", "HH/HL/LH/LL", "break_candidates", "break_confirmations"],
                "identity_scope": "snapshot_deterministic",
                "later_zone_calculation": "not_performed",
                "configuration": config.as_dict(),
                "retention_sort": ["created_at", "second_pivot_source_index", "range_id"],
            },
            metadata={
                "deterministic_structural_dealing_range_intelligence": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "identity_scope": "snapshot_deterministic",
                "authority_scope": "read_only",
            },
        )
        output_errors = StructuralDealingRangeIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid structural dealing range result: " + "; ".join(output_errors))
        return result


STRUCTURAL_DEALING_RANGE_INTELLIGENCE = StructuralDealingRangeAnalyzer()

__all__ = [
    "StructuralDealingRangeAnalyzer",
    "StructuralDealingRangeConfig",
    "StructuralDealingRangeInput",
    "StructuralDealingRangeResult",
    "StructuralDealingRangeValidator",
    "StructuralDealingRangeIntelligenceCapability",
    "StructuralDealingRangeIntelligenceSpecialist",
    "STRUCTURAL_DEALING_RANGE_INTELLIGENCE",
    "RULE_VERSION",
]
