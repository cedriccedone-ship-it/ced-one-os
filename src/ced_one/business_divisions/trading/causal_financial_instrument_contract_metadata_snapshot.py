"""One supplied instrument specification revision, without valuation authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_financial_instrument_contract_metadata_snapshot.v1"
RULE_VERSION = "causal_financial_instrument_contract_metadata_snapshot_v1"
MODEL = "LINEAR_REFERENCE_NOTIONAL"
ECONOMICS = {"reference_asset_id", "reference_unit", "reference_units_per_quantity_unit", "price_currency"}


def _keys(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Object requires exactly its declared fields.")


def _opaque(value: Any) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("Identifier must contain a non-whitespace character.")


def _enum(value: Any, allowed: set[str]) -> None:
    if type(value) is not str or value not in allowed:
        raise ValueError("Unsupported contract value.")


def _decimal(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value) is None:
        raise ValueError("Financial values require plain decimal strings.")
    normalized = value.rstrip("0").rstrip(".") if "." in value else value
    return "0" if normalized in {"0", "-0"} else normalized


def _timestamp(value: Any) -> str:
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})"
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise ValueError("Timestamp requires seconds and an explicit timezone.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid calendar timestamp.") from exc


def _normalize(payload: Any) -> dict[str, Any]:
    _keys(payload, {"contract", "rule_version", "requested_evaluation_timestamp", "specification"})
    _enum(payload["contract"], {CONTRACT})
    _enum(payload["rule_version"], {RULE_VERSION})
    boundary = _timestamp(payload["requested_evaluation_timestamp"])
    spec = payload["specification"]
    _keys(spec, {"source", "position_namespace", "timing", "economic_model", "completeness", "economics"})
    source = spec["source"]
    _keys(source, {"source_id", "source_contract", "source_contract_version", "source_snapshot_id"})
    for value in source.values():
        _opaque(value)
    namespace = spec["position_namespace"]
    _keys(namespace, {"source_id", "source_contract", "source_contract_version", "environment", "instrument_id", "quantity_unit"})
    for key, value in namespace.items():
        if key == "environment":
            _enum(value, {"DEMO", "LIVE"})
        else:
            _opaque(value)
    timing = spec["timing"]
    _keys(timing, {"effective_at", "observed_at", "source_available_at"})
    normalized_timing = {key: None if key == "source_available_at" and value is None else _timestamp(value)
                         for key, value in timing.items()}
    effective, observed, available = (normalized_timing[key] for key in ("effective_at", "observed_at", "source_available_at"))
    # Announcements may precede their effective start; availability is independent.
    if observed > boundary or (available is not None and available > observed):
        raise ValueError("Specification was not causally available at the supplied boundary.")
    model = spec["economic_model"]
    if model is not None:
        _opaque(model)
    support = "UNAVAILABLE" if model is None else "SUPPORTED" if model == MODEL else "UNSUPPORTED"
    _enum(spec["completeness"], {"COMPLETE", "PARTIAL", "UNAVAILABLE"})
    economics = spec["economics"]
    _keys(economics, ECONOMICS)
    normalized_economics = deepcopy(economics)
    count = sum(value is not None for value in economics.values())
    if support != "SUPPORTED":
        if count or spec["completeness"] != "UNAVAILABLE":
            raise ValueError("Unsupported or unavailable models cannot supply interpreted economics.")
    else:
        for key in ("reference_asset_id", "reference_unit"):
            if economics[key] is not None:
                _opaque(economics[key])
        multiplier = economics["reference_units_per_quantity_unit"]
        if multiplier is not None:
            multiplier = _decimal(multiplier)
            if multiplier == "0" or multiplier.startswith("-"):
                raise ValueError("Reference units per quantity unit must be strictly positive.")
            normalized_economics["reference_units_per_quantity_unit"] = multiplier
        currency = economics["price_currency"]
        if currency is not None and (type(currency) is not str or re.fullmatch(r"[A-Z]{3}", currency) is None):
            raise ValueError("Price currency requires three uppercase ASCII letters.")
        expected = "COMPLETE" if count == 4 else "UNAVAILABLE" if count == 0 else "PARTIAL"
        if spec["completeness"] != expected:
            raise ValueError("Economics completeness contradicts supplied fields.")
    normalized = deepcopy(spec)
    normalized["timing"] = normalized_timing
    normalized["economics"] = normalized_economics
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "requested_evaluation_timestamp": boundary, "specification": normalized,
        "model_support": support,
        "effective_start_status": "EFFECTIVE_FROM_REACHED" if effective <= boundary else "FUTURE_EFFECTIVE",
        "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "limitations": ["REVISION_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED",
                        "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"],
        "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
    }


@dataclass(frozen=True)
class CausalFinancialInstrumentContractMetadataSnapshotResult:
    snapshot_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"snapshot_id": self.snapshot_id, **self.payload})


class CausalFinancialInstrumentContractMetadataSnapshotAnalyzer:
    def analyze(self, payload: Any) -> CausalFinancialInstrumentContractMetadataSnapshotResult:
        result = _normalize(payload)
        return CausalFinancialInstrumentContractMetadataSnapshotResult(
            _hash_id("financial_instrument_contract_metadata_snapshot_", result), result)


CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT = CausalFinancialInstrumentContractMetadataSnapshotAnalyzer()


def validate_causal_financial_instrument_contract_metadata_snapshot(value: Any, snapshot_input: Any) -> dict[str, Any]:
    """Reconstruct complete owned content; do not authenticate source assertions."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT.analyze(snapshot_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Instrument specification content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized instrument specification.") from exc
