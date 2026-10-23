"""Slice #20: attributed descriptive observations, never trading decisions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    _configuration_fingerprint, _hash_id, envelope_reference, validate_factual_envelope,
)
from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
    CAPABILITY_ORDER, TIMEFRAME_ORDER, validate_factual_context,
)
from ced_one.business_divisions.trading.factual_market_context_composition import validate_factual_composition
from ced_one.business_divisions.trading.causal_factual_event_chronology import (
    EVENT_FAMILIES, validate_factual_chronology,
)

CONTRACT = "trading.causal_market_state_synthesis.v1"
RULE_VERSION = "causal_market_state_synthesis_v1"
CONFIGURATION_VERSION = "causal_market_state_synthesis_configuration_v1"
IDENTITY_SCOPE = "snapshot_deterministic"
SUPPORT_STATES = frozenset({"EVIDENCED", "ABSENT_IN_SCOPE", "UNKNOWN"})
DIMENSIONS = (
    "market_structure", "volatility_range", "liquidity", "fvg_imbalance_intelligence",
    "displacement_intelligence", "structural_dealing_range_intelligence",
    "premium_discount_intelligence", "order_block_intelligence", "adjacent_timeframe_availability",
)
# These are producer fields, not newly inferred classifications.
CURRENT_FIELDS = {
    "market_structure": ("structure_state", "latest_high_relationship", "latest_low_relationship",
        "continuation_break_candidate", "continuation_break_confirmed", "reversal_break_candidate",
        "reversal_break_confirmed"),
    "volatility_range": ("volatility_state", "range_state", "volatility_trend", "abnormal_range", "gap_state"),
}
COLLECTIONS = {
    "liquidity": ("liquidity_intelligence", "liquidity_levels", "causal_boundary_id"),
    "fvg_imbalance_intelligence": ("fvg_imbalance_intelligence", "fair_value_gaps", "fvg_id"),
    "displacement_intelligence": ("displacement_intelligence", "displacement_events", "event_id"),
    "order_block_intelligence": ("order_block_intelligence", "order_blocks", "order_block_id"),
}


@dataclass(frozen=True)
class CausalMarketStateSynthesisResult:
    """Detached structured output; no mutation or execution interface."""
    synthesis_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"synthesis_id": self.synthesis_id, **self.payload})


def _configuration(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - {"schema_version"}:
        raise ValueError("Synthesis configuration accepts only schema_version.")
    if value.get("schema_version", CONFIGURATION_VERSION) != CONFIGURATION_VERSION:
        raise ValueError("Unsupported synthesis configuration version.")
    return {"schema_version": CONFIGURATION_VERSION}


def _usable(envelope: dict[str, Any]) -> bool:
    # No current owner contract grants narrower semantic authority to a failed
    # terminal result. Retained CLASSIFICATION_FAILED payloads remain UNKNOWN.
    return (envelope["factual_availability"] in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"}
            and envelope["provenance"]["execution_progress"]["terminal"] == "COMPLETED")


def _owner_scope(envelope: dict[str, Any], field: str) -> dict[str, Any]:
    result = envelope["authoritative_result"] or {}
    return {
        "basis": "producer_configured_domain", "source_field": field,
        "source_bounds": envelope["provenance"].get("source_bounds"),
        "effective_configuration": envelope["capability"]["configuration"],
        "owner_evidence": result.get("evidence", {}),
        "owner_diagnostics": result.get("diagnostics", {}),
        "availability_reason": envelope["availability_reason"],
    }


def _absence(envelope: dict[str, Any], field: str) -> bool:
    """Use existing owner absence classifications, qualified by their exact domain."""
    if not _usable(envelope) or envelope["factual_availability"] != "AVAILABLE_ABSENT":
        return False
    result = envelope["authoritative_result"] or {}
    config = envelope["capability"]["configuration"]
    evidence, diagnostics = result.get("evidence", {}), result.get("diagnostics", {})
    if field == "fair_value_gaps":
        return (envelope["availability_reason"] == "no_fvg_rows_after_valid_evaluation"
                and result.get("scanned_candle_count", 0) > 0
                and config.get("include_fully_filled") is True
                and evidence.get("filtered_out_fully_filled_count") == 0)
    if field == "displacement_events":
        return (envelope["availability_reason"] == "no_displacement_after_valid_evaluation"
                and evidence.get("evaluable_candidate_count", 0) > 0
                and evidence.get("insufficient_history_count") == 0
                and evidence.get("insufficient_context_count") == 0)
    if field == "order_blocks":
        return (envelope["availability_reason"] == "no_order_blocks_after_valid_evaluation"
                and diagnostics.get("truncated_order_block_count") == 0
                and diagnostics.get("truncated_interaction_count") == 0)
    if field == "current_range":
        return (envelope["availability_reason"] == "no_current_structural_range_after_valid_evaluation"
                and diagnostics.get("source_pivot_count", 0) > 0)
    # No extra absence rule is invented for other fields or boundary collections.
    return False


def _provenance(envelope, context, field, locator, coverage, event=None):
    return {
        "source_capability": deepcopy(envelope["capability"]),
        "authoritative_result_id": envelope["authoritative_result_id"],
        "factual_envelope_id": envelope["factual_envelope_id"],
        "envelope_content_fingerprint": envelope_reference(envelope)["content_fingerprint"],
        "factual_context_id": context["factual_context_id"],
        "source_snapshot_id": envelope["source_snapshot_id"], "source_timeframe": envelope["timeframe"],
        "source_cutoff": envelope["effective_causal_cutoff"],
        "requested_evaluation_timestamp": context["requested_evaluation_timestamp"],
        "source_field": field, "object_event_locator": locator,
        "causal_availability_timestamp": event["causal_availability_timestamp"] if event else envelope["effective_causal_cutoff"],
        "causal_availability_basis": deepcopy(event["causal_availability_basis"]) if event else {
            "basis": "authoritative_snapshot_at_source_cutoff", "historical_creation_state": False},
        "configuration_fingerprint": envelope["provenance"]["configuration_fingerprint"],
        "effective_configuration": deepcopy(envelope["capability"]["configuration"]),
        "coverage": deepcopy(coverage),
        "degradation": {"factual_availability": envelope["factual_availability"],
            "source_completion_state": envelope["source_completion_state"],
            "execution_progress": deepcopy(envelope["provenance"]["execution_progress"]),
            "availability_reason": envelope["availability_reason"]},
    }


def _claim(envelope, context, field, value, locator=None, *, absent=False, coverage=None, event=None):
    positive = _usable(envelope) and value is not None
    support = "EVIDENCED" if positive else "ABSENT_IN_SCOPE" if absent else "UNKNOWN"
    return {"source_field": field, "support_state": support,
        "value": deepcopy(value) if positive else None,
        "temporal_scope": "historical_event" if event else "snapshot_current",
        "provenance": _provenance(envelope, context, field, locator,
                                  coverage if coverage is not None else _owner_scope(envelope, field), event)}


class CausalMarketStateSynthesisAnalyzer:
    def analyze(self, payload: dict[str, Any]) -> CausalMarketStateSynthesisResult:
        try:
            return self._analyze(payload)
        except (KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError("Malformed synthesis bundle or authoritative observation.") from exc

    def _analyze(self, payload):
        required = {"factual_context", "factual_envelopes", "composition", "chronology", "configuration"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("Synthesis requires exactly the fixed five-field authoritative bundle.")
        config = _configuration(payload["configuration"])
        context = validate_factual_context(payload["factual_context"])
        matrix = payload["factual_envelopes"]
        if not isinstance(matrix, dict) or set(matrix) != set(TIMEFRAME_ORDER):
            raise ValueError("Synthesis requires seven envelope timeframe slots.")
        validated = {}
        for tf in TIMEFRAME_ORDER:
            if not isinstance(matrix[tf], dict) or set(matrix[tf]) != set(CAPABILITY_ORDER):
                raise ValueError("Synthesis requires the ten bound capability envelopes.")
            validated[tf] = {}
            for name in CAPABILITY_ORDER:
                env = validate_factual_envelope(matrix[tf][name])
                if envelope_reference(env) != context["timeframes"][tf]["factual_capabilities"][name]:
                    raise ValueError("Synthesis envelope/context binding mismatch.")
                if env.get("context_id") not in (None, context["source_context_id"]):
                    raise ValueError("Synthesis source context binding mismatch.")
                validated[tf][name] = env
        composition = validate_factual_composition(payload["composition"], context)
        chronology = validate_factual_chronology(payload["chronology"], context, validated, composition)
        frames = {}
        for tf in TIMEFRAME_ORDER:
            dimensions = {name: [] for name in DIMENSIONS}
            for name, fields in CURRENT_FIELDS.items():
                env = validated[tf][name]
                result = env["authoritative_result"] or {}
                for field in fields:
                    dimensions[name].append(_claim(env, context, field, result.get(field)))
            for dimension, (name, field, id_field) in COLLECTIONS.items():
                env = validated[tf][name]
                rows = (env["authoritative_result"] or {}).get(field, []) if _usable(env) else []
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise ValueError("Malformed authoritative object collection.")
                dimensions[dimension] = [_claim(env, context, field, row,
                    {"index": index, id_field: row.get(id_field)}) for index, row in enumerate(rows)]
                if not rows:
                    dimensions[dimension].append(_claim(env, context, field, None, absent=_absence(env, field)))
            env = validated[tf]["displacement_intelligence"]
            sequences = (env["authoritative_result"] or {}).get("displacement_sequences", []) if _usable(env) else []
            if not isinstance(sequences, list) or any(not isinstance(row, dict) for row in sequences):
                raise ValueError("Malformed authoritative displacement sequences.")
            for index, row in enumerate(sequences):
                dimensions["displacement_intelligence"].append(_claim(env, context, "displacement_sequences", row,
                    {"index": index, "sequence_id": row.get("sequence_id")}))
            for name, field, id_field in (
                ("structural_dealing_range_intelligence", "current_range", "range_id"),
                ("premium_discount_intelligence", "observation", "observation_id"),
            ):
                env = validated[tf][name]
                value = (env["authoritative_result"] or {}).get(field) if _usable(env) else None
                if value is not None and not isinstance(value, dict):
                    raise ValueError("Malformed authoritative current observation.")
                dimensions[name].append(_claim(env, context, field, value,
                    {id_field: value.get(id_field)} if value else None, absent=_absence(env, field)))
            # Historical claims use ONLY #19's event manifest and scoped coverage.
            for name, families in EVENT_FAMILIES.items():
                if name == "structural_dealing_range_intelligence":
                    continue  # v1 maps selected current range, not a new range lifecycle.
                dimension = "liquidity" if name == "liquidity_events" else name
                env = validated[tf][name]
                coverage = chronology["timeframes"][tf]["coverage"][name]
                for family in families:
                    events = [e for e in chronology["events"] if e["timeframe"] == tf and e["event_family"] == family]
                    for event in events:
                        claim = _claim(env, context, family, event,
                            {"chronology_event_id": event["chronology_event_id"], "source_event_id": event["source_event_id"]},
                            coverage=coverage, event=event)
                        claim["provenance"]["chronology_id"] = chronology["chronology_id"]
                        dimensions[dimension].append(claim)
                    if not events:
                        scope = coverage["coverage_scope"]
                        omissions = scope["filter_omissions"]
                        clear = (not scope["source_truncated_event_count"]
                                 and not any(v for v in omissions.values() if v is not None)
                                 and not (name == "liquidity_events" and scope["output_filters"].get("include_touch_events") is False)
                                 and not (name == "fvg_imbalance_intelligence" and scope["output_filters"].get("include_fully_filled") is False))
                        absent = (_usable(env) and coverage["coverage_state"] in {"FULLY_COVERED", "SOURCE_BOUNDED"}
                                  and family in scope["event_families"] and clear)
                        claim = _claim(env, context, family, None, absent=absent, coverage=coverage)
                        claim["temporal_scope"] = "historical_event_domain"
                        claim["provenance"]["chronology_id"] = chronology["chronology_id"]
                        dimensions[dimension].append(claim)
            for index, relationship in enumerate(composition["adjacent_relationships"]):
                if relationship["parent_timeframe"] != tf:
                    continue  # Store each canonical adjacent relation once, on its parent.
                name = relationship["capability_name"]
                child = relationship["child_timeframe"]
                env = validated[tf][name]
                child_env = validated[child][name]
                usable = _usable(env) and _usable(child_env)
                claim = _claim(env, context, "adjacent_relationships", relationship if usable else None,
                    {"index": index, "parent_timeframe": tf, "child_timeframe": child, "capability_name": name},
                    coverage={"basis": "slice18_availability_relationship_only"})
                claim["provenance"].update(composition_id=composition["composition_id"],
                    source_owner_contract=composition["metadata"]["contract"], source_owner_rule=composition["metadata"]["rule_version"],
                    child_source=_provenance(child_env, context, "adjacent_relationships", None,
                                             {"basis": "slice18_availability_relationship_only"}),
                    authoritative_relationship=deepcopy(relationship))
                dimensions["adjacent_timeframe_availability"].append(claim)
            frames[tf] = {"timeframe": tf, "source_snapshot_id": context["timeframes"][tf]["source_snapshot_id"],
                "effective_causal_cutoff": context["timeframes"][tf]["effective_causal_cutoff"],
                "factual_context_state": context["timeframes"][tf]["factual_context_state"], "dimensions": dimensions}
        references = {tf: {name: envelope_reference(validated[tf][name]) for name in CAPABILITY_ORDER} for tf in TIMEFRAME_ORDER}
        output = {"symbol": context["symbol"], "requested_evaluation_timestamp": context["requested_evaluation_timestamp"],
            "identity_scope": IDENTITY_SCOPE, "configuration": config,
            "configuration_fingerprint": _configuration_fingerprint(config),
            "source_factual_context_id": context["factual_context_id"], "source_composition_id": composition["composition_id"],
            "source_chronology_id": chronology["chronology_id"], "envelope_references": references,
            "input_content_fingerprint": _hash_id("synthesis_inputs_", {"context": context, "envelopes": references,
                "composition": composition, "chronology": chronology}),
            "upstream_context_state": context["context_state"], "timeframes": frames,
            "ordering_groups": deepcopy(chronology["ordering_groups"]),
            "metadata": {"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": IDENTITY_SCOPE,
                "observation_only": True, "advisory_output": False, "strategy_output": False,
                "execution_output": False, "authority_scope": "read_only"}}
        return CausalMarketStateSynthesisResult(_hash_id("market_state_synthesis_", output), deepcopy(output))


CAUSAL_MARKET_STATE_SYNTHESIS = CausalMarketStateSynthesisAnalyzer()
