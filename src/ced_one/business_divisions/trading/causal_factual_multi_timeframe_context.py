"""Seven-layer factual context over Slice #14 and Slice #15 results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any

TIMEFRAME_ORDER = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
CAPABILITY_ORDER = (
    "market_structure",
    "candle_intelligence",
    "volatility_range",
    "liquidity_intelligence",
    "liquidity_events",
    "fvg_imbalance_intelligence",
    "displacement_intelligence",
    "order_block_intelligence",
    "structural_dealing_range_intelligence",
    "premium_discount_intelligence",
)
CAPABILITY_CONTRACTS = {name: f"trading.{name}.v1" for name in CAPABILITY_ORDER}
ENVELOPE_CONTRACT = "trading.causal_factual_intelligence_envelope.v1"
SOURCE_CONTEXT_CONTRACT = "trading.causal_multi_timeframe_context.v1"
RULE_VERSION = "causal_factual_multi_timeframe_context_v1"
PROFILE_VERSION = "factual_profile_v1"
IDENTITY_SCOPE = "snapshot_deterministic"
FACTUAL_STATES = {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
CONTEXT_STATES = {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
STATE_RANK = {"COMPLETE": 0, "INCOMPLETE": 1, "NOT_EVALUATED": 2, "UNAVAILABLE": 3, "INVALID": 4}
DEPENDENCY_REQUIREMENTS = {
    "liquidity_events": (("liquidity_intelligence",),),
    "order_block_intelligence": (("displacement_intelligence",),),
    "structural_dealing_range_intelligence": (("market_structure",),),
    "premium_discount_intelligence": (("market_structure", "structural_dealing_range_intelligence"),),
}


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise ValueError("Expected a serialized repository result or typed result object.")
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _hash_id(value: Any) -> str:
    encoded = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return "factual_context_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class CausalFactualMultiTimeframeContextInput:
    symbol: str
    requested_evaluation_timestamp: str
    source_context: Any
    factual_envelopes: dict[str, dict[str, Any]]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CausalFactualMultiTimeframeContextInput":
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            requested_evaluation_timestamp=str(payload.get("requested_evaluation_timestamp", "")),
            source_context=payload.get("source_context"),
            factual_envelopes=dict(payload.get("factual_envelopes") or {}) if isinstance(payload.get("factual_envelopes"), dict) else {},
        )


@dataclass
class CausalFactualMultiTimeframeContextResult:
    symbol: str
    requested_evaluation_timestamp: str
    source_context_id: str | None
    factual_context_id: str | None
    identity_scope: str
    context_state: str
    timeframes: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "source_context_id": self.source_context_id,
            "factual_context_id": self.factual_context_id,
            "identity_scope": self.identity_scope,
            "context_state": self.context_state,
            "timeframes": {name: dict(record) for name, record in self.timeframes.items()},
            "diagnostics": dict(self.diagnostics),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }


class CausalFactualMultiTimeframeContextValidator:
    @staticmethod
    def validate_input(payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        errors: list[str] = []
        allowed = {"symbol", "requested_evaluation_timestamp", "source_context", "factual_envelopes"}
        extra = sorted(set(payload) - allowed)
        if extra:
            errors.append(f"Unsupported input fields: {extra}")
        if str(payload.get("symbol", "")).upper() != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")
        try:
            _parse_timestamp(payload.get("requested_evaluation_timestamp"))
        except ValueError as exc:
            errors.append(f"Invalid requested_evaluation_timestamp: {exc}")
        if "source_context" not in payload:
            errors.append("Missing required field: source_context")
        if not isinstance(payload.get("factual_envelopes"), dict):
            errors.append("Missing required field: factual_envelopes")
        return errors


class CausalFactualMultiTimeframeContextAnalyzer:
    def analyze(self, payload: dict[str, Any]) -> CausalFactualMultiTimeframeContextResult:
        errors = CausalFactualMultiTimeframeContextValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid causal factual multi-timeframe context input: " + "; ".join(errors))
        request = CausalFactualMultiTimeframeContextInput.from_payload(payload)
        requested = _parse_timestamp(request.requested_evaluation_timestamp)
        requested_text = requested.isoformat().replace("+00:00", "Z")
        source_context = _as_dict(request.source_context)
        self._validate_source_context(source_context, request.symbol, requested)
        envelope_groups = request.factual_envelopes
        if set(envelope_groups) != set(TIMEFRAME_ORDER):
            raise ValueError("Factual envelopes must contain exactly the seven canonical timeframes.")

        source_context_id = source_context.get("context_id")
        timeframe_records: dict[str, dict[str, Any]] = {}
        identity_descriptors: list[dict[str, Any]] = []
        counts = {
            "required_timeframe_count": 7,
            "required_capability_count_per_timeframe": 10,
            "complete_timeframe_count": 0,
            "incomplete_timeframe_count": 0,
            "unavailable_timeframe_count": 0,
            "invalid_timeframe_count": 0,
            "not_evaluated_timeframe_count": 0,
            "evaluated_envelope_count": 0,
            "present_envelope_count": 0,
            "absent_envelope_count": 0,
            "unavailable_envelope_count": 0,
            "invalid_envelope_count": 0,
            "not_evaluated_envelope_count": 0,
        }
        for timeframe in TIMEFRAME_ORDER:
            source_slot = _as_dict(source_context["timeframes"][timeframe])
            envelope_group = envelope_groups[timeframe]
            if not isinstance(envelope_group, dict) or set(envelope_group) != set(CAPABILITY_ORDER):
                raise ValueError(f"{timeframe} must contain exactly the ten canonical capabilities.")
            source_availability = source_slot["source_availability"]
            source_completion = source_slot["completion_state"]
            capabilities: dict[str, dict[str, Any]] = {}
            timeframe_descriptors: list[dict[str, Any]] = []
            for capability in CAPABILITY_ORDER:
                envelope = self._validate_envelope(
                    envelope_group[capability], timeframe, capability, request.symbol, requested,
                    source_slot,
                )
                capabilities[capability] = envelope
                factual_state = envelope["factual_availability"]
                if factual_state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}:
                    counts["evaluated_envelope_count"] += 1
                    counts["present_envelope_count"] += factual_state == "AVAILABLE_PRESENT"
                    counts["absent_envelope_count"] += factual_state == "AVAILABLE_ABSENT"
                elif factual_state == "UNAVAILABLE":
                    counts["unavailable_envelope_count"] += 1
                elif factual_state == "INVALID":
                    counts["invalid_envelope_count"] += 1
                else:
                    counts["not_evaluated_envelope_count"] += 1
                timeframe_descriptors.append({
                    "capability": capability,
                    "factual_envelope_id": envelope["factual_envelope_id"],
                    "factual_availability": factual_state,
                    "capability_contract": envelope["capability"]["contract"],
                    "capability_rule_version": envelope["capability"]["rule_version"],
                    "dependency_provenance": envelope["dependency_provenance"],
                })
            timeframe_state = self._timeframe_state(source_availability, source_completion, capabilities)
            counts_key = {
                "COMPLETE": "complete_timeframe_count",
                "INCOMPLETE": "incomplete_timeframe_count",
                "UNAVAILABLE": "unavailable_timeframe_count",
                "INVALID": "invalid_timeframe_count",
                "NOT_EVALUATED": "not_evaluated_timeframe_count",
            }[timeframe_state]
            counts[counts_key] += 1
            record = {
                "timeframe": timeframe,
                "source_snapshot_id": source_slot["source_snapshot_id"],
                "effective_causal_cutoff": source_slot["effective_causal_cutoff"],
                "source_availability": source_availability,
                "source_completion_state": source_completion,
                "factual_context_state": timeframe_state,
                "factual_capabilities": capabilities,
            }
            timeframe_records[timeframe] = record
            identity_descriptors.append({
                "timeframe": timeframe,
                "source_snapshot_id": source_slot["source_snapshot_id"],
                "source_availability": source_availability,
                "source_completion_state": source_completion,
                "effective_causal_cutoff": source_slot["effective_causal_cutoff"],
                "capabilities": timeframe_descriptors,
            })

        context_state = max(
            (record["factual_context_state"] for record in timeframe_records.values()),
            key=lambda state: {"COMPLETE": 0, "INCOMPLETE": 1, "NOT_EVALUATED": 2, "UNAVAILABLE": 3, "INVALID": 4}[state],
        )
        identity_parts = [RULE_VERSION, PROFILE_VERSION, request.symbol, requested_text, source_context_id, list(TIMEFRAME_ORDER), list(CAPABILITY_ORDER), identity_descriptors, context_state]
        factual_context_id = _hash_id(identity_parts)
        evidence = {
            "source_context_id": source_context_id,
            "requested_evaluation_timestamp": requested_text,
            "timeframe_order": list(TIMEFRAME_ORDER),
            "capability_order": list(CAPABILITY_ORDER),
            "required_profile": PROFILE_VERSION,
            "identity_descriptors": identity_descriptors,
            "context_state_precedence": ["INVALID", "UNAVAILABLE", "NOT_EVALUATED", "INCOMPLETE", "COMPLETE"],
            "context_state": context_state,
            "rule_version": RULE_VERSION,
            "identity_scope": IDENTITY_SCOPE,
        }
        metadata = {
            "contract": "trading.causal_factual_multi_timeframe_context.v1",
            "rule_version": RULE_VERSION,
            "profile_version": PROFILE_VERSION,
            "identity_scope": IDENTITY_SCOPE,
            "source_context_only": False,
            "factual_context_only": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
            "authority_scope": "read_only",
        }
        return CausalFactualMultiTimeframeContextResult(
            symbol=request.symbol,
            requested_evaluation_timestamp=requested_text,
            source_context_id=source_context_id,
            factual_context_id=factual_context_id,
            identity_scope=IDENTITY_SCOPE,
            context_state=context_state,
            timeframes=timeframe_records,
            diagnostics=counts,
            evidence=evidence,
            metadata=metadata,
        )

    @staticmethod
    def _validate_source_context(source: dict[str, Any], symbol: str, requested: datetime) -> None:
        required = {"symbol", "requested_evaluation_timestamp", "context_id", "identity_scope", "context_state", "timeframes", "edges", "metadata"}
        missing = sorted(required - set(source))
        if missing:
            raise ValueError(f"Malformed Slice #14 source context: missing fields {missing}.")
        if str(source["symbol"]).upper() != symbol or _parse_timestamp(source["requested_evaluation_timestamp"]) != requested:
            raise ValueError("Slice #14 source context symbol or requested timestamp mismatch.")
        if source["identity_scope"] != IDENTITY_SCOPE or source["metadata"].get("contract") != SOURCE_CONTEXT_CONTRACT:
            raise ValueError("Slice #14 source context identity or contract is unsupported.")
        if set(source["timeframes"]) != set(TIMEFRAME_ORDER):
            raise ValueError("Slice #14 source context must contain exactly the seven canonical timeframes.")
        for timeframe in TIMEFRAME_ORDER:
            slot = _as_dict(source["timeframes"][timeframe])
            if slot.get("timeframe") != timeframe:
                raise ValueError(f"Slice #14 timeframe slot mismatch for {timeframe}.")
            if slot.get("source_availability") not in {"AVAILABLE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}:
                raise ValueError("Slice #14 source context has unknown source availability.")

    @staticmethod
    def _validate_envelope(envelope_value: Any, timeframe: str, capability: str, symbol: str, requested: datetime, source_slot: dict[str, Any]) -> dict[str, Any]:
        envelope = _as_dict(envelope_value)
        required = {
            "factual_envelope_id", "factual_availability", "symbol", "timeframe", "requested_evaluation_timestamp",
            "effective_causal_cutoff", "source_snapshot_id", "source_completion_state", "capability",
            "authoritative_result", "authoritative_result_id", "dependency_provenance", "availability_reason",
            "provenance", "diagnostics", "evidence", "metadata",
        }
        missing = sorted(required - set(envelope))
        if missing:
            raise ValueError(f"Malformed Slice #15 envelope for {timeframe}/{capability}: missing fields {missing}.")
        if envelope["metadata"].get("contract") != ENVELOPE_CONTRACT or envelope["metadata"].get("identity_scope") != IDENTITY_SCOPE:
            raise ValueError("Slice #15 envelope contract or identity scope is unsupported.")
        if envelope["symbol"] != symbol or envelope["timeframe"] != timeframe or _parse_timestamp(envelope["requested_evaluation_timestamp"]) != requested:
            raise ValueError("Slice #15 envelope symbol, timeframe, or timestamp mismatch.")
        if envelope["source_snapshot_id"] != source_slot["source_snapshot_id"] or envelope["effective_causal_cutoff"] != source_slot["effective_causal_cutoff"]:
            raise ValueError("Slice #15 envelope source identity or cutoff mismatch.")
        if envelope["factual_availability"] not in FACTUAL_STATES:
            raise ValueError("Slice #15 envelope has unknown factual availability.")
        capability_record = envelope["capability"]
        if capability_record.get("name") != capability or capability_record.get("contract") != CAPABILITY_CONTRACTS[capability]:
            raise ValueError("Slice #15 envelope capability slot mismatch.")
        if envelope["factual_availability"] in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}:
            if not envelope["factual_envelope_id"] or not envelope["authoritative_result_id"] or envelope["authoritative_result"] is None:
                raise ValueError("Successful Slice #15 envelope requires result and identities.")
        elif envelope["factual_envelope_id"] is not None:
            raise ValueError("Non-success Slice #15 envelope must not have a factual envelope identity.")
        if envelope["provenance"].get("controlled_invocation") is not True:
            raise ValueError("Slice #15 envelope lacks controlled invocation provenance.")
        CausalFactualMultiTimeframeContextAnalyzer._validate_dependencies(envelope, capability, source_slot)
        return {
            "factual_availability": envelope["factual_availability"],
            "factual_envelope_id": envelope["factual_envelope_id"],
            "authoritative_result_id": envelope["authoritative_result_id"],
            "source_snapshot_id": envelope["source_snapshot_id"],
            "capability": dict(capability_record),
            "dependency_provenance": [dict(item) for item in envelope["dependency_provenance"]],
            "availability_reason": envelope["availability_reason"],
        }

    @staticmethod
    def _validate_dependencies(envelope: dict[str, Any], capability: str, source_slot: dict[str, Any]) -> None:
        required_chains = DEPENDENCY_REQUIREMENTS.get(capability, ())
        dependencies = envelope["dependency_provenance"]
        expected = required_chains[0] if required_chains else ()
        if required_chains and [item.get("capability_name") for item in dependencies] != list(expected):
            raise ValueError(f"Slice #15 dependency ordering is invalid for {capability}.")
        for index, dependency in enumerate(dependencies, start=1):
            required = {"dependency_order", "capability_name", "capability_contract", "capability_rule_version", "factual_availability", "authoritative_result_id", "source_snapshot_id", "symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff", "configuration_fingerprint", "controlled_invocation", "provenance_validation"}
            if not required <= set(dependency):
                raise ValueError(f"Malformed dependency provenance for {capability}.")
            if dependency["dependency_order"] != index or dependency["source_snapshot_id"] != source_slot["source_snapshot_id"] or dependency["symbol"] != source_slot.get("symbol", "XAUUSD") or dependency["timeframe"] != source_slot["timeframe"] or dependency["requested_evaluation_timestamp"] != source_slot["requested_evaluation_timestamp"] or dependency["effective_causal_cutoff"] != source_slot["effective_causal_cutoff"]:
                raise ValueError(f"Dependency source provenance mismatch for {capability}.")
            if dependency["factual_availability"] not in FACTUAL_STATES or not dependency["authoritative_result_id"] or dependency["controlled_invocation"] is not True or dependency["provenance_validation"] != "validated_controlled_dependency":
                raise ValueError(f"Dependency provenance is not validated for {capability}.")

    @staticmethod
    def _timeframe_state(source_availability: str, source_completion: str, capabilities: dict[str, dict[str, Any]]) -> str:
        states = [item["factual_availability"] for item in capabilities.values()]
        if source_availability == "INVALID" or "INVALID" in states:
            return "INVALID"
        if source_availability == "UNAVAILABLE" or "UNAVAILABLE" in states:
            return "UNAVAILABLE"
        if source_availability == "NOT_EVALUATED" or "NOT_EVALUATED" in states:
            return "NOT_EVALUATED"
        if source_completion == "UNKNOWN" or source_completion == "INCOMPLETE":
            return "INCOMPLETE"
        return "COMPLETE"


CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT = CausalFactualMultiTimeframeContextAnalyzer()

__all__ = [
    "CAPABILITY_ORDER",
    "CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT",
    "CausalFactualMultiTimeframeContextAnalyzer",
    "CausalFactualMultiTimeframeContextInput",
    "CausalFactualMultiTimeframeContextResult",
    "CausalFactualMultiTimeframeContextValidator",
    "TIMEFRAME_ORDER",
]