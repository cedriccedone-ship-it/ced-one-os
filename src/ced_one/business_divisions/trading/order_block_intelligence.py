"""Deterministic Order Block Intelligence composed from Slice #8 displacement events."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import hashlib
import json
import re
from typing import Any

from ced_one.business_divisions.trading.displacement_intelligence import (
    RULE_VERSION as DISPLACEMENT_RULE_VERSION,
    DisplacementIntelligenceAnalyzer,
    DisplacementIntelligenceConfig,
    DisplacementIntelligenceValidator,
)

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "order_block_intelligence_v1"


@dataclass(frozen=True)
class OrderBlockIntelligenceConfig:
    lookback_candles: int = 100
    origin_search_lookback: int = 3
    maximum_order_blocks: int = 50
    maximum_interactions_per_block: int = 100
    displacement_config: dict[str, Any] | DisplacementIntelligenceConfig | None = None

    @staticmethod
    def _integer(value: Any, field_name: str) -> list[str]:
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"Invalid config field {field_name}: must be an integer."]
        return []

    def validate(self) -> list[str]:
        errors: list[str] = []
        for field_name in [
            "lookback_candles",
            "origin_search_lookback",
            "maximum_order_blocks",
            "maximum_interactions_per_block",
        ]:
            errors.extend(self._integer(getattr(self, field_name), field_name))
        if isinstance(self.lookback_candles, int) and not isinstance(self.lookback_candles, bool) and self.lookback_candles < 1:
            errors.append("Invalid config field lookback_candles: must be at least 1.")
        if isinstance(self.origin_search_lookback, int) and not isinstance(self.origin_search_lookback, bool) and not 1 <= self.origin_search_lookback <= 10:
            errors.append("Invalid config field origin_search_lookback: must be between 1 and 10.")
        if isinstance(self.maximum_order_blocks, int) and not isinstance(self.maximum_order_blocks, bool) and not 1 <= self.maximum_order_blocks <= 1000:
            errors.append("Invalid config field maximum_order_blocks: must be between 1 and 1000.")
        if isinstance(self.maximum_interactions_per_block, int) and not isinstance(self.maximum_interactions_per_block, bool) and not 1 <= self.maximum_interactions_per_block <= 1000:
            errors.append("Invalid config field maximum_interactions_per_block: must be between 1 and 1000.")
        try:
            self.source_config()
        except ValueError as exc:
            errors.append(str(exc))
        return errors

    def source_config(self) -> DisplacementIntelligenceConfig:
        nested = self.displacement_config
        if nested is None:
            values: dict[str, Any] = {}
        elif isinstance(nested, DisplacementIntelligenceConfig):
            values = nested.as_dict()
        elif isinstance(nested, dict):
            values = dict(nested)
        else:
            raise ValueError("Invalid displacement_config: must be a dictionary or DisplacementIntelligenceConfig.")
        if "lookback_candles" in values:
            raise ValueError("Invalid displacement_config: lookback_candles is controlled by Slice #10.")
        values["lookback_candles"] = self.lookback_candles
        return DisplacementIntelligenceConfig.from_payload(values)

    @classmethod
    def from_payload(cls, payload: Any | None) -> "OrderBlockIntelligenceConfig":
        if payload is None:
            return cls()
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid order block intelligence config: config must be a dictionary or OrderBlockIntelligenceConfig.")
        valid_keys = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - valid_keys)
        if unknown:
            raise ValueError(f"Invalid order block intelligence config: unknown fields {unknown}.")
        config = cls(**{name: payload.get(name, getattr(cls(), name)) for name in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid order block intelligence config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {
            "lookback_candles": self.lookback_candles,
            "origin_search_lookback": self.origin_search_lookback,
            "maximum_order_blocks": self.maximum_order_blocks,
            "maximum_interactions_per_block": self.maximum_interactions_per_block,
            "displacement_config": self.source_config().as_dict(),
        }


@dataclass
class OrderBlockIntelligenceInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: OrderBlockIntelligenceConfig = field(default_factory=OrderBlockIntelligenceConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OrderBlockIntelligenceInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=OrderBlockIntelligenceConfig.from_payload(payload.get("config")),
        )


@dataclass
class OrderBlockIntelligenceResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    order_blocks: list[dict[str, Any]] = field(default_factory=list)
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
            "order_blocks": self.order_blocks,
            "summary": self.summary,
            "diagnostics": self.diagnostics,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class OrderBlockIntelligenceValidator:
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
        candles = payload.get("candle_history")
        if not isinstance(candles, list):
            errors.append("Missing required field: candle_history")
        elif not candles:
            errors.append("Candle history cannot be empty.")
        try:
            config = OrderBlockIntelligenceConfig.from_payload(payload.get("config"))
        except ValueError as exc:
            return errors + [str(exc)]
        source_payload = {
            "symbol": payload.get("symbol"),
            "timeframe": payload.get("timeframe"),
            "evaluation_time": payload.get("evaluation_time"),
            "candle_history": candles,
            "config": config.source_config().as_dict(),
        }
        errors.extend(DisplacementIntelligenceValidator.validate_input(source_payload))
        return errors


class OrderBlockIntelligenceCapability:
    def __init__(self):
        self.name = "order_block_intelligence"
        self.contract = "trading.order_block_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual order block origin and subsequent interaction intelligence for XAUUSD."
        self.metadata = {
            "deterministic_order_block_intelligence": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "identity_scope": "snapshot_deterministic",
        }

    def validate_input(self, payload: dict[str, Any], **_: Any) -> list[str]:
        return OrderBlockIntelligenceValidator.validate_input(payload)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        required = ["symbol", "timeframe", "evaluation_time", "timestamp", "scanned_candle_count", "order_blocks", "summary", "diagnostics", "evidence", "metadata"]
        errors = [f"Missing required output field: {name}" for name in required if name not in payload]
        forbidden = ["buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "target", "risk_reward", "position_size", "leverage", "signal", "setup", "confidence", "probability", "recommendation", "expected_direction", "broker_instruction", "execution_command", "institutional_order", "smart_money_order", "bank_order", "manipulation", "mitigated", "unmitigated", "invalidation", "invalidated", "failure", "failed"]
        text = str(payload).lower()
        errors.extend(f"Forbidden advisory term detected: {term}" for term in forbidden if re.search(rf"\b{re.escape(term)}\b", text))
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> OrderBlockIntelligenceResult:
        return OrderBlockIntelligenceAnalyzer().analyze(payload)


class OrderBlockIntelligenceSpecialist:
    def __init__(self):
        self.name = "order_block_analyst"
        self.division_name = "trading"
        self.capability_name = "order_block_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return division_name == "trading" and specialist_name == self.name and capability_name == self.capability_name and permission_scope == "read_only"

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

    def analyze_order_blocks(self, payload: dict[str, Any], **_: Any) -> OrderBlockIntelligenceResult:
        return OrderBlockIntelligenceAnalyzer().analyze(payload)


class OrderBlockIntelligenceAnalyzer:
    _STATE_RANK = {"unvisited": 0, "wick_revisited": 1, "body_revisited": 2, "closed_through": 3}
    _EVENT_STATE = {
        "order_block_wick_touch": "wick_revisited",
        "order_block_body_revisit": "body_revisited",
        "order_block_close_through": "closed_through",
    }

    @staticmethod
    def _hash_id(parts: list[str]) -> str:
        value = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
        return "order_block_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _direction(candle: dict[str, float]) -> str:
        if candle["close"] > candle["open"]:
            return "bullish"
        if candle["close"] < candle["open"]:
            return "bearish"
        return "neutral"

    @classmethod
    def _interaction(cls, block: dict[str, Any], candle: dict[str, float]) -> tuple[str | None, bool, bool]:
        candle_body_low = min(candle["open"], candle["close"])
        candle_body_high = max(candle["open"], candle["close"])
        close_through = (
            candle["close"] < block["range_low"]
            if block["direction"] == "bullish"
            else candle["close"] > block["range_high"]
        )
        body_overlap = block["body_low"] <= candle_body_high and candle_body_low <= block["body_high"]
        range_contact = candle["high"] >= block["body_low"] and candle["low"] <= block["body_high"]
        if close_through:
            return "order_block_close_through", body_overlap, range_contact
        if body_overlap:
            return "order_block_body_revisit", body_overlap, range_contact
        if range_contact:
            return "order_block_wick_touch", body_overlap, range_contact
        return None, body_overlap, range_contact

    def analyze(self, payload: dict[str, Any]) -> OrderBlockIntelligenceResult:
        errors = OrderBlockIntelligenceValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid order block intelligence input: " + "; ".join(errors))
        input_model = OrderBlockIntelligenceInput.from_payload(payload)
        config = input_model.config
        source_config = config.source_config()
        source_payload = {
            "symbol": input_model.symbol,
            "timeframe": input_model.timeframe,
            "evaluation_time": input_model.evaluation_time,
            "candle_history": input_model.candle_history,
            "config": source_config.as_dict(),
        }
        displacement_result = DisplacementIntelligenceAnalyzer().analyze(source_payload)
        candles = [
            {"timestamp": str(item["timestamp"]), "open": float(item["open"]), "high": float(item["high"]), "low": float(item["low"]), "close": float(item["close"])}
            for item in input_model.candle_history
        ]
        origin_search_count = len(displacement_result.displacement_events)
        origin_found_count = 0
        origin_not_found_count = 0
        duplicate_candidate_count = 0
        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        event_order: dict[str, int] = {}
        origin_evidence: list[dict[str, Any]] = []
        candidate_min = displacement_result.evidence["candidate_index_range"]["candidate_index_min"]
        for event_position, event in enumerate(displacement_result.displacement_events):
            event_id = event["event_id"]
            source_index = event.get("evidence", {}).get("index")
            if not isinstance(source_index, int) or not 0 <= source_index < len(candles):
                raise ValueError("Invalid Slice #8 displacement event: missing valid evidence index.")
            start_index = source_index - 1
            end_index = max(-1, start_index - config.origin_search_lookback + 1)
            inspected = 0
            origin = None
            for index in range(start_index, end_index - 1, -1):
                inspected += 1
                direction = self._direction(candles[index])
                if direction == ("bearish" if event["direction"] == "bullish" else "bullish"):
                    origin = (index, candles[index])
                    break
            origin_evidence.append({
                "displacement_event_id": event_id,
                "displacement_source_index": source_index,
                "origin_search_start_index": start_index,
                "origin_search_end_index": end_index,
                "inspected_candle_count": inspected,
                "crossed_source_candidate_boundary": start_index < candidate_min or end_index < candidate_min,
            })
            if origin is None:
                origin_not_found_count += 1
                continue
            origin_found_count += 1
            origin_index, source = origin
            direction = event["direction"]
            key = (source["timestamp"], direction)
            candidate = {
                "source_timestamp": source["timestamp"],
                "source_index": origin_index,
                "direction": direction,
                "source_open": source["open"],
                "source_high": source["high"],
                "source_low": source["low"],
                "source_close": source["close"],
                "body_low": min(source["open"], source["close"]),
                "body_high": max(source["open"], source["close"]),
                "range_low": source["low"],
                "range_high": source["high"],
                "confirmed_at": event["confirmed_at"],
                "created_at": event["confirmed_at"],
                "source_displacement_event_id": event_id,
                "source_displacement_timestamp": event["source_timestamp"],
                "source_displacement_direction": event["direction"],
                "contributing_event_ids": [event_id],
                "event_order": event_order.setdefault(event_id, event_position),
            }
            existing = candidates.get(key)
            if existing is None:
                candidates[key] = candidate
            else:
                duplicate_candidate_count += 1
                existing["contributing_event_ids"].append(event_id)
                ordering = (candidate["confirmed_at"], candidate["source_index"], candidate["event_order"])
                current_ordering = (existing["confirmed_at"], existing["source_index"], existing["event_order"])
                if ordering < current_ordering:
                    candidate["contributing_event_ids"] = existing["contributing_event_ids"]
                    candidates[key] = candidate
        blocks = []
        source_interaction_scan_count = 0
        exact_duplicate_interaction_count = 0
        for candidate in candidates.values():
            block_id = self._hash_id([candidate["source_timestamp"], candidate["direction"], candidate["source_displacement_event_id"]])
            block = {**candidate, "order_block_id": block_id, "current_state": "unvisited", "interactions": [], "evidence": {"contributing_displacement_event_ids": list(candidate["contributing_event_ids"]), "source_displacement_event_id": candidate["source_displacement_event_id"]}}
            source_index = next(index for index, item in enumerate(candles) if item["timestamp"] == candidate["source_displacement_timestamp"])
            seen_pairs: set[tuple[str, str]] = set()
            for candle in candles[source_index + 1 :]:
                source_interaction_scan_count += 1
                event_type, body_overlap, range_contact = self._interaction(block, candle)
                if event_type is None:
                    continue
                pair = (block_id, candle["timestamp"])
                if pair in seen_pairs:
                    exact_duplicate_interaction_count += 1
                    continue
                seen_pairs.add(pair)
                prior_state = block["current_state"]
                resulting_state = max((prior_state, self._EVENT_STATE[event_type]), key=lambda state: self._STATE_RANK[state])
                block["current_state"] = resulting_state
                block["interactions"].append({
                    "interaction_id": self._hash_id([block_id, candle["timestamp"], event_type]),
                    "order_block_id": block_id,
                    "candle_timestamp": candle["timestamp"],
                    "event_type": event_type,
                    "candle_open": candle["open"],
                    "candle_high": candle["high"],
                    "candle_low": candle["low"],
                    "candle_close": candle["close"],
                    "body_overlap": body_overlap,
                    "range_contact": range_contact,
                    "prior_state": prior_state,
                    "resulting_state": resulting_state,
                    "applied_body_low": block["body_low"],
                    "applied_body_high": block["body_high"],
                    "applied_range_low": block["range_low"],
                    "applied_range_high": block["range_high"],
                })
            blocks.append(block)
        blocks.sort(key=lambda item: (item["created_at"], item["source_timestamp"], item["direction"], item["order_block_id"]))
        pre_block_count = len(blocks)
        candidate_interaction_count = sum(len(block["interactions"]) for block in blocks)
        retained_blocks = blocks[-config.maximum_order_blocks:]
        retained_blocks.sort(key=lambda item: (item["created_at"], item["source_timestamp"], item["direction"], item["order_block_id"]))
        emitted_interactions = 0
        pre_interactions = candidate_interaction_count
        blocks_truncated = 0
        earliest_omitted = 0
        for block in retained_blocks:
            if len(block["interactions"]) > config.maximum_interactions_per_block:
                blocks_truncated += 1
                earliest_omitted += 1
                block["interactions"] = block["interactions"][-config.maximum_interactions_per_block:]
            emitted_interactions += len(block["interactions"])
        for block in retained_blocks:
            block["interaction_count"] = len(block["interactions"])
            block.pop("event_order", None)
            block.pop("contributing_event_ids", None)
        diagnostics = {
            "source_displacement_event_count": len(displacement_result.displacement_events),
            "origin_search_count": origin_search_count,
            "origin_found_count": origin_found_count,
            "origin_not_found_count": origin_not_found_count,
            "duplicate_candidate_count": duplicate_candidate_count,
            "pre_retention_order_block_count": pre_block_count,
            "emitted_order_block_count": len(retained_blocks),
            "truncated_order_block_count": pre_block_count - len(retained_blocks),
            "source_interaction_scan_count": source_interaction_scan_count,
            "candidate_interaction_count": candidate_interaction_count,
            "exact_duplicate_interaction_count": exact_duplicate_interaction_count,
            "pre_retention_interaction_count": pre_interactions,
            "emitted_interaction_count": emitted_interactions,
            "truncated_interaction_count": pre_interactions - emitted_interactions,
            "blocks_with_truncated_interactions": blocks_truncated,
            "blocks_with_earliest_interaction_omitted": earliest_omitted,
        }
        summary = {
            "bullish_order_block_count": sum(block["direction"] == "bullish" for block in retained_blocks),
            "bearish_order_block_count": sum(block["direction"] == "bearish" for block in retained_blocks),
            "unvisited_count": sum(block["current_state"] == "unvisited" for block in retained_blocks),
            "wick_revisited_count": sum(block["current_state"] == "wick_revisited" for block in retained_blocks),
            "body_revisited_count": sum(block["current_state"] == "body_revisited" for block in retained_blocks),
            "closed_through_count": sum(block["current_state"] == "closed_through" for block in retained_blocks),
            "total_returned_order_blocks": len(retained_blocks),
        }
        result = OrderBlockIntelligenceResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=displacement_result.timestamp,
            scanned_candle_count=displacement_result.scanned_candle_count,
            order_blocks=retained_blocks,
            summary=summary,
            diagnostics=diagnostics,
            evidence={
                "displacement_rule_version": DISPLACEMENT_RULE_VERSION,
                "order_block_rule_version": RULE_VERSION,
                "source_model": "displacement_events_only",
                "requested_source_lookback_candles": config.lookback_candles,
                "effective_source_lookback_candles": source_config.lookback_candles,
                "effective_displacement_config": source_config.as_dict(),
                "origin_search_lookback": config.origin_search_lookback,
                "origin_searches": origin_evidence,
                "identity_scope": "snapshot_deterministic",
                "retention_policy": "deterministic_created_source_direction_id_order",
                "interaction_precedence": ["order_block_close_through", "order_block_body_revisit", "order_block_wick_touch"],
                "state_precedence": ["closed_through", "body_revisited", "wick_revisited", "unvisited"],
            },
            metadata={
                "deterministic_order_block_intelligence": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "identity_scope": "snapshot_deterministic",
                "authority_scope": "read_only",
            },
        )
        output_errors = OrderBlockIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid order block intelligence result: "+"; ".join(output_errors))
        return result


ORDER_BLOCK_INTELLIGENCE = OrderBlockIntelligenceAnalyzer()

__all__ = [
    "OrderBlockIntelligenceAnalyzer",
    "OrderBlockIntelligenceCapability",
    "OrderBlockIntelligenceConfig",
    "OrderBlockIntelligenceInput",
    "OrderBlockIntelligenceResult",
    "OrderBlockIntelligenceSpecialist",
    "OrderBlockIntelligenceValidator",
    "ORDER_BLOCK_INTELLIGENCE",
    "RULE_VERSION",
]
