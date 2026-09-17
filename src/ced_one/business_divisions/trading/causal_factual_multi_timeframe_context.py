"""Seven-layer factual context over Slice #14 and Slice #15 results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    ADAPTERS, RULE_VERSION as ENVELOPE_RULE_VERSION, EXECUTION_STATES, VALIDATED_STATES,
    FAILURE_STATES, execution_diagnostics, dependency_configurations, _configuration_fingerprint, _invocation_configuration,
)

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
RULE_VERSION = "causal_factual_multi_timeframe_context_v2"
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
                raw_envelope = _as_dict(envelope_group[capability])
                if raw_envelope.get("context_id") not in (None, source_context_id):
                    raise ValueError("Slice #15 source context identity mismatch.")
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
                    "execution_progress": raw_envelope["provenance"]["execution_progress"],
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
        CausalFactualMultiTimeframeContextAnalyzer._validate_execution(envelope, capability, source_slot)
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
    def _validate_execution(envelope, capability, source_slot):
        if envelope["metadata"].get("rule_version") != ENVELOPE_RULE_VERSION:
            raise ValueError("Legacy or unsupported Slice #15 rule version.")
        adapter = ADAPTERS[CAPABILITY_CONTRACTS[capability]]
        descriptor = envelope["capability"]
        if descriptor.get("rule_version") != adapter.rule_version:
            raise ValueError("Capability rule version mismatch.")
        config = descriptor.get("configuration")
        if not isinstance(config, dict):
            raise ValueError("Capability configuration must be a dictionary.")
        nested_key = {
            "trading.liquidity_events.v1": "liquidity_config",
            "trading.order_block_intelligence.v1": "displacement_config",
        }.get(adapter.contract)
        if nested_key is not None:
            nested = config.get(nested_key)
            outer = config.get("lookback_candles")
            if (not isinstance(nested, dict)
                    or type(outer) is not int
                    or type(nested.get("lookback_candles")) is not int
                    or nested["lookback_candles"] != outer):
                raise ValueError("Effective nested lookback must match the outer lookback.")
        invocation_config = _invocation_configuration(adapter.contract, config)
        if config != adapter.normalize_configuration(invocation_config):
            raise ValueError("Capability configuration is not effective configuration.")
        fingerprint = _configuration_fingerprint(config)
        provenance, evidence = envelope["provenance"], envelope["evidence"]
        if not isinstance(provenance, dict) or not isinstance(evidence, dict):
            raise ValueError("Malformed envelope provenance.")
        if provenance.get("configuration_fingerprint") != fingerprint or evidence.get("configuration_fingerprint") != fingerprint:
            raise ValueError("Terminal configuration fingerprint mismatch.")
        if provenance.get("source_snapshot_id") != source_slot["source_snapshot_id"] or provenance.get("source_contract") != "trading.causal_snapshot_availability.v1":
            raise ValueError("Source provenance mismatch.")
        if provenance.get("identity_scope") != IDENTITY_SCOPE or envelope["source_completion_state"] != source_slot["completion_state"]:
            raise ValueError("Source completion or identity scope mismatch.")
        if provenance.get("dependency_contracts") != list(adapter.dependencies):
            raise ValueError("Declared dependency contracts mismatch.")
        progress = provenance.get("execution_progress")
        if not isinstance(progress, dict) or set(progress) != {"terminal", "dependencies"}:
            raise ValueError("Missing or malformed execution progress.")
        terminal, steps = progress["terminal"], progress["dependencies"]
        if not isinstance(terminal, str) or terminal not in EXECUTION_STATES - {"PROVENANCE_VALIDATION_FAILED"}:
            raise ValueError("Invalid terminal progress.")
        if not isinstance(steps, list) or len(steps) != len(adapter.dependencies):
            raise ValueError("Dependency progress must cover the declared chain.")
        for step, contract in zip(steps, adapter.dependencies):
            if not isinstance(step, dict) or set(step) != {"capability_contract", "state", "authoritative_result_id"}:
                raise ValueError("Malformed dependency progress record.")
            state = step["state"]
            if step["capability_contract"] != contract or not isinstance(state, str) or state not in EXECUTION_STATES:
                raise ValueError("Dependency progress binding mismatch.")
            identity = step["authoritative_result_id"]
            if state in VALIDATED_STATES:
                if not isinstance(identity, str) or not identity:
                    raise ValueError("Validated dependency result requires an identity.")
            elif identity is not None:
                raise ValueError("Unvalidated dependency cannot have an identity.")
        states = [step["state"] for step in steps] + [terminal]
        stopped = False
        for state in states:
            if stopped and state != "NOT_STARTED":
                raise ValueError("Execution continued after an unfinished step.")
            if state != "COMPLETED":
                stopped = True
        diagnostics = envelope["diagnostics"]
        if not isinstance(diagnostics, dict):
            raise ValueError("Missing execution diagnostics.")
        expected = execution_diagnostics(progress)
        for key, value in expected.items():
            if type(diagnostics.get(key)) is not type(value) or diagnostics[key] != value:
                raise ValueError(f"Execution diagnostic contradicts progress: {key}.")
        if provenance.get("controlled_invocation") is not expected["controlled_invocation_performed"]:
            raise ValueError("Invocation provenance contradicts progress.")
        dependencies = envelope["dependency_provenance"]
        completed = [step for step in steps if step["state"] == "COMPLETED"]
        if not isinstance(dependencies, list) or len(dependencies) != len(completed):
            raise ValueError("Dependency records must exactly match completed progress.")
        if provenance.get("dependency_provenance") != dependencies or evidence.get("dependency_provenance") != dependencies:
            raise ValueError("Dependency provenance copies disagree.")
        configs = dependency_configurations(adapter.contract, config)
        blocked = False
        for index, (step, dependency) in enumerate(zip(completed, dependencies)):
            if not isinstance(dependency, dict):
                raise ValueError("Malformed dependency provenance.")
            owner = ADAPTERS[step["capability_contract"]]
            expected_record = {
                "dependency_order": index + 1, "capability_name": owner.name,
                "capability_contract": owner.contract, "capability_rule_version": owner.rule_version,
                "authoritative_result_id": step["authoritative_result_id"],
                "result_identity": step["authoritative_result_id"],
                "source_snapshot_id": source_slot["source_snapshot_id"], "symbol": envelope["symbol"],
                "timeframe": envelope["timeframe"], "requested_evaluation_timestamp": source_slot["requested_evaluation_timestamp"],
                "effective_causal_cutoff": source_slot["effective_causal_cutoff"],
                "configuration_fingerprint": _configuration_fingerprint(configs[index]),
                "controlled_invocation": True, "provenance_validation": "validated_controlled_dependency",
            }
            if any(dependency.get(key) != value for key, value in expected_record.items()):
                raise ValueError("Dependency source, contract, identity or configuration mismatch.")
            if dependency.get("controlled_invocation") is not True or dependency.get("factual_availability") not in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE"}:
                raise ValueError("Invalid completed dependency provenance.")
            if dependency["factual_availability"] == "UNAVAILABLE" and not (adapter.name == "premium_discount_intelligence" and index == 1):
                blocked = True
                if any(state != "NOT_STARTED" for state in states[index + 1:]):
                    raise ValueError("Execution continued after unavailable dependency.")
        valid_terminal = terminal in {"CLASSIFICATION_FAILED", "COMPLETED"}
        result, result_id = envelope["authoritative_result"], envelope["authoritative_result_id"]
        if valid_terminal:
            if not isinstance(result, dict) or not isinstance(result_id, str) or not result_id:
                raise ValueError("Validated terminal result requires payload and identity.")
        elif result is not None or result_id is not None:
            raise ValueError("Unvalidated terminal cannot expose a result.")
        availability = envelope["factual_availability"]
        envelope_id = envelope["factual_envelope_id"]
        if availability in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}:
            if terminal != "COMPLETED" or not isinstance(envelope_id, str) or not envelope_id:
                raise ValueError("Successful availability requires completed analysis and envelope identity.")
        elif envelope_id is not None:
            raise ValueError("Degraded envelopes cannot have an envelope identity.")
        usable = source_slot["source_availability"] == "AVAILABLE" and source_slot["completion_state"] != "UNKNOWN"
        if diagnostics.get("source_usable") is not usable or diagnostics.get("adapter_selected") is not True:
            raise ValueError("Source usability diagnostics mismatch.")
        if not usable:
            expected_state = source_slot["source_availability"] if source_slot["source_availability"] != "AVAILABLE" else "UNAVAILABLE"
            expected_reason = "source_" + expected_state.lower() if source_slot["source_availability"] != "AVAILABLE" else "unknown_source_completion"
            if any(state != "NOT_STARTED" for state in states) or availability != expected_state or envelope["availability_reason"] != expected_reason:
                raise ValueError("Rejected source cannot claim execution or a different state.")
        elif any(state in FAILURE_STATES for state in states):
            if availability != "INVALID":
                raise ValueError("Execution failure requires INVALID availability.")
        elif blocked:
            if availability != "UNAVAILABLE":
                raise ValueError("Unavailable dependency must remain unavailable.")
        elif terminal != "COMPLETED" or availability not in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE"}:
            raise ValueError("Usable source lacks a justified execution outcome.")
        if terminal == "COMPLETED" and adapter.name == "premium_discount_intelligence" and any(row["factual_availability"] == "UNAVAILABLE" for row in dependencies) and availability != "UNAVAILABLE":
            raise ValueError("Premium dependency unavailability must be preserved.")

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