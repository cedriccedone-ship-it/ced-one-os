"""Deterministic liquidity event intelligence composed from Slice #6."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import hashlib
import json
import re
from typing import Any

from ced_one.business_divisions.trading.liquidity_intelligence import (
    RULE_VERSION as LIQUIDITY_RULE_VERSION,
    LiquidityIntelligenceAnalyzer,
    LiquidityIntelligenceConfig,
    LiquidityIntelligenceValidator,
)

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "liquidity_events_v1"


@dataclass(frozen=True)
class LiquidityEventsConfig:
    lookback_candles: int = 100
    maximum_events: int = 200
    include_touch_events: bool = True
    liquidity_config: dict[str, Any] | LiquidityIntelligenceConfig | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.lookback_candles, int):
            errors.append("Invalid config field lookback_candles: must be an integer.")
        elif self.lookback_candles < 3:
            errors.append("Invalid config field lookback_candles: must be at least 3.")
        if not isinstance(self.maximum_events, int):
            errors.append("Invalid config field maximum_events: must be an integer.")
        elif not 1 <= self.maximum_events <= 1000:
            errors.append("Invalid config field maximum_events: must be between 1 and 1000.")
        if not isinstance(self.include_touch_events, bool):
            errors.append("Invalid config field include_touch_events: must be a boolean.")
        if isinstance(self.liquidity_config, dict) and "lookback_candles" in self.liquidity_config:
            errors.append("Invalid liquidity_config: lookback_candles is controlled by Slice #9.")
        try:
            self.source_config()
        except ValueError as exc:
            errors.append(str(exc))
        return errors

    def source_config(self) -> LiquidityIntelligenceConfig:
        nested = self.liquidity_config
        if nested is None:
            nested_values: dict[str, Any] = {}
        elif isinstance(nested, LiquidityIntelligenceConfig):
            nested_values = nested.as_dict()
        elif isinstance(nested, dict):
            nested_values = dict(nested)
        else:
            raise ValueError("Invalid liquidity_config: must be a dictionary or LiquidityIntelligenceConfig.")
        if "lookback_candles" in nested_values:
            raise ValueError("Invalid liquidity_config: lookback_candles is controlled by Slice #9.")
        nested_values["lookback_candles"] = self.lookback_candles
        return LiquidityIntelligenceConfig.from_payload(nested_values)

    @classmethod
    def from_payload(cls, payload: Any | None) -> "LiquidityEventsConfig":
        if payload is None:
            return cls()
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid liquidity events config: config must be a dictionary or LiquidityEventsConfig.")
        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid liquidity events config: unknown fields {unknown_keys}.")
        config = cls(
            lookback_candles=payload.get("lookback_candles", cls.lookback_candles),
            maximum_events=payload.get("maximum_events", cls.maximum_events),
            include_touch_events=payload.get("include_touch_events", cls.include_touch_events),
            liquidity_config=payload.get("liquidity_config"),
        )
        errors = config.validate()
        if errors:
            raise ValueError("Invalid liquidity events config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        nested = self.source_config().as_dict()
        return {
            "lookback_candles": self.lookback_candles,
            "maximum_events": self.maximum_events,
            "include_touch_events": self.include_touch_events,
            "liquidity_config": nested,
        }


@dataclass
class LiquidityEventsInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: LiquidityEventsConfig = field(default_factory=LiquidityEventsConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LiquidityEventsInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=LiquidityEventsConfig.from_payload(payload.get("config")),
        )


@dataclass
class LiquidityEventsResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    liquidity_events: list[dict[str, Any]] = field(default_factory=list)
    level_event_states: dict[str, str] = field(default_factory=dict)
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
            "liquidity_events": self.liquidity_events,
            "level_event_states": self.level_event_states,
            "summary": self.summary,
            "diagnostics": self.diagnostics,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class LiquidityEventsValidator:
    @staticmethod
    def validate_input(payload: dict[str, Any]) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        errors: list[str] = []
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
            LiquidityEventsConfig.from_payload(payload.get("config"))
        except ValueError as exc:
            errors.append(str(exc))
        if isinstance(candles, list):
            source_errors = LiquidityIntelligenceValidator.validate_input(
                {
                    "symbol": payload.get("symbol"),
                    "timeframe": payload.get("timeframe"),
                    "evaluation_time": payload.get("evaluation_time"),
                    "candle_history": candles,
                    "config": LiquidityEventsConfig.from_payload(payload.get("config")).source_config().as_dict()
                    if not errors
                    else None,
                }
            )
            errors.extend(source_errors)
        return errors


class LiquidityEventsCapability:
    def __init__(self):
        self.name = "liquidity_events"
        self.contract = "trading.liquidity_events.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual liquidity touch, sweep, and close-beyond event intelligence for XAUUSD."
        self.metadata = {
            "deterministic_liquidity_events": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "identity_scope": "snapshot_deterministic",
        }

    def validate_input(self, payload: dict[str, Any], **_: Any) -> list[str]:
        return LiquidityEventsValidator.validate_input(payload)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        required = ["symbol", "timeframe", "evaluation_time", "timestamp", "scanned_candle_count", "liquidity_events", "level_event_states", "summary", "diagnostics", "evidence", "metadata"]
        errors = [f"Missing required output field: {name}" for name in required if name not in payload]
        forbidden = ["buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "target", "risk_reward", "setup", "signal", "probability", "confidence", "recommendation", "stop_hunt", "manipulation", "smart_money_intent", "expected_direction", "position_size", "broker_instruction", "execution_command"]
        text = str(payload).lower()
        errors.extend(f"Forbidden advisory term detected: {term}" for term in forbidden if re.search(rf"\b{re.escape(term)}\b", text))
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> LiquidityEventsResult:
        return LiquidityEventsAnalyzer().analyze(payload)


class LiquidityEventsSpecialist:
    def __init__(self):
        self.name = "liquidity_events_analyst"
        self.division_name = "trading"
        self.capability_name = "liquidity_events"
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

    def analyze_liquidity_events(self, payload: dict[str, Any], **_: Any) -> LiquidityEventsResult:
        return LiquidityEventsAnalyzer().analyze(payload)


class LiquidityEventsAnalyzer:
    _EVENT_MAP = {
        "touched": "liquidity_touch",
        "breached": "liquidity_sweep",
        "closed_beyond": "liquidity_close_beyond",
    }
    _STATE_RANK = {"untouched": 0, "touched": 1, "swept": 2, "closed_beyond": 3}

    @staticmethod
    def _event_id(level_id: str, timestamp: str, event_type: str) -> str:
        identity = json.dumps([level_id, timestamp, event_type], separators=(",", ":"), ensure_ascii=True)
        return "liquidity_event_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def _map_interaction(cls, level: dict[str, Any], interaction: dict[str, Any], candles: dict[str, dict[str, Any]]) -> dict[str, Any]:
        level_id = level.get("level_id")
        side = level.get("side")
        source_type = interaction.get("event_type")
        if not isinstance(level_id, str) or not level_id:
            raise ValueError("Invalid Slice #6 source interaction: missing level_id.")
        if side not in {"high", "low"}:
            raise ValueError("Invalid Slice #6 source interaction: invalid liquidity side.")
        if source_type not in cls._EVENT_MAP:
            raise ValueError(f"Invalid Slice #6 source interaction: unknown event_type {source_type!r}.")
        wick = interaction.get("wick_breach_without_close")
        if source_type == "breached" and wick is not True:
            raise ValueError("Invalid Slice #6 source interaction: breached requires wick_breach_without_close=True.")
        if source_type != "breached" and wick is not False:
            raise ValueError("Invalid Slice #6 source interaction: non-breached interaction has contradictory wick metadata.")
        boundary = interaction.get("applied_boundary")
        if not isinstance(boundary, dict) or "lower_boundary" not in boundary or "upper_boundary" not in boundary:
            raise ValueError("Invalid Slice #6 source interaction: missing applied boundaries.")
        lower = float(boundary["lower_boundary"])
        upper = float(boundary["upper_boundary"])
        if lower > upper:
            raise ValueError("Invalid Slice #6 source interaction: lower boundary exceeds upper boundary.")
        timestamp = interaction.get("candle_timestamp")
        if not isinstance(timestamp, str) or timestamp not in candles:
            raise ValueError("Invalid Slice #6 source interaction: missing referenced candle.")
        candle = candles[timestamp]
        event_type = cls._EVENT_MAP[source_type]
        observed_high = float(interaction["observed_high"])
        observed_low = float(interaction["observed_low"])
        observed_close = float(interaction["observed_close"])
        if event_type == "liquidity_touch":
            excursion = 0.0
        elif side == "high":
            excursion = max(0.0, observed_high - upper)
        else:
            excursion = max(0.0, lower - observed_low)
        return {
            "event_id": cls._event_id(level_id, timestamp, event_type),
            "event_type": event_type,
            "event_timestamp": timestamp,
            "liquidity_side": side,
            "level_id": level_id,
            "level_type": level.get("level_type"),
            "level_source_timestamp": level.get("source_timestamp"),
            "level_created_at": level.get("created_at"),
            "representative_price": float(level["representative_price"]),
            "lower_boundary": lower,
            "upper_boundary": upper,
            "observed_open": candle["open"],
            "observed_high": observed_high,
            "observed_low": observed_low,
            "observed_close": observed_close,
            "boundary_excursion": excursion,
            "closed_beyond_boundary": source_type == "closed_beyond",
            "source_interaction_type": source_type,
            "source_wick_breach_without_close": wick,
        }

    def analyze(self, payload: dict[str, Any]) -> LiquidityEventsResult:
        errors = LiquidityEventsValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid liquidity events input: " + "; ".join(errors))
        input_model = LiquidityEventsInput.from_payload(payload)
        config = input_model.config
        source_config = config.source_config()
        source_payload = {
            "symbol": input_model.symbol,
            "timeframe": input_model.timeframe,
            "evaluation_time": input_model.evaluation_time,
            "candle_history": input_model.candle_history,
            "config": source_config.as_dict(),
        }
        source_result = LiquidityIntelligenceAnalyzer().analyze(source_payload)
        candles = {
            str(item["timestamp"]): {
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
            }
            for item in input_model.candle_history
        }
        raw_count = sum(len(level.get("interactions", [])) for level in source_result.liquidity_levels)
        complete_events: list[dict[str, Any]] = []
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        deduplicated = 0
        for level in source_result.liquidity_levels:
            for interaction in level.get("interactions", []):
                event = self._map_interaction(level, interaction, candles)
                key = (event["level_id"], event["event_timestamp"])
                if key in seen:
                    if seen[key] != event:
                        raise ValueError("Conflicting Slice #6 source interactions for the same level/candle pair.")
                    deduplicated += 1
                    continue
                seen[key] = event
                complete_events.append(event)
        complete_events.sort(key=lambda item: (item["event_timestamp"], item["level_id"], item["event_type"]))
        states = {level["level_id"]: "untouched" for level in source_result.liquidity_levels}
        for event in complete_events:
            state = {
                "liquidity_touch": "touched",
                "liquidity_sweep": "swept",
                "liquidity_close_beyond": "closed_beyond",
            }[event["event_type"]]
            if self._STATE_RANK[state] > self._STATE_RANK[states[event["level_id"]]]:
                states[event["level_id"]] = state
        touch_count = sum(item["event_type"] == "liquidity_touch" for item in complete_events)
        sweep_count = sum(item["event_type"] == "liquidity_sweep" for item in complete_events)
        close_count = sum(item["event_type"] == "liquidity_close_beyond" for item in complete_events)
        excluded_touch_count = touch_count if not config.include_touch_events else 0
        candidates = complete_events if config.include_touch_events else [item for item in complete_events if item["event_type"] != "liquidity_touch"]
        pre_truncation = len(candidates)
        emitted = candidates[-config.maximum_events:]
        emitted.sort(key=lambda item: (item["event_timestamp"], item["level_id"], item["event_type"]))
        diagnostics = {
            "source_liquidity_level_count": len(source_result.liquidity_levels),
            "source_interaction_count": raw_count,
            "candidate_interaction_count": len(complete_events),
            "touch_candidate_count": touch_count,
            "sweep_candidate_count": sweep_count,
            "close_beyond_candidate_count": close_count,
            "excluded_touch_count": excluded_touch_count,
            "deduplicated_event_count": deduplicated,
            "pre_truncation_event_count": pre_truncation,
            "emitted_event_count": len(emitted),
            "truncated_event_count": pre_truncation - len(emitted),
        }
        summary = {
            "total_event_count": len(emitted),
            "touch_event_count": sum(item["event_type"] == "liquidity_touch" for item in emitted),
            "sweep_event_count": sum(item["event_type"] == "liquidity_sweep" for item in emitted),
            "close_beyond_event_count": sum(item["event_type"] == "liquidity_close_beyond" for item in emitted),
            "high_side_event_count": sum(item["liquidity_side"] == "high" for item in emitted),
            "low_side_event_count": sum(item["liquidity_side"] == "low" for item in emitted),
            "high_side_sweep_count": sum(item["liquidity_side"] == "high" and item["event_type"] == "liquidity_sweep" for item in emitted),
            "low_side_sweep_count": sum(item["liquidity_side"] == "low" and item["event_type"] == "liquidity_sweep" for item in emitted),
            "unique_level_count": len({item["level_id"] for item in emitted}),
        }
        result = LiquidityEventsResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=source_result.timestamp,
            scanned_candle_count=source_result.scanned_candle_count,
            liquidity_events=emitted,
            level_event_states=states,
            summary=summary,
            diagnostics=diagnostics,
            evidence={
                "liquidity_rule_version": LIQUIDITY_RULE_VERSION,
                "liquidity_event_rule_version": RULE_VERSION,
                "effective_liquidity_config": source_config.as_dict(),
                "effective_slice9_config": config.as_dict(),
                "requested_source_lookback_candles": config.lookback_candles,
                "effective_source_lookback_candles": source_config.lookback_candles,
                "source_level_ids": [level["level_id"] for level in source_result.liquidity_levels],
                "source_interaction_types": [item["source_interaction_type"] for item in complete_events],
                "classification_mapping": dict(self._EVENT_MAP),
                "event_precedence": ["liquidity_close_beyond", "liquidity_sweep", "liquidity_touch"],
                "source_boundary_reuse": "Slice #6 interaction applied_boundary copied without recomputation",
                "retention_policy": "most_recent_events_in_chronological_order",
                "identity_scope": "snapshot_deterministic",
                "truncation": diagnostics["truncated_event_count"] > 0,
            },
            metadata={
                "deterministic_liquidity_events": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "authority_scope": "read_only",
                "identity_scope": "snapshot_deterministic",
            },
        )
        output_errors = LiquidityEventsCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid liquidity events result: " + "; ".join(output_errors))
        return result


LIQUIDITY_EVENTS = LiquidityEventsAnalyzer()

__all__ = [
    "LiquidityEventsAnalyzer",
    "LiquidityEventsCapability",
    "LiquidityEventsConfig",
    "LiquidityEventsInput",
    "LiquidityEventsResult",
    "LiquidityEventsSpecialist",
    "LiquidityEventsValidator",
    "LIQUIDITY_EVENTS",
    "RULE_VERSION",
]
