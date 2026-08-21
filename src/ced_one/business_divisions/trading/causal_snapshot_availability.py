"""Deterministic causal source snapshots for controlled Trading composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any

VALID_SYMBOL = "XAUUSD"
VALID_TIMEFRAME_DURATIONS = {
    "D1": timedelta(hours=24),
    "H4": timedelta(hours=4),
    "H1": timedelta(hours=1),
    "M30": timedelta(minutes=30),
    "M15": timedelta(minutes=15),
    "M5": timedelta(minutes=5),
    "M1": timedelta(minutes=1),
}
TIMEFRAME_DURATION_RULE_VERSION = "timeframe_duration_map_v1"
CANDLE_TIMESTAMP_SEMANTICS = "open_time"
RULE_VERSION = "causal_snapshot_availability_v1"
CONTRACT = "trading.causal_snapshot_availability.v1"
IDENTITY_SCOPE = "snapshot_deterministic"
SOURCE_AVAILABILITY_STATES = {"AVAILABLE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
COMPLETION_STATES = {"COMPLETED", "INCOMPLETE", "UNKNOWN"}


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CausalSnapshotAvailabilityInput:
    symbol: str
    timeframe: str
    requested_evaluation_timestamp: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CausalSnapshotAvailabilityInput":
        history = payload.get("candle_history")
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            requested_evaluation_timestamp=str(payload.get("requested_evaluation_timestamp", "")),
            candle_history=[dict(item) for item in history] if isinstance(history, list) and all(isinstance(item, dict) for item in history) else [],
        )


@dataclass
class CausalSnapshotAvailabilityResult:
    symbol: str
    timeframe: str
    requested_evaluation_timestamp: str
    effective_causal_cutoff: str | None
    source_snapshot_id: str | None
    source_availability: str
    availability_reason: str
    completion_state: str
    approved_candle_history: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "effective_causal_cutoff": self.effective_causal_cutoff,
            "source_snapshot_id": self.source_snapshot_id,
            "source_availability": self.source_availability,
            "availability_reason": self.availability_reason,
            "completion_state": self.completion_state,
            "approved_candle_history": [dict(item) for item in self.approved_candle_history],
            "diagnostics": dict(self.diagnostics),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }


class CausalSnapshotAvailabilityValidator:
    @staticmethod
    def validate_input(payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        errors: list[str] = []
        if str(payload.get("symbol", "")).upper() != VALID_SYMBOL:
            errors.append(f"Unsupported symbol: only {VALID_SYMBOL} is accepted in this slice.")
        if str(payload.get("timeframe", "")).upper() not in VALID_TIMEFRAME_DURATIONS:
            errors.append("Unsupported timeframe: expected one of the seven supported Trading timeframes.")
        try:
            _parse_timestamp(payload.get("requested_evaluation_timestamp"))
        except ValueError as exc:
            errors.append(f"Invalid requested_evaluation_timestamp: {exc}")
        history = payload.get("candle_history")
        if not isinstance(history, list):
            errors.append("Missing required field: candle_history")
        elif any(not isinstance(item, dict) for item in history):
            errors.append("Every candle_history item must be a dictionary.")
        return errors


class CausalSnapshotAvailabilityAnalyzer:
    @staticmethod
    def _hash_id(parts: list[Any]) -> str:
        encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
        return "causal_snapshot_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _base_metadata() -> dict[str, Any]:
        return {
            "contract": CONTRACT,
            "rule_version": RULE_VERSION,
            "deterministic_causal_snapshot_availability": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "authority_scope": "read_only",
            "identity_scope": IDENTITY_SCOPE,
            "candle_timestamp_semantics": CANDLE_TIMESTAMP_SEMANTICS,
            "timeframe_duration_rule_version": TIMEFRAME_DURATION_RULE_VERSION,
        }

    @staticmethod
    def _diagnostics(**overrides: int) -> dict[str, int]:
        diagnostics = {
            "input_candle_count": 0,
            "approved_candle_count": 0,
            "future_candle_count": 0,
            "incomplete_candle_count": 0,
            "invalid_candle_count": 0,
            "duplicate_timestamp_count": 0,
        }
        diagnostics.update(overrides)
        return diagnostics

    @classmethod
    def _result(
        cls,
        source: CausalSnapshotAvailabilityInput,
        *,
        availability: str,
        reason: str,
        completion_state: str,
        diagnostics: dict[str, int],
        requested_timestamp: str,
        effective_cutoff: str | None = None,
        approved_history: list[dict[str, Any]] | None = None,
        snapshot_id: str | None = None,
        evidence_extra: dict[str, Any] | None = None,
    ) -> CausalSnapshotAvailabilityResult:
        duration = VALID_TIMEFRAME_DURATIONS.get(source.timeframe)
        evidence = {
            "candle_timestamp_semantics": CANDLE_TIMESTAMP_SEMANTICS,
            "timeframe_duration": None if duration is None else duration.total_seconds(),
            "timeframe_duration_rule_version": TIMEFRAME_DURATION_RULE_VERSION,
            "requested_evaluation_timestamp": requested_timestamp,
            "effective_causal_cutoff": effective_cutoff,
            "first_approved_candle_timestamp": None,
            "last_approved_candle_timestamp": None,
            "last_completed_candle_timestamp": None,
            "source_snapshot_id": snapshot_id,
            "availability_reason": reason,
        }
        approved = approved_history or []
        if approved:
            evidence["first_approved_candle_timestamp"] = approved[0]["timestamp"]
            evidence["last_approved_candle_timestamp"] = approved[-1]["timestamp"]
            evidence["last_completed_candle_timestamp"] = effective_cutoff
        if evidence_extra:
            evidence.update(evidence_extra)
        metadata = cls._base_metadata()
        metadata.update(
            {
                "source_availability": availability,
                "availability_reason": reason,
                "completion_state": completion_state,
            }
        )
        return CausalSnapshotAvailabilityResult(
            symbol=source.symbol,
            timeframe=source.timeframe,
            requested_evaluation_timestamp=requested_timestamp,
            effective_causal_cutoff=effective_cutoff,
            source_snapshot_id=snapshot_id,
            source_availability=availability,
            availability_reason=reason,
            completion_state=completion_state,
            approved_candle_history=approved,
            diagnostics=diagnostics,
            evidence=evidence,
            metadata=metadata,
        )

    def analyze(self, payload: dict[str, Any]) -> CausalSnapshotAvailabilityResult:
        source = CausalSnapshotAvailabilityInput.from_payload(payload if isinstance(payload, dict) else {})
        requested_text = source.requested_evaluation_timestamp
        base_errors = CausalSnapshotAvailabilityValidator.validate_input(payload)
        diagnostics = self._diagnostics(input_candle_count=len(source.candle_history))
        if base_errors:
            diagnostics["invalid_candle_count"] = sum(not isinstance(item, dict) for item in (payload.get("candle_history", []) if isinstance(payload, dict) and isinstance(payload.get("candle_history"), list) else []))
            reason = "invalid_source"
            if any("requested_evaluation_timestamp" in error for error in base_errors):
                reason = "invalid_timestamp"
            return self._result(
                source,
                availability="INVALID",
                reason=reason,
                completion_state="UNKNOWN",
                diagnostics=diagnostics,
                requested_timestamp=requested_text,
                evidence_extra={"validation_errors": base_errors},
            )

        requested = _parse_timestamp(requested_text)
        requested_text = _timestamp_text(requested)
        duration = VALID_TIMEFRAME_DURATIONS[source.timeframe]
        normalized_history: list[dict[str, Any]] = []
        parsed_timestamps: list[datetime] = []
        invalid_count = 0
        duplicate_count = 0
        seen_timestamps: set[str] = set()
        future_count = 0
        incomplete_count = 0
        invalid_reasons: list[str] = []

        for index, candle in enumerate(source.candle_history):
            candle_invalid = False
            counted_invalid = False
            required = ["timestamp", "open", "high", "low", "close"]
            missing = [name for name in required if name not in candle]
            if missing:
                candle_invalid = True
                invalid_reasons.append(f"candle {index} missing fields {missing}")
                invalid_count += 1
                counted_invalid = True
                continue
            timestamp_text = str(candle["timestamp"])
            try:
                opened = _parse_timestamp(timestamp_text)
            except ValueError as exc:
                candle_invalid = True
                invalid_reasons.append(f"candle {index} invalid timestamp: {exc}")
                invalid_count += 1
                counted_invalid = True
                continue
            if timestamp_text in seen_timestamps:
                duplicate_count += 1
                candle_invalid = True
                invalid_reasons.append(f"duplicate candle timestamp: {timestamp_text}")
            seen_timestamps.add(timestamp_text)
            if parsed_timestamps and opened <= parsed_timestamps[-1]:
                candle_invalid = True
                invalid_reasons.append(f"candle {index} timestamps are not strictly increasing")
            parsed_timestamps.append(opened)
            values: dict[str, float] = {}
            for field_name in ["open", "high", "low", "close"]:
                try:
                    numeric = float(candle[field_name])
                except (TypeError, ValueError):
                    candle_invalid = True
                    invalid_reasons.append(f"candle {index} has non-numeric {field_name}")
                    continue
                if not math.isfinite(numeric) or numeric <= 0:
                    candle_invalid = True
                    invalid_reasons.append(f"candle {index} has invalid {field_name}")
                    continue
                values[field_name] = numeric
            if len(values) == 4:
                if values["high"] < max(values["open"], values["close"]):
                    candle_invalid = True
                    invalid_reasons.append(f"candle {index} has impossible high")
                if values["low"] > min(values["open"], values["close"]):
                    candle_invalid = True
                    invalid_reasons.append(f"candle {index} has impossible low")
            if opened > requested:
                future_count += 1
                candle_invalid = True
                invalid_reasons.append(f"candle {index} opens after requested evaluation timestamp")
            completion = opened + duration
            normalized = dict(candle)
            normalized["timestamp"] = _timestamp_text(opened)
            normalized.update(values)
            if opened <= requested and completion > requested:
                incomplete_count += 1
            if candle_invalid and not counted_invalid:
                invalid_count += 1
            normalized_history.append((opened, completion, normalized, candle_invalid))

        diagnostics.update(
            future_candle_count=future_count,
            incomplete_candle_count=incomplete_count,
            invalid_candle_count=invalid_count,
            duplicate_timestamp_count=duplicate_count,
        )
        if invalid_reasons:
            return self._result(
                source,
                availability="INVALID",
                reason="future_source_data" if future_count else "invalid_source",
                completion_state="UNKNOWN",
                diagnostics=diagnostics,
                requested_timestamp=requested_text,
                evidence_extra={"validation_errors": invalid_reasons},
            )

        approved = [item[2] for item in normalized_history if item[0] + duration <= requested]
        approved.sort(key=lambda item: item["timestamp"])
        diagnostics["approved_candle_count"] = len(approved)
        if not approved:
            return self._result(
                source,
                availability="UNAVAILABLE",
                reason="incomplete_current_candle" if incomplete_count else "empty_source_history",
                completion_state="INCOMPLETE" if incomplete_count else "UNKNOWN",
                diagnostics=diagnostics,
                requested_timestamp=requested_text,
                evidence_extra={"input_history_was_valid": True},
            )

        effective_cutoff = _timestamp_text(max(item[0] + duration for item in normalized_history if item[0] + duration <= requested))
        snapshot_parts = [
            source.symbol,
            source.timeframe,
            requested_text,
            effective_cutoff,
            CANDLE_TIMESTAMP_SEMANTICS,
            TIMEFRAME_DURATION_RULE_VERSION,
            RULE_VERSION,
            approved,
        ]
        snapshot_id = self._hash_id(snapshot_parts)
        completion_state = "INCOMPLETE" if incomplete_count else "COMPLETED"
        return self._result(
            source,
            availability="AVAILABLE",
            reason="sufficient_causal_source",
            completion_state=completion_state,
            diagnostics=diagnostics,
            requested_timestamp=requested_text,
            effective_cutoff=effective_cutoff,
            approved_history=approved,
            snapshot_id=snapshot_id,
        )


CAUSAL_SNAPSHOT_AVAILABILITY = CausalSnapshotAvailabilityAnalyzer()

__all__ = [
    "CausalSnapshotAvailabilityAnalyzer",
    "CausalSnapshotAvailabilityInput",
    "CausalSnapshotAvailabilityResult",
    "CausalSnapshotAvailabilityValidator",
    "CAUSAL_SNAPSHOT_AVAILABILITY",
    "CANDLE_TIMESTAMP_SEMANTICS",
    "CONTRACT",
    "RULE_VERSION",
    "TIMEFRAME_DURATION_RULE_VERSION",
    "VALID_TIMEFRAME_DURATIONS",
]