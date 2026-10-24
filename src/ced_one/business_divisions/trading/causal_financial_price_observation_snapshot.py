"""One supplied point-price revision, without selection or financial authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_financial_price_observation_snapshot.v1"
RULE_VERSION = "causal_financial_price_observation_snapshot_v1"


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
    _keys(payload, {"contract", "rule_version", "requested_evaluation_timestamp", "observation"})
    _enum(payload["contract"], {CONTRACT})
    _enum(payload["rule_version"], {RULE_VERSION})
    boundary = _timestamp(payload["requested_evaluation_timestamp"])
    observation = payload["observation"]
    _keys(observation, {"source", "target_namespace", "denomination", "timing", "price_type", "availability", "price"})
    denomination = observation["denomination"]
    _keys(denomination, {"specification_source", "reference_asset_id", "reference_unit", "price_currency"})
    for source in (observation["source"], denomination["specification_source"]):
        _keys(source, {"source_id", "source_contract", "source_contract_version", "source_snapshot_id"})
        for value in source.values():
            _opaque(value)
    namespace = observation["target_namespace"]
    _keys(namespace, {"source_id", "source_contract", "source_contract_version", "environment", "instrument_id"})
    for key, value in namespace.items():
        if key == "environment":
            _enum(value, {"DEMO", "LIVE"})
        else:
            _opaque(value)
    for key in ("reference_asset_id", "reference_unit"):
        _opaque(denomination[key])
    currency = denomination["price_currency"]
    if type(currency) is not str or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError("Price currency requires three uppercase ASCII letters.")
    _enum(observation["price_type"], {"BID", "ASK", "MID", "MARK", "LAST"})
    _enum(observation["availability"], {"AVAILABLE", "UNAVAILABLE"})
    if observation["availability"] == "AVAILABLE":
        price = _decimal(observation["price"])
    else:
        if observation["price"] is not None:
            raise ValueError("Unavailable price must be null.")
        price = None
    timing = observation["timing"]
    _keys(timing, {"price_time", "observed_at", "source_available_at"})
    normalized_timing = {key: None if key == "source_available_at" and value is None else _timestamp(value)
                         for key, value in timing.items()}
    market, observed, available = (normalized_timing[key] for key in ("price_time", "observed_at", "source_available_at"))
    if not market <= observed <= boundary or (available is not None and not market <= available <= observed):
        raise ValueError("Price observation was not causally available at the supplied boundary.")
    normalized = deepcopy(observation)
    normalized.update(timing=normalized_timing, price=price)
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "requested_evaluation_timestamp": boundary, "observation": normalized,
        "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "limitations": ["PRICE_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED",
                        "PRICE_SUITABILITY_NOT_EVALUATED", "SPECIFICATION_COMPATIBILITY_NOT_VALIDATED",
                        "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"],
        "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
    }


@dataclass(frozen=True)
class CausalFinancialPriceObservationSnapshotResult:
    snapshot_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"snapshot_id": self.snapshot_id, **self.payload})


class CausalFinancialPriceObservationSnapshotAnalyzer:
    def analyze(self, payload: Any) -> CausalFinancialPriceObservationSnapshotResult:
        result = _normalize(payload)
        return CausalFinancialPriceObservationSnapshotResult(
            _hash_id("financial_price_observation_snapshot_", result), result)


CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT = CausalFinancialPriceObservationSnapshotAnalyzer()


def validate_causal_financial_price_observation_snapshot(value: Any, snapshot_input: Any) -> dict[str, Any]:
    """Reconstruct complete owned content; do not authenticate source assertions."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(snapshot_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Price observation content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized price observation.") from exc
