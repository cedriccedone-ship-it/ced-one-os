"""Deterministic XAUUSD market-structure intelligence for Vertical Slice #3.

This module intentionally remains read-only, descriptive, and provider-independent.
It adds deterministic swing and structure analysis over validated candle history
without introducing advisory, execution, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}


@dataclass
class MarketStructureInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MarketStructureInput":
        history = payload.get("candle_history") or []
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in history if isinstance(item, dict)],
        )


@dataclass
class MarketStructureResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    structure_state: str
    latest_swing_high: dict[str, Any] | None = None
    latest_swing_low: dict[str, Any] | None = None
    latest_high_relationship: str = "UNCLASSIFIED_HIGH"
    latest_low_relationship: str = "UNCLASSIFIED_LOW"
    continuation_break_candidate: bool = False
    continuation_break_confirmed: bool = False
    reversal_break_candidate: bool = False
    reversal_break_confirmed: bool = False
    broken_anchor_type: str | None = None
    broken_anchor_timestamp: str | None = None
    broken_anchor_price: float | None = None
    confirmation_timestamp: str | None = None
    confirmation_close: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_time": self.evaluation_time,
            "structure_state": self.structure_state,
            "latest_swing_high": self.latest_swing_high,
            "latest_swing_low": self.latest_swing_low,
            "latest_high_relationship": self.latest_high_relationship,
            "latest_low_relationship": self.latest_low_relationship,
            "continuation_break_candidate": self.continuation_break_candidate,
            "continuation_break_confirmed": self.continuation_break_confirmed,
            "reversal_break_candidate": self.reversal_break_candidate,
            "reversal_break_confirmed": self.reversal_break_confirmed,
            "broken_anchor_type": self.broken_anchor_type,
            "broken_anchor_timestamp": self.broken_anchor_timestamp,
            "broken_anchor_price": self.broken_anchor_price,
            "confirmation_timestamp": self.confirmation_timestamp,
            "confirmation_close": self.confirmation_close,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class MarketStructureValidator:
    """Deterministic validation for the XAUUSD market-structure contract."""

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def validate_input(
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]

        symbol = str(payload.get("symbol", "")).upper()
        if symbol != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")

        timeframe = str(payload.get("timeframe", "")).upper()
        if timeframe not in VALID_TIMEFRAMES:
            errors.append(f"Unsupported timeframe: {timeframe or '<missing>'} is not in the allowed deterministic set {sorted(VALID_TIMEFRAMES)}")

        candidate_time = payload.get("evaluation_time")
        if candidate_time is None:
            errors.append("Missing required evaluation_time.")
        else:
            try:
                MarketStructureValidator._parse_timestamp(candidate_time)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

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
                    parsed = MarketStructureValidator._parse_timestamp(timestamp_value)
                except ValueError:
                    errors.append(f"Invalid timestamp at index {idx}: must be parseable ISO 8601.")
                    continue
                if last_timestamp is not None and parsed <= last_timestamp:
                    errors.append(f"Timestamps must be strictly increasing; candle at index {idx} is not greater than the previous timestamp.")
                last_timestamp = parsed
            for field_name in ["open", "high", "low", "close"]:
                if field_name not in candle:
                    continue
                value = candle[field_name]
                try:
                    numeric = float(value)
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


class MarketStructureAnalyzer:
    """Deterministic market-structure analyzer for XAUUSD candle history."""

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
    def _find_confirmed_swings(candles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        swing_highs: list[dict[str, Any]] = []
        swing_lows: list[dict[str, Any]] = []
        for idx, current in enumerate(candles):
            previous = candles[idx - 1] if idx > 0 else None
            next_candle = candles[idx + 1] if idx < len(candles) - 1 else None

            is_swing_high = True
            if previous is not None and current["high"] <= previous["high"]:
                is_swing_high = False
            if next_candle is not None and current["high"] <= next_candle["high"]:
                is_swing_high = False
            if is_swing_high:
                swing_highs.append({"index": idx, "timestamp": current["timestamp"], "high": current["high"]})

            is_swing_low = True
            if previous is not None and current["low"] >= previous["low"]:
                is_swing_low = False
            if next_candle is not None and current["low"] >= next_candle["low"]:
                is_swing_low = False
            if is_swing_low:
                swing_lows.append({"index": idx, "timestamp": current["timestamp"], "low": current["low"]})
        return swing_highs, swing_lows

    @staticmethod
    def _classify_high_relation(current_high: dict[str, Any], previous_high: dict[str, Any]) -> str:
        if current_high["high"] > previous_high["high"]:
            return "HH"
        if current_high["high"] < previous_high["high"]:
            return "LH"
        return "UNCLASSIFIED_HIGH"

    @staticmethod
    def _classify_low_relation(current_low: dict[str, Any], previous_low: dict[str, Any]) -> str:
        if current_low["low"] > previous_low["low"]:
            return "HL"
        if current_low["low"] < previous_low["low"]:
            return "LL"
        return "UNCLASSIFIED_LOW"

    @staticmethod
    def _resolve_structure(high_swings: list[dict[str, Any]], low_swings: list[dict[str, Any]]) -> tuple[str, str, str]:
        # Require at least two confirmed highs and two confirmed lows
        # to classify directional structure. If insufficient confirmed
        # pivots exist, return unresolved_structure and leave
        # relationships unclassified.
        if len(high_swings) < 2 or len(low_swings) < 2:
            return "unresolved_structure", "UNCLASSIFIED_HIGH", "UNCLASSIFIED_LOW"

        latest_high_relationship = MarketStructureAnalyzer._classify_high_relation(high_swings[-1], high_swings[-2])
        latest_low_relationship = MarketStructureAnalyzer._classify_low_relation(low_swings[-1], low_swings[-2])

        if latest_high_relationship == "HH" and latest_low_relationship == "HL":
            return "bullish_structure", latest_high_relationship, latest_low_relationship
        if latest_high_relationship == "LH" and latest_low_relationship == "LL":
            return "bearish_structure", latest_high_relationship, latest_low_relationship
        if latest_high_relationship in {"HH", "LH"} and latest_low_relationship in {"HL", "LL"}:
            if (latest_high_relationship == "HH" and latest_low_relationship == "LL") or (
                latest_high_relationship == "LH" and latest_low_relationship == "HL"
            ):
                return "unresolved_structure", latest_high_relationship, latest_low_relationship
        return "unresolved_structure", latest_high_relationship, latest_low_relationship

    @staticmethod
    def _break_state_for_bullish(
        candles: list[dict[str, Any]],
        latest_swing_high: dict[str, Any],
        latest_swing_low: dict[str, Any],
    ) -> tuple[bool, bool, bool, bool, str | None, str | None, float | None, float | None, str | None]:
        last_candle = candles[-1]
        continuation_candidate = last_candle["high"] > latest_swing_high["high"]
        continuation_confirmed = (
            last_candle["timestamp"] > latest_swing_high["timestamp"] and last_candle["close"] > latest_swing_high["high"]
        )
        reversal_candidate = last_candle["low"] < latest_swing_low["low"]
        reversal_confirmed = (
            last_candle["timestamp"] > latest_swing_low["timestamp"] and last_candle["close"] < latest_swing_low["low"]
        )

        broken_anchor_type = None
        broken_anchor_timestamp = None
        broken_anchor_price = None
        confirmation_timestamp = None
        confirmation_close = None
        if continuation_confirmed:
            broken_anchor_type = "swing_high"
            broken_anchor_timestamp = latest_swing_high["timestamp"]
            broken_anchor_price = float(latest_swing_high["high"])
            confirmation_timestamp = last_candle["timestamp"]
            confirmation_close = float(last_candle["close"])
        elif reversal_confirmed:
            broken_anchor_type = "swing_low"
            broken_anchor_timestamp = latest_swing_low["timestamp"]
            broken_anchor_price = float(latest_swing_low["low"])
            confirmation_timestamp = last_candle["timestamp"]
            confirmation_close = float(last_candle["close"])
        return (
            continuation_candidate,
            continuation_confirmed,
            reversal_candidate,
            reversal_confirmed,
            broken_anchor_type,
            broken_anchor_timestamp,
            broken_anchor_price,
            confirmation_timestamp,
            confirmation_close,
        )

    @staticmethod
    def _break_state_for_bearish(
        candles: list[dict[str, Any]],
        latest_swing_high: dict[str, Any],
        latest_swing_low: dict[str, Any],
    ) -> tuple[bool, bool, bool, bool, str | None, str | None, float | None, str | None]:
        last_candle = candles[-1]
        continuation_candidate = last_candle["low"] < latest_swing_low["low"]
        continuation_confirmed = (
            last_candle["timestamp"] > latest_swing_low["timestamp"] and last_candle["close"] < latest_swing_low["low"]
        )
        reversal_candidate = last_candle["high"] > latest_swing_high["high"]
        reversal_confirmed = (
            last_candle["timestamp"] > latest_swing_high["timestamp"] and last_candle["close"] > latest_swing_high["high"]
        )

        broken_anchor_type = None
        broken_anchor_timestamp = None
        broken_anchor_price = None
        confirmation_timestamp = None
        confirmation_close = None
        if continuation_confirmed:
            broken_anchor_type = "swing_low"
            broken_anchor_timestamp = latest_swing_low["timestamp"]
            broken_anchor_price = float(latest_swing_low["low"])
            confirmation_timestamp = last_candle["timestamp"]
            confirmation_close = float(last_candle["close"])
        elif reversal_confirmed:
            broken_anchor_type = "swing_high"
            broken_anchor_timestamp = latest_swing_high["timestamp"]
            broken_anchor_price = float(latest_swing_high["high"])
            confirmation_timestamp = last_candle["timestamp"]
            confirmation_close = float(last_candle["close"])
        return (
            continuation_candidate,
            continuation_confirmed,
            reversal_candidate,
            reversal_confirmed,
            broken_anchor_type,
            broken_anchor_timestamp,
            broken_anchor_price,
            confirmation_timestamp,
            confirmation_close,
        )

    def analyze(
        self,
        payload: dict[str, Any],
        *,
        evaluation_time: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> MarketStructureResult:
        errors = MarketStructureValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid market structure input: " + "; ".join(errors))

        normalized = self._normalize_candles(payload["candle_history"])
        swing_highs, swing_lows = self._find_confirmed_swings(normalized)

        latest_high_relationship = "UNCLASSIFIED_HIGH"
        latest_low_relationship = "UNCLASSIFIED_LOW"
        if len(swing_highs) >= 2:
            latest_high_relationship = self._classify_high_relation(swing_highs[-1], swing_highs[-2])
        if len(swing_lows) >= 2:
            latest_low_relationship = self._classify_low_relation(swing_lows[-1], swing_lows[-2])

        structure_state, latest_high_relationship, latest_low_relationship = self._resolve_structure(swing_highs, swing_lows)

        # No deterministic monotonic fallback: structure must be derived
        # from confirmed pivots only. If insufficient evidence exists,
        # `structure_state` remains "unresolved_structure".

        latest_swing_high = swing_highs[-1] if swing_highs else None
        latest_swing_low = swing_lows[-1] if swing_lows else None

        continuation_break_candidate = False
        continuation_break_confirmed = False
        reversal_break_candidate = False
        reversal_break_confirmed = False
        broken_anchor_type = None
        broken_anchor_timestamp = None
        broken_anchor_price = None
        confirmation_timestamp = None
        confirmation_close = None

        if structure_state == "bullish_structure":
            (
                continuation_break_candidate,
                continuation_break_confirmed,
                reversal_break_candidate,
                reversal_break_confirmed,
                broken_anchor_type,
                broken_anchor_timestamp,
                broken_anchor_price,
                confirmation_timestamp,
                confirmation_close,
            ) = self._break_state_for_bullish(normalized, latest_swing_high, latest_swing_low)
        elif structure_state == "bearish_structure":
            (
                continuation_break_candidate,
                continuation_break_confirmed,
                reversal_break_candidate,
                reversal_break_confirmed,
                broken_anchor_type,
                broken_anchor_timestamp,
                broken_anchor_price,
                confirmation_timestamp,
                confirmation_close,
            ) = self._break_state_for_bearish(normalized, latest_swing_high, latest_swing_low)

        result = MarketStructureResult(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            structure_state=structure_state,
            latest_swing_high=latest_swing_high,
            latest_swing_low=latest_swing_low,
            latest_high_relationship=latest_high_relationship,
            latest_low_relationship=latest_low_relationship,
            continuation_break_candidate=continuation_break_candidate,
            continuation_break_confirmed=continuation_break_confirmed,
            reversal_break_candidate=reversal_break_candidate,
            reversal_break_confirmed=reversal_break_confirmed,
            broken_anchor_type=broken_anchor_type,
            broken_anchor_timestamp=broken_anchor_timestamp,
            broken_anchor_price=broken_anchor_price,
            confirmation_timestamp=confirmation_timestamp,
            confirmation_close=confirmation_close,
            evidence={
                "swing_highs": swing_highs,
                "swing_lows": swing_lows,
                "relationship_rule": "strict_3_candle_pivot",
                "confirmed_structure_requires": {
                    "minimum_confirmed_high_swings": 2,
                    "minimum_confirmed_low_swings": 2,
                },
            },
            metadata={
                "deterministic_structure_analysis": True,
                "observation_only": True,
                "advisory_output": False,
                "synthetic_contract": True,
                "authority_scope": "read_only",
                "action_capability": False,
                "structure_rule_version": "market_structure_v1",
                "analysis_scope": "read_only",
            },
        )
        return result


MARKET_STRUCTURE = MarketStructureAnalyzer()

__all__ = [
    "MarketStructureAnalyzer",
    "MarketStructureInput",
    "MarketStructureResult",
    "MarketStructureValidator",
    "MARKET_STRUCTURE",
]
