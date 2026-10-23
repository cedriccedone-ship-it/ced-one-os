"""Slice #22: exact policy prerequisite binding, without trading authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
import json
from typing import Any

from ced_one.business_divisions.trading import causal_factual_condition_evaluation as conditions
from ced_one.business_divisions.trading.causal_market_state_synthesis import (
    TIMEFRAME_ORDER, _hash_id, validate_market_state_synthesis,
)

CONTRACT = "trading.causal_trading_policy_prerequisite_assessment.v1"
RULE_VERSION = "causal_trading_policy_prerequisite_assessment_v1"
DEFINITION_CONTRACT = "trading.causal_trading_policy_prerequisite_definition.v1"
DEFINITION_RULE_VERSION = "causal_trading_policy_prerequisite_definition_v1"


def normalize_policy_definition(value: Any) -> dict[str, Any]:
    required = {"policy_definition_contract", "policy_definition_rule_version", "policy_id",
                "policy_version", "instrument", "timeframe", "required_condition"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("Policy requires exactly seven caller-supplied definition fields.")
    for field, expected in (("policy_definition_contract", DEFINITION_CONTRACT),
                            ("policy_definition_rule_version", DEFINITION_RULE_VERSION)):
        if type(value[field]) is not str or value[field] != expected:
            raise ValueError("Unsupported policy definition contract or rule.")
    if type(value["policy_id"]) is not str or not value["policy_id"]:
        raise ValueError("Policy identifier must be a nonempty string.")
    if type(value["policy_version"]) is not int or value["policy_version"] <= 0:
        raise ValueError("Policy version must be a positive integer, not a boolean.")
    instrument = value["instrument"]
    if type(instrument) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]*", instrument) is None:
        raise ValueError("Instrument must be an uppercase identifier without whitespace.")
    if type(value["timeframe"]) is not str or value["timeframe"] not in TIMEFRAME_ORDER:
        raise ValueError("Policy requires one canonical timeframe.")
    normalized = deepcopy(value)
    normalized["required_condition"] = conditions.normalize_condition(value["required_condition"])
    normalized["required_condition_identity"] = conditions.condition_identity(normalized["required_condition"])
    normalized["complete_definition_fingerprint"] = _hash_id("policy_prerequisite_definition_", normalized)
    return normalized


@dataclass(frozen=True)
class CausalTradingPolicyPrerequisiteAssessmentResult:
    assessment_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"assessment_id": self.assessment_id, **self.payload})


class CausalTradingPolicyPrerequisiteAssessmentAnalyzer:
    def analyze(self, payload: Any) -> CausalTradingPolicyPrerequisiteAssessmentResult:
        required = {"policy_definition", "condition_evaluation", "synthesis", "upstream_bundle", "condition"}
        if type(payload) is not dict or set(payload) != required:
            raise ValueError("Assessment requires the policy, evaluation and exact Slice #21 input bundle.")
        policy = normalize_policy_definition(payload["policy_definition"])
        evaluation = conditions.validate_causal_factual_condition_evaluation(
            payload["condition_evaluation"], payload["synthesis"], payload["upstream_bundle"], payload["condition"])
        if policy["required_condition"] != evaluation["condition"]:
            raise ValueError("Policy required condition differs from the complete evaluated condition.")
        timeframe = policy["timeframe"]
        if timeframe != policy["required_condition"]["timeframe"] or timeframe != evaluation["timeframe"]:
            raise ValueError("Policy, required condition and evaluation timeframe must match.")
        # Only the synthesis owner supplies instrument identity. No factual claims
        # are read here, and no condition/constituent truth is recomputed.
        synthesis = validate_market_state_synthesis(payload["synthesis"], payload["upstream_bundle"])
        if (evaluation["source_synthesis_id"] != synthesis["synthesis_id"]
                or evaluation["requested_evaluation_timestamp"] != synthesis["requested_evaluation_timestamp"]
                or evaluation["effective_causal_cutoff"] != synthesis["timeframes"][timeframe]["effective_causal_cutoff"]):
            raise ValueError("Evaluation synthesis or causal boundary mismatch.")
        instrument = synthesis["symbol"]
        matches = instrument == policy["instrument"]
        outcome_mapping = {"SATISFIED": "PREREQUISITE_ESTABLISHED",
                           "NOT_SATISFIED": "PREREQUISITE_NOT_ESTABLISHED", "UNKNOWN": "PREREQUISITE_UNKNOWN"}
        result = {
            "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
            "policy_definition": policy, "evaluated_instrument": instrument,
            "condition_evaluation": evaluation,
            "applicability": "APPLICABLE" if matches else "NOT_APPLICABLE",
            "prerequisite_assessment": outcome_mapping[evaluation["outcome"]] if matches else None,
            "reason_codes": ["POLICY_SCOPE_MATCH" if matches else "INSTRUMENT_SCOPE_MISMATCH"],
            "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
        }
        return CausalTradingPolicyPrerequisiteAssessmentResult(
            _hash_id("policy_prerequisite_assessment_", result), deepcopy(result))


CAUSAL_TRADING_POLICY_PREREQUISITE_ASSESSMENT = CausalTradingPolicyPrerequisiteAssessmentAnalyzer()


def validate_causal_trading_policy_prerequisite_assessment(
    value: Any, assessment_input: Any,
) -> dict[str, Any]:
    """Reconstruct complete owned content; consistency does not prove authenticity."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_TRADING_POLICY_PREREQUISITE_ASSESSMENT.analyze(assessment_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Prerequisite assessment content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized prerequisite assessment.") from exc
