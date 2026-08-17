"""Deterministic XAUUSD displacement intelligence for Vertical Slice #8.

This module stays read-only, provider-independent, and observational. It detects
factual single-candle displacement events and bounded contiguous same-direction
displacement sequences from validated candle history, without strategy,
execution, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from statistics import median
import re
from typing import Any

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "displacement_intelligence_v1"


@dataclass(frozen=True)
class DisplacementIntelligenceConfig:
    lookback_candles: int = 100
    baseline_window: int = 20
    minimum_body_ratio: float = 0.70
    minimum_range_expansion_ratio: float = 1.50
    bullish_close_location_min: float = 0.80
    bearish_close_location_max: float = 0.20
    minimum_sequence_events: int = 2

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not isinstance(self.lookback_candles, int):
            errors.append("Invalid config field lookback_candles: must be an integer.")
        elif self.lookback_candles < 1:
            errors.append("Invalid config field lookback_candles: must be at least 1.")

        if not isinstance(self.baseline_window, int):
            errors.append("Invalid config field baseline_window: must be an integer.")
        elif self.baseline_window < 1:
            errors.append("Invalid config field baseline_window: must be at least 1.")

        ratio_fields = ["minimum_body_ratio", "bullish_close_location_min", "bearish_close_location_max"]
        for field_name in ratio_fields:
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)):
                errors.append(f"Invalid config field {field_name}: must be numeric.")
                continue
            if value < 0 or value > 1:
                errors.append(f"Invalid config field {field_name}: must be within [0, 1].")

        if not isinstance(self.minimum_range_expansion_ratio, (int, float)):
            errors.append("Invalid config field minimum_range_expansion_ratio: must be numeric.")
        elif self.minimum_range_expansion_ratio <= 0:
            errors.append("Invalid config field minimum_range_expansion_ratio: must be greater than 0.")

        if not isinstance(self.minimum_sequence_events, int):
            errors.append("Invalid config field minimum_sequence_events: must be an integer.")
        elif self.minimum_sequence_events < 2:
            errors.append("Invalid config field minimum_sequence_events: must be at least 2.")

        if (
            isinstance(self.bearish_close_location_max, (int, float))
            and isinstance(self.bullish_close_location_min, (int, float))
            and self.bearish_close_location_max >= self.bullish_close_location_min
        ):
            errors.append("Invalid config: bearish_close_location_max must be less than bullish_close_location_min.")

        return errors

    @classmethod
    def from_payload(cls, payload: Any | None) -> "DisplacementIntelligenceConfig":
        if payload is None:
            return cls()
        if isinstance(payload, DisplacementIntelligenceConfig):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid displacement intelligence config: config must be a dictionary or DisplacementIntelligenceConfig.")

        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid displacement intelligence config: unknown fields {unknown_keys}.")

        config = cls(**{key: payload.get(key, getattr(cls(), key)) for key in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid displacement intelligence config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class DisplacementIntelligenceInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: DisplacementIntelligenceConfig = field(default_factory=DisplacementIntelligenceConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DisplacementIntelligenceInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=DisplacementIntelligenceConfig.from_payload(payload.get("config")),
        )


@dataclass
class DisplacementIntelligenceResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    displacement_events: list[dict[str, Any]] = field(default_factory=list)
    displacement_sequences: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_time": self.evaluation_time,
            "timestamp": self.timestamp,
            "scanned_candle_count": self.scanned_candle_count,
            "displacement_events": self.displacement_events,
            "displacement_sequences": self.displacement_sequences,
            "summary": self.summary,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class DisplacementIntelligenceValidator:
    """Deterministic validation for the displacement intelligence contract."""

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def validate_input(payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]

        symbol = str(payload.get("symbol", "")).upper()
        if symbol != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")

        timeframe = str(payload.get("timeframe", "")).upper()
        if timeframe not in VALID_TIMEFRAMES:
            errors.append(f"Unsupported timeframe: {timeframe or '<missing>'} is not in the allowed deterministic set {sorted(VALID_TIMEFRAMES)}")

        evaluation_time_value = payload.get("evaluation_time")
        if evaluation_time_value is None:
            errors.append("Missing required evaluation_time.")
        else:
            try:
                DisplacementIntelligenceValidator._parse_timestamp(evaluation_time_value)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

        config_value = payload.get("config")
        try:
            DisplacementIntelligenceConfig.from_payload(config_value)
        except ValueError as exc:
            errors.append(str(exc))

        seen_timestamps: set[str] = set()
        last_timestamp: datetime | None = None
        for idx, candle in enumerate(candle_history):
            if not isinstance(candle, dict):
                errors.append(f"Candle at index {idx} must be a dictionary.")
                continue

            required = ["timestamp", "open", "high", "low", "close"]
            for field_name in required:
                if field_name not in candle:
                    errors.append(f"Missing required candle field: {field_name} at index {idx}.")

            if "timestamp" in candle:
                timestamp_value = str(candle["timestamp"])
                if timestamp_value in seen_timestamps:
                    errors.append(f"Duplicate timestamp in candle_history: {timestamp_value}.")
                seen_timestamps.add(timestamp_value)
                try:
                    parsed = DisplacementIntelligenceValidator._parse_timestamp(timestamp_value)
                except ValueError:
                    errors.append(f"Invalid timestamp at index {idx}: must be parseable ISO 8601.")
                    continue
                if last_timestamp is not None and parsed <= last_timestamp:
                    errors.append(f"Timestamps must be strictly increasing; candle at index {idx} is not greater than the previous timestamp.")
                last_timestamp = parsed

            for field_name in ["open", "high", "low", "close"]:
                if field_name not in candle:
                    continue
                try:
                    numeric = float(candle[field_name])
                except (TypeError, ValueError):
                    errors.append(f"Non-numeric value for {field_name} at index {idx}.")
                    continue
                if numeric <= 0:
                    errors.append(f"Invalid numeric value for {field_name} at index {idx}: must be greater than 0.")

            if all(field_name in candle for field_name in ["open", "high", "low", "close"]):
                try:
                    open_value = float(candle["open"])
                    high_value = float(candle["high"])
                    low_value = float(candle["low"])
                    close_value = float(candle["close"])
                except (TypeError, ValueError):
                    continue
                if high_value < max(open_value, close_value):
                    errors.append(f"Impossible OHLC at index {idx}: high must be greater than or equal to max(open, close).")
                if low_value > min(open_value, close_value):
                    errors.append(f"Impossible OHLC at index {idx}: low must be less than or equal to min(open, close).")

        return errors


class DisplacementIntelligenceCapability:
    """Provider-independent deterministic displacement intelligence capability."""

    def __init__(self):
        self.name = "displacement_intelligence"
        self.contract = "trading.displacement_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual displacement intelligence for XAUUSD architecture validation."
        self.metadata = {
            "deterministic_displacement_intelligence": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
        }

    def validate_input(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        validator = DisplacementIntelligenceValidator()
        return validator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required = [
            "symbol",
            "timeframe",
            "evaluation_time",
            "timestamp",
            "scanned_candle_count",
            "displacement_events",
            "displacement_sequences",
            "summary",
            "evidence",
            "metadata",
        ]
        for field_name in required:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")

        forbidden_patterns = {
            "buy": r"\bbuy\b",
            "sell": r"\bsell\b",
            "entry": r"\bentry\b",
            "exit": r"\bexit\b",
            "stop_loss": r"\bstop_loss\b",
            "take_profit": r"\btake_profit\b",
            "risk_reward": r"\brisk_reward\b",
            "setup": r"\bsetup\b",
            "probability": r"\bprobability\b",
            "prediction": r"\bprediction\b",
            "forecast": r"\bforecast\b",
            "expected_direction": r"\bexpected_direction\b",
            "trade_recommendation": r"\btrade_recommendation\b",
            "position_size": r"\bposition_size\b",
            "broker_instruction": r"\bbroker_instruction\b",
            "execution_command": r"\bexecution_command\b",
            "stop_hunt": r"\bstop_hunt\b",
            "manipulation": r"\bmanipulation\b",
            "smart_money_intent": r"\bsmart_money_intent\b",
            "bos": r"\bbos\b",
            "choch": r"\bchoch\b",
            "mss": r"\bmss\b",
        }
        payload_text = str(payload).lower()
        for forbidden_term, pattern in forbidden_patterns.items():
            if re.search(pattern, payload_text):
                errors.append(f"Forbidden advisory term detected: {forbidden_term}")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> DisplacementIntelligenceResult:
        return DisplacementIntelligenceAnalyzer().analyze(payload)


class DisplacementIntelligenceSpecialist:
    """Read-only specialist wrapper for deterministic displacement intelligence."""

    def __init__(self):
        self.name = "displacement_analyst"
        self.division_name = "trading"
        self.capability_name = "displacement_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == "displacement_analyst"
            and capability_name == "displacement_intelligence"
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

    def analyze_displacement(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> DisplacementIntelligenceResult:
        return DisplacementIntelligenceAnalyzer().analyze(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)


class DisplacementIntelligenceAnalyzer:
    """Deterministic single-candle displacement and sequence analyzer for XAUUSD."""

    @staticmethod
    def _normalize_candles(candle_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for candle in candle_history:
            normalized.append(
                {
                    "timestamp": str(candle["timestamp"]),
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                }
            )
        return normalized

    @staticmethod
    def _build_true_range_series(candles: list[dict[str, Any]]) -> list[float]:
        true_ranges: list[float] = []
        for i, candle in enumerate(candles):
            high_value = candle["high"]
            low_value = candle["low"]
            if i == 0:
                true_ranges.append(high_value - low_value)
                continue
            previous_close = candles[i - 1]["close"]
            true_ranges.append(
                max(
                    high_value - low_value,
                    abs(high_value - previous_close),
                    abs(low_value - previous_close),
                )
            )
        return true_ranges

    def _evaluate_candidate(
        self,
        *,
        index: int,
        candles: list[dict[str, Any]],
        true_ranges: list[float],
        config: DisplacementIntelligenceConfig,
    ) -> dict[str, Any]:
        candle = candles[index]
        open_value = candle["open"]
        high_value = candle["high"]
        low_value = candle["low"]
        close_value = candle["close"]

        if close_value > open_value:
            direction = "bullish"
        elif close_value < open_value:
            direction = "bearish"
        else:
            direction = "neutral"

        candle_range = high_value - low_value
        body_size = abs(close_value - open_value)
        body_to_range_ratio = None if candle_range == 0 else body_size / candle_range
        close_location_ratio = None if candle_range == 0 else (close_value - low_value) / candle_range
        true_range = true_ranges[index]

        baseline_values: list[float] = []
        median_true_range = None
        if index >= config.baseline_window:
            baseline_values = true_ranges[index - config.baseline_window : index]
            median_true_range = median(baseline_values)
            if median_true_range == 0:
                baseline_state = "insufficient_context"
            else:
                baseline_state = "available"
        else:
            baseline_state = "insufficient_history"

        range_expansion_ratio = None
        if baseline_state == "available":
            range_expansion_ratio = true_range / median_true_range

        qualifies = False
        if direction != "neutral" and body_to_range_ratio is not None and baseline_state == "available":
            if direction == "bullish":
                close_gate = close_location_ratio >= config.bullish_close_location_min
            else:
                close_gate = close_location_ratio <= config.bearish_close_location_max
            qualifies = (
                body_to_range_ratio >= config.minimum_body_ratio
                and close_gate
                and range_expansion_ratio >= config.minimum_range_expansion_ratio
            )

        return {
            "index": index,
            "candle": candle,
            "direction": direction,
            "candle_range": candle_range,
            "body_size": body_size,
            "body_to_range_ratio": body_to_range_ratio,
            "close_location_ratio": close_location_ratio,
            "true_range": true_range,
            "baseline_state": baseline_state,
            "median_true_range": median_true_range,
            "baseline_values": baseline_values,
            "range_expansion_ratio": range_expansion_ratio,
            "qualifies": qualifies,
        }

    @staticmethod
    def _build_summary(events: list[dict[str, Any]], sequences: list[dict[str, Any]]) -> dict[str, int]:
        summary = {
            "bullish_event_count": 0,
            "bearish_event_count": 0,
            "bullish_sequence_count": 0,
            "bearish_sequence_count": 0,
        }
        for event in events:
            if event["direction"] == "bullish":
                summary["bullish_event_count"] += 1
            elif event["direction"] == "bearish":
                summary["bearish_event_count"] += 1
        for sequence in sequences:
            if sequence["direction"] == "bullish":
                summary["bullish_sequence_count"] += 1
            elif sequence["direction"] == "bearish":
                summary["bearish_sequence_count"] += 1
        return summary

    def analyze(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> DisplacementIntelligenceResult:
        errors = DisplacementIntelligenceValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid displacement intelligence input: " + "; ".join(errors))

        input_model = DisplacementIntelligenceInput.from_payload(payload)
        config = input_model.config
        candles = self._normalize_candles(input_model.candle_history)
        length = len(candles)
        current_timestamp = candles[-1]["timestamp"]
        last_index = length - 1

        true_ranges = self._build_true_range_series(candles)

        candidate_index_min = max(0, length - config.lookback_candles)
        candidate_index_max = length - 1
        scanned_candle_count = max(0, candidate_index_max - candidate_index_min + 1)

        candidate_evaluations = [
            self._evaluate_candidate(index=i, candles=candles, true_ranges=true_ranges, config=config)
            for i in range(candidate_index_min, candidate_index_max + 1)
        ]

        insufficient_history_count = sum(1 for item in candidate_evaluations if item["baseline_state"] == "insufficient_history")
        insufficient_context_count = sum(1 for item in candidate_evaluations if item["baseline_state"] == "insufficient_context")
        evaluable_candidate_count = sum(1 for item in candidate_evaluations if item["baseline_state"] == "available")

        boundary_continuation_checked = candidate_index_min > 0
        boundary_continuation_source_index = candidate_index_min - 1 if boundary_continuation_checked else None
        boundary_continuation_excluded = False
        if boundary_continuation_checked and candidate_evaluations:
            prior_evaluation = self._evaluate_candidate(index=candidate_index_min - 1, candles=candles, true_ranges=true_ranges, config=config)
            first_evaluation = candidate_evaluations[0]
            if prior_evaluation["qualifies"] and first_evaluation["qualifies"] and prior_evaluation["direction"] == first_evaluation["direction"]:
                boundary_continuation_excluded = True

        events: list[dict[str, Any]] = []
        event_position_by_index: dict[int, int] = {}
        direction_counters = {"bullish": 0, "bearish": 0}
        for item in candidate_evaluations:
            if not item["qualifies"]:
                continue
            direction = item["direction"]
            direction_counters[direction] += 1
            candle = item["candle"]
            event_id = f"{direction}_displacement_{direction_counters[direction]}"
            event = {
                "event_id": event_id,
                "direction": direction,
                "source_timestamp": candle["timestamp"],
                "confirmed_at": candle["timestamp"],
                "created_at": candle["timestamp"],
                "candle_range": item["candle_range"],
                "true_range": item["true_range"],
                "body_size": item["body_size"],
                "body_to_range_ratio": item["body_to_range_ratio"],
                "close_location_ratio": item["close_location_ratio"],
                "range_expansion_ratio": item["range_expansion_ratio"],
                "start_price": candle["open"],
                "end_price": candle["close"],
                "absolute_move": item["body_size"],
                "bars_since_event": last_index - item["index"],
                "evidence": {
                    "index": item["index"],
                    "timestamp": candle["timestamp"],
                    "ohlc": {
                        "open": candle["open"],
                        "high": candle["high"],
                        "low": candle["low"],
                        "close": candle["close"],
                    },
                    "baseline_state": item["baseline_state"],
                    "median_true_range": item["median_true_range"],
                    "baseline_values": item["baseline_values"],
                    "thresholds": {
                        "minimum_body_ratio": config.minimum_body_ratio,
                        "bullish_close_location_min": config.bullish_close_location_min,
                        "bearish_close_location_max": config.bearish_close_location_max,
                        "minimum_range_expansion_ratio": config.minimum_range_expansion_ratio,
                    },
                    "rule_branch": f"{direction}_displacement",
                    "rule_version": RULE_VERSION,
                },
            }
            event_position_by_index[item["index"]] = len(events)
            events.append(event)

        sequences: list[dict[str, Any]] = []
        sequence_counters = {"bullish": 0, "bearish": 0}
        current_run_indices: list[int] = []
        current_run_direction: str | None = None
        current_run_excluded = False

        def finalize_run() -> None:
            nonlocal current_run_indices, current_run_direction, current_run_excluded
            if (
                not current_run_excluded
                and current_run_direction is not None
                and len(current_run_indices) >= config.minimum_sequence_events
            ):
                member_events = [events[event_position_by_index[idx]] for idx in current_run_indices]
                created_at_member = member_events[config.minimum_sequence_events - 1]
                created_at_index = current_run_indices[config.minimum_sequence_events - 1]
                end_index = current_run_indices[-1]
                sequence_counters[current_run_direction] += 1
                sequence = {
                    "sequence_id": f"{current_run_direction}_sequence_{sequence_counters[current_run_direction]}",
                    "direction": current_run_direction,
                    "member_event_ids": [member["event_id"] for member in member_events],
                    "member_timestamps": [member["source_timestamp"] for member in member_events],
                    "member_count": len(member_events),
                    "source_timestamp": member_events[0]["source_timestamp"],
                    "created_at": created_at_member["source_timestamp"],
                    "start_timestamp": member_events[0]["source_timestamp"],
                    "end_timestamp": member_events[-1]["source_timestamp"],
                    "start_price": member_events[0]["start_price"],
                    "end_price": member_events[-1]["end_price"],
                    "cumulative_body_move": sum(member["body_size"] for member in member_events),
                    "cumulative_range": sum(member["candle_range"] for member in member_events),
                    "maximum_range_expansion_ratio": max(member["range_expansion_ratio"] for member in member_events),
                    "bars_since_creation": last_index - created_at_index,
                    "bars_since_end": last_index - end_index,
                    "evidence": {
                        "member_indices": list(current_run_indices),
                        "rule_version": RULE_VERSION,
                    },
                }
                sequences.append(sequence)
            current_run_indices = []
            current_run_direction = None
            current_run_excluded = False

        for position, item in enumerate(candidate_evaluations):
            if item["qualifies"]:
                direction = item["direction"]
                if current_run_indices and current_run_direction == direction:
                    current_run_indices.append(item["index"])
                else:
                    finalize_run()
                    current_run_indices = [item["index"]]
                    current_run_direction = direction
                    current_run_excluded = position == 0 and boundary_continuation_excluded
            else:
                finalize_run()
        finalize_run()

        summary = self._build_summary(events, sequences)

        evidence = {
            "displacement_rule_version": RULE_VERSION,
            "candidate_index_range": {
                "candidate_index_min": candidate_index_min,
                "candidate_index_max": candidate_index_max,
            },
            "scanned_candle_count_basis": "candidate_index_range_inclusive",
            "baseline_window": config.baseline_window,
            "config": config.as_dict(),
            "evaluated_candidate_count": len(candidate_evaluations),
            "insufficient_history_count": insufficient_history_count,
            "insufficient_context_count": insufficient_context_count,
            "evaluable_candidate_count": evaluable_candidate_count,
            "qualifying_event_count": len(events),
            "boundary_continuation_checked": boundary_continuation_checked,
            "boundary_continuation_source_index": boundary_continuation_source_index,
            "boundary_continuation_excluded": boundary_continuation_excluded,
        }
        if not events:
            evidence["reason"] = "no_qualifying_displacement"

        result = DisplacementIntelligenceResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=current_timestamp,
            scanned_candle_count=scanned_candle_count,
            displacement_events=events,
            displacement_sequences=sequences,
            summary=summary,
            evidence=evidence,
            metadata={
                "deterministic_displacement_intelligence": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "displacement_rule_version": RULE_VERSION,
                "authority_scope": "read_only",
                "analysis_scope": "read_only",
            },
        )

        output_errors = DisplacementIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid displacement intelligence result: " + "; ".join(output_errors))
        return result


DISPLACEMENT_INTELLIGENCE = DisplacementIntelligenceAnalyzer()

__all__ = [
    "DisplacementIntelligenceAnalyzer",
    "DisplacementIntelligenceCapability",
    "DisplacementIntelligenceSpecialist",
    "DisplacementIntelligenceConfig",
    "DisplacementIntelligenceInput",
    "DisplacementIntelligenceValidator",
    "DisplacementIntelligenceResult",
    "DISPLACEMENT_INTELLIGENCE",
    "RULE_VERSION",
]
