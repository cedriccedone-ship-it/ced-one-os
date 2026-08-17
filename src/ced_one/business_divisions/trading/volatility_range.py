"""Deterministic XAUUSD volatility and range intelligence for Vertical Slice #5.

This module stays read-only, provider-independent, and observational. It derives
realized range and volatility context from validated candle history without
introducing trading, prediction, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import re
from statistics import mean, median
from typing import Any

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "volatility_range_v1"


@dataclass(frozen=True)
class VolatilityRangeConfig:
    atr_window: int = 14
    range_window: int = 20
    short_volatility_window: int = 5
    long_volatility_window: int = 20
    low_volatility_ratio_max: float = 0.75
    elevated_volatility_ratio_min: float = 1.50
    compressed_range_ratio_max: float = 0.75
    normal_range_ratio_max: float = 1.25
    extreme_range_ratio_min: float = 2.00
    contraction_ratio_max: float = 0.80
    expansion_ratio_min: float = 1.20
    abnormal_range_ratio_min: float = 2.50

    def validate(self) -> list[str]:
        errors: list[str] = []
        int_fields = ["atr_window", "range_window", "short_volatility_window", "long_volatility_window"]
        for field_name in int_fields:
            value = getattr(self, field_name)
            if not isinstance(value, int):
                errors.append(f"Invalid config field {field_name}: must be an integer.")
                continue
            if value < 1:
                errors.append(f"Invalid config field {field_name}: must be at least 1.")

        if self.short_volatility_window >= self.long_volatility_window:
            errors.append("Invalid config: short_volatility_window must be less than long_volatility_window.")

        ratio_fields = [
            "low_volatility_ratio_max",
            "elevated_volatility_ratio_min",
            "compressed_range_ratio_max",
            "normal_range_ratio_max",
            "extreme_range_ratio_min",
            "contraction_ratio_max",
            "expansion_ratio_min",
            "abnormal_range_ratio_min",
        ]
        for field_name in ratio_fields:
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)):
                errors.append(f"Invalid config field {field_name}: must be numeric.")
                continue
            if value <= 0:
                errors.append(f"Invalid config field {field_name}: must be greater than 0.")

        if self.low_volatility_ratio_max >= self.elevated_volatility_ratio_min:
            errors.append("Invalid config: low_volatility_ratio_max must be less than elevated_volatility_ratio_min.")
        if self.compressed_range_ratio_max >= self.normal_range_ratio_max:
            errors.append("Invalid config: compressed_range_ratio_max must be less than normal_range_ratio_max.")
        if self.normal_range_ratio_max >= self.extreme_range_ratio_min:
            errors.append("Invalid config: normal_range_ratio_max must be less than extreme_range_ratio_min.")
        if self.contraction_ratio_max >= self.expansion_ratio_min:
            errors.append("Invalid config: contraction_ratio_max must be less than expansion_ratio_min.")
        return errors

    @classmethod
    def from_payload(cls, payload: Any | None) -> "VolatilityRangeConfig":
        if payload is None:
            return cls()
        if isinstance(payload, VolatilityRangeConfig):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid volatility range config: config must be a dictionary or VolatilityRangeConfig.")

        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid volatility range config: unknown fields {unknown_keys}.")

        config = cls(**{key: payload.get(key, getattr(cls(), key)) for key in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid volatility range config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class VolatilityRangeInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: VolatilityRangeConfig = field(default_factory=VolatilityRangeConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "VolatilityRangeInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=VolatilityRangeConfig.from_payload(payload.get("config")),
        )


@dataclass
class VolatilityRangeResult:
    symbol: str
    timeframe: str
    timestamp: str
    evaluation_time: str
    candle_range: float
    true_range: float
    atr: float | None
    median_candle_range: float | None
    median_true_range: float | None
    short_median_true_range: float | None
    long_median_true_range: float | None
    current_range_to_median_ratio: float | None
    current_true_range_to_median_ratio: float | None
    current_range_to_atr_ratio: float | None
    short_to_long_volatility_ratio: float | None
    volatility_state: str
    range_state: str
    volatility_trend: str
    abnormal_range: bool | None
    gap_state: str
    gap_amount: float
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "evaluation_time": self.evaluation_time,
            "candle_range": self.candle_range,
            "true_range": self.true_range,
            "atr": self.atr,
            "median_candle_range": self.median_candle_range,
            "median_true_range": self.median_true_range,
            "short_median_true_range": self.short_median_true_range,
            "long_median_true_range": self.long_median_true_range,
            "current_range_to_median_ratio": self.current_range_to_median_ratio,
            "current_true_range_to_median_ratio": self.current_true_range_to_median_ratio,
            "current_range_to_atr_ratio": self.current_range_to_atr_ratio,
            "short_to_long_volatility_ratio": self.short_to_long_volatility_ratio,
            "volatility_state": self.volatility_state,
            "range_state": self.range_state,
            "volatility_trend": self.volatility_trend,
            "abnormal_range": self.abnormal_range,
            "gap_state": self.gap_state,
            "gap_amount": self.gap_amount,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class VolatilityRangeValidator:
    """Deterministic validation for the volatility and range contract."""

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
                VolatilityRangeValidator._parse_timestamp(evaluation_time_value)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

        config_value = payload.get("config")
        try:
            VolatilityRangeConfig.from_payload(config_value)
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
                    parsed = VolatilityRangeValidator._parse_timestamp(timestamp_value)
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


class VolatilityRangeCapability:
    """Provider-independent realized volatility and range capability."""

    def __init__(self):
        self.name = "volatility_range"
        self.contract = "trading.volatility_range.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic realized volatility and range intelligence for XAUUSD."
        self.metadata = {
            "deterministic_volatility_intelligence": True,
            "realized_volatility_only": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
        }

    def validate_input(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        validator = VolatilityRangeValidator()
        return validator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required = [
            "symbol",
            "timeframe",
            "timestamp",
            "evaluation_time",
            "candle_range",
            "true_range",
            "atr",
            "median_candle_range",
            "median_true_range",
            "short_median_true_range",
            "long_median_true_range",
            "current_range_to_median_ratio",
            "current_true_range_to_median_ratio",
            "current_range_to_atr_ratio",
            "short_to_long_volatility_ratio",
            "volatility_state",
            "range_state",
            "volatility_trend",
            "abnormal_range",
            "gap_state",
            "gap_amount",
        ]
        for field_name in required:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")

        forbidden_patterns = {
            "buy": r"\bbuy\b",
            "sell": r"\bsell\b",
            "long": r"\blong\b",
            "short": r"\bshort\b",
            "entry": r"\bentry\b",
            "exit": r"\bexit\b",
            "stop_loss": r"\bstop_loss\b",
            "take_profit": r"\btake_profit\b",
            "risk_reward": r"\brisk_reward\b",
            "setup": r"\bsetup\b",
            "setup_quality": r"\bsetup_quality\b",
            "breakout_signal": r"\bbreakout_signal\b",
            "reversal_signal": r"\breversal_signal\b",
            "expected_volatility": r"\bexpected_volatility\b",
            "forecast": r"\bforecast\b",
            "probability": r"\bprobability\b",
            "trading_confidence": r"\btrading_confidence\b",
            "trade_recommendation": r"\btrade_recommendation\b",
            "position_size": r"\bposition_size\b",
            "broker_instruction": r"\bbroker_instruction\b",
            "execution_command": r"\bexecution_command\b",
        }
        payload_text = str(payload).lower()
        for forbidden_term, pattern in forbidden_patterns.items():
            if re.search(pattern, payload_text):
                errors.append(f"Forbidden advisory term detected: {forbidden_term}")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> VolatilityRangeResult:
        return VolatilityRangeAnalyzer().analyze(payload)


class VolatilityRangeSpecialist:
    """Read-only specialist wrapper for deterministic realized volatility and range."""

    def __init__(self):
        self.name = "volatility_analyst"
        self.division_name = "trading"
        self.capability_name = "volatility_range"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == "volatility_analyst"
            and capability_name == "volatility_range"
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

    def analyze_volatility(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> VolatilityRangeResult:
        return VolatilityRangeAnalyzer().analyze(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)


class VolatilityRangeAnalyzer:
    """Deterministic realized-volatility analyzer for XAUUSD candle history."""

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
    def _series_metrics(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        for idx, candle in enumerate(candles):
            candle_range = float(candle["high"]) - float(candle["low"])
            if idx == 0:
                true_range = candle_range
                gap_state = "no_gap"
                gap_amount = 0.0
            else:
                previous = candles[idx - 1]
                previous_close = float(previous["close"])
                true_range = max(
                    candle_range,
                    abs(float(candle["high"]) - previous_close),
                    abs(float(candle["low"]) - previous_close),
                )
                if float(candle["low"]) > float(previous["high"]):
                    gap_state = "gap_up"
                    gap_amount = float(candle["low"]) - float(previous["high"])
                elif float(candle["high"]) < float(previous["low"]):
                    gap_state = "gap_down"
                    gap_amount = float(previous["low"]) - float(candle["high"])
                else:
                    gap_state = "no_gap"
                    gap_amount = 0.0

            series.append(
                {
                    "timestamp": candle["timestamp"],
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                    "candle_range": candle_range,
                    "true_range": true_range,
                    "gap_state": gap_state,
                    "gap_amount": gap_amount,
                }
            )
        return series

    @staticmethod
    def _tail_mean(values: list[float], window: int) -> float | None:
        if len(values) < window:
            return None
        return mean(values[-window:])

    @staticmethod
    def _tail_median(values: list[float], window: int) -> float | None:
        if len(values) < window:
            return None
        return median(values[-window:])

    @staticmethod
    def _ratio(numerator: float, denominator: float | None) -> float | None:
        if denominator is None or denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _state_from_ratio(ratio: float | None, *, low_max: float, high_min: float, low_label: str, high_label: str, middle_label: str, insufficient_state: str) -> str:
        if ratio is None:
            return insufficient_state
        if ratio < low_max:
            return low_label
        if ratio > high_min:
            return high_label
        return middle_label

    def analyze(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> VolatilityRangeResult:
        errors = VolatilityRangeValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid volatility range input: " + "; ".join(errors))

        input_model = VolatilityRangeInput.from_payload(payload)
        config = input_model.config
        normalized = self._normalize_candles(input_model.candle_history)
        series = self._series_metrics(normalized)
        current = series[-1]

        prior_ranges = [item["candle_range"] for item in series[:-1]]
        prior_true_ranges = [item["true_range"] for item in series[:-1]]

        atr = self._tail_mean(prior_true_ranges, config.atr_window)
        median_candle_range = self._tail_median(prior_ranges, config.range_window)
        median_true_range = self._tail_median(prior_true_ranges, config.range_window)
        short_median_true_range = self._tail_median(prior_true_ranges, config.short_volatility_window)
        long_median_true_range = self._tail_median(prior_true_ranges, config.long_volatility_window)

        current_range_to_atr_ratio = self._ratio(current["candle_range"], atr)
        current_range_to_median_ratio = self._ratio(current["candle_range"], median_candle_range)
        current_true_range_to_median_ratio = self._ratio(current["true_range"], median_true_range)
        short_to_long_volatility_ratio = self._ratio(short_median_true_range, long_median_true_range)

        atr_state = "available"
        if len(prior_true_ranges) < config.atr_window:
            atr_state = "insufficient_history"
        elif atr == 0:
            atr_state = "insufficient_context"

        range_baseline_state = "available"
        if len(prior_ranges) < config.range_window:
            range_baseline_state = "insufficient_history"
        elif median_candle_range == 0:
            range_baseline_state = "insufficient_context"

        volatility_baseline_state = "available"
        if len(prior_true_ranges) < config.range_window:
            volatility_baseline_state = "insufficient_history"
        elif median_true_range == 0:
            volatility_baseline_state = "insufficient_context"

        short_volatility_state = "available" if len(prior_true_ranges) >= config.short_volatility_window else "insufficient_history"
        long_volatility_state = "available"
        if len(prior_true_ranges) < config.long_volatility_window:
            long_volatility_state = "insufficient_history"
        elif long_median_true_range == 0:
            long_volatility_state = "insufficient_context"

        volatility_state = "insufficient_history"
        if volatility_baseline_state == "insufficient_context":
            volatility_state = "insufficient_context"
        elif volatility_baseline_state == "available" and current_true_range_to_median_ratio is not None:
            if current_true_range_to_median_ratio < config.low_volatility_ratio_max:
                volatility_state = "low"
            elif current_true_range_to_median_ratio > config.elevated_volatility_ratio_min:
                volatility_state = "elevated"
            else:
                volatility_state = "moderate"

        range_state = "insufficient_history"
        if range_baseline_state == "insufficient_context":
            range_state = "insufficient_context"
        elif range_baseline_state == "available" and current_range_to_median_ratio is not None:
            if current_range_to_median_ratio < config.compressed_range_ratio_max:
                range_state = "compressed"
            elif current_range_to_median_ratio > config.normal_range_ratio_max:
                if current_range_to_median_ratio <= config.extreme_range_ratio_min:
                    range_state = "expanded"
                else:
                    range_state = "extreme"
            else:
                range_state = "normal"

        volatility_trend = "insufficient_history"
        if len(prior_true_ranges) >= config.long_volatility_window:
            if long_median_true_range == 0:
                volatility_trend = "insufficient_context"
            elif short_to_long_volatility_ratio is not None:
                if short_to_long_volatility_ratio < config.contraction_ratio_max:
                    volatility_trend = "contracting"
                elif short_to_long_volatility_ratio > config.expansion_ratio_min:
                    volatility_trend = "expanding"
                else:
                    volatility_trend = "stable"

        abnormal_range: bool | None = None
        abnormal_range_state = "insufficient_history"
        if range_baseline_state == "available" and current_range_to_median_ratio is not None:
            abnormal_range = current_range_to_median_ratio >= config.abnormal_range_ratio_min
            abnormal_range_state = "available"
        elif range_baseline_state == "insufficient_context":
            abnormal_range_state = "insufficient_context"

        evidence = {
            "current_candle": current,
            "thresholds": config.as_dict(),
            "series_windows": {
                "atr_window": config.atr_window,
                "range_window": config.range_window,
                "short_volatility_window": config.short_volatility_window,
                "long_volatility_window": config.long_volatility_window,
            },
            "historical_values": {
                "prior_candle_ranges": prior_ranges[-config.range_window :],
                "prior_true_ranges": prior_true_ranges[-config.range_window :],
                "atr_inputs": prior_true_ranges[-config.atr_window :],
                "median_candle_range_inputs": prior_ranges[-config.range_window :],
                "median_true_range_inputs": prior_true_ranges[-config.range_window :],
                "short_median_true_range_inputs": prior_true_ranges[-config.short_volatility_window :],
                "long_median_true_range_inputs": prior_true_ranges[-config.long_volatility_window :],
            },
            "baseline_states": {
                "atr_state": atr_state,
                "range_baseline_state": range_baseline_state,
                "volatility_baseline_state": volatility_baseline_state,
                "short_volatility_state": short_volatility_state,
                "long_volatility_state": long_volatility_state,
                "abnormal_range_state": abnormal_range_state,
            },
            "normalized_ratios": {
                "current_range_to_median_ratio": current_range_to_median_ratio,
                "current_true_range_to_median_ratio": current_true_range_to_median_ratio,
                "current_range_to_atr_ratio": current_range_to_atr_ratio,
                "short_to_long_volatility_ratio": short_to_long_volatility_ratio,
            },
            "classification_rules": {
                "volatility_state": {
                    "low": f"ratio < {config.low_volatility_ratio_max}",
                    "moderate": f"ratio >= {config.low_volatility_ratio_max} and ratio <= {config.elevated_volatility_ratio_min}",
                    "elevated": f"ratio > {config.elevated_volatility_ratio_min}",
                },
                "range_state": {
                    "compressed": f"ratio < {config.compressed_range_ratio_max}",
                    "normal": f"ratio >= {config.compressed_range_ratio_max} and ratio <= {config.normal_range_ratio_max}",
                    "expanded": f"ratio > {config.normal_range_ratio_max} and ratio <= {config.extreme_range_ratio_min}",
                    "extreme": f"ratio > {config.extreme_range_ratio_min}",
                },
                "volatility_trend": {
                    "contracting": f"ratio < {config.contraction_ratio_max}",
                    "stable": f"ratio >= {config.contraction_ratio_max} and ratio <= {config.expansion_ratio_min}",
                    "expanding": f"ratio > {config.expansion_ratio_min}",
                },
                "abnormal_range": f"current_range_to_median_ratio >= {config.abnormal_range_ratio_min}",
            },
            "gap_evidence": {
                "gap_state": current["gap_state"],
                "gap_amount": current["gap_amount"],
            },
            "candle_rule_version": RULE_VERSION,
        }

        result = VolatilityRangeResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            timestamp=current["timestamp"],
            evaluation_time=input_model.evaluation_time,
            candle_range=current["candle_range"],
            true_range=current["true_range"],
            atr=atr,
            median_candle_range=median_candle_range,
            median_true_range=median_true_range,
            short_median_true_range=short_median_true_range,
            long_median_true_range=long_median_true_range,
            current_range_to_median_ratio=current_range_to_median_ratio,
            current_true_range_to_median_ratio=current_true_range_to_median_ratio,
            current_range_to_atr_ratio=current_range_to_atr_ratio,
            short_to_long_volatility_ratio=short_to_long_volatility_ratio,
            volatility_state=volatility_state,
            range_state=range_state,
            volatility_trend=volatility_trend,
            abnormal_range=abnormal_range,
            gap_state=current["gap_state"],
            gap_amount=current["gap_amount"],
            evidence=evidence,
            metadata={
                "deterministic_volatility_intelligence": True,
                "realized_volatility_only": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "volatility_rule_version": RULE_VERSION,
                "authority_scope": "read_only",
                "analysis_scope": "read_only",
            },
        )

        output_errors = VolatilityRangeCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid volatility range result: " + "; ".join(output_errors))
        return result


VOLATILITY_RANGE = VolatilityRangeAnalyzer()

__all__ = [
    "VolatilityRangeAnalyzer",
    "VolatilityRangeCapability",
    "VolatilityRangeConfig",
    "VolatilityRangeInput",
    "VolatilityRangeResult",
    "VolatilityRangeSpecialist",
    "VolatilityRangeValidator",
    "VOLATILITY_RANGE",
    "RULE_VERSION",
]