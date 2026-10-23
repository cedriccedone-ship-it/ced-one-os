"""Slice #21: bounded factual predicate truth, without trading significance."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any

from ced_one.business_divisions.trading.causal_market_state_synthesis import (
    TIMEFRAME_ORDER, _hash_id, validate_market_state_synthesis,
)

CONTRACT = "trading.causal_factual_condition_evaluation.v1"
RULE_VERSION = "causal_factual_condition_evaluation_v1"
CONDITION_CONTRACT = "trading.causal_factual_condition_definition.v1"
SCALAR = "SCALAR_COMPARISON"
OBJECT = "OBJECT_EXISTS"
CLAIM = "CLAIM_EXISTS"
ALL = "ALL_OF"


@dataclass(frozen=True)
class ConditionTarget:
    dimension: str
    source_field: str
    value_type: type
    families: tuple[str, ...]
    projection: str | None = None
    filter_fields: tuple[str, ...] = ()
    absence_supported: bool = False


def _targets() -> dict[str, ConditionTarget]:
    targets = {}
    for dimension, fields in (
        ("market_structure", ("structure_state", "latest_high_relationship", "latest_low_relationship",
            "continuation_break_candidate", "continuation_break_confirmed", "reversal_break_candidate",
            "reversal_break_confirmed")),
        ("volatility_range", ("volatility_state", "range_state", "volatility_trend", "abnormal_range", "gap_state")),
    ):
        for field in fields:
            kind = bool if field.endswith(("_candidate", "_confirmed")) or field == "abnormal_range" else str
            targets[field] = ConditionTarget(dimension, field, kind, (SCALAR, CLAIM))
    targets.update({
        "current_structural_range": ConditionTarget("structural_dealing_range_intelligence", "current_range", dict, (CLAIM,), absence_supported=True),
        "current_range_order": ConditionTarget("structural_dealing_range_intelligence", "current_range", str, (SCALAR,), projection="chronological_order", absence_supported=True),
        "premium_discount_observation": ConditionTarget("premium_discount_intelligence", "observation", dict, (CLAIM,)),
        "premium_discount_classification": ConditionTarget("premium_discount_intelligence", "observation", str, (SCALAR,), projection="classification"),
        "liquidity_levels": ConditionTarget("liquidity", "liquidity_levels", dict, (OBJECT,), filter_fields=("side", "level_type", "current_status")),
        "fair_value_gaps": ConditionTarget("fvg_imbalance_intelligence", "fair_value_gaps", dict, (OBJECT,), filter_fields=("side", "current_status"), absence_supported=True),
        "displacement_events": ConditionTarget("displacement_intelligence", "displacement_events", dict, (OBJECT,), filter_fields=("direction",), absence_supported=True),
        "displacement_sequences": ConditionTarget("displacement_intelligence", "displacement_sequences", dict, (OBJECT,), filter_fields=("direction",)),
        "order_blocks": ConditionTarget("order_block_intelligence", "order_blocks", dict, (OBJECT,), filter_fields=("direction", "current_state"), absence_supported=True),
    })
    return targets


TARGETS = MappingProxyType(_targets())


def _keys(value: Any, required: set[str]) -> None:
    if type(value) is not dict or set(value) != required:
        raise ValueError("Missing, additional or family-forbidden condition fields.")


def _comparison(operator: Any, expected: Any, kind: type) -> None:
    if type(operator) is not str or operator not in ("EQ", "NE"):
        raise ValueError("Only EQ and NE are supported.")
    if type(expected) is not kind:
        raise ValueError("Expected value has incompatible type; coercion is forbidden.")


def normalize_condition(value: Any, *, atomic: bool = False) -> dict[str, Any]:
    """Strict versioned data; dictionary order alone is non-semantic."""
    if type(value) is not dict:
        raise ValueError("Condition must be a dictionary.")
    family = value.get("predicate_type")
    if type(family) is not str or family not in (SCALAR, OBJECT, CLAIM, ALL):
        raise ValueError("Unsupported predicate family.")
    common = {"contract", "condition_id", "timeframe", "predicate_type"}
    extra = {SCALAR: {"target", "operator", "expected_value"}, OBJECT: {"target", "filters"},
             CLAIM: {"target"}, ALL: {"constituents"}}[family]
    _keys(value, common | extra)
    if type(value["contract"]) is not str or value["contract"] != CONDITION_CONTRACT:
        raise ValueError("Unsupported condition contract.")
    if type(value["condition_id"]) is not str or not value["condition_id"]:
        raise ValueError("Condition identifier must be a nonempty string.")
    if type(value["timeframe"]) is not str or value["timeframe"] not in TIMEFRAME_ORDER:
        raise ValueError("Condition requires one canonical timeframe.")
    normalized = {key: value[key] for key in ("contract", "condition_id", "timeframe", "predicate_type")}
    if family == ALL:
        children = value["constituents"]
        if atomic or type(children) is not list or not 1 <= len(children) <= 32:
            raise ValueError("ALL_OF requires 1–32 atomic constituents; nesting is forbidden.")
        children = [normalize_condition(child, atomic=True) for child in children]
        if any(child["timeframe"] != value["timeframe"] for child in children):
            raise ValueError("Cross-timeframe conjunction is forbidden.")
        if len({child["condition_id"] for child in children}) != len(children):
            raise ValueError("Duplicate constituent identifiers.")
        normalized["constituents"] = children
    else:
        name = value["target"]
        if type(name) is not str or name not in TARGETS or family not in TARGETS[name].families:
            raise ValueError("Unsupported target or target/predicate combination.")
        target = TARGETS[name]
        normalized["target"] = name
        if family == SCALAR:
            _comparison(value["operator"], value["expected_value"], target.value_type)
            normalized.update(operator=value["operator"], expected_value=value["expected_value"])
        elif family == OBJECT:
            if type(value["filters"]) is not list:
                raise ValueError("Object filters must be an explicit list.")
            filters, seen = [], set()
            for item in value["filters"]:
                _keys(item, {"field", "operator", "expected_value"})
                field = item["field"]
                if type(field) is not str or field not in target.filter_fields or field in seen:
                    raise ValueError("Unsupported or duplicate object filter field.")
                _comparison(item["operator"], item["expected_value"], str)
                seen.add(field)
                filters.append({key: item[key] for key in ("field", "operator", "expected_value")})
            normalized["filters"] = filters
    return normalized


@dataclass(frozen=True)
class CausalFactualConditionEvaluationResult:
    evaluation_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"evaluation_id": self.evaluation_id, **self.payload})


def condition_identity(value: Any) -> str:
    """Owner-controlled identity of the complete normalized condition."""
    return _hash_id("factual_condition_", normalize_condition(value))


def _equal(actual: Any, operator: str, expected: Any) -> bool:
    return (actual == expected) if operator == "EQ" else (actual != expected)


def _evaluate(synthesis: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    """Internal evaluator receives only the validated synthesis and condition data."""
    tf, family = condition["timeframe"], condition["predicate_type"]
    result = {"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "condition_id": condition["condition_id"], "condition": deepcopy(condition),
        "condition_identity": condition_identity(condition),
        "timeframe": tf, "effective_causal_cutoff": synthesis["timeframes"][tf]["effective_causal_cutoff"],
        "requested_evaluation_timestamp": synthesis["requested_evaluation_timestamp"],
        "source_synthesis_id": synthesis["synthesis_id"], "predicate_type": family,
        "evidence": [], "constituent_results": [],
        "metadata": {"observation_only": True, "authority_scope": "read_only", "strategy_output": False,
                     "advisory_output": False, "execution_output": False}}
    if family == ALL:
        children = [_evaluate(synthesis, child) for child in condition["constituents"]]
        outcomes = [child["outcome"] for child in children]
        outcome = "NOT_SATISFIED" if "NOT_SATISFIED" in outcomes else "UNKNOWN" if "UNKNOWN" in outcomes else "SATISFIED"
        result.update(outcome=outcome, reason_codes=["CONJUNCTION_" + outcome], constituent_results=children)
    else:
        target = TARGETS[condition["target"]]
        rows = [(i, row) for i, row in enumerate(synthesis["timeframes"][tf]["dimensions"][target.dimension])
                if row["source_field"] == target.source_field and row["temporal_scope"] == "snapshot_current"]
        if family != OBJECT and len(rows) != 1:
            raise ValueError("Singular target must resolve to exactly one structural record.")
        if family == OBJECT and not rows and target.source_field != "displacement_sequences":
            raise ValueError("Required object collection placeholder is missing.")
        matches, absent, placeholders = [], False, 0
        for index, row in rows:
            support, value = row["support_state"], row["value"]
            if support not in ("EVIDENCED", "ABSENT_IN_SCOPE", "UNKNOWN"):
                raise ValueError("Unsupported claim support.")
            entry = {"locator": {"synthesis_id": synthesis["synthesis_id"], "timeframe": tf,
                "dimension": target.dimension, "claim_index": index, "source_field": target.source_field,
                "source_object_locator": deepcopy(row["provenance"]["object_event_locator"])},
                "support_state": support, "observed_value": None}
            if support != "EVIDENCED":
                placeholders += 1
                if value is not None or (support == "ABSENT_IN_SCOPE" and not target.absence_supported):
                    raise ValueError("Contradictory claim support/value/domain.")
                absent = support == "ABSENT_IN_SCOPE"
            else:
                expected_type = dict if target.projection else target.value_type
                if type(value) is not expected_type:
                    raise ValueError("Evidenced target has incompatible type.")
                if target.projection:
                    value = value.get(target.projection)
                    if type(value) is not target.value_type:
                        raise ValueError("Evidenced projection is missing or has incompatible type.")
                if family == OBJECT:
                    if any(type(value.get(field)) is not str for field in target.filter_fields):
                        raise ValueError("Evidenced object has missing or incorrectly typed allowlisted fields.")
                    entry["observed_value"] = {field: value[field] for field in target.filter_fields}
                    matched = all(_equal(value[f["field"]], f["operator"], f["expected_value"]) for f in condition["filters"])
                elif family == SCALAR:
                    entry["observed_value"] = value
                    matched = _equal(value, condition["operator"], condition["expected_value"])
                else:
                    # Object existence needs no unselected geometry or nested facts.
                    entry["observed_value"] = value if target.value_type is not dict else None
                    matched = True
                entry["matches"] = matched
                matches.append(matched)
            result["evidence"].append(entry)
        if family == OBJECT and placeholders and len(rows) != 1:
            raise ValueError("Collection placeholder cannot coexist with other records.")
        if family == SCALAR:
            outcome = ("SATISFIED" if matches[0] else "NOT_SATISFIED") if matches else "UNKNOWN"
            reason = "SCALAR_COMPARISON_" + outcome if matches else "SCALAR_UNDEFINED"
        elif any(matches):
            outcome, reason = "SATISFIED", "AUTHORITATIVE_PRESENCE"
        elif absent:
            outcome, reason = "NOT_SATISFIED", "EXPLICIT_SCOPED_ABSENCE"
        else:
            outcome, reason = "UNKNOWN", "NO_AUTHORITATIVE_MATCH_OR_ABSENCE"
        result.update(outcome=outcome, reason_codes=[reason])
    return {"evaluation_id": _hash_id("factual_condition_evaluation_", result), **result}


class CausalFactualConditionEvaluationAnalyzer:
    def analyze(self, payload: Any) -> CausalFactualConditionEvaluationResult:
        _keys(payload, {"synthesis", "upstream_bundle", "condition"})
        condition = normalize_condition(payload["condition"])
        # The upstream bundle is opaque here: only the #20 owner consumes it.
        synthesis = validate_market_state_synthesis(payload["synthesis"], payload["upstream_bundle"])
        try:
            result = _evaluate(synthesis, condition)
        except (KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError("Malformed authoritative condition evidence.") from exc
        identity = result.pop("evaluation_id")
        return CausalFactualConditionEvaluationResult(identity, result)


CAUSAL_FACTUAL_CONDITION_EVALUATION = CausalFactualConditionEvaluationAnalyzer()


def validate_causal_factual_condition_evaluation(
    value: Any, synthesis: Any, upstream_bundle: Any, condition: Any,
) -> dict[str, Any]:
    """Reconstruct and compare all serialized content; never rerun detectors."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_FACTUAL_CONDITION_EVALUATION.analyze({
            "synthesis": synthesis, "upstream_bundle": upstream_bundle, "condition": condition,
        }).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Condition evaluation content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized condition evaluation.") from exc
