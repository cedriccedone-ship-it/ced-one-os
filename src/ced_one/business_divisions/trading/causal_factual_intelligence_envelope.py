"""Controlled causal envelopes for one Trading factual capability result."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
from typing import Any, Callable

from ced_one.business_divisions.trading.causal_snapshot_availability import (
    COMPLETION_STATES,
    CONTRACT as SOURCE_CONTRACT,
    SOURCE_AVAILABILITY_STATES,
)

RULE_VERSION = "causal_factual_intelligence_envelope_v1"
CONTRACT = "trading.causal_factual_intelligence_envelope.v1"
IDENTITY_SCOPE = "snapshot_deterministic"
AVAILABILITY_STATES = {
    "AVAILABLE_PRESENT",
    "AVAILABLE_ABSENT",
    "UNAVAILABLE",
    "INVALID",
    "NOT_EVALUATED",
}
TARGET_CONTRACTS = {
    "trading.market_structure.v1",
    "trading.candle_intelligence.v1",
    "trading.volatility_range.v1",
    "trading.liquidity_intelligence.v1",
    "trading.fvg_imbalance_intelligence.v1",
    "trading.displacement_intelligence.v1",
    "trading.liquidity_events.v1",
    "trading.order_block_intelligence.v1",
    "trading.structural_dealing_range_intelligence.v1",
    "trading.premium_discount_intelligence.v1",
}


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed


def _canonical(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _canonical(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite values cannot be canonicalized.")
        return value
    return value


def _hash_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class CausalFactualEnvelopeInput:
    symbol: str
    timeframe: str
    requested_evaluation_timestamp: str
    causal_source: Any
    capability: dict[str, Any]
    context_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CausalFactualEnvelopeInput":
        capability = payload.get("capability")
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            requested_evaluation_timestamp=str(payload.get("requested_evaluation_timestamp", "")),
            causal_source=payload.get("causal_source"),
            capability=dict(capability) if isinstance(capability, dict) else {},
            context_id=payload.get("context_id"),
        )


@dataclass
class CausalFactualIntelligenceEnvelopeResult:
    factual_envelope_id: str | None
    factual_availability: str
    symbol: str
    timeframe: str
    requested_evaluation_timestamp: str
    effective_causal_cutoff: str | None
    source_snapshot_id: str | None
    source_completion_state: str | None
    context_id: str | None
    capability: dict[str, Any]
    authoritative_result: dict[str, Any] | None
    authoritative_result_id: str | None
    dependency_provenance: list[dict[str, Any]] = field(default_factory=list)
    availability_reason: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factual_envelope_id": self.factual_envelope_id,
            "factual_availability": self.factual_availability,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "effective_causal_cutoff": self.effective_causal_cutoff,
            "source_snapshot_id": self.source_snapshot_id,
            "source_completion_state": self.source_completion_state,
            "context_id": self.context_id,
            "capability": dict(self.capability),
            "authoritative_result": self.authoritative_result,
            "authoritative_result_id": self.authoritative_result_id,
            "dependency_provenance": [dict(item) for item in self.dependency_provenance],
            "availability_reason": self.availability_reason,
            "provenance": dict(self.provenance),
            "diagnostics": dict(self.diagnostics),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityAdapter:
    name: str
    contract: str
    rule_version: str
    dependencies: tuple[str, ...]
    invoke: Callable[[CausalFactualEnvelopeInput, dict[str, Any]], tuple[Any, list[dict[str, Any]]]]
    classify: Callable[[dict[str, Any], list[dict[str, Any]]], tuple[str, str]]


def _source_dict(source: Any) -> dict[str, Any]:
    if hasattr(source, "to_dict"):
        source = source.to_dict()
    if not isinstance(source, dict):
        raise ValueError("causal_source must be a Slice #13 result or dictionary.")
    required = [
        "symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff",
        "source_snapshot_id", "source_availability", "availability_reason", "completion_state",
        "approved_candle_history", "diagnostics", "evidence", "metadata",
    ]
    missing = [name for name in required if name not in source]
    if missing:
        raise ValueError(f"Malformed causal source: missing fields {missing}.")
    if source["source_availability"] not in SOURCE_AVAILABILITY_STATES:
        raise ValueError("Malformed causal source: unknown source availability.")
    if source["completion_state"] not in COMPLETION_STATES:
        raise ValueError("Malformed causal source: unknown completion state.")
    if not isinstance(source["approved_candle_history"], list):
        raise ValueError("Malformed causal source: approved_candle_history must be a list.")
    if source["source_availability"] == "AVAILABLE" and not source["source_snapshot_id"]:
        raise ValueError("Malformed causal source: AVAILABLE source requires source_snapshot_id.")
    if source["source_availability"] == "AVAILABLE" and source["effective_causal_cutoff"] is None:
        raise ValueError("Malformed causal source: AVAILABLE source requires effective_causal_cutoff.")
    _parse_timestamp(source["requested_evaluation_timestamp"])
    if source["effective_causal_cutoff"] is not None:
        _parse_timestamp(source["effective_causal_cutoff"])
    return source


def _payload(source: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": source["symbol"],
        "timeframe": source["timeframe"],
        "evaluation_time": source["requested_evaluation_timestamp"],
        "candle_history": [dict(item) for item in source["approved_candle_history"]],
        "config": dict(configuration),
    }


def _result_dict(result: Any) -> dict[str, Any]:
    if not hasattr(result, "to_dict"):
        raise ValueError("Authoritative analyzer did not return a result with to_dict().")
    value = result.to_dict()
    if not isinstance(value, dict):
        raise ValueError("Authoritative analyzer returned a non-dictionary result.")
    return value


def _valid_result(result: dict[str, Any], required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> None:
    missing = [name for name in required if name not in result]
    if missing:
        raise ValueError(f"Authoritative result missing fields: {missing}.")
    text = str(result).lower()
    if any(term in text for term in forbidden):
        raise ValueError("Authoritative result contains forbidden advisory semantics.")


def _direct_invoke(analyzer: Any, required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> Callable[[CausalFactualEnvelopeInput, dict[str, Any]], tuple[Any, list[dict[str, Any]]]]:
    def invoke(request: CausalFactualEnvelopeInput, configuration: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
        result = analyzer.analyze(_payload(_source_dict(request.causal_source), configuration))
        result_dict = _result_dict(result)
        _valid_result(result_dict, required, forbidden)
        return result, []
    return invoke


def _classify_structure(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    state = result.get("structure_state")
    if state in {"bullish_structure", "bearish_structure"}:
        return "AVAILABLE_PRESENT", "explicit_resolved_structure"
    return "UNAVAILABLE", "unresolved_or_insufficient_structure"


def _classify_candle(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    return "AVAILABLE_PRESENT", "valid_current_candle_observation"


def _classify_volatility(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    evidence = result.get("evidence", {})
    states = str(evidence).lower()
    if "insufficient_history" in states or "insufficient_context" in states:
        return "UNAVAILABLE", "capability_insufficient_history_or_context"
    return "AVAILABLE_PRESENT", "valid_volatility_range_observation"


def _classify_liquidity(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    evidence = result.get("evidence", {})
    if evidence.get("reason") == "insufficient_confirmed_pivots":
        return "UNAVAILABLE", "insufficient_confirmed_pivots"
    return ("AVAILABLE_PRESENT", "liquidity_levels_present") if result.get("liquidity_levels") else ("AVAILABLE_ABSENT", "no_liquidity_levels_after_valid_evaluation")


def _classify_fvg(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    if result.get("fair_value_gaps"):
        return "AVAILABLE_PRESENT", "fvg_rows_present"
    if int(result.get("scanned_candle_count", 0)) < 1:
        return "UNAVAILABLE", "insufficient_fvg_scan_history"
    return "AVAILABLE_ABSENT", "no_fvg_rows_after_valid_evaluation"


def _classify_displacement(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    evidence = result.get("evidence", {})
    if evidence.get("insufficient_history_count", 0) or evidence.get("insufficient_context_count", 0):
        if not result.get("displacement_events") and not result.get("displacement_sequences"):
            return "UNAVAILABLE", "insufficient_displacement_history_or_context"
    if result.get("displacement_events") or result.get("displacement_sequences"):
        return "AVAILABLE_PRESENT", "displacement_facts_present"
    return "AVAILABLE_ABSENT", "no_displacement_after_valid_evaluation"


def _classify_events(result: dict[str, Any], dependencies: list[dict[str, Any]]) -> tuple[str, str]:
    if any(item.get("factual_availability") == "UNAVAILABLE" for item in dependencies):
        return "UNAVAILABLE", "liquidity_dependency_unavailable"
    return ("AVAILABLE_PRESENT", "liquidity_events_present") if result.get("liquidity_events") else ("AVAILABLE_ABSENT", "no_liquidity_events_after_valid_evaluation")


def _classify_blocks(result: dict[str, Any], dependencies: list[dict[str, Any]]) -> tuple[str, str]:
    if any(item.get("factual_availability") == "UNAVAILABLE" for item in dependencies):
        return "UNAVAILABLE", "displacement_dependency_unavailable"
    if result.get("order_blocks"):
        return "AVAILABLE_PRESENT", "order_blocks_present"
    return "AVAILABLE_ABSENT", "no_order_blocks_after_valid_evaluation"


def _classify_range(result: dict[str, Any], _: list[dict[str, Any]]) -> tuple[str, str]:
    if result.get("current_range") is not None:
        return "AVAILABLE_PRESENT", "current_structural_range_present"
    if result.get("diagnostics", {}).get("source_pivot_count", 0) == 0:
        return "UNAVAILABLE", "insufficient_structural_pivot_source"
    return "AVAILABLE_ABSENT", "no_current_structural_range_after_valid_evaluation"


def _classify_premium(result: dict[str, Any], dependencies: list[dict[str, Any]]) -> tuple[str, str]:
    if any(item.get("factual_availability") == "UNAVAILABLE" for item in dependencies):
        return "UNAVAILABLE", "structural_range_dependency_unavailable"
    return ("AVAILABLE_PRESENT", "premium_discount_observation_present") if result.get("observation") is not None else ("AVAILABLE_ABSENT", "no_current_range_observation")


def _dependency_result(result: Any, contract: str, source: dict[str, Any]) -> dict[str, Any]:
    result_dict = _result_dict(result)
    return {
        "capability_contract": contract,
        "capability_rule_version": result_dict.get("evidence", {}).get("structural_range_rule_version") or result_dict.get("evidence", {}).get("liquidity_event_rule_version") or result_dict.get("metadata", {}).get("structure_rule_version") or result_dict.get("metadata", {}).get("identity_scope"),
        "result_identity": _hash_id("authoritative_result_", result_dict),
        "source_snapshot_id": source["source_snapshot_id"],
        "requested_evaluation_timestamp": source["requested_evaluation_timestamp"],
        "effective_causal_cutoff": source["effective_causal_cutoff"],
        "controlled_invocation": True,
    }


def _dependent_invoke(dependency_contract: str, dependency_invoke: Callable[[CausalFactualEnvelopeInput, dict[str, Any]], Any], analyzer: Any, required: tuple[str, ...], classify: Callable[[dict[str, Any], list[dict[str, Any]]], tuple[str, str]], forbidden: tuple[str, ...] = ()) -> Callable[[CausalFactualEnvelopeInput, dict[str, Any]], tuple[Any, list[dict[str, Any]]]]:
    def invoke(request: CausalFactualEnvelopeInput, configuration: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
        source = _source_dict(request.causal_source)
        dependency_result, ignored = dependency_invoke(request, configuration)
        dependency_record = _dependency_result(dependency_result, dependency_contract, source)
        result = analyzer.analyze(_payload(source, configuration))
        result_dict = _result_dict(result)
        _valid_result(result_dict, required, forbidden)
        return result, [dependency_record]
    return invoke


def _premium_invoke(request: CausalFactualEnvelopeInput, configuration: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    source = _source_dict(request.causal_source)
    market_structure = _market_structure().analyze(_payload(source, {}))
    structural = _structural_range().analyze(_payload(source, configuration))
    structural_dict = _result_dict(structural)
    observation_timestamp = structural_dict["timestamp"]
    approved = source["approved_candle_history"]
    close = next((float(item["close"]) for item in reversed(approved) if item.get("timestamp") == observation_timestamp), None)
    if close is None:
        raise ValueError("Premium/discount source pairing could not find the Slice #11 result candle close.")
    premium_payload = {
        "source_result": structural,
        "observation": {"timestamp": observation_timestamp, "close": close},
    }
    result = _premium_discount().analyze(premium_payload)
    result_dict = _result_dict(result)
    _valid_result(result_dict, ("symbol", "timeframe", "timestamp", "observation", "diagnostics", "evidence", "metadata"))
    return result, [
        _dependency_result(market_structure, "trading.market_structure.v1", source),
        _dependency_result(structural, "trading.structural_dealing_range_intelligence.v1", source),
    ]


def _market_structure():
    from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer
    return MarketStructureAnalyzer()


def _candle():
    from ced_one.business_divisions.trading.candle_intelligence import CandleIntelligenceAnalyzer
    return CandleIntelligenceAnalyzer()


def _volatility():
    from ced_one.business_divisions.trading.volatility_range import VolatilityRangeAnalyzer
    return VolatilityRangeAnalyzer()


def _liquidity():
    from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceAnalyzer
    return LiquidityIntelligenceAnalyzer()


def _fvg():
    from ced_one.business_divisions.trading.fvg_imbalance_intelligence import FVGImbalanceIntelligenceAnalyzer
    return FVGImbalanceIntelligenceAnalyzer()


def _displacement():
    from ced_one.business_divisions.trading.displacement_intelligence import DisplacementIntelligenceAnalyzer
    return DisplacementIntelligenceAnalyzer()


def _liquidity_events():
    from ced_one.business_divisions.trading.liquidity_events import LiquidityEventsAnalyzer
    return LiquidityEventsAnalyzer()


def _order_blocks():
    from ced_one.business_divisions.trading.order_block_intelligence import OrderBlockIntelligenceAnalyzer
    return OrderBlockIntelligenceAnalyzer()


def _structural_range():
    from ced_one.business_divisions.trading.structural_dealing_range_intelligence import StructuralDealingRangeAnalyzer
    return StructuralDealingRangeAnalyzer()


def _premium_discount():
    from ced_one.business_divisions.trading.premium_discount_intelligence import PremiumDiscountAnalyzer
    return PremiumDiscountAnalyzer()


def _build_adapters() -> dict[str, CapabilityAdapter]:
    forbidden = ("buy", "sell", "entry", "exit", "recommendation", "execution_command")
    structure = CapabilityAdapter("market_structure", "trading.market_structure.v1", "market_structure_v1", (), _direct_invoke(_market_structure(), ("symbol", "timeframe", "structure_state", "evidence", "metadata"), forbidden), _classify_structure)
    displacement = CapabilityAdapter("displacement_intelligence", "trading.displacement_intelligence.v1", "displacement_intelligence_v1", (), _direct_invoke(_displacement(), ("symbol", "timeframe", "displacement_events", "displacement_sequences", "evidence", "metadata"), forbidden), _classify_displacement)
    liquidity = CapabilityAdapter("liquidity_intelligence", "trading.liquidity_intelligence.v1", "liquidity_intelligence_v1", (), _direct_invoke(_liquidity(), ("symbol", "timeframe", "liquidity_levels", "evidence", "metadata"), forbidden), _classify_liquidity)
    return {
        structure.contract: structure,
        "trading.candle_intelligence.v1": CapabilityAdapter("candle_intelligence", "trading.candle_intelligence.v1", "candle_intelligence_v1", (), _direct_invoke(_candle(), ("symbol", "timeframe", "timestamp", "candle_direction", "evidence", "metadata"), forbidden), _classify_candle),
        "trading.volatility_range.v1": CapabilityAdapter("volatility_range", "trading.volatility_range.v1", "volatility_range_v1", (), _direct_invoke(_volatility(), ("symbol", "timeframe", "timestamp", "volatility_state", "range_state", "evidence", "metadata"), forbidden), _classify_volatility),
        liquidity.contract: liquidity,
        "trading.fvg_imbalance_intelligence.v1": CapabilityAdapter("fvg_imbalance_intelligence", "trading.fvg_imbalance_intelligence.v1", "fvg_imbalance_intelligence_v1", (), _direct_invoke(_fvg(), ("symbol", "timeframe", "fair_value_gaps", "evidence", "metadata"), forbidden), _classify_fvg),
        displacement.contract: displacement,
        "trading.liquidity_events.v1": CapabilityAdapter("liquidity_events", "trading.liquidity_events.v1", "liquidity_events_v1", (liquidity.contract,), _dependent_invoke(liquidity.contract, liquidity.invoke, _liquidity_events(), ("symbol", "timeframe", "liquidity_events", "level_event_states", "evidence", "metadata"), _classify_events, forbidden), _classify_events),
        "trading.order_block_intelligence.v1": CapabilityAdapter("order_block_intelligence", "trading.order_block_intelligence.v1", "order_block_intelligence_v1", (displacement.contract,), _dependent_invoke(displacement.contract, displacement.invoke, _order_blocks(), ("symbol", "timeframe", "order_blocks", "evidence", "metadata"), _classify_blocks, forbidden), _classify_blocks),
        "trading.structural_dealing_range_intelligence.v1": CapabilityAdapter("structural_dealing_range_intelligence", "trading.structural_dealing_range_intelligence.v1", "structural_dealing_range_intelligence_v1", (structure.contract,), _dependent_invoke(structure.contract, structure.invoke, _structural_range(), ("symbol", "timeframe", "structural_ranges", "current_range", "evidence", "metadata"), _classify_range, forbidden), _classify_range),
        "trading.premium_discount_intelligence.v1": CapabilityAdapter("premium_discount_intelligence", "trading.premium_discount_intelligence.v1", "premium_discount_intelligence_v1", (structure.contract, "trading.structural_dealing_range_intelligence.v1"), _premium_invoke, _classify_premium),
    }


ADAPTERS = _build_adapters()


class CausalFactualIntelligenceEnvelopeAnalyzer:
    def analyze(self, payload: dict[str, Any]) -> CausalFactualIntelligenceEnvelopeResult:
        request = CausalFactualEnvelopeInput.from_payload(payload if isinstance(payload, dict) else {})
        if set(payload or {}) - {"symbol", "timeframe", "requested_evaluation_timestamp", "causal_source", "capability", "context_id"}:
            raise ValueError("Invalid envelope input: unsupported fields.")
        if request.symbol != "XAUUSD":
            raise ValueError("Unsupported symbol: only XAUUSD is accepted in this slice.")
        if request.timeframe not in {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}:
            raise ValueError("Unsupported timeframe.")
        requested = _parse_timestamp(request.requested_evaluation_timestamp)
        requested_text = requested.isoformat().replace("+00:00", "Z")
        source = _source_dict(request.causal_source)
        if str(source["symbol"]).upper() != request.symbol or str(source["timeframe"]).upper() != request.timeframe:
            raise ValueError("Causal source symbol or timeframe mismatch.")
        if _parse_timestamp(source["requested_evaluation_timestamp"]) != requested:
            raise ValueError("Causal source requested timestamp mismatch.")
        capability = request.capability
        contract = capability.get("contract")
        adapter = ADAPTERS.get(contract)
        if adapter is None or capability.get("name") != adapter.name or capability.get("rule_version") != adapter.rule_version:
            raise ValueError("Unsupported or mismatched allowlisted capability adapter.")
        configuration = capability.get("configuration") or {}
        if not isinstance(configuration, dict):
            raise ValueError("Capability configuration must be a dictionary.")
        base = {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "requested_evaluation_timestamp": requested_text,
            "effective_causal_cutoff": source["effective_causal_cutoff"],
            "source_snapshot_id": source["source_snapshot_id"],
            "source_completion_state": source["completion_state"],
            "context_id": request.context_id,
            "capability": {"name": adapter.name, "contract": adapter.contract, "rule_version": adapter.rule_version, "configuration": dict(configuration)},
        }
        source_state = source["source_availability"]
        source_completion = source["completion_state"]
        diagnostics = {"controlled_invocation_performed": False, "adapter_selected": True, "source_usable": False, "dependency_count": len(adapter.dependencies), "dependency_invocation_count": 0, "dependency_failure_count": 0, "result_validation_outcome": False, "provenance_validation_outcome": True, "classification_outcome": False}
        provenance = {"source_contract": SOURCE_CONTRACT, "source_snapshot_id": source["source_snapshot_id"], "controlled_invocation": False, "dependency_contracts": list(adapter.dependencies), "identity_scope": IDENTITY_SCOPE}
        if source_state in {"INVALID", "UNAVAILABLE", "NOT_EVALUATED"}:
            availability = "INVALID" if source_state == "INVALID" else source_state
            return self._failure(base, availability, f"source_{source_state.lower()}", diagnostics, provenance, source_completion)
        if source_completion == "UNKNOWN":
            return self._failure(base, "UNAVAILABLE", "unknown_source_completion", diagnostics, provenance, source_completion)
        diagnostics["source_usable"] = True
        try:
            result, dependencies = adapter.invoke(request, configuration)
            result_dict = _result_dict(result)
            availability, reason = adapter.classify(result_dict, dependencies)
            authoritative_id = _hash_id("authoritative_result_", result_dict)
            dependency_count = len(dependencies)
            diagnostics.update(controlled_invocation_performed=True, dependency_invocation_count=dependency_count, result_validation_outcome=True, classification_outcome=True)
            provenance.update(controlled_invocation=True, dependency_provenance=dependencies)
            envelope_id = _hash_id("factual_envelope_", [RULE_VERSION, adapter.name, adapter.contract, adapter.rule_version, configuration, request.symbol, request.timeframe, requested_text, source["effective_causal_cutoff"], source["source_snapshot_id"], request.context_id, dependencies, availability, result_dict]) if availability in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None
            return CausalFactualIntelligenceEnvelopeResult(
                factual_envelope_id=envelope_id, factual_availability=availability, authoritative_result=result_dict, authoritative_result_id=authoritative_id,
                dependency_provenance=dependencies, availability_reason=reason, provenance=provenance, diagnostics=diagnostics,
                evidence={"source_snapshot_id": source["source_snapshot_id"], "source_completion_state": source_completion, "capability": base["capability"], "dependency_provenance": dependencies, "classification_reason": reason, "factual_availability": availability, "provenance_validation": "controlled_invocation"},
                metadata={"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": IDENTITY_SCOPE, "observation_only": True, "advisory_output": False, "strategy_output": False, "execution_output": False, "authority_scope": "read_only"}, **{key: base[key] for key in ["symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff", "source_snapshot_id", "source_completion_state", "context_id", "capability"]}
            )
        except (TypeError, ValueError, KeyError) as exc:
            diagnostics["dependency_failure_count"] = len(adapter.dependencies)
            return self._failure(base, "INVALID", "controlled_invocation_failed", diagnostics, {**provenance, "error_type": type(exc).__name__}, source_completion, str(exc))

    @staticmethod
    def _failure(base: dict[str, Any], availability: str, reason: str, diagnostics: dict[str, Any], provenance: dict[str, Any], completion: str, error: str | None = None) -> CausalFactualIntelligenceEnvelopeResult:
        evidence = {"source_snapshot_id": base["source_snapshot_id"], "source_completion_state": completion, "capability": base["capability"], "availability_reason": reason, "factual_availability": availability, "provenance_validation": "controlled_source_rejected" if not provenance.get("controlled_invocation") else "controlled_invocation"}
        if error:
            evidence["error"] = error
        return CausalFactualIntelligenceEnvelopeResult(
            factual_envelope_id=None, factual_availability=availability, authoritative_result=None, authoritative_result_id=None,
            dependency_provenance=[], availability_reason=reason, provenance=provenance, diagnostics=diagnostics, evidence=evidence,
            metadata={"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": IDENTITY_SCOPE, "observation_only": True, "advisory_output": False, "strategy_output": False, "execution_output": False, "authority_scope": "read_only"},
            **{key: base[key] for key in ["symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff", "source_snapshot_id", "source_completion_state", "context_id", "capability"]}
        )


CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE = CausalFactualIntelligenceEnvelopeAnalyzer()

__all__ = [
    "ADAPTERS",
    "AVAILABILITY_STATES",
    "CONTRACT",
    "CausalFactualEnvelopeInput",
    "CausalFactualIntelligenceEnvelopeAnalyzer",
    "CausalFactualIntelligenceEnvelopeResult",
    "CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE",
    "RULE_VERSION",
]