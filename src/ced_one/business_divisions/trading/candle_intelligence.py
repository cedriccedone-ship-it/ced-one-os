"""Deterministic XAUUSD candle intelligence for Vertical Slice #4.

This module stays read-only, provider-independent, and observational. It
derives factual candle morphology and bounded sequence evidence without
introducing strategy, execution, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from statistics import median
from typing import Any

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "candle_intelligence_v1"


@dataclass(frozen=True)
class CandleIntelligenceConfig:
    small_body_ratio_max: float = 0.25
    large_body_ratio_min: float = 0.60
    dominant_wick_ratio_min: float = 0.50
    minimal_wick_ratio_max: float = 0.10
    balanced_wick_difference_max: float = 0.10
    rejection_wick_ratio_min: float = 0.50
    rejection_body_ratio_max: float = 0.30
    bullish_rejection_close_min: float = 0.75
    bearish_rejection_close_max: float = 0.25
    close_near_high_min: float = 0.80
    close_upper_region_min: float = 0.60
    close_lower_region_max: float = 0.40
    close_near_low_max: float = 0.20
    expansion_multiplier: float = 1.20
    compression_multiplier: float = 0.80
    sequence_window: int = 5
    alternating_sequence_length: int = 4
    range_sequence_length: int = 3

    def validate(self) -> list[str]:
        errors: list[str] = []

        ratio_fields = [
            "small_body_ratio_max",
            "large_body_ratio_min",
            "dominant_wick_ratio_min",
            "minimal_wick_ratio_max",
            "balanced_wick_difference_max",
            "rejection_wick_ratio_min",
            "rejection_body_ratio_max",
            "bullish_rejection_close_min",
            "bearish_rejection_close_max",
            "close_near_high_min",
            "close_upper_region_min",
            "close_lower_region_max",
            "close_near_low_max",
            "expansion_multiplier",
            "compression_multiplier",
        ]
        for field_name in ratio_fields:
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)):
                errors.append(f"Invalid config field {field_name}: must be numeric.")
                continue
            if field_name in {"expansion_multiplier", "compression_multiplier"}:
                if value <= 0:
                    errors.append(f"Invalid config field {field_name}: must be greater than 0.")
                continue
            if value < 0 or value > 1:
                errors.append(f"Invalid config field {field_name}: ratio thresholds must be between 0 and 1.")

        if self.expansion_multiplier <= self.compression_multiplier:
            errors.append("Invalid config: expansion_multiplier must be greater than compression_multiplier.")
        if self.sequence_window < 1:
            errors.append("Invalid config: sequence_window must be at least 1.")
        if self.alternating_sequence_length < 2:
            errors.append("Invalid config: alternating_sequence_length must be at least 2.")
        if self.range_sequence_length < 2:
            errors.append("Invalid config: range_sequence_length must be at least 2.")
        if self.small_body_ratio_max >= self.large_body_ratio_min:
            errors.append("Invalid config: small_body_ratio_max must be less than large_body_ratio_min.")
        if self.bearish_rejection_close_max >= self.bullish_rejection_close_min:
            errors.append("Invalid config: bearish_rejection_close_max must be less than bullish_rejection_close_min.")
        if self.close_near_low_max >= self.close_upper_region_min:
            errors.append("Invalid config: close_near_low_max must be less than close_upper_region_min.")
        return errors

    @classmethod
    def from_payload(cls, payload: Any | None) -> "CandleIntelligenceConfig":
        if payload is None:
            return cls()
        if isinstance(payload, CandleIntelligenceConfig):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid candle intelligence config: config must be a dictionary or CandleIntelligenceConfig.")

        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid candle intelligence config: unknown fields {unknown_keys}.")

        config = cls(**{key: payload.get(key, getattr(cls(), key)) for key in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid candle intelligence config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class CandleIntelligenceInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: CandleIntelligenceConfig = field(default_factory=CandleIntelligenceConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CandleIntelligenceInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=CandleIntelligenceConfig.from_payload(payload.get("config")),
        )


@dataclass
class CandleIntelligenceResult:
    symbol: str
    timeframe: str
    timestamp: str
    evaluation_time: str
    range: float
    body_size: float
    upper_wick_size: float
    lower_wick_size: float
    body_to_range_ratio: float | None
    upper_wick_to_range_ratio: float | None
    lower_wick_to_range_ratio: float | None
    close_location_ratio: float | None
    candle_direction: str
    body_classification: str
    wick_classification: str
    close_location_classification: str
    rejection_classification: str
    engulfing_classification: str
    bar_relationship: str
    relative_range_classification: str
    consecutive_bullish_count: int
    consecutive_bearish_count: int
    alternating_sequence: bool
    range_expansion_sequence: bool
    range_compression_sequence: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "evaluation_time": self.evaluation_time,
            "range": self.range,
            "body_size": self.body_size,
            "upper_wick_size": self.upper_wick_size,
            "lower_wick_size": self.lower_wick_size,
            "body_to_range_ratio": self.body_to_range_ratio,
            "upper_wick_to_range_ratio": self.upper_wick_to_range_ratio,
            "lower_wick_to_range_ratio": self.lower_wick_to_range_ratio,
            "close_location_ratio": self.close_location_ratio,
            "candle_direction": self.candle_direction,
            "body_classification": self.body_classification,
            "wick_classification": self.wick_classification,
            "close_location_classification": self.close_location_classification,
            "rejection_classification": self.rejection_classification,
            "engulfing_classification": self.engulfing_classification,
            "bar_relationship": self.bar_relationship,
            "relative_range_classification": self.relative_range_classification,
            "consecutive_bullish_count": self.consecutive_bullish_count,
            "consecutive_bearish_count": self.consecutive_bearish_count,
            "alternating_sequence": self.alternating_sequence,
            "range_expansion_sequence": self.range_expansion_sequence,
            "range_compression_sequence": self.range_compression_sequence,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class CandleIntelligenceValidator:
    """Deterministic validation for the candle intelligence contract."""

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
                CandleIntelligenceValidator._parse_timestamp(evaluation_time_value)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

        config_value = payload.get("config")
        try:
            CandleIntelligenceConfig.from_payload(config_value)
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
                    parsed = CandleIntelligenceValidator._parse_timestamp(timestamp_value)
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


class CandleIntelligenceCapability:
    """Provider-independent deterministic candle intelligence capability."""

    def __init__(self):
        self.name = "candle_intelligence"
        self.contract = "trading.candle_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual candle intelligence for XAUUSD architecture validation."
        self.metadata = {
            "deterministic_candle_intelligence": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
        }

    def validate_input(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        validator = CandleIntelligenceValidator()
        return validator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required = [
            "symbol",
            "timeframe",
            "timestamp",
            "range",
            "body_size",
            "upper_wick_size",
            "lower_wick_size",
            "body_to_range_ratio",
            "upper_wick_to_range_ratio",
            "lower_wick_to_range_ratio",
            "close_location_ratio",
            "candle_direction",
            "body_classification",
            "wick_classification",
            "close_location_classification",
            "rejection_classification",
            "engulfing_classification",
            "bar_relationship",
            "relative_range_classification",
        ]
        for field_name in required:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")

        forbidden = [
            "BUY",
            "SELL",
            "long",
            "short",
            "entry",
            "exit",
            "stop_loss",
            "take_profit",
            "risk_reward",
            "setup_quality",
            "trading_confidence",
            "trade_recommendation",
            "broker_instruction",
            "execution_command",
        ]
        payload_text = str(payload).lower()
        for forbidden_term in forbidden:
            if forbidden_term.lower() in payload_text:
                errors.append(f"Forbidden advisory term detected: {forbidden_term}")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> CandleIntelligenceResult:
        return CandleIntelligenceAnalyzer().analyze(payload)


class CandleIntelligenceSpecialist:
    """Read-only trading specialist wrapper for deterministic candle intelligence."""

    def __init__(self):
        self.name = "candle_analyst"
        self.division_name = "trading"
        self.capability_name = "candle_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == "candle_analyst"
            and capability_name == "candle_intelligence"
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

    def analyze_candles(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> CandleIntelligenceResult:
        return CandleIntelligenceAnalyzer().analyze(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)


class CandleIntelligenceAnalyzer:
    """Deterministic candle morphology analyzer for the latest XAUUSD candle."""

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
    def _candle_metrics(candle: dict[str, Any]) -> dict[str, float | None]:
        open_value = float(candle["open"])
        high_value = float(candle["high"])
        low_value = float(candle["low"])
        close_value = float(candle["close"])
        candle_range = high_value - low_value
        body_size = abs(close_value - open_value)
        upper_wick_size = high_value - max(open_value, close_value)
        lower_wick_size = min(open_value, close_value) - low_value
        if candle_range == 0:
            return {
                "range": 0.0,
                "body_size": 0.0,
                "upper_wick_size": 0.0,
                "lower_wick_size": 0.0,
                "body_to_range_ratio": None,
                "upper_wick_to_range_ratio": None,
                "lower_wick_to_range_ratio": None,
                "close_location_ratio": None,
            }
        return {
            "range": candle_range,
            "body_size": body_size,
            "upper_wick_size": upper_wick_size,
            "lower_wick_size": lower_wick_size,
            "body_to_range_ratio": body_size / candle_range,
            "upper_wick_to_range_ratio": upper_wick_size / candle_range,
            "lower_wick_to_range_ratio": lower_wick_size / candle_range,
            "close_location_ratio": (close_value - low_value) / candle_range,
        }

    @staticmethod
    def _classify_direction(candle: dict[str, Any]) -> str:
        if candle["close"] > candle["open"]:
            return "bullish"
        if candle["close"] < candle["open"]:
            return "bearish"
        return "neutral"

    @staticmethod
    def _classify_body(metrics: dict[str, float | None], config: CandleIntelligenceConfig) -> str:
        if metrics["range"] == 0:
            return "zero_range"
        body_ratio = metrics["body_to_range_ratio"]
        if body_ratio is None:
            return "zero_range"
        if body_ratio <= config.small_body_ratio_max:
            return "small_body"
        if body_ratio < config.large_body_ratio_min:
            return "medium_body"
        return "large_body"

    @staticmethod
    def _classify_wick(metrics: dict[str, float | None], config: CandleIntelligenceConfig) -> str:
        if metrics["range"] == 0:
            return "zero_range"
        upper_ratio = metrics["upper_wick_to_range_ratio"]
        lower_ratio = metrics["lower_wick_to_range_ratio"]
        if upper_ratio is None or lower_ratio is None:
            return "zero_range"
        if upper_ratio >= config.dominant_wick_ratio_min and upper_ratio > lower_ratio:
            return "dominant_upper_wick"
        if lower_ratio >= config.dominant_wick_ratio_min and lower_ratio > upper_ratio:
            return "dominant_lower_wick"
        if upper_ratio <= config.minimal_wick_ratio_max and lower_ratio <= config.minimal_wick_ratio_max:
            return "minimal_wicks"
        if abs(upper_ratio - lower_ratio) <= config.balanced_wick_difference_max:
            return "balanced_wicks"
        return "mixed_wicks"

    @staticmethod
    def _classify_close_location(metrics: dict[str, float | None], config: CandleIntelligenceConfig) -> str:
        if metrics["range"] == 0:
            return "zero_range"
        ratio = metrics["close_location_ratio"]
        if ratio is None:
            return "zero_range"
        if ratio >= config.close_near_high_min:
            return "close_near_high"
        if ratio >= config.close_upper_region_min:
            return "close_upper_region"
        if ratio > config.close_lower_region_max:
            return "close_middle_region"
        if ratio > config.close_near_low_max:
            return "close_lower_region"
        return "close_near_low"

    @staticmethod
    def _classify_rejection(candle: dict[str, Any], metrics: dict[str, float | None], config: CandleIntelligenceConfig) -> str:
        if metrics["range"] == 0:
            return "none"
        body_ratio = metrics["body_to_range_ratio"]
        upper_ratio = metrics["upper_wick_to_range_ratio"]
        lower_ratio = metrics["lower_wick_to_range_ratio"]
        close_ratio = metrics["close_location_ratio"]
        if body_ratio is None or upper_ratio is None or lower_ratio is None or close_ratio is None:
            return "none"
        if (
            candle["close"] > candle["open"]
            and lower_ratio >= config.rejection_wick_ratio_min
            and body_ratio <= config.rejection_body_ratio_max
            and close_ratio >= config.bullish_rejection_close_min
        ):
            return "bullish_rejection"
        if (
            candle["close"] < candle["open"]
            and upper_ratio >= config.rejection_wick_ratio_min
            and body_ratio <= config.rejection_body_ratio_max
            and close_ratio <= config.bearish_rejection_close_max
        ):
            return "bearish_rejection"
        return "none"

    @staticmethod
    def _classify_engulfing(candles: list[dict[str, Any]]) -> str:
        if len(candles) < 2:
            return "none"
        current = candles[-1]
        previous = candles[-2]
        current_body_high = max(current["open"], current["close"])
        current_body_low = min(current["open"], current["close"])
        previous_body_high = max(previous["open"], previous["close"])
        previous_body_low = min(previous["open"], previous["close"])
        if (
            current["close"] > current["open"]
            and previous["close"] < previous["open"]
            and current_body_high > previous_body_high
            and current_body_low < previous_body_low
        ):
            return "bullish_engulfing"
        if (
            current["close"] < current["open"]
            and previous["close"] > previous["open"]
            and current_body_high > previous_body_high
            and current_body_low < previous_body_low
        ):
            return "bearish_engulfing"
        return "none"

    @staticmethod
    def _classify_bar_relationship(candles: list[dict[str, Any]]) -> str:
        if len(candles) < 2:
            return "none"
        current = candles[-1]
        previous = candles[-2]
        if current["high"] < previous["high"] and current["low"] > previous["low"]:
            return "inside_bar"
        if current["high"] > previous["high"] and current["low"] < previous["low"]:
            return "outside_bar"
        return "none"

    @staticmethod
    def _relative_range_classification(candles: list[dict[str, Any]], config: CandleIntelligenceConfig) -> tuple[str, dict[str, Any]]:
        if len(candles) <= config.sequence_window:
            return "insufficient_sequence_context", {"baseline_ranges": [], "median_baseline_range": None}
        prior_candles = candles[:-1]
        baseline_source = prior_candles[-config.sequence_window :]
        baseline_ranges = [candle["high"] - candle["low"] for candle in baseline_source]
        if len(baseline_ranges) < config.sequence_window:
            return "insufficient_sequence_context", {"baseline_ranges": baseline_ranges, "median_baseline_range": None}
        baseline = median(baseline_ranges)
        if baseline == 0:
            return "insufficient_sequence_context", {"baseline_ranges": baseline_ranges, "median_baseline_range": baseline}
        current_range = candles[-1]["high"] - candles[-1]["low"]
        if current_range < baseline * config.compression_multiplier:
            classification = "compressed"
        elif current_range > baseline * config.expansion_multiplier:
            classification = "expanded"
        else:
            classification = "normal"
        return classification, {
            "baseline_ranges": baseline_ranges,
            "median_baseline_range": baseline,
            "current_range": current_range,
            "compression_multiplier": config.compression_multiplier,
            "expansion_multiplier": config.expansion_multiplier,
        }

    @staticmethod
    def _sequence_evidence(candles: list[dict[str, Any]], config: CandleIntelligenceConfig) -> dict[str, Any]:
        bounded_candles = candles[-config.sequence_window :]
        directions = [CandleIntelligenceAnalyzer._classify_direction(candle) for candle in bounded_candles]
        ranges = [candle["high"] - candle["low"] for candle in bounded_candles]

        consecutive_bullish_count = 0
        for direction in reversed(directions):
            if direction != "bullish":
                break
            consecutive_bullish_count += 1

        consecutive_bearish_count = 0
        for direction in reversed(directions):
            if direction != "bearish":
                break
            consecutive_bearish_count += 1

        alternating_sequence = False
        if len(directions) >= config.alternating_sequence_length:
            last_directions = directions[-config.alternating_sequence_length :]
            if all(direction in {"bullish", "bearish"} for direction in last_directions):
                alternating_sequence = all(last_directions[index] != last_directions[index - 1] for index in range(1, len(last_directions)))

        range_expansion_sequence = False
        range_compression_sequence = False
        if len(ranges) >= config.range_sequence_length:
            last_ranges = ranges[-config.range_sequence_length :]
            range_expansion_sequence = all(last_ranges[index] > last_ranges[index - 1] for index in range(1, len(last_ranges)))
            range_compression_sequence = all(last_ranges[index] < last_ranges[index - 1] for index in range(1, len(last_ranges)))

        return {
            "directions": directions,
            "ranges": ranges,
            "consecutive_bullish_count": consecutive_bullish_count,
            "consecutive_bearish_count": consecutive_bearish_count,
            "alternating_sequence": alternating_sequence,
            "range_expansion_sequence": range_expansion_sequence,
            "range_compression_sequence": range_compression_sequence,
            "sequence_window": config.sequence_window,
            "alternating_sequence_length": config.alternating_sequence_length,
            "range_sequence_length": config.range_sequence_length,
        }

    def analyze(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> CandleIntelligenceResult:
        errors = CandleIntelligenceValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid candle intelligence input: " + "; ".join(errors))

        input_model = CandleIntelligenceInput.from_payload(payload)
        normalized = self._normalize_candles(input_model.candle_history)
        current = normalized[-1]
        config = input_model.config

        metrics = self._candle_metrics(current)
        candle_direction = self._classify_direction(current)
        body_classification = self._classify_body(metrics, config)
        wick_classification = self._classify_wick(metrics, config)
        close_location_classification = self._classify_close_location(metrics, config)
        rejection_classification = self._classify_rejection(current, metrics, config)
        engulfing_classification = self._classify_engulfing(normalized)
        bar_relationship = self._classify_bar_relationship(normalized)
        relative_range_classification, relative_range_evidence = self._relative_range_classification(normalized, config)
        sequence_evidence = self._sequence_evidence(normalized, config)

        evidence = {
            "current_candle": current,
            "metrics": metrics,
            "thresholds": config.as_dict(),
            "body_rule": {
                "small_body": f"body_to_range_ratio <= {config.small_body_ratio_max}",
                "medium_body": f"body_to_range_ratio > {config.small_body_ratio_max} and body_to_range_ratio < {config.large_body_ratio_min}",
                "large_body": f"body_to_range_ratio >= {config.large_body_ratio_min}",
            },
            "wick_rule": {
                "dominant_wick_ratio_min": config.dominant_wick_ratio_min,
                "minimal_wick_ratio_max": config.minimal_wick_ratio_max,
                "balanced_wick_difference_max": config.balanced_wick_difference_max,
            },
            "close_location_rule": {
                "close_near_high_min": config.close_near_high_min,
                "close_upper_region_min": config.close_upper_region_min,
                "close_lower_region_max": config.close_lower_region_max,
                "close_near_low_max": config.close_near_low_max,
            },
            "rejection_rule": {
                "rejection_wick_ratio_min": config.rejection_wick_ratio_min,
                "rejection_body_ratio_max": config.rejection_body_ratio_max,
                "bullish_rejection_close_min": config.bullish_rejection_close_min,
                "bearish_rejection_close_max": config.bearish_rejection_close_max,
            },
            "engulfing_rule": {
                "body_engulfing": True,
                "requires_opposite_previous_direction": True,
            },
            "bar_relationship_rule": {
                "inside_bar": "current.high < previous.high and current.low > previous.low",
                "outside_bar": "current.high > previous.high and current.low < previous.low",
            },
            "relative_range_rule": {
                "sequence_window": config.sequence_window,
                "compression_multiplier": config.compression_multiplier,
                "expansion_multiplier": config.expansion_multiplier,
                **relative_range_evidence,
            },
            "sequence_evidence": sequence_evidence,
            "candle_rule_version": RULE_VERSION,
        }

        result = CandleIntelligenceResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            timestamp=current["timestamp"],
            evaluation_time=input_model.evaluation_time,
            range=metrics["range"] or 0.0,
            body_size=metrics["body_size"] or 0.0,
            upper_wick_size=metrics["upper_wick_size"] or 0.0,
            lower_wick_size=metrics["lower_wick_size"] or 0.0,
            body_to_range_ratio=metrics["body_to_range_ratio"],
            upper_wick_to_range_ratio=metrics["upper_wick_to_range_ratio"],
            lower_wick_to_range_ratio=metrics["lower_wick_to_range_ratio"],
            close_location_ratio=metrics["close_location_ratio"],
            candle_direction=candle_direction,
            body_classification=body_classification,
            wick_classification=wick_classification,
            close_location_classification=close_location_classification,
            rejection_classification=rejection_classification,
            engulfing_classification=engulfing_classification,
            bar_relationship=bar_relationship,
            relative_range_classification=relative_range_classification,
            consecutive_bullish_count=sequence_evidence["consecutive_bullish_count"],
            consecutive_bearish_count=sequence_evidence["consecutive_bearish_count"],
            alternating_sequence=sequence_evidence["alternating_sequence"],
            range_expansion_sequence=sequence_evidence["range_expansion_sequence"],
            range_compression_sequence=sequence_evidence["range_compression_sequence"],
            evidence=evidence,
            metadata={
                "deterministic_candle_intelligence": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "candle_rule_version": RULE_VERSION,
                "authority_scope": "read_only",
                "analysis_scope": "read_only",
            },
        )

        output_errors = CandleIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid candle intelligence result: " + "; ".join(output_errors))
        return result


CANDLE_INTELLIGENCE = CandleIntelligenceAnalyzer()

__all__ = [
    "CandleIntelligenceAnalyzer",
    "CandleIntelligenceCapability",
    "CandleIntelligenceConfig",
    "CandleIntelligenceInput",
    "CandleIntelligenceResult",
    "CandleIntelligenceSpecialist",
    "CandleIntelligenceValidator",
    "CANDLE_INTELLIGENCE",
    "RULE_VERSION",
]