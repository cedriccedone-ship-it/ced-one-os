"""Slice #23: policy-declared directional intent without decision authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ced_one.business_divisions.trading import causal_trading_policy_prerequisite_assessment as prerequisites
from ced_one.business_divisions.trading.causal_market_state_synthesis import _hash_id

CONTRACT = "trading.causal_trading_policy_action_formulation.v1"
RULE_VERSION = "causal_trading_policy_action_formulation_v1"
DEFINITION_CONTRACT = "trading.causal_trading_policy_action_definition.v1"
DEFINITION_RULE_VERSION = "causal_trading_policy_action_definition_v1"


def normalize_action_policy_definition(value: Any) -> dict[str, Any]:
    required = {"action_policy_contract", "action_policy_rule_version", "action_policy_id",
                "action_policy_version", "prerequisite_definition", "declared_action"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("Action policy requires exactly six caller-supplied fields.")
    for field, expected in (("action_policy_contract", DEFINITION_CONTRACT),
                            ("action_policy_rule_version", DEFINITION_RULE_VERSION)):
        if type(value[field]) is not str or value[field] != expected:
            raise ValueError("Unsupported action-policy contract or rule.")
    if type(value["action_policy_id"]) is not str or not value["action_policy_id"]:
        raise ValueError("Action-policy identifier must be a nonempty string.")
    if type(value["action_policy_version"]) is not int or value["action_policy_version"] <= 0:
        raise ValueError("Action-policy version must be a positive integer, not a boolean.")
    action = value["declared_action"]
    if type(action) is not dict or set(action) != {"action_type", "direction"}:
        raise ValueError("Declared action requires exactly action_type and direction.")
    if type(action["action_type"]) is not str or action["action_type"] != "DIRECTIONAL_ENTRY_INTENT":
        raise ValueError("Unsupported declared action type.")
    if type(action["direction"]) is not str or action["direction"] not in {"LONG", "SHORT"}:
        raise ValueError("Direction must be the explicit string LONG or SHORT.")
    normalized = deepcopy(value)
    normalized["prerequisite_definition"] = prerequisites.normalize_policy_definition(value["prerequisite_definition"])
    normalized["complete_action_policy_fingerprint"] = _hash_id("action_policy_definition_", normalized)
    return normalized


@dataclass(frozen=True)
class CausalTradingPolicyActionFormulationResult:
    formulation_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"formulation_id": self.formulation_id, **self.payload})


class CausalTradingPolicyActionFormulationAnalyzer:
    def analyze(self, payload: Any) -> CausalTradingPolicyActionFormulationResult:
        required = {"action_policy_definition", "prerequisite_assessment", "assessment_input"}
        if type(payload) is not dict or set(payload) != required:
            raise ValueError("Formulation requires exactly action policy, assessment and reconstruction input.")
        policy = normalize_action_policy_definition(payload["action_policy_definition"])
        assessment = prerequisites.validate_causal_trading_policy_prerequisite_assessment(
            payload["prerequisite_assessment"], payload["assessment_input"])
        if policy["prerequisite_definition"] != assessment["policy_definition"]:
            raise ValueError("Action-policy prerequisite differs from the complete assessed definition.")
        state = (assessment["applicability"], assessment["prerequisite_assessment"])
        reasons = {
            ("APPLICABLE", "PREREQUISITE_ESTABLISHED"): "ACTION_FORMULATED",
            ("APPLICABLE", "PREREQUISITE_NOT_ESTABLISHED"): "PREREQUISITE_NOT_ESTABLISHED",
            ("APPLICABLE", "PREREQUISITE_UNKNOWN"): "PREREQUISITE_UNKNOWN",
            ("NOT_APPLICABLE", None): "POLICY_NOT_APPLICABLE",
        }
        if state not in reasons:
            raise ValueError("Unsupported prerequisite assessment state.")
        formulated = reasons[state] == "ACTION_FORMULATED"
        result = {
            "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
            "action_policy_definition": policy, "prerequisite_assessment": assessment,
            "formulation_status": "FORMULATED" if formulated else "NOT_FORMULATED",
            "formulated_action": deepcopy(policy["declared_action"]) if formulated else None,
            "reason_codes": [reasons[state]],
            "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
        }
        return CausalTradingPolicyActionFormulationResult(
            _hash_id("policy_action_formulation_", result), deepcopy(result))


CAUSAL_TRADING_POLICY_ACTION_FORMULATION = CausalTradingPolicyActionFormulationAnalyzer()
