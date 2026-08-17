"""Deterministic XAUUSD fair value gap and imbalance intelligence for Vertical Slice #7.

This module stays read-only, provider-independent, and observational. It detects
factual three-candle geometric imbalances and tracks deterministic fill behavior
without strategy, execution, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import re
from typing import Any

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "fvg_imbalance_intelligence_v1"


@dataclass(frozen=True)
class FVGIntelligenceConfig:
    lookback_candles: int = 100
    interaction_tolerance: float = 0.0
    include_fully_filled: bool = True
    minimum_gap_size: float = 0.0

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not isinstance(self.lookback_candles, int):
            errors.append("Invalid config field lookback_candles: must be an integer.")
        elif self.lookback_candles < 3:
            errors.append("Invalid config field lookback_candles: must be at least 3.")

        if not isinstance(self.interaction_tolerance, (int, float)):
            errors.append("Invalid config field interaction_tolerance: must be numeric.")
        elif self.interaction_tolerance < 0:
            errors.append("Invalid config field interaction_tolerance: must be greater than or equal to 0.")

        if not isinstance(self.include_fully_filled, bool):
            errors.append("Invalid config field include_fully_filled: must be a boolean.")

        if not isinstance(self.minimum_gap_size, (int, float)):
            errors.append("Invalid config field minimum_gap_size: must be numeric.")
        elif self.minimum_gap_size < 0:
            errors.append("Invalid config field minimum_gap_size: must be greater than or equal to 0.")

        return errors

    @classmethod
    def from_payload(cls, payload: Any | None) -> "FVGIntelligenceConfig":
        if payload is None:
            return cls()
        if isinstance(payload, FVGIntelligenceConfig):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid fvg intelligence config: config must be a dictionary or FVGIntelligenceConfig.")

        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid fvg intelligence config: unknown fields {unknown_keys}.")

        config = cls(**{key: payload.get(key, getattr(cls(), key)) for key in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid fvg intelligence config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class FVGIntelligenceInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: FVGIntelligenceConfig = field(default_factory=FVGIntelligenceConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FVGIntelligenceInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=FVGIntelligenceConfig.from_payload(payload.get("config")),
        )


@dataclass
class FairValueGapIntelligenceResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    fair_value_gaps: list[dict[str, Any]] = field(default_factory=list)
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
            "fair_value_gaps": self.fair_value_gaps,
            "summary": self.summary,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class FVGIntelligenceValidator:
    """Deterministic validation for the fvg and imbalance contract."""

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
                FVGIntelligenceValidator._parse_timestamp(evaluation_time_value)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

        config_value = payload.get("config")
        try:
            FVGIntelligenceConfig.from_payload(config_value)
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
                    parsed = FVGIntelligenceValidator._parse_timestamp(timestamp_value)
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


class FVGImbalanceIntelligenceCapability:
    """Provider-independent deterministic fair value gap and imbalance capability."""

    def __init__(self):
        self.name = "fvg_imbalance_intelligence"
        self.contract = "trading.fvg_imbalance_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual fair value gap and imbalance intelligence for XAUUSD architecture validation."
        self.metadata = {
            "deterministic_fvg_intelligence": True,
            "chart_inferred_imbalance": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
        }

    def validate_input(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        validator = FVGIntelligenceValidator()
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
            "fair_value_gaps",
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
            "setup_quality": r"\bsetup_quality\b",
            "probability": r"\bprobability\b",
            "forecast": r"\bforecast\b",
            "prediction": r"\bprediction\b",
            "expected_direction": r"\bexpected_direction\b",
            "trade_recommendation": r"\btrade_recommendation\b",
            "position_size": r"\bposition_size\b",
            "broker_instruction": r"\bbroker_instruction\b",
            "execution_command": r"\bexecution_command\b",
            "stop_hunt": r"\bstop_hunt\b",
            "manipulation": r"\bmanipulation\b",
            "smart_money_intent": r"\bsmart_money_intent\b",
        }
        payload_text = str(payload).lower()
        for forbidden_term, pattern in forbidden_patterns.items():
            if re.search(pattern, payload_text):
                errors.append(f"Forbidden advisory term detected: {forbidden_term}")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> FairValueGapIntelligenceResult:
        return FVGImbalanceIntelligenceAnalyzer().analyze(payload)


class FVGImbalanceIntelligenceSpecialist:
    """Read-only specialist wrapper for deterministic fair value gap intelligence."""

    def __init__(self):
        self.name = "fvg_imbalance_analyst"
        self.division_name = "trading"
        self.capability_name = "fvg_imbalance_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == "fvg_imbalance_analyst"
            and capability_name == "fvg_imbalance_intelligence"
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

    def analyze_imbalance(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> FairValueGapIntelligenceResult:
        return FVGImbalanceIntelligenceAnalyzer().analyze(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)


class FVGImbalanceIntelligenceAnalyzer:
    """Deterministic three-candle fvg and imbalance analyzer for XAUUSD."""

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
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _bars_since(index: int, reference_index: int) -> int:
        if index <= reference_index:
            return 0
        return index - reference_index

    @staticmethod
    def _build_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
        summary = {
            "bullish_fvg_count": 0,
            "bearish_fvg_count": 0,
            "open_count": 0,
            "partially_filled_count": 0,
            "fully_filled_count": 0,
        }
        for row in rows:
            if row["side"] == "bullish":
                summary["bullish_fvg_count"] += 1
            elif row["side"] == "bearish":
                summary["bearish_fvg_count"] += 1

            if row["current_status"] == "open":
                summary["open_count"] += 1
            elif row["current_status"] == "partially_filled":
                summary["partially_filled_count"] += 1
            elif row["current_status"] == "fully_filled":
                summary["fully_filled_count"] += 1
        return summary

    def analyze(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> FairValueGapIntelligenceResult:
        errors = FVGIntelligenceValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid fvg intelligence input: " + "; ".join(errors))

        input_model = FVGIntelligenceInput.from_payload(payload)
        config = input_model.config
        candles = self._normalize_candles(input_model.candle_history)
        length = len(candles)
        current_timestamp = candles[-1]["timestamp"]
        last_index = length - 1

        b_min = max(1, length - config.lookback_candles)
        b_max = length - 2
        scanned_candle_count = max(0, b_max - b_min + 1)

        candidates: list[dict[str, Any]] = []
        if scanned_candle_count > 0:
            for b in range(b_min, b_max + 1):
                a = b - 1
                c = b + 1
                a_candle = candles[a]
                b_candle = candles[b]
                c_candle = candles[c]

                bullish = float(a_candle["high"]) < float(c_candle["low"])
                bearish = float(a_candle["low"]) > float(c_candle["high"])

                if bullish:
                    gap_lower = float(a_candle["high"])
                    gap_upper = float(c_candle["low"])
                    side = "bullish"
                    rule_branch = "bullish_fvg"
                elif bearish:
                    gap_lower = float(c_candle["high"])
                    gap_upper = float(a_candle["low"])
                    side = "bearish"
                    rule_branch = "bearish_fvg"
                else:
                    continue

                gap_width = float(gap_upper - gap_lower)
                if gap_width < float(config.minimum_gap_size):
                    continue

                candidates.append(
                    {
                        "side": side,
                        "a_index": a,
                        "b_index": b,
                        "c_index": c,
                        "source_timestamp": b_candle["timestamp"],
                        "confirmed_at": c_candle["timestamp"],
                        "created_at": c_candle["timestamp"],
                        "created_at_index": c,
                        "gap_lower": gap_lower,
                        "gap_upper": gap_upper,
                        "gap_width": gap_width,
                        "rule_branch": rule_branch,
                        "source_values": {
                            "a": {
                                "timestamp": a_candle["timestamp"],
                                "open": float(a_candle["open"]),
                                "high": float(a_candle["high"]),
                                "low": float(a_candle["low"]),
                                "close": float(a_candle["close"]),
                            },
                            "b": {
                                "timestamp": b_candle["timestamp"],
                                "open": float(b_candle["open"]),
                                "high": float(b_candle["high"]),
                                "low": float(b_candle["low"]),
                                "close": float(b_candle["close"]),
                            },
                            "c": {
                                "timestamp": c_candle["timestamp"],
                                "open": float(c_candle["open"]),
                                "high": float(c_candle["high"]),
                                "low": float(c_candle["low"]),
                                "close": float(c_candle["close"]),
                            },
                        },
                    }
                )

        rows_pre_filter: list[dict[str, Any]] = []
        for idx, item in enumerate(candidates):
            gap_lower = float(item["gap_lower"])
            gap_upper = float(item["gap_upper"])
            gap_width = float(item["gap_width"])
            interaction_lower = gap_lower - float(config.interaction_tolerance)
            interaction_upper = gap_upper + float(config.interaction_tolerance)

            interactions: list[dict[str, Any]] = []
            fill_history: list[dict[str, Any]] = []
            current_fill_depth = 0.0
            current_fill_percentage = 0.0
            current_status = "open"
            first_interaction_at: str | None = None
            last_interaction_at: str | None = None
            full_fill_at: str | None = None

            for candle_index in range(int(item["created_at_index"]) + 1, length):
                candle = candles[candle_index]
                high = float(candle["high"])
                low = float(candle["low"])
                close = float(candle["close"])

                if item["side"] == "bullish":
                    fill_depth = self._clamp(gap_upper - low, 0.0, gap_width)
                    full_condition = low <= gap_lower
                else:
                    fill_depth = self._clamp(high - gap_lower, 0.0, gap_width)
                    full_condition = high >= gap_upper

                fill_percentage = 0.0
                if gap_width > 0:
                    fill_percentage = (fill_depth / gap_width) * 100.0

                intersects_interaction_zone = not (high < interaction_lower or low > interaction_upper)

                if full_condition:
                    event_type = "fully_filled_event"
                    resulting_status = "fully_filled"
                elif fill_depth > 0:
                    event_type = "partial_fill_event"
                    resulting_status = "partially_filled"
                elif intersects_interaction_zone:
                    event_type = "touched_event"
                    resulting_status = current_status
                else:
                    continue

                current_fill_depth = max(current_fill_depth, fill_depth)
                current_fill_percentage = max(current_fill_percentage, fill_percentage)

                if current_status != "fully_filled":
                    if resulting_status == "fully_filled":
                        current_status = "fully_filled"
                    elif resulting_status == "partially_filled" and current_status == "open":
                        current_status = "partially_filled"

                if first_interaction_at is None:
                    first_interaction_at = candle["timestamp"]
                last_interaction_at = candle["timestamp"]
                if event_type == "fully_filled_event" and full_fill_at is None:
                    full_fill_at = candle["timestamp"]

                fill_history.append(
                    {
                        "candle_timestamp": candle["timestamp"],
                        "fill_depth": fill_depth,
                        "fill_percentage": fill_percentage,
                    }
                )

                interactions.append(
                    {
                        "candle_timestamp": candle["timestamp"],
                        "event_type": event_type,
                        "observed_high": high,
                        "observed_low": low,
                        "observed_close": close,
                        "fill_depth": fill_depth,
                        "fill_percentage": fill_percentage,
                        "resulting_status": current_status,
                    }
                )

            row = {
                "fvg_id": f"{item['side']}_fvg_{idx + 1}",
                "side": item["side"],
                "source_timestamp": item["source_timestamp"],
                "confirmed_at": item["confirmed_at"],
                "created_at": item["created_at"],
                "gap_lower": gap_lower,
                "gap_upper": gap_upper,
                "gap_width": gap_width,
                "current_status": current_status,
                "current_fill_depth": current_fill_depth,
                "current_fill_percentage": current_fill_percentage,
                "first_interaction_at": first_interaction_at,
                "last_interaction_at": last_interaction_at,
                "full_fill_at": full_fill_at,
                "interaction_count": len(interactions),
                "interactions": interactions,
                "bars_since_creation": self._bars_since(last_index, int(item["created_at_index"])),
                "bars_since_last_interaction": (
                    None
                    if last_interaction_at is None
                    else self._bars_since(
                        last_index,
                        next(index for index, c in enumerate(candles) if c["timestamp"] == last_interaction_at),
                    )
                ),
                "evidence": {
                    "window_indices": {
                        "a": item["a_index"],
                        "b": item["b_index"],
                        "c": item["c_index"],
                    },
                    "window_timestamps": {
                        "a": item["source_values"]["a"]["timestamp"],
                        "b": item["source_values"]["b"]["timestamp"],
                        "c": item["source_values"]["c"]["timestamp"],
                    },
                    "source_values": item["source_values"],
                    "rule_branch": item["rule_branch"],
                    "gap_boundaries": {
                        "gap_lower": gap_lower,
                        "gap_upper": gap_upper,
                        "gap_width": gap_width,
                    },
                    "minimum_gap_size": float(config.minimum_gap_size),
                    "interaction_tolerance": float(config.interaction_tolerance),
                    "interaction_lower": interaction_lower,
                    "interaction_upper": interaction_upper,
                    "fill_history": fill_history,
                    "fvg_rule_version": RULE_VERSION,
                },
            }
            rows_pre_filter.append(row)

        summary_pre_filter = self._build_summary(rows_pre_filter)
        filtered_out_fully_filled_count = 0
        emitted_rows = rows_pre_filter
        if not config.include_fully_filled:
            emitted_rows = [row for row in rows_pre_filter if row["current_status"] != "fully_filled"]
            filtered_out_fully_filled_count = len(rows_pre_filter) - len(emitted_rows)

        summary = self._build_summary(emitted_rows)

        evidence = {
            "fvg_rule_version": RULE_VERSION,
            "candidate_source_index_range": {
                "b_min": b_min,
                "b_max": b_max,
            },
            "scanned_candle_count_basis": "middle_candle_candidates",
            "totals_pre_filter": summary_pre_filter,
            "filtered_out_fully_filled_count": filtered_out_fully_filled_count,
            "config": config.as_dict(),
        }
        if not emitted_rows:
            evidence["reason"] = "no_qualifying_fvg"

        result = FairValueGapIntelligenceResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=current_timestamp,
            scanned_candle_count=scanned_candle_count,
            fair_value_gaps=emitted_rows,
            summary=summary,
            evidence=evidence,
            metadata={
                "deterministic_fvg_intelligence": True,
                "chart_inferred_imbalance": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "fvg_rule_version": RULE_VERSION,
                "authority_scope": "read_only",
                "analysis_scope": "read_only",
            },
        )

        output_errors = FVGImbalanceIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid fvg intelligence result: " + "; ".join(output_errors))
        return result


FVG_IMBALANCE_INTELLIGENCE = FVGImbalanceIntelligenceAnalyzer()

__all__ = [
    "FVGImbalanceIntelligenceAnalyzer",
    "FVGImbalanceIntelligenceCapability",
    "FVGImbalanceIntelligenceSpecialist",
    "FVGIntelligenceConfig",
    "FVGIntelligenceInput",
    "FVGIntelligenceValidator",
    "FairValueGapIntelligenceResult",
    "FVG_IMBALANCE_INTELLIGENCE",
    "RULE_VERSION",
]
