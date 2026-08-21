"""Deterministic seven-layer context over Slice #13 source snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any

from ced_one.business_divisions.trading.causal_snapshot_availability import (
    COMPLETION_STATES,
    CONTRACT as SOURCE_CONTRACT,
    SOURCE_AVAILABILITY_STATES,
)

TIMEFRAME_ORDER = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
EDGE_ALIGNMENT_STATES = {
    "ALIGNED",
    "PARENT_UNAVAILABLE",
    "CHILD_UNAVAILABLE",
    "PARENT_INVALID",
    "CHILD_INVALID",
    "UNAVAILABLE",
}
RULE_VERSION = "causal_multi_timeframe_context_v1"
CONTRACT = "trading.causal_multi_timeframe_context.v1"
IDENTITY_SCOPE = "snapshot_deterministic"
CONTEXT_STATES = {"COMPLETE", "INCOMPLETE", "INVALID", "UNAVAILABLE", "NOT_EVALUATED"}


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed


def _hash_id(parts: Any) -> str:
    encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
    return "causal_context_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class CausalMultiTimeframeContextInput:
    symbol: str
    requested_evaluation_timestamp: str
    timeframe_sources: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CausalMultiTimeframeContextInput":
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            requested_evaluation_timestamp=str(payload.get("requested_evaluation_timestamp", "")),
            timeframe_sources=dict(payload.get("timeframe_sources") or {}) if isinstance(payload.get("timeframe_sources"), dict) else {},
        )


@dataclass
class CausalMultiTimeframeContextResult:
    symbol: str
    requested_evaluation_timestamp: str
    context_id: str | None
    identity_scope: str
    context_state: str
    timeframes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "context_id": self.context_id,
            "identity_scope": self.identity_scope,
            "context_state": self.context_state,
            "timeframes": {name: dict(record) for name, record in self.timeframes.items()},
            "edges": [dict(edge) for edge in self.edges],
            "diagnostics": dict(self.diagnostics),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }


class CausalMultiTimeframeContextValidator:
    @staticmethod
    def validate_input(payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        errors: list[str] = []
        if str(payload.get("symbol", "")).upper() != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")
        unknown_fields = sorted(set(payload) - {"symbol", "requested_evaluation_timestamp", "timeframe_sources"})
        if unknown_fields:
            errors.append(f"Unsupported input fields: {unknown_fields}")
        try:
            _parse_timestamp(payload.get("requested_evaluation_timestamp"))
        except ValueError as exc:
            errors.append(f"Invalid requested_evaluation_timestamp: {exc}")
        sources = payload.get("timeframe_sources")
        if not isinstance(sources, dict):
            errors.append("Missing required field: timeframe_sources")
        elif set(sources) != set(TIMEFRAME_ORDER):
            missing = sorted(set(TIMEFRAME_ORDER) - set(sources))
            extra = sorted(set(sources) - set(TIMEFRAME_ORDER))
            if missing:
                errors.append(f"Missing required timeframe sources: {missing}")
            if extra:
                errors.append(f"Unsupported timeframe sources: {extra}")
        return errors


class CausalMultiTimeframeContextAnalyzer:
    _STATE_RANK = {"COMPLETE": 0, "INCOMPLETE": 1, "NOT_EVALUATED": 2, "UNAVAILABLE": 3, "INVALID": 4}

    @staticmethod
    def _source_dict(source: Any) -> dict[str, Any]:
        if hasattr(source, "to_dict"):
            source = source.to_dict()
        if not isinstance(source, dict):
            raise ValueError("Each timeframe source must be a Slice #13 result or dictionary.")
        required = [
            "symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff",
            "source_snapshot_id", "source_availability", "availability_reason", "completion_state",
            "approved_candle_history", "diagnostics", "evidence", "metadata",
        ]
        missing = [name for name in required if name not in source]
        if missing:
            raise ValueError(f"Malformed Slice #13 result: missing fields {missing}.")
        if source["source_availability"] not in SOURCE_AVAILABILITY_STATES:
            raise ValueError("Malformed Slice #13 result: unknown source availability state.")
        if source["completion_state"] not in COMPLETION_STATES:
            raise ValueError("Malformed Slice #13 result: unknown completion state.")
        if not isinstance(source["approved_candle_history"], list):
            raise ValueError("Malformed Slice #13 result: approved_candle_history must be a list.")
        if not isinstance(source["diagnostics"], dict) or not isinstance(source["evidence"], dict) or not isinstance(source["metadata"], dict):
            raise ValueError("Malformed Slice #13 result: diagnostics, evidence, and metadata must be dictionaries.")
        try:
            _parse_timestamp(source["requested_evaluation_timestamp"])
            if source["effective_causal_cutoff"] is not None:
                _parse_timestamp(source["effective_causal_cutoff"])
        except ValueError as exc:
            raise ValueError(f"Malformed Slice #13 result timestamp: {exc}") from exc
        availability = source["source_availability"]
        snapshot_id = source["source_snapshot_id"]
        if availability == "AVAILABLE" and (not isinstance(snapshot_id, str) or not snapshot_id):
            raise ValueError("Malformed Slice #13 result: AVAILABLE source requires source_snapshot_id.")
        if availability != "AVAILABLE" and snapshot_id is not None and not isinstance(snapshot_id, str):
            raise ValueError("Malformed Slice #13 result: source_snapshot_id must be a string or None.")
        if availability == "AVAILABLE" and source["effective_causal_cutoff"] is None:
            raise ValueError("Malformed Slice #13 result: AVAILABLE source requires effective_causal_cutoff.")
        return source

    @staticmethod
    def _record(source: dict[str, Any]) -> dict[str, Any]:
        return {
            "timeframe": source["timeframe"],
            "requested_evaluation_timestamp": source["requested_evaluation_timestamp"],
            "effective_causal_cutoff": source["effective_causal_cutoff"],
            "source_snapshot_id": source["source_snapshot_id"],
            "source_availability": source["source_availability"],
            "availability_reason": source["availability_reason"],
            "completion_state": source["completion_state"],
        }

    @classmethod
    def _state_for_record(cls, record: dict[str, Any]) -> str:
        availability = record["source_availability"]
        if availability == "INVALID":
            return "INVALID"
        if availability == "UNAVAILABLE" or (availability == "AVAILABLE" and record["completion_state"] == "UNKNOWN"):
            return "UNAVAILABLE"
        if availability == "NOT_EVALUATED":
            return "NOT_EVALUATED"
        if record["completion_state"] == "INCOMPLETE":
            return "INCOMPLETE"
        return "COMPLETE"

    @classmethod
    def _edge_alignment(cls, parent: dict[str, Any], child: dict[str, Any]) -> str:
        if parent["source_availability"] == "INVALID":
            return "PARENT_INVALID"
        if child["source_availability"] == "INVALID":
            return "CHILD_INVALID"
        parent_unavailable = parent["source_availability"] != "AVAILABLE" or (
            parent["source_availability"] == "AVAILABLE" and parent["completion_state"] == "UNKNOWN"
        )
        child_unavailable = child["source_availability"] != "AVAILABLE" or (
            child["source_availability"] == "AVAILABLE" and child["completion_state"] == "UNKNOWN"
        )
        if parent_unavailable and child_unavailable:
            return "UNAVAILABLE"
        if parent_unavailable:
            return "PARENT_UNAVAILABLE"
        if child_unavailable:
            return "CHILD_UNAVAILABLE"
        return "ALIGNED"

    def analyze(self, payload: dict[str, Any]) -> CausalMultiTimeframeContextResult:
        context_input = CausalMultiTimeframeContextInput.from_payload(payload if isinstance(payload, dict) else {})
        base_errors = CausalMultiTimeframeContextValidator.validate_input(payload)
        if base_errors:
            raise ValueError("Invalid causal multi-timeframe context input: " + "; ".join(base_errors))
        requested = _parse_timestamp(context_input.requested_evaluation_timestamp)
        requested_text = requested.isoformat().replace("+00:00", "Z")
        source_records: dict[str, dict[str, Any]] = {}
        for timeframe in TIMEFRAME_ORDER:
            try:
                source = self._source_dict(context_input.timeframe_sources[timeframe])
            except ValueError as exc:
                raise ValueError(f"Invalid {timeframe} Slice #13 source: {exc}") from exc
            if str(source["timeframe"]).upper() != timeframe:
                raise ValueError(f"Invalid {timeframe} Slice #13 source: embedded timeframe does not match slot.")
            if str(source["symbol"]).upper() != context_input.symbol:
                raise ValueError(f"Invalid {timeframe} Slice #13 source: symbol does not match context symbol.")
            try:
                source_requested = _parse_timestamp(source["requested_evaluation_timestamp"])
            except ValueError as exc:
                raise ValueError(f"Invalid {timeframe} Slice #13 source timestamp: {exc}") from exc
            if source_requested != requested:
                raise ValueError(f"Invalid {timeframe} Slice #13 source: requested evaluation timestamp does not match context.")
            source_records[timeframe] = self._record(source)

        timeframes = {timeframe: source_records[timeframe] for timeframe in TIMEFRAME_ORDER}
        states = [self._state_for_record(timeframes[timeframe]) for timeframe in TIMEFRAME_ORDER]
        context_state = max(states, key=lambda state: self._STATE_RANK[state])
        edges: list[dict[str, Any]] = []
        for parent, child in zip(TIMEFRAME_ORDER, TIMEFRAME_ORDER[1:]):
            parent_record = timeframes[parent]
            child_record = timeframes[child]
            edges.append(
                {
                    "parent_timeframe": parent,
                    "child_timeframe": child,
                    "parent_source_snapshot_id": parent_record["source_snapshot_id"],
                    "child_source_snapshot_id": child_record["source_snapshot_id"],
                    "parent_availability": parent_record["source_availability"],
                    "child_availability": child_record["source_availability"],
                    "alignment_status": self._edge_alignment(parent_record, child_record),
                }
            )

        descriptors = [timeframes[timeframe] for timeframe in TIMEFRAME_ORDER]
        context_id = _hash_id([context_input.symbol, requested_text, list(TIMEFRAME_ORDER), descriptors, RULE_VERSION])
        diagnostics = {
            "required_timeframe_count": 7,
            "available_timeframe_count": sum(record["source_availability"] == "AVAILABLE" for record in timeframes.values()),
            "unavailable_timeframe_count": sum(record["source_availability"] == "UNAVAILABLE" for record in timeframes.values()),
            "invalid_timeframe_count": sum(record["source_availability"] == "INVALID" for record in timeframes.values()),
            "not_evaluated_timeframe_count": sum(record["source_availability"] == "NOT_EVALUATED" for record in timeframes.values()),
            "completed_timeframe_count": sum(record["source_availability"] == "AVAILABLE" and record["completion_state"] == "COMPLETED" for record in timeframes.values()),
            "incomplete_timeframe_count": sum(record["source_availability"] == "AVAILABLE" and record["completion_state"] == "INCOMPLETE" for record in timeframes.values()),
            "complete_edge_count": sum(edge["alignment_status"] == "ALIGNED" for edge in edges),
            "incomplete_edge_count": sum(edge["alignment_status"] != "ALIGNED" for edge in edges),
        }
        evidence = {
            "requested_evaluation_timestamp": requested_text,
            "timeframe_order": list(TIMEFRAME_ORDER),
            "timeframes": [dict(record) for record in descriptors],
            "edges": [dict(edge) for edge in edges],
            "context_state_precedence": ["INVALID", "UNAVAILABLE", "NOT_EVALUATED", "INCOMPLETE", "COMPLETE"],
            "context_state": context_state,
            "rule_version": RULE_VERSION,
            "identity_scope": IDENTITY_SCOPE,
            "source_contract": SOURCE_CONTRACT,
        }
        metadata = {
            "contract": CONTRACT,
            "rule_version": RULE_VERSION,
            "identity_scope": IDENTITY_SCOPE,
            "deterministic_causal_multi_timeframe_context": True,
            "source_context_only": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "authority_scope": "read_only",
        }
        return CausalMultiTimeframeContextResult(
            symbol=context_input.symbol,
            requested_evaluation_timestamp=requested_text,
            context_id=context_id,
            identity_scope=IDENTITY_SCOPE,
            context_state=context_state,
            timeframes=timeframes,
            edges=edges,
            diagnostics=diagnostics,
            evidence=evidence,
            metadata=metadata,
        )


CAUSAL_MULTI_TIMEFRAME_CONTEXT = CausalMultiTimeframeContextAnalyzer()

__all__ = [
    "CausalMultiTimeframeContextAnalyzer",
    "CausalMultiTimeframeContextInput",
    "CausalMultiTimeframeContextResult",
    "CausalMultiTimeframeContextValidator",
    "CAUSAL_MULTI_TIMEFRAME_CONTEXT",
    "CONTRACT",
    "EDGE_ALIGNMENT_STATES",
    "RULE_VERSION",
    "TIMEFRAME_ORDER",
]