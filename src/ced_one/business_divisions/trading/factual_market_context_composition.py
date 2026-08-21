"""Structured factual composition over the authoritative Slice #16 context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any

TIMEFRAME_ORDER = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
CAPABILITY_ORDER = (
    "market_structure", "candle_intelligence", "volatility_range", "liquidity_intelligence",
    "liquidity_events", "fvg_imbalance_intelligence", "displacement_intelligence",
    "order_block_intelligence", "structural_dealing_range_intelligence", "premium_discount_intelligence",
)
RELATIONSHIP_TYPES = {
    "PRESENT_ON_BOTH", "PRESENT_ON_PARENT_ONLY", "PRESENT_ON_CHILD_ONLY", "ABSENT_ON_BOTH",
    "STATE_DIFFERENCE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED", "NOT_COMPARABLE",
}
CONTEXT_STATES = {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
FACTUAL_STATES = {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
SLICE16_CONTRACT = "trading.causal_factual_multi_timeframe_context.v1"
RULE_VERSION = "factual_market_context_composition_v1"
PROFILE_VERSION = "factual_context_composition_profile_v1"
CONTRACT = "trading.factual_market_context_composition.v1"
IDENTITY_SCOPE = "snapshot_deterministic"


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise ValueError("factual_context must be a Slice #16 result or serialized dictionary.")
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
    return "factual_composition_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class FactualMarketContextCompositionInput:
    factual_context: Any

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FactualMarketContextCompositionInput":
        return cls(factual_context=payload.get("factual_context"))


@dataclass
class FactualMarketContextCompositionResult:
    symbol: str
    requested_evaluation_timestamp: str
    source_factual_context_id: str | None
    composition_id: str
    identity_scope: str
    composition_state: str
    timeframes: dict[str, dict[str, Any]] = field(default_factory=dict)
    adjacent_relationships: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "source_factual_context_id": self.source_factual_context_id,
            "composition_id": self.composition_id,
            "identity_scope": self.identity_scope,
            "composition_state": self.composition_state,
            "timeframes": {name: dict(record) for name, record in self.timeframes.items()},
            "adjacent_relationships": [dict(item) for item in self.adjacent_relationships],
            "diagnostics": dict(self.diagnostics),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }


class FactualMarketContextCompositionValidator:
    @staticmethod
    def validate_input(payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]
        extra = sorted(set(payload) - {"factual_context"})
        return [f"Unsupported input fields: {extra}"] if extra else []


class FactualMarketContextCompositionAnalyzer:
    def analyze(self, payload: dict[str, Any]) -> FactualMarketContextCompositionResult:
        errors = FactualMarketContextCompositionValidator.validate_input(payload)
        if errors:
            raise ValueError("Invalid factual market context input: " + "; ".join(errors))
        context = _as_dict(payload.get("factual_context"))
        self._validate_context(context)
        symbol = str(context["symbol"]).upper()
        requested = _parse_timestamp(context["requested_evaluation_timestamp"])
        requested_text = requested.isoformat().replace("+00:00", "Z")
        source_context_id = context["source_context_id"]
        timeframes: dict[str, dict[str, Any]] = {}
        for timeframe in TIMEFRAME_ORDER:
            source_record = context["timeframes"][timeframe]
            capabilities = source_record["factual_capabilities"]
            timeframes[timeframe] = {
                "timeframe": timeframe,
                "source_snapshot_id": source_record["source_snapshot_id"],
                "factual_context_state": source_record["factual_context_state"],
                "capability_observations": {
                    capability: self._capability_observation(capabilities[capability])
                    for capability in CAPABILITY_ORDER
                },
            }

        relationships = []
        for parent, child in zip(TIMEFRAME_ORDER, TIMEFRAME_ORDER[1:]):
            for capability in CAPABILITY_ORDER:
                parent_observation = timeframes[parent]["capability_observations"][capability]
                child_observation = timeframes[child]["capability_observations"][capability]
                relationships.append(self._relationship(parent, child, capability, parent_observation, child_observation))

        diagnostics = {
            "required_timeframe_count": 7,
            "required_capability_count_per_timeframe": 10,
            "timeframe_record_count": len(timeframes),
            "adjacent_edge_count": 6,
            "relationship_count": len(relationships),
            "present_on_both_count": sum(item["relationship_type"] == "PRESENT_ON_BOTH" for item in relationships),
            "present_on_parent_only_count": sum(item["relationship_type"] == "PRESENT_ON_PARENT_ONLY" for item in relationships),
            "present_on_child_only_count": sum(item["relationship_type"] == "PRESENT_ON_CHILD_ONLY" for item in relationships),
            "absent_on_both_count": sum(item["relationship_type"] == "ABSENT_ON_BOTH" for item in relationships),
            "unavailable_relationship_count": sum(item["relationship_type"] == "UNAVAILABLE" for item in relationships),
            "invalid_relationship_count": sum(item["relationship_type"] == "INVALID" for item in relationships),
            "not_evaluated_relationship_count": sum(item["relationship_type"] == "NOT_EVALUATED" for item in relationships),
            "not_comparable_relationship_count": sum(item["relationship_type"] == "NOT_COMPARABLE" for item in relationships),
        }
        composition_state = context["context_state"]
        identity_descriptors = [
            {
                "timeframe": timeframe,
                "source_snapshot_id": record["source_snapshot_id"],
                "factual_context_state": record["factual_context_state"],
                "capabilities": [
                    {
                        "capability": capability,
                        "factual_envelope_id": timeframes[timeframe]["capability_observations"][capability]["factual_envelope_id"],
                        "factual_availability": timeframes[timeframe]["capability_observations"][capability]["factual_availability"],
                    }
                    for capability in CAPABILITY_ORDER
                ],
            }
            for timeframe, record in context["timeframes"].items()
        ]
        composition_id = _hash_id([RULE_VERSION, PROFILE_VERSION, context["factual_context_id"], source_context_id, symbol, requested_text, list(TIMEFRAME_ORDER), list(CAPABILITY_ORDER), identity_descriptors, [item["relationship_type"] for item in relationships], composition_state])
        return FactualMarketContextCompositionResult(
            symbol=symbol,
            requested_evaluation_timestamp=requested_text,
            source_factual_context_id=context["factual_context_id"],
            composition_id=composition_id,
            identity_scope=IDENTITY_SCOPE,
            composition_state=composition_state,
            timeframes=timeframes,
            adjacent_relationships=relationships,
            diagnostics=diagnostics,
            evidence={
                "source_factual_context_id": context["factual_context_id"],
                "source_context_id": source_context_id,
                "timeframe_order": list(TIMEFRAME_ORDER),
                "capability_order": list(CAPABILITY_ORDER),
                "relationship_types": sorted(RELATIONSHIP_TYPES),
                "composition_state": composition_state,
                "rule_version": RULE_VERSION,
                "profile_version": PROFILE_VERSION,
                "identity_scope": IDENTITY_SCOPE,
            },
            metadata={
                "contract": CONTRACT,
                "rule_version": RULE_VERSION,
                "profile_version": PROFILE_VERSION,
                "identity_scope": IDENTITY_SCOPE,
                "structured_output_only": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "authority_scope": "read_only",
            },
        )

    @staticmethod
    def _validate_context(context: dict[str, Any]) -> None:
        required = {"symbol", "requested_evaluation_timestamp", "source_context_id", "factual_context_id", "identity_scope", "context_state", "timeframes", "diagnostics", "evidence", "metadata"}
        missing = sorted(required - set(context))
        if missing:
            raise ValueError(f"Malformed Slice #16 context: missing fields {missing}.")
        if context["symbol"].upper() != "XAUUSD" or context["identity_scope"] != IDENTITY_SCOPE:
            raise ValueError("Malformed Slice #16 context identity or symbol.")
        if context["metadata"].get("contract") != SLICE16_CONTRACT or context["context_state"] not in CONTEXT_STATES:
            raise ValueError("Unsupported Slice #16 contract or context state.")
        _parse_timestamp(context["requested_evaluation_timestamp"])
        if set(context["timeframes"]) != set(TIMEFRAME_ORDER):
            raise ValueError("Slice #16 context must contain exactly seven timeframes.")
        for timeframe in TIMEFRAME_ORDER:
            record = context["timeframes"][timeframe]
            if record.get("timeframe") != timeframe or set(record.get("factual_capabilities", {})) != set(CAPABILITY_ORDER):
                raise ValueError(f"Malformed Slice #16 timeframe record: {timeframe}.")
            if record.get("factual_context_state") not in CONTEXT_STATES:
                raise ValueError("Unknown Slice #16 timeframe context state.")
            for capability in CAPABILITY_ORDER:
                observation = record["factual_capabilities"][capability]
                if observation.get("source_snapshot_id") != record.get("source_snapshot_id"):
                    raise ValueError(f"Slice #16 capability source mismatch for {timeframe}/{capability}.")

    @staticmethod
    def _capability_observation(value: dict[str, Any]) -> dict[str, Any]:
        required = {"factual_availability", "factual_envelope_id", "authoritative_result_id", "source_snapshot_id", "capability", "dependency_provenance", "availability_reason"}
        if not required <= set(value):
            raise ValueError("Malformed Slice #16 capability observation.")
        if value["factual_availability"] not in FACTUAL_STATES:
            raise ValueError("Unknown factual availability state.")
        capability = value["capability"]
        if not isinstance(capability, dict) or not capability.get("name") or not capability.get("contract") or not capability.get("rule_version"):
            raise ValueError("Malformed capability identity in Slice #16 context.")
        return {
            "capability_name": capability["name"],
            "factual_availability": value["factual_availability"],
            "factual_envelope_id": value["factual_envelope_id"],
            "authoritative_result_id": value["authoritative_result_id"],
            "source_snapshot_id": value["source_snapshot_id"],
            "capability_contract": capability["contract"],
            "capability_rule_version": capability["rule_version"],
            "availability_reason": value["availability_reason"],
            "dependency_provenance_reference": value["dependency_provenance"],
        }

    @staticmethod
    def _relationship(parent: str, child: str, capability: str, parent_record: dict[str, Any], child_record: dict[str, Any]) -> dict[str, Any]:
        parent_state = parent_record["factual_availability"]
        child_state = child_record["factual_availability"]
        if "INVALID" in {parent_state, child_state}:
            relationship_type = "INVALID"
        elif "UNAVAILABLE" in {parent_state, child_state}:
            relationship_type = "UNAVAILABLE"
        elif "NOT_EVALUATED" in {parent_state, child_state}:
            relationship_type = "NOT_EVALUATED"
        elif parent_state == "AVAILABLE_PRESENT" and child_state == "AVAILABLE_PRESENT":
            relationship_type = "PRESENT_ON_BOTH"
        elif parent_state == "AVAILABLE_PRESENT" and child_state == "AVAILABLE_ABSENT":
            relationship_type = "PRESENT_ON_PARENT_ONLY"
        elif parent_state == "AVAILABLE_ABSENT" and child_state == "AVAILABLE_PRESENT":
            relationship_type = "PRESENT_ON_CHILD_ONLY"
        elif parent_state == "AVAILABLE_ABSENT" and child_state == "AVAILABLE_ABSENT":
            relationship_type = "ABSENT_ON_BOTH"
        else:
            relationship_type = "NOT_COMPARABLE"
        return {
            "parent_timeframe": parent,
            "child_timeframe": child,
            "capability_name": capability,
            "parent_source_snapshot_id": parent_record["source_snapshot_id"],
            "child_source_snapshot_id": child_record["source_snapshot_id"],
            "parent_capability_envelope_id": parent_record["factual_envelope_id"],
            "child_capability_envelope_id": child_record["factual_envelope_id"],
            "relationship_type": relationship_type,
        }


class FactualMarketContextSpecialist:
    name = "factual_market_context_analyst"
    division_name = "trading"
    capability_name = "factual_market_context_composition"
    permission_scope = "read_only"

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

    def compose_factual_context(self, payload: dict[str, Any], **_: Any) -> FactualMarketContextCompositionResult:
        return FactualMarketContextCompositionAnalyzer().analyze(payload)


FACTUAL_MARKET_CONTEXT_COMPOSITION = FactualMarketContextCompositionAnalyzer()

__all__ = [
    "CAPABILITY_ORDER",
    "CONTRACT",
    "FactualMarketContextCompositionAnalyzer",
    "FactualMarketContextCompositionInput",
    "FactualMarketContextCompositionResult",
    "FactualMarketContextCompositionValidator",
    "FactualMarketContextSpecialist",
    "FACTUAL_MARKET_CONTEXT_COMPOSITION",
    "RELATIONSHIP_TYPES",
    "RULE_VERSION",
    "TIMEFRAME_ORDER",
]