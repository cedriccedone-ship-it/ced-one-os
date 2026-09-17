"""Controlled causal envelopes for one Trading factual capability result."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
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

RULE_VERSION = "causal_factual_intelligence_envelope_v2"
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


def _configuration_fingerprint(configuration: dict[str, Any]) -> str:
    return _hash_id("configuration_", configuration)


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
    normalize_configuration: Callable[[dict[str, Any]], dict[str, Any]]
    invoke: Callable[..., Any]
    classify: Callable[[dict[str, Any], list[dict[str, Any]]], tuple[str, str]]


class DependencyStateError(ValueError):
    def __init__(self, availability: str, message: str):
        super().__init__(message)
        self.availability = availability


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


EXECUTION_STATES = {"NOT_STARTED", "PREPARATION_FAILED", "INVOCATION_FAILED", "RESULT_VALIDATION_FAILED", "CLASSIFICATION_FAILED", "PROVENANCE_VALIDATION_FAILED", "COMPLETED"}
VALIDATED_STATES = {"CLASSIFICATION_FAILED", "PROVENANCE_VALIDATION_FAILED", "COMPLETED"}
FAILURE_STATES = EXECUTION_STATES - {"NOT_STARTED", "COMPLETED"}


def execution_diagnostics(progress: dict[str, Any]) -> dict[str, Any]:
    dependencies = progress["dependencies"]
    states = [row["state"] for row in dependencies]
    invoked = lambda state: state not in {"NOT_STARTED", "PREPARATION_FAILED"}
    return {
        "controlled_invocation_performed": any(invoked(state) for state in [*states, progress["terminal"]]),
        "dependency_count": len(dependencies),
        "dependency_invocation_count": sum(invoked(state) for state in states),
        "dependency_failure_count": sum(state in FAILURE_STATES for state in states),
        "result_validation_outcome": progress["terminal"] in {"CLASSIFICATION_FAILED", "COMPLETED"},
        "classification_outcome": progress["terminal"] == "COMPLETED",
        "provenance_validation_outcome": "PROVENANCE_VALIDATION_FAILED" not in states,
    }


class _ExecutionProgress:
    """One envelope's bounded progress; no replay and no global execution state."""
    def __init__(self, adapter):
        self.adapter = adapter
        self.value = {"terminal": "NOT_STARTED", "dependencies": [
            {"capability_contract": contract, "state": "NOT_STARTED", "authoritative_result_id": None}
            for contract in adapter.dependencies]}
        self.records = []
        self.results = {}
        self.identities = {}
        self.classifications = {}

    def set_state(self, contract, state):
        if contract == self.adapter.contract:
            self.value["terminal"] = state
        else:
            next(row for row in self.value["dependencies"] if row["capability_contract"] == contract)["state"] = state

    def run(self, request, configuration, contract, analyzer, required, forbidden=(), prepare=None):
        stage = "PREPARATION_FAILED"
        try:
            source = _source_dict(request.causal_source)
            payload = prepare() if prepare else _payload(source, configuration)
            stage = "INVOCATION_FAILED"
            result = analyzer.analyze(payload)
            stage = "RESULT_VALIDATION_FAILED"
            result_dict = _result_dict(result)
            _valid_result(result_dict, required, forbidden)
            result_id = _hash_id("authoritative_result_", result_dict)
            self.results[contract] = result_dict
            self.identities[contract] = result_id
            if contract != self.adapter.contract:
                next(row for row in self.value["dependencies"] if row["capability_contract"] == contract)["authoritative_result_id"] = result_id
            stage = "CLASSIFICATION_FAILED"
            adapter = ADAPTERS[contract]
            classification = adapter.classify(result_dict, self.records if contract == self.adapter.contract else [])
            if classification[0] not in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE"}:
                raise ValueError("Unsupported completed classification.")
            self.classifications[contract] = classification
            if contract != self.adapter.contract:
                stage = "PROVENANCE_VALIDATION_FAILED"
                order = self.adapter.dependencies.index(contract) + 1
                record = _dependency_result(result, adapter, source, configuration, order,
                                            classification=classification, result_id=result_id)
                _validate_dependency_record(record, adapter, source, configuration, order)
                self.records.append(record)
            self.set_state(contract, "COMPLETED")
            return result
        except (TypeError, ValueError, KeyError):
            self.set_state(contract, stage)
            raise


def _direct_invoke(analyzer: Any, required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> Callable:
    def invoke(request, configuration, progress, contract):
        return progress.run(request, configuration, contract, analyzer, required, forbidden)
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


def _dependency_result(
    result: Any,
    adapter: CapabilityAdapter,
    source: dict[str, Any],
    configuration: dict[str, Any],
    dependency_order: int,
    *, classification=None, result_id=None,
) -> dict[str, Any]:
    result_dict = _result_dict(result)
    factual_availability, _ = classification if classification is not None else adapter.classify(result_dict, [])
    return {
        "dependency_order": dependency_order,
        "capability_name": adapter.name,
        "capability_contract": adapter.contract,
        "capability_rule_version": adapter.rule_version,
        "factual_availability": factual_availability,
        "result_identity": result_id or _hash_id("authoritative_result_", result_dict),
        "authoritative_result_id": result_id or _hash_id("authoritative_result_", result_dict),
        "source_snapshot_id": source["source_snapshot_id"],
        "symbol": source["symbol"],
        "timeframe": source["timeframe"],
        "requested_evaluation_timestamp": source["requested_evaluation_timestamp"],
        "effective_causal_cutoff": source["effective_causal_cutoff"],
        "configuration_fingerprint": _configuration_fingerprint(configuration),
        "controlled_invocation": True,
        "provenance_validation": "validated_controlled_dependency",
    }


def _validate_dependency_record(
    record: dict[str, Any],
    adapter: CapabilityAdapter,
    source: dict[str, Any],
    configuration: dict[str, Any],
    dependency_order: int,
) -> None:
    expected = {
        "dependency_order": dependency_order,
        "capability_name": adapter.name,
        "capability_contract": adapter.contract,
        "capability_rule_version": adapter.rule_version,
        "source_snapshot_id": source["source_snapshot_id"],
        "symbol": source["symbol"],
        "timeframe": source["timeframe"],
        "requested_evaluation_timestamp": source["requested_evaluation_timestamp"],
        "effective_causal_cutoff": source["effective_causal_cutoff"],
        "configuration_fingerprint": _configuration_fingerprint(configuration),
        "controlled_invocation": True,
        "provenance_validation": "validated_controlled_dependency",
    }
    required = set(expected) | {"factual_availability", "authoritative_result_id"}
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"Dependency provenance missing fields: {missing}.")
    for field_name, expected_value in expected.items():
        if record[field_name] != expected_value:
            raise ValueError(f"Dependency provenance mismatch: {field_name}.")
    if record["factual_availability"] not in AVAILABILITY_STATES:
        raise ValueError("Dependency provenance has unknown factual availability.")
    if not isinstance(record["authoritative_result_id"], str) or not record["authoritative_result_id"]:
        raise ValueError("Dependency provenance requires authoritative_result_id.")


def _dependent_invoke(dependency_adapter, analyzer, required, classify, forbidden=(), dependency_configuration=None):
    def invoke(request, configuration, progress, contract):
        dependency_contract = dependency_adapter.contract
        try:
            dependency_config = configuration if dependency_configuration is None else dependency_configuration(configuration)
        except (TypeError, ValueError, KeyError):
            progress.set_state(dependency_contract, "PREPARATION_FAILED")
            raise
        dependency_adapter.invoke(request, dependency_config, progress, dependency_contract)
        availability = progress.classifications[dependency_contract][0]
        if availability == "UNAVAILABLE":
            raise DependencyStateError(availability, f"Dependency {dependency_contract} is unavailable.")
        return progress.run(request, configuration, contract, analyzer, required, forbidden)
    return invoke


def _premium_invoke(request, configuration, progress, contract):
    structure_contract = "trading.market_structure.v1"
    range_contract = "trading.structural_dealing_range_intelligence.v1"
    ADAPTERS[structure_contract].invoke(request, {}, progress, structure_contract)
    if progress.classifications[structure_contract][0] == "UNAVAILABLE":
        raise DependencyStateError("UNAVAILABLE", "Market structure dependency is unavailable.")
    structural = progress.run(request, configuration, range_contract, _structural_range(),
        ("symbol", "timeframe", "structural_ranges", "current_range", "evidence", "metadata"),
        ("buy", "sell", "entry", "exit", "recommendation", "execution_command"))
    def prepare():
        source = _source_dict(request.causal_source)
        timestamp = progress.results[range_contract]["timestamp"]
        close = next((float(item["close"]) for item in reversed(source["approved_candle_history"]) if item.get("timestamp") == timestamp), None)
        if close is None:
            raise ValueError("Premium/discount source pairing could not find the Slice #11 result candle close.")
        return {"source_result": structural, "observation": {"timestamp": timestamp, "close": close}}
    return progress.run(request, configuration, contract, _premium_discount(),
        ("symbol", "timeframe", "timestamp", "observation", "diagnostics", "evidence", "metadata"), prepare=prepare)


def dependency_configurations(contract, effective_configuration):
    """The invocation configurations also used to validate dependency references."""
    config = _invocation_configuration(contract, effective_configuration)
    if contract == "trading.liquidity_events.v1":
        return [{"lookback_candles": config["lookback_candles"], **config["liquidity_config"]}]
    if contract == "trading.order_block_intelligence.v1":
        return [{"lookback_candles": config["lookback_candles"], **config["displacement_config"]}]
    if contract == "trading.structural_dealing_range_intelligence.v1":
        return [{}]
    if contract == "trading.premium_discount_intelligence.v1":
        return [{}, config]
    return []


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


def _empty_configuration(_: dict[str, Any]) -> dict[str, Any]:
    return {}


def _candle_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.candle_intelligence import CandleIntelligenceConfig
    return CandleIntelligenceConfig.from_payload(configuration).as_dict()


def _volatility_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.volatility_range import VolatilityRangeConfig
    return VolatilityRangeConfig.from_payload(configuration).as_dict()


def _liquidity_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceConfig
    return LiquidityIntelligenceConfig.from_payload(configuration).as_dict()


def _fvg_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.fvg_imbalance_intelligence import FVGIntelligenceConfig
    return FVGIntelligenceConfig.from_payload(configuration).as_dict()


def _displacement_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.displacement_intelligence import DisplacementIntelligenceConfig
    return DisplacementIntelligenceConfig.from_payload(configuration).as_dict()


def _liquidity_events_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.liquidity_events import LiquidityEventsConfig
    return LiquidityEventsConfig.from_payload(configuration).as_dict()


def _order_block_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.order_block_intelligence import OrderBlockIntelligenceConfig
    return OrderBlockIntelligenceConfig.from_payload(configuration).as_dict()


def _invocation_configuration(contract: str, effective_configuration: dict[str, Any]) -> dict[str, Any]:
    configuration = _canonical(effective_configuration)
    if contract == "trading.liquidity_events.v1":
        configuration["liquidity_config"].pop("lookback_candles", None)
    if contract == "trading.order_block_intelligence.v1":
        configuration["displacement_config"].pop("lookback_candles", None)
    return configuration


def _structural_range_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    from ced_one.business_divisions.trading.structural_dealing_range_intelligence import StructuralDealingRangeConfig
    return StructuralDealingRangeConfig.from_payload(configuration).as_dict()


def _build_adapters() -> dict[str, CapabilityAdapter]:
    forbidden = ("buy", "sell", "entry", "exit", "recommendation", "execution_command")
    structure = CapabilityAdapter("market_structure", "trading.market_structure.v1", "market_structure_v2", (), _empty_configuration, _direct_invoke(_market_structure(), ("symbol", "timeframe", "structure_state", "evidence", "metadata"), forbidden), _classify_structure)
    displacement = CapabilityAdapter("displacement_intelligence", "trading.displacement_intelligence.v1", "displacement_intelligence_v1", (), _displacement_configuration, _direct_invoke(_displacement(), ("symbol", "timeframe", "displacement_events", "displacement_sequences", "evidence", "metadata"), forbidden), _classify_displacement)
    liquidity = CapabilityAdapter("liquidity_intelligence", "trading.liquidity_intelligence.v1", "liquidity_intelligence_v1", (), _liquidity_configuration, _direct_invoke(_liquidity(), ("symbol", "timeframe", "liquidity_levels", "evidence", "metadata"), forbidden), _classify_liquidity)
    return {
        structure.contract: structure,
        "trading.candle_intelligence.v1": CapabilityAdapter("candle_intelligence", "trading.candle_intelligence.v1", "candle_intelligence_v1", (), _candle_configuration, _direct_invoke(_candle(), ("symbol", "timeframe", "timestamp", "candle_direction", "evidence", "metadata"), forbidden), _classify_candle),
        "trading.volatility_range.v1": CapabilityAdapter("volatility_range", "trading.volatility_range.v1", "volatility_range_v1", (), _volatility_configuration, _direct_invoke(_volatility(), ("symbol", "timeframe", "timestamp", "volatility_state", "range_state", "evidence", "metadata"), forbidden), _classify_volatility),
        liquidity.contract: liquidity,
        "trading.fvg_imbalance_intelligence.v1": CapabilityAdapter("fvg_imbalance_intelligence", "trading.fvg_imbalance_intelligence.v1", "fvg_imbalance_intelligence_v1", (), _fvg_configuration, _direct_invoke(_fvg(), ("symbol", "timeframe", "fair_value_gaps", "evidence", "metadata"), forbidden), _classify_fvg),
        displacement.contract: displacement,
        "trading.liquidity_events.v1": CapabilityAdapter("liquidity_events", "trading.liquidity_events.v1", "liquidity_events_v1", (liquidity.contract,), _liquidity_events_configuration, _dependent_invoke(liquidity, _liquidity_events(), ("symbol", "timeframe", "liquidity_events", "level_event_states", "evidence", "metadata"), _classify_events, forbidden, lambda config: {"lookback_candles": config["lookback_candles"], **config["liquidity_config"]}), _classify_events),
        "trading.order_block_intelligence.v1": CapabilityAdapter("order_block_intelligence", "trading.order_block_intelligence.v1", "order_block_intelligence_v1", (displacement.contract,), _order_block_configuration, _dependent_invoke(displacement, _order_blocks(), ("symbol", "timeframe", "order_blocks", "evidence", "metadata"), _classify_blocks, forbidden, lambda config: {"lookback_candles": config["lookback_candles"], **config["displacement_config"]}), _classify_blocks),
        "trading.structural_dealing_range_intelligence.v1": CapabilityAdapter("structural_dealing_range_intelligence", "trading.structural_dealing_range_intelligence.v1", "structural_dealing_range_intelligence_v1", (structure.contract,), _structural_range_configuration, _dependent_invoke(structure, _structural_range(), ("symbol", "timeframe", "structural_ranges", "current_range", "evidence", "metadata"), _classify_range, forbidden, _empty_configuration), _classify_range),
        "trading.premium_discount_intelligence.v1": CapabilityAdapter("premium_discount_intelligence", "trading.premium_discount_intelligence.v1", "premium_discount_intelligence_v1", (structure.contract, "trading.structural_dealing_range_intelligence.v1"), _empty_configuration, _premium_invoke, _classify_premium),
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
        effective_configuration = adapter.normalize_configuration(configuration)
        invocation_configuration = _invocation_configuration(adapter.contract, effective_configuration)
        configuration_fingerprint = _configuration_fingerprint(effective_configuration)
        base = {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "requested_evaluation_timestamp": requested_text,
            "effective_causal_cutoff": source["effective_causal_cutoff"],
            "source_snapshot_id": source["source_snapshot_id"],
            "source_completion_state": source["completion_state"],
            "context_id": request.context_id,
            "capability": {"name": adapter.name, "contract": adapter.contract, "rule_version": adapter.rule_version, "configuration": effective_configuration},
        }
        source_state = source["source_availability"]
        source_completion = source["completion_state"]
        progress = _ExecutionProgress(adapter)
        usable = source_state == "AVAILABLE" and source_completion != "UNKNOWN"
        error = None
        if source_state in {"INVALID", "UNAVAILABLE", "NOT_EVALUATED"}:
            availability, reason = source_state, f"source_{source_state.lower()}"
        elif source_completion == "UNKNOWN":
            availability, reason = "UNAVAILABLE", "unknown_source_completion"
        else:
            try:
                adapter.invoke(request, invocation_configuration, progress, adapter.contract)
                availability, reason = progress.classifications[adapter.contract]
            except DependencyStateError as exc:
                availability, reason, error = exc.availability, "dependency_" + exc.availability.lower(), exc
            except (TypeError, ValueError, KeyError) as exc:
                availability, reason, error = "INVALID", "controlled_invocation_failed", exc
        execution = deepcopy(progress.value)
        dependencies = deepcopy(progress.records)
        result_dict = progress.results.get(adapter.contract)
        authoritative_id = progress.identities.get(adapter.contract)
        diagnostics = {**execution_diagnostics(execution), "adapter_selected": True, "source_usable": usable}
        provenance = {
            "source_contract": SOURCE_CONTRACT, "source_snapshot_id": source["source_snapshot_id"],
            "configuration_fingerprint": configuration_fingerprint,
            "controlled_invocation": diagnostics["controlled_invocation_performed"],
            "dependency_contracts": list(adapter.dependencies), "identity_scope": IDENTITY_SCOPE,
            "execution_progress": execution, "dependency_provenance": deepcopy(dependencies),
        }
        if error is not None:
            provenance["error_type"] = type(error).__name__
        evidence = {
            "source_snapshot_id": source["source_snapshot_id"], "source_completion_state": source_completion,
            "capability": base["capability"], "configuration_fingerprint": configuration_fingerprint,
            "dependency_provenance": deepcopy(dependencies), "classification_reason": reason,
            "availability_reason": reason, "factual_availability": availability,
            "provenance_validation": "controlled_source_rejected" if not usable else "controlled_invocation",
        }
        if error is not None:
            evidence["error"] = str(error)
        envelope_id = _hash_id("factual_envelope_", [RULE_VERSION, adapter.name, adapter.contract, adapter.rule_version,
            configuration, request.symbol, request.timeframe, requested_text, source["effective_causal_cutoff"],
            source["source_snapshot_id"], request.context_id, dependencies, availability, result_dict, execution]
        ) if availability in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None
        return CausalFactualIntelligenceEnvelopeResult(
            factual_envelope_id=envelope_id, factual_availability=availability,
            authoritative_result=result_dict, authoritative_result_id=authoritative_id,
            dependency_provenance=dependencies, availability_reason=reason, provenance=provenance,
            diagnostics=diagnostics, evidence=evidence,
            metadata={"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": IDENTITY_SCOPE,
                      "observation_only": True, "advisory_output": False, "strategy_output": False,
                      "execution_output": False, "authority_scope": "read_only"}, **base)


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