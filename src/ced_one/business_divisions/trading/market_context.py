"""Deterministic top-down XAUUSD market context for Vertical Slice #2.

This module intentionally stays read-only and provider-independent. It composes
validated observation results for the D1/H4/H1/M30/M15/M5/M1 timeframes into a
structured market-context summary without introducing trading semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ced_one.business_divisions.trading.market_observation import (
    MarketAnalysisSpecialist,
    MarketObservationResult,
    MarketObservationValidator,
)

ALLOWED_TIMEFRAMES = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]
HTF_TIMEFRAMES = ["D1", "H4", "H1"]
MTF_TIMEFRAMES = ["M30", "M15"]
LTF_TIMEFRAMES = ["M5", "M1"]


@dataclass
class MarketContextInput:
    symbol: str
    evaluation_time: str
    max_age_seconds: int
    timeframes: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MarketContextInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            max_age_seconds=int(payload.get("max_age_seconds", 300)),
            timeframes={
                str(key): dict(value) for key, value in dict(payload.get("timeframes") or {}).items()
            },
        )


@dataclass
class MarketContextResult:
    symbol: str
    timeframe_observations: dict[str, MarketObservationResult]
    htf_context: str
    mtf_context: str
    ltf_context: str
    overall_context: str
    htf_structure: str
    mtf_structure: str
    ltf_structure: str
    htf_volatility: str
    mtf_volatility: str
    ltf_volatility: str
    alignment_metadata: dict[str, float | str] = field(default_factory=dict)
    observation_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe_observations": {
                name: result.to_dict() for name, result in self.timeframe_observations.items()
            },
            "htf_context": self.htf_context,
            "mtf_context": self.mtf_context,
            "ltf_context": self.ltf_context,
            "overall_context": self.overall_context,
            "htf_structure": self.htf_structure,
            "mtf_structure": self.mtf_structure,
            "ltf_structure": self.ltf_structure,
            "htf_volatility": self.htf_volatility,
            "mtf_volatility": self.mtf_volatility,
            "ltf_volatility": self.ltf_volatility,
            "alignment_metadata": self.alignment_metadata,
            "observation_summary": self.observation_summary,
            "metadata": self.metadata,
        }


class MarketContextValidator:
    """Deterministic validation for the top-down XAUUSD market context contract."""

    @staticmethod
    def validate_input(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]

        symbol = str(payload.get("symbol", "")).upper()
        if symbol != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")

        timeframes = payload.get("timeframes")
        if not isinstance(timeframes, dict):
            return errors + ["Missing required field: timeframes"]

        observed = sorted(str(k).upper() for k in timeframes.keys())
        expected = sorted(ALLOWED_TIMEFRAMES)
        if observed != expected:
            missing = [item for item in expected if item not in observed]
            extra = [item for item in observed if item not in expected]
            if missing:
                errors.append(f"Missing required timeframe entries: {missing}")
            if extra:
                errors.append(f"Extra timeframe entries are not allowed: {extra}")

        evaluation_time = payload.get("evaluation_time")
        if evaluation_time is None:
            errors.append("Missing required evaluation_time.")
        else:
            try:
                datetime.fromisoformat(str(evaluation_time).replace("Z", "+00:00"))
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        max_age_seconds = payload.get("max_age_seconds", 300)
        try:
            max_age_seconds = int(max_age_seconds)
        except (TypeError, ValueError):
            errors.append("Invalid max_age_seconds: must be an integer.")

        if not errors:
            validator = MarketObservationValidator()
            for timeframe_name, timeframe_payload in timeframes.items():
                timeframe = str(timeframe_name).upper()
                if timeframe not in ALLOWED_TIMEFRAMES:
                    errors.append(f"Unsupported timeframe: {timeframe_name}")
                    continue
                if not isinstance(timeframe_payload, dict):
                    errors.append(f"Timeframe payload for {timeframe_name} must be a dictionary.")
                    continue
                timeframe_errors = validator.validate_input(
                    timeframe_payload,
                    evaluation_time=datetime.fromisoformat(str(evaluation_time).replace("Z", "+00:00")),
                    max_age_seconds=max_age_seconds,
                )
                if timeframe_errors:
                    errors.append(f"Invalid observation payload for {timeframe_name}: {'; '.join(timeframe_errors)}")

        return errors


class MarketContextAggregator:
    """Deterministic aggregation of validated XAUUSD observations."""

    @staticmethod
    def _group_context(values: list[str]) -> str:
        if not values:
            return "mixed"
        if all(value == "bullish" for value in values):
            return "bullish"
        if all(value == "bearish" for value in values):
            return "bearish"
        if all(value == "neutral" for value in values):
            return "neutral"
        return "mixed"

    @staticmethod
    def _group_structure(values: list[str]) -> str:
        if not values:
            return "mixed"
        if all(value == "uptrend" for value in values):
            return "uptrend"
        if all(value == "downtrend" for value in values):
            return "downtrend"
        if all(value == "range" for value in values):
            return "range"
        return "mixed"

    @staticmethod
    def _group_volatility(values: list[str]) -> str:
        if not values:
            return "mixed"
        if all(value == "low" for value in values):
            return "low"
        if all(value == "moderate" for value in values):
            return "moderate"
        if all(value == "elevated" for value in values):
            return "elevated"
        return "mixed"

    @staticmethod
    def _alignment_score(values: list[str]) -> float:
        if len(values) == 3:
            non_neutral = [v for v in values if v != "neutral"]
            if all(v == "neutral" for v in values):
                return 1.0
            if len(non_neutral) == 3 and all(v == non_neutral[0] for v in non_neutral):
                return 1.0
            if len(non_neutral) == 3 and len(set(non_neutral)) == 2:
                return 0.67
            return 0.33
        if len(values) == 2:
            if all(v == "neutral" for v in values):
                return 1.0
            if values[0] == values[1]:
                return 1.0
            return 0.5
        return 0.0

    @staticmethod
    def _overall_context(htf_context: str, mtf_context: str, ltf_context: str) -> str:
        if htf_context == "bullish" and mtf_context == "bullish" and ltf_context == "bullish":
            return "bullish_aligned"
        if htf_context == "bearish" and mtf_context == "bearish" and ltf_context == "bearish":
            return "bearish_aligned"
        if htf_context == "bullish" and mtf_context == "bullish" and ltf_context != "bullish":
            return "bullish_with_ltf_misalignment"
        if htf_context == "bearish" and mtf_context == "bearish" and ltf_context != "bearish":
            return "bearish_with_ltf_misalignment"
        if htf_context == "bullish" and mtf_context != "bullish":
            return "bullish_with_mtf_misalignment"
        if htf_context == "bearish" and mtf_context != "bearish":
            return "bearish_with_mtf_misalignment"
        if htf_context == "neutral" and mtf_context == "neutral" and ltf_context == "neutral":
            return "neutral"
        return "mixed"

    def aggregate(self, payload: dict[str, Any]) -> MarketContextResult:
        errors = MarketContextValidator().validate_input(payload)
        if errors:
            raise ValueError("Invalid market context input: " + "; ".join(errors))

        evaluation_time = payload.get("evaluation_time")
        if isinstance(evaluation_time, str):
            evaluation_time_dt = datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
        else:
            evaluation_time_dt = datetime.now(timezone.utc)

        specialist = MarketAnalysisSpecialist()
        timeframe_observations: dict[str, MarketObservationResult] = {}
        for timeframe_name in ALLOWED_TIMEFRAMES:
            timeframe_payload = payload["timeframes"][timeframe_name]
            result = specialist.observe_market(
                timeframe_payload,
                evaluation_time=evaluation_time_dt,
                max_age_seconds=int(payload.get("max_age_seconds", 300)),
            )
            timeframe_observations[timeframe_name] = result
            if result.metadata.get("status") in {"rejected", "failed"}:
                raise ValueError(f"Observation failed for {timeframe_name}: {result.metadata}")

        htf_biases = [timeframe_observations[name].market_bias for name in HTF_TIMEFRAMES]
        mtf_biases = [timeframe_observations[name].market_bias for name in MTF_TIMEFRAMES]
        ltf_biases = [timeframe_observations[name].market_bias for name in LTF_TIMEFRAMES]

        htf_context = self._group_context(htf_biases)
        mtf_context = self._group_context(mtf_biases)
        ltf_context = self._group_context(ltf_biases)
        overall_context = self._overall_context(htf_context, mtf_context, ltf_context)

        htf_structure_values = [timeframe_observations[name].market_structure for name in HTF_TIMEFRAMES]
        mtf_structure_values = [timeframe_observations[name].market_structure for name in MTF_TIMEFRAMES]
        ltf_structure_values = [timeframe_observations[name].market_structure for name in LTF_TIMEFRAMES]

        htf_structure = self._group_structure(htf_structure_values)
        mtf_structure = self._group_structure(mtf_structure_values)
        ltf_structure = self._group_structure(ltf_structure_values)

        htf_volatility_values = [timeframe_observations[name].volatility_state for name in HTF_TIMEFRAMES]
        mtf_volatility_values = [timeframe_observations[name].volatility_state for name in MTF_TIMEFRAMES]
        ltf_volatility_values = [timeframe_observations[name].volatility_state for name in LTF_TIMEFRAMES]

        htf_volatility = self._group_volatility(htf_volatility_values)
        mtf_volatility = self._group_volatility(mtf_volatility_values)
        ltf_volatility = self._group_volatility(ltf_volatility_values)

        alignment_metadata = {
            "htf_alignment_score": self._alignment_score(htf_biases),
            "mtf_alignment_score": self._alignment_score(mtf_biases),
            "ltf_alignment_score": self._alignment_score(ltf_biases),
        }

        result = MarketContextResult(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe_observations=timeframe_observations,
            htf_context=htf_context,
            mtf_context=mtf_context,
            ltf_context=ltf_context,
            overall_context=overall_context,
            htf_structure=htf_structure,
            mtf_structure=mtf_structure,
            ltf_structure=ltf_structure,
            htf_volatility=htf_volatility,
            mtf_volatility=mtf_volatility,
            ltf_volatility=ltf_volatility,
            alignment_metadata=alignment_metadata,
            observation_summary=(
                "Deterministic top-down XAUUSD market context derived from validated multi-timeframe synthetic observations."
            ),
            metadata={
                "synthetic_observation_rule": True,
                "deterministic_observation_mode": True,
                "multi_timeframe_context": True,
                "observation_only": True,
                "advisory_output": False,
                "aggregation_rule_version": "topdown_v1",
            },
        )
        return result
