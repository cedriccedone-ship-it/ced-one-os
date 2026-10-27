"""Whole instrument revision with explicit gross reference payoff; no calculation."""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from . import causal_financial_instrument_contract_metadata_snapshot as reference
from .causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_financial_instrument_contract_metadata_snapshot.v2"
RULE_VERSION = "causal_financial_instrument_contract_metadata_snapshot_v2"
MODEL = "LINEAR_SAME_CURRENCY_PAYOFF_V1"


def _normalize(payload):
    reference._keys(payload, {"contract", "rule_version", "requested_evaluation_timestamp", "specification"})
    reference._enum(payload["contract"], {CONTRACT})
    reference._enum(payload["rule_version"], {RULE_VERSION})
    spec = payload["specification"]
    reference._keys(spec, {"source", "position_namespace", "timing", "economic_model", "completeness", "economics", "payoff"})
    payoff = spec["payoff"]
    reference._keys(payoff, {"model", "payoff_units_per_quantity_unit", "pnl_currency", "uniformity"})
    reference._enum(payoff["uniformity"], {"UNIFORM", "NONUNIFORM", "UNKNOWN"})
    # Reuse reference validation only, not a supplied v1 artifact or its identity.
    projected = deepcopy(payload)
    projected.update(contract=reference.CONTRACT, rule_version=reference.RULE_VERSION)
    del projected["specification"]["payoff"]
    result = reference._normalize(projected)
    model = payoff["model"]
    if model is not None:
        reference._opaque(model)
    normalized = deepcopy(payoff)
    coefficient = payoff["payoff_units_per_quantity_unit"]
    currency = payoff["pnl_currency"]
    if coefficient is not None:
        coefficient = reference._decimal(coefficient)
        if coefficient == "0" or coefficient.startswith("-"):
            raise ValueError("Payoff coefficient must be strictly positive.")
        normalized["payoff_units_per_quantity_unit"] = coefficient
    if currency is not None and (type(currency) is not str or re.fullmatch(r"[A-Z]{3}", currency) is None):
        raise ValueError("P&L currency requires three uppercase ASCII letters.")
    support = "UNAVAILABLE" if model is None else "UNSUPPORTED"
    completeness = "UNAVAILABLE"
    if model == MODEL:
        economics = result["specification"]["economics"]
        price_currency = economics["price_currency"]
        if currency is not None and price_currency is not None and currency != price_currency:
            raise ValueError("Same-currency payoff contradicts price denomination.")
        support = "UNSUPPORTED" if payoff["uniformity"] == "NONUNIFORM" else "SUPPORTED"
        complete = all(v is not None for v in (coefficient, currency, economics["reference_asset_id"],
                                               economics["reference_unit"], price_currency))
        completeness = "COMPLETE" if complete and payoff["uniformity"] != "UNKNOWN" else "PARTIAL"
    elif coefficient is not None or currency is not None:
        raise ValueError("Unknown or unavailable payoff models cannot supply interpreted parameters.")
    result.update(contract=CONTRACT, rule_version=RULE_VERSION,
                  payoff_model_support=support, payoff_completeness=completeness)
    result["specification"]["payoff"] = normalized
    return result


@dataclass(frozen=True)
class CausalFinancialInstrumentContractMetadataSnapshotV2Result:
    snapshot_id: str
    _payload: dict

    @property
    def payload(self):
        return deepcopy(self._payload)

    def to_dict(self):
        return deepcopy({"snapshot_id": self.snapshot_id, **self._payload})


class CausalFinancialInstrumentContractMetadataSnapshotV2Analyzer:
    def analyze(self, payload):
        try:
            result = _normalize(payload)
            return CausalFinancialInstrumentContractMetadataSnapshotV2Result(
                _hash_id("financial_instrument_contract_metadata_snapshot_v2_", result), result)
        except (KeyError, TypeError, AttributeError, RecursionError) as exc:
            raise ValueError("Malformed payoff-bearing instrument specification.") from exc


CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2 = CausalFinancialInstrumentContractMetadataSnapshotV2Analyzer()


def validate_causal_financial_instrument_contract_metadata_snapshot_v2(value, snapshot_input):
    """Reconstruct full content; supplied source assertions remain unauthenticated."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2.analyze(snapshot_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Payoff specification content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized payoff specification.") from exc
