"""Additive #23 strategy path; only the strategy owner evaluates prerequisites."""
from copy import deepcopy
from dataclasses import dataclass

from .xauusd_causal_liquidity_reversal import (
    AUTHORITY, exact, identity, normalize_strategy_definition,
    validate_strategy_assessment,
)

CONTRACT = "trading.causal_trading_policy_action_formulation.strategy.v1"
DEFINITION_CONTRACT = "trading.causal_trading_policy_action_definition.strategy.v1"
RULE_VERSION = "strategy_action_formulation_v1"


@dataclass(frozen=True)
class StrategyActionFormulationResult:
    payload: dict

    def to_dict(self):
        return deepcopy(self.payload)


class StrategyActionFormulationAnalyzer:
    def analyze(self, payload):
        exact(payload, {"action_policy_definition", "strategy_assessment", "assessment_input"}, "Strategy formulation")
        policy = deepcopy(payload["action_policy_definition"])
        exact(policy, {"contract", "policy_id", "policy_version", "strategy_definition",
                       "configuration_fingerprint", "declared_action"}, "Strategy action policy")
        if policy["contract"] != DEFINITION_CONTRACT:
            raise ValueError("Unsupported strategy action policy contract.")
        if type(policy["policy_id"]) is not str or not policy["policy_id"]:
            raise ValueError("Policy ID must be a nonempty string.")
        if type(policy["policy_version"]) is not int or policy["policy_version"] < 1:
            raise ValueError("Policy version must be a positive integer.")
        policy["strategy_definition"] = normalize_strategy_definition(policy["strategy_definition"])
        expected_fingerprint = identity("configuration_", policy["strategy_definition"]["configuration"])
        if policy["configuration_fingerprint"] != expected_fingerprint:
            raise ValueError("Policy fingerprint differs from its own effective configuration.")
        exact(policy["declared_action"], {"action_type", "direction"}, "Declared action")
        if policy["declared_action"]["action_type"] != "DIRECTIONAL_ENTRY_INTENT":
            raise ValueError("Unsupported declared action.")
        if policy["declared_action"]["direction"] != policy["strategy_definition"]["direction"]:
            raise ValueError("Declared direction differs from strategy direction.")
        assessment = validate_strategy_assessment(payload["strategy_assessment"], payload["assessment_input"])
        if identity("", policy["strategy_definition"]) != identity("", assessment["strategy_definition"]):
            raise ValueError("Policy strategy definition differs from assessed definition.")
        if policy["configuration_fingerprint"] != assessment["configuration_fingerprint"]:
            raise ValueError("Policy configuration fingerprint mismatch.")
        complete = assessment["status"] == "COMPLETE"
        result = {"contract": CONTRACT, "rule_version": RULE_VERSION,
                  "action_policy_definition": policy, "strategy_assessment": assessment,
                  "setup_identity": assessment["setup_identity"],
                  "completion_identity": assessment["completion_identity"],
                  "evaluation_boundary": assessment["evaluation_boundary"],
                  "knowledge_boundary": assessment["knowledge_boundary"],
                  "formulation_status": "FORMULATED" if complete else "NOT_FORMULATED",
                  "formulated_action": deepcopy(policy["declared_action"]) if complete else None,
                  "reason": "ACTION_FORMULATED" if complete else "STRATEGY_NOT_COMPLETE",
                  "authority": dict(AUTHORITY), "execution": False}
        result["formulation_identity"] = identity("strategy_formulation_", result)
        return StrategyActionFormulationResult(result)


STRATEGY_ACTION_FORMULATION = StrategyActionFormulationAnalyzer()
