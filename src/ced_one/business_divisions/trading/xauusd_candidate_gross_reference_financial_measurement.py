"""Historical frozen-reference loss rate; no current eligibility or risk authority."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import re

from . import xauusd_technical_trade_candidate as candidates
from . import causal_instrument_specification_applicability_resolver as applicability
from . import causal_financial_instrument_contract_metadata_snapshot as metadata
from . import causal_financial_instrument_contract_metadata_snapshot_v2 as payoff
from .causal_snapshot_availability import candle_completion
from .xauusd_causal_liquidity_reversal import identity

CONTRACT = "trading.xauusd_candidate_gross_reference_financial_measurement.v1"
RULE_VERSION = "xauusd_candidate_gross_reference_financial_measurement_v1"
SCENARIO = "T1_COMPLETION_FROZEN_REFERENCE_V1"
NUMERIC_RULE = "CANDIDATE_PRICE_DECIMAL_INTERPRETATION_V1"
ASSERTION_CONTRACT = "CANDIDATE_FINANCIAL_PRICE_DOMAIN_BINDING_ASSERTION_V1"
RELATIONSHIP = "DIRECT_PRICE_DENOMINATION_COMPATIBILITY"
AUTHORITY = {"trade_decision": False, "financial_risk": False, "execution": False}
EXCLUSIONS = (
    "CURRENT_CANDIDATE_ACTIONABILITY", "SUPPLIED_QUANTITY_LOSS", "QUANTITY_SELECTION",
    "ACCOUNT_BINDING", "BALANCE_EQUITY", "ACCOUNT_RISK", "MAXIMUM_PERMITTED_LOSS",
    "RISK_HEADROOM", "FX", "SPREAD", "SLIPPAGE", "COMMISSION", "SWAP", "MARGIN",
    "EXECUTABLE_BID_ASK", "TICK_ORDER_ROUNDING", "MIN_MAX_QUANTITY", "QUANTITY_STEP",
    "CANDIDATE_COMPLIANCE", "TRADE_AUTHORIZATION", "EXECUTION",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _same(value, expected, label):
    if _canonical(value) != _canonical(expected):
        raise ValueError(label + " differs from owner-reconstructed content.")


def _decimal(text):
    """Exact signed integer coefficient/scale; input is already validated or repr."""
    match = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?", text)
    if match is None:
        raise ValueError("Malformed decimal representation.")
    sign, whole, fraction, exponent = match.groups()
    fraction = fraction or ""
    coefficient = int(whole + fraction) * (-1 if sign else 1)
    scale = len(fraction) - int(exponent or "0")
    if scale < 0:
        coefficient *= 10 ** -scale
        scale = 0
    return coefficient, scale


def _price(value):
    if type(value) is bool:
        raise ValueError("Malformed boolean price.")
    if type(value) is int:
        return value, 0
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite price.")
        return _decimal(repr(value))
    return None


def _plain(value):
    coefficient, scale = value
    if coefficient == 0:
        return "0"
    negative = coefficient < 0
    digits = str(-coefficient if negative else coefficient)
    if scale:
        digits = digits.zfill(scale + 1)
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if negative else "") + digits


def _distance(entry, stop, direction):
    scale = max(entry[1], stop[1])
    difference = entry[0] * 10 ** (scale - entry[1]) - stop[0] * 10 ** (scale - stop[1])
    if direction == "SHORT":
        difference = -difference
    if difference <= 0:
        raise ValueError("INTERPRETED_GEOMETRY_INCONSISTENCY")
    return difference, scale


def _assertions(values, formulation, selected):
    if type(values) is not list:
        raise ValueError("Bridge assertions require a list.")
    revisions, normalized = {}, {}
    for supplied in values:
        metadata._keys(supplied, {"contract", "assertion_revision_id", "source", "available_at",
                                  "candidate_formulation", "selected_specification", "relationship", "verdict"})
        metadata._enum(supplied["contract"], {ASSERTION_CONTRACT})
        metadata._opaque(supplied["assertion_revision_id"])
        metadata._keys(supplied["source"], {"source_id", "source_contract", "source_contract_version"})
        for value in supplied["source"].values():
            metadata._opaque(value)
        metadata._enum(supplied["relationship"], {RELATIONSHIP})
        metadata._enum(supplied["verdict"], {"COMPATIBLE", "INCOMPATIBLE"})
        _same(supplied["candidate_formulation"], formulation, "Bridge technical subject")
        if selected is None:
            raise ValueError("Bridge requires an exact selected specification.")
        _same(supplied["selected_specification"], selected, "Bridge financial subject")
        row = deepcopy(supplied)
        row["available_at"] = metadata._timestamp(row["available_at"])
        encoded = _canonical(row)
        revision = row["assertion_revision_id"]
        if revision in revisions and revisions[revision] != encoded:
            raise ValueError("Conflicting assertion revision content.")
        revisions[revision] = encoded
        normalized[encoded] = row
    rows = [normalized[key] for key in sorted(normalized)]
    if len({row["verdict"] for row in rows}) > 1:
        raise ValueError("Contradictory bridge assertions.")
    return rows


def _analyze(payload):
    metadata._keys(payload, {"contract", "rule_version", "knowledge_boundary", "candidate_formulation",
                             "formulation_input", "applicability", "applicability_input", "bridge_assertions"})
    metadata._enum(payload["contract"], {CONTRACT})
    metadata._enum(payload["rule_version"], {RULE_VERSION})
    k = metadata._timestamp(payload["knowledge_boundary"])
    formulation = candidates.validate_technical_candidate_formulation(
        payload["candidate_formulation"], payload["formulation_input"])
    candidate = formulation["candidate"]
    if candidate is None:
        raise ValueError("Measurement requires a formulated frozen candidate.")
    t = metadata._timestamp(candidate["valid_from"])
    completion = candle_completion(candidate["entry_reference"]["evidence"]["candle"]["timestamp"], "M1")
    if t != metadata._timestamp(completion):
        raise ValueError("Candidate entry boundary is not T1 completion.")
    resolved = applicability.validate_causal_instrument_specification_applicability_resolver_v2(
        payload["applicability"], payload["applicability_input"])
    selected = None
    # Revalidate all revisions; never accept an independently supplied selected artifact.
    for item in payload["applicability_input"]["specification_revisions"]:
        artifact = applicability._validate_metadata_version(item["snapshot"], item["snapshot_input"])
        if artifact["specification"]["source"] == resolved["selected_revision"]:
            _same(applicability._artifact_reference(artifact), resolved["selected_specification_snapshot_reference"],
                  "Selected specification reference")
            selected = artifact
    rows = _assertions(payload["bridge_assertions"], formulation, selected)
    entry = _price(candidate["entry_reference"]["value"])
    stop = _price(candidate["stop_reference"]["value"])
    distance = None if entry is None or stop is None else _distance(entry, stop, candidate["direction"])
    # All supplied content has been checked before normal blockers are considered.
    if resolved["requested_knowledge_boundary"] != k or resolved["economic_timestamp"] != t:
        raise ValueError("Applicability T/K differs from measurement scenario.")
    if t > k or metadata._timestamp(formulation["upstream_formulation"]["knowledge_boundary"]) > k:
        raise ValueError("Frozen candidate evidence is unavailable by K.")
    if any(row["available_at"] > k for row in rows):
        raise ValueError("Supplied bridge assertion is unavailable by K.")
    decisive, missing = [], []
    if entry is None or stop is None:
        decisive.append("UNSUPPORTED_PRICE_REPRESENTATION")
    coefficient = currency = unit = None
    if selected is None:
        missing.append(resolved["outcome"])
    else:
        spec = selected["specification"]
        unit = spec["position_namespace"]["quantity_unit"]
        if selected["contract"] == metadata.CONTRACT:
            decisive.append("SELECTED_METADATA_HAS_NO_PAYOFF")
        else:
            terms = spec["payoff"]
            currency = terms["pnl_currency"]
            if terms["model"] is not None and terms["model"] != payoff.MODEL:
                decisive.append("UNSUPPORTED_PAYOFF_MODEL")
            if terms["uniformity"] == "NONUNIFORM":
                decisive.append("NONUNIFORM_PAYOFF")
            if selected["payoff_model_support"] == "SUPPORTED" and selected["payoff_completeness"] == "COMPLETE":
                coefficient = terms["payoff_units_per_quantity_unit"]
            else:
                missing.append("INCOMPLETE_PAYOFF_EVIDENCE")
    if rows and rows[0]["verdict"] == "INCOMPATIBLE":
        decisive.append("DIRECT_PRICE_DOMAIN_INCOMPATIBLE")
    if not rows:
        missing.append("MISSING_BRIDGE_PROOF")
    outcome = "NOT_MEASURABLE" if decisive else "UNKNOWN" if missing else "MEASURED"
    monetary = None
    if outcome == "MEASURED":
        factor = _decimal(coefficient)
        monetary = _plain((distance[0] * factor[0], distance[1] + factor[1]))
    result = {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "scenario": SCENARIO,
        "numeric_interpretation": NUMERIC_RULE, "candidate_formulation": formulation,
        "bridge_assertions": rows, "applicability": resolved, "selected_specification": selected,
        "economic_timestamp": t, "knowledge_boundary": k,
        "interpreted_entry": None if entry is None else _plain(entry),
        "interpreted_stop": None if stop is None else _plain(stop),
        "reference_price_distance": None if distance is None else _plain(distance),
        "payoff_units_per_quantity_unit": coefficient, "pnl_currency": currency, "quantity_unit": unit,
        "outcome": outcome, "reasons": decisive if decisive else missing if missing else ["GROSS_REFERENCE_LOSS_MEASURED"],
        "gross_reference_loss_per_quantity_unit": monetary,
        "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "authority": dict(AUTHORITY), "exclusions": list(EXCLUSIONS),
    }
    result["assessment_identity"] = identity("candidate_gross_reference_measurement_", result)
    return result


@dataclass(frozen=True)
class CandidateGrossReferenceFinancialMeasurementResult:
    _payload: dict

    @property
    def payload(self):
        return deepcopy(self._payload)

    def to_dict(self):
        return deepcopy(self._payload)


class XAUUSDCandidateGrossReferenceFinancialMeasurementAnalyzer:
    def analyze(self, payload):
        try:
            return CandidateGrossReferenceFinancialMeasurementResult(_analyze(payload))
        except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed gross reference measurement input.") from exc


XAUUSD_CANDIDATE_GROSS_REFERENCE_FINANCIAL_MEASUREMENT = XAUUSDCandidateGrossReferenceFinancialMeasurementAnalyzer()


def validate_candidate_gross_reference_financial_measurement(value, measurement_input):
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = XAUUSD_CANDIDATE_GROSS_REFERENCE_FINANCIAL_MEASUREMENT.analyze(measurement_input).to_dict()
        _same(supplied, expected, "Measurement")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed serialized measurement.") from exc
