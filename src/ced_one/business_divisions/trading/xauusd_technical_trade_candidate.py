"""Strategy #1 technical terms and completed-M1 validity; no financial authority.

Formulation freezes the original strategy/action artifacts and M1 source. Later
validity reconstruction never refreshes those artifacts or changes the terms.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import json

from . import causal_trading_policy_strategy_action_formulation as actions
from .causal_snapshot_availability import validate_source, VALID_TIMEFRAME_DURATIONS
from .validation import parse_timestamp
from .xauusd_causal_liquidity_reversal import AUTHORITY, exact, identity, stamp

CONTRACT = "trading.xauusd_technical_trade_candidate.formulation.v1"
CANDIDATE_CONTRACT = "trading.xauusd_technical_trade_candidate.v1"
POLICY_CONTRACT = "trading.xauusd_technical_trade_candidate.policy.v1"
VALIDITY_CONTRACT = "trading.xauusd_technical_trade_candidate.validity.v1"
RULE_VERSION = "xauusd_technical_trade_candidate_v1"
M1 = VALID_TIMEFRAME_DURATIONS["M1"]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _same(supplied, expected, label):
    if _canonical(supplied) != _canonical(expected):
        raise ValueError(label + " differs from complete owner reconstruction.")


def _policy(value):
    exact(value, {"contract", "policy_id", "policy_version", "configuration"}, "Candidate policy")
    if value["contract"] != POLICY_CONTRACT:
        raise ValueError("Unsupported candidate policy contract.")
    if type(value["policy_id"]) is not str or not value["policy_id"].strip():
        raise ValueError("Candidate policy ID must be a nonempty string.")
    if type(value["policy_version"]) is not int or value["policy_version"] < 1:
        raise ValueError("Candidate policy version must be a positive integer.")
    exact(value["configuration"], {"entry_validity_duration_seconds"}, "Candidate configuration")
    seconds = value["configuration"]["entry_validity_duration_seconds"]
    if type(seconds) is not int or seconds <= 0:
        raise ValueError("Entry validity duration must be positive integer elapsed seconds.")
    return deepcopy(value)


@dataclass(frozen=True)
class TechnicalCandidateResult:
    _payload: dict

    @property
    def payload(self):
        return deepcopy(self._payload)

    def to_dict(self):
        return deepcopy(self._payload)


def _formulate(payload):
    exact(payload, {"candidate_policy_definition", "strategy_assessment", "action_formulation",
                    "action_formulation_input"}, "Technical candidate formulation")
    policy = _policy(payload["candidate_policy_definition"])
    reconstruction = payload["action_formulation_input"]
    exact(reconstruction, {"action_policy_definition", "strategy_assessment", "assessment_input"},
          "Original action reconstruction input")
    _same(payload["strategy_assessment"], reconstruction["strategy_assessment"], "Supplied assessment")
    # #23 delegates complete StrategyAssessment reconstruction to its owner.
    action = actions.STRATEGY_ACTION_FORMULATION.analyze(reconstruction).to_dict()
    _same(payload["action_formulation"], action, "Supplied action formulation")
    assessment = action["strategy_assessment"]
    _same(payload["strategy_assessment"], assessment, "Embedded assessment")
    if assessment["status"] != "COMPLETE" or action["formulation_status"] != "FORMULATED":
        raise ValueError("Candidate formulation requires COMPLETE and matching FORMULATED intent.")
    origin = deepcopy(validate_source(reconstruction["assessment_input"]["sources"]["M1"]))
    direction = assessment["strategy_definition"]["direction"]
    t1, e1 = assessment["bindings"]["T1"], assessment["bindings"]["E1"]
    entry = t1["candle"]["close"]
    stop = e1["candle"]["low" if direction == "LONG" else "high"]
    admissible = entry > stop if direction == "LONG" else entry < stop
    candidate = None
    if admissible:
        seconds = policy["configuration"]["entry_validity_duration_seconds"]
        valid_from = parse_timestamp(t1["available_at"])
        candidate = {
            "contract": CANDIDATE_CONTRACT, "rule_version": RULE_VERSION,
            "candidate_policy_fingerprint": identity("candidate_policy_", policy),
            "upstream_formulation_fingerprint": identity("candidate_upstream_", action),
            "m1_origin_fingerprint": identity("candidate_m1_origin_", origin),
            "assessment_identity": assessment["assessment_identity"],
            "formulation_identity": action["formulation_identity"],
            "strategy_id": assessment["strategy_definition"]["strategy_id"],
            "strategy_version": assessment["strategy_definition"]["strategy_version"],
            "instrument": assessment["strategy_definition"]["instrument"], "direction": direction,
            "setup_identity": assessment["setup_identity"], "completion_identity": assessment["completion_identity"],
            "entry_reference": {"kind": "TECHNICAL_ENTRY_REFERENCE", "value": entry, "evidence": deepcopy(t1)},
            "stop_reference": {"kind": "TECHNICAL_STOP_REFERENCE", "value": stop, "evidence": deepcopy(e1)},
            "entry_validity_duration_seconds": seconds,
            "valid_from": stamp(valid_from), "valid_until": stamp(valid_from + timedelta(seconds=seconds)),
            "authority": dict(AUTHORITY), "execution": False,
        }
        candidate["candidate_identity"] = identity("technical_candidate_", candidate)
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION,
        "candidate_policy_definition": policy, "upstream_formulation": action, "m1_origin_source": origin,
        "formulation_status": "FORMULATED" if admissible else "NOT_FORMULATED", "candidate": candidate,
        "reason": "CANDIDATE_FORMULATED" if admissible else "ENTRY_STOP_GEOMETRY_NOT_ADMISSIBLE",
        "authority": dict(AUTHORITY), "execution": False,
    }


def _candles(source):
    return {c["timestamp"]: {k: c[k] for k in ("timestamp", "open", "high", "low", "close")}
            for c in source["approved_candle_history"]}


def _evaluate(payload):
    exact(payload, {"candidate_formulation", "formulation_input", "evaluation_boundary", "m1_source"},
          "Technical candidate validity")
    formulated = validate_technical_candidate_formulation(payload["candidate_formulation"], payload["formulation_input"])
    candidate = formulated["candidate"]
    if candidate is None:
        raise ValueError("No admissible candidate exists for validity evaluation.")
    k = parse_timestamp(payload["evaluation_boundary"])
    upstream = formulated["upstream_formulation"]
    if k < parse_timestamp(upstream["knowledge_boundary"]):
        raise ValueError("Evaluation precedes frozen upstream availability.")
    start, expiry = (parse_timestamp(candidate[f]) for f in ("valid_from", "valid_until"))
    if k < start:
        raise ValueError("Evaluation precedes candidate availability.")
    source = deepcopy(validate_source(payload["m1_source"]))
    if source["source_availability"] not in ("AVAILABLE", "UNAVAILABLE"):
        raise ValueError("Invalid or unsupported M1 source state.")
    if source["timeframe"] != "M1" or source["symbol"] != candidate["instrument"]:
        raise ValueError("Validity source instrument/timeframe mismatch.")
    if parse_timestamp(source["requested_evaluation_timestamp"]) != k:
        raise ValueError("Validity source evaluation boundary mismatch.")
    original = _candles(formulated["m1_origin_source"])
    observed = _candles(source)
    for timestamp, candle in observed.items():
        # Off-grid/overlapping intervals are malformed, not missing coverage.
        if (parse_timestamp(timestamp) - start) % M1 != timedelta(0):
            raise ValueError("M1 source is not on the original one-minute grid.")
        if timestamp in original and candle != original[timestamp]:
            raise ValueError("Conflicting replacement of frozen M1 history.")
    t1 = candidate["entry_reference"]["evidence"]["candle"]
    status, reason, terminal = "VALID", "NO_COMPLETED_STOP_BREACH", None
    if t1["timestamp"] not in observed:
        status, reason = "UNKNOWN", "MISSING_ORIGINAL_T1_ANCHOR"
    else:
        if observed[t1["timestamp"]] != t1:
            raise ValueError("Validity history substitutes the original T1 anchor.")
        opened, horizon = start, min(k, expiry)
        stop = candidate["stop_reference"]["value"]
        while opened + M1 <= horizon:
            candle = observed.get(stamp(opened))
            if candle is None:
                status, reason = "UNKNOWN", "MISSING_REQUIRED_M1_INTERVAL"
                break
            breach = candle["low"] < stop if candidate["direction"] == "LONG" else candle["high"] > stop
            if breach:
                status, reason, terminal = "INVALIDATED", "FIRST_COMPLETED_STOP_BREACH", stamp(opened + M1)
                break
            opened += M1
        else:
            if k > expiry:
                status, reason, terminal = "EXPIRED", "ENTRY_VALIDITY_ELAPSED", stamp(expiry)
    return {
        "contract": VALIDITY_CONTRACT, "rule_version": RULE_VERSION,
        "candidate_identity": candidate["candidate_identity"], "evaluation_boundary": stamp(k),
        "m1_source": source, "status": status, "reason": reason, "terminal_boundary": terminal,
        "authority": dict(AUTHORITY), "execution": False,
    }


class XAUUSDTechnicalTradeCandidateAnalyzer:
    def analyze(self, payload):
        try:
            return TechnicalCandidateResult(_formulate(payload))
        except (KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError("Malformed technical candidate formulation input.") from exc

    def evaluate_validity(self, payload):
        try:
            return TechnicalCandidateResult(_evaluate(payload))
        except (KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError("Malformed technical candidate validity input.") from exc


XAUUSD_TECHNICAL_TRADE_CANDIDATE = XAUUSDTechnicalTradeCandidateAnalyzer()


def validate_technical_candidate_formulation(value, formulation_input):
    try:
        supplied = value.to_dict() if isinstance(value, TechnicalCandidateResult) else value
        expected = XAUUSD_TECHNICAL_TRADE_CANDIDATE.analyze(formulation_input).to_dict()
        _same(supplied, expected, "Candidate formulation")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed candidate formulation artifact.") from exc


def validate_technical_candidate_validity(value, validity_input):
    try:
        supplied = value.to_dict() if isinstance(value, TechnicalCandidateResult) else value
        expected = XAUUSD_TECHNICAL_TRADE_CANDIDATE.evaluate_validity(validity_input).to_dict()
        _same(supplied, expected, "Candidate validity")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed candidate validity artifact.") from exc
