"""One source-declared account observation; no financial-risk authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_financial_account_state_snapshot.v1"
RULE_VERSION = "causal_financial_account_state_snapshot_v1"
COMPLETENESS = {"COMPLETE", "PARTIAL", "UNAVAILABLE"}
MEASURES = ("balance", "equity", "used_margin", "free_margin")


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
    _keys(observation, {"account", "source", "timing", "account_measures", "positions", "pending_obligations"})
    account = observation["account"]
    _keys(account, {"account_id", "environment", "currency", "position_mode"})
    _opaque(account["account_id"])
    _enum(account["environment"], {"DEMO", "LIVE"})
    _enum(account["position_mode"], {"NETTING", "HEDGING", "UNKNOWN"})
    if type(account["currency"]) is not str or re.fullmatch(r"[A-Z]{3}", account["currency"]) is None:
        raise ValueError("Currency requires three uppercase ASCII letters.")
    source = observation["source"]
    _keys(source, {"source_id", "source_contract", "source_contract_version", "source_snapshot_id"})
    for value in source.values():
        _opaque(value)
    timing = observation["timing"]
    _keys(timing, {"effective_at", "observed_at", "source_available_at"})
    normalized_timing = {key: (None if key == "source_available_at" and value is None else _timestamp(value))
                         for key, value in timing.items()}
    effective, observed, available = (normalized_timing[key] for key in ("effective_at", "observed_at", "source_available_at"))
    if not effective <= observed <= boundary or (available is not None and not effective <= available <= observed):
        raise ValueError("Observation was not causally available at the supplied boundary.")
    measures = observation["account_measures"]
    _keys(measures, {"completeness", *MEASURES})
    _enum(measures["completeness"], COMPLETENESS)
    normalized_measures = {key: None if measures[key] is None else _decimal(measures[key]) for key in MEASURES}
    count = sum(value is not None for value in normalized_measures.values())
    expected = "COMPLETE" if count == 4 else "UNAVAILABLE" if count == 0 else "PARTIAL"
    if measures["completeness"] != expected:
        raise ValueError("Account-measure completeness contradicts supplied values.")
    used = normalized_measures["used_margin"]
    if used is not None and used.startswith("-"):
        raise ValueError("Used margin must be nonnegative.")
    normalized_measures["completeness"] = expected
    positions = observation["positions"]
    _keys(positions, {"completeness", "items"})
    _enum(positions["completeness"], COMPLETENESS)
    if type(positions["items"]) is not list:
        raise ValueError("Position inventory must be a list.")
    if positions["completeness"] == "UNAVAILABLE" and positions["items"]:
        raise ValueError("Unavailable inventory cannot contain positions.")
    items, identifiers, instruments = [], set(), set()
    for row in positions["items"]:
        _keys(row, {"position_id", "instrument_id", "direction", "quantity", "quantity_unit"})
        for key in ("position_id", "instrument_id", "quantity_unit"):
            _opaque(row[key])
        _enum(row["direction"], {"LONG", "SHORT"})
        quantity = _decimal(row["quantity"])
        if quantity == "0" or quantity.startswith("-"):
            raise ValueError("Position quantity must be strictly positive.")
        if row["position_id"] in identifiers:
            raise ValueError("Duplicate position identifier.")
        if account["position_mode"] == "NETTING" and row["instrument_id"] in instruments:
            raise ValueError("Netting inventory has multiple positions for one instrument.")
        identifiers.add(row["position_id"])
        instruments.add(row["instrument_id"])
        items.append({**row, "quantity": quantity})
    pending = observation["pending_obligations"]
    _keys(pending, {"scope"})
    _enum(pending["scope"], {"NOT_IN_SCOPE"})
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "requested_evaluation_timestamp": boundary,
        "observation": {"account": deepcopy(account), "source": deepcopy(source), "timing": normalized_timing,
                        "account_measures": normalized_measures,
                        "positions": {"completeness": positions["completeness"], "items": sorted(items, key=lambda row: row["position_id"])},
                        "pending_obligations": deepcopy(pending)},
        "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "limitations": ["PENDING_OBLIGATIONS_NOT_IN_SCOPE", "FINANCIAL_EXPOSURE_NOT_CALCULATED", "FRESHNESS_NOT_EVALUATED"],
        "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
    }


@dataclass(frozen=True)
class CausalFinancialAccountStateSnapshotResult:
    snapshot_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"snapshot_id": self.snapshot_id, **self.payload})


class CausalFinancialAccountStateSnapshotAnalyzer:
    def analyze(self, payload: Any) -> CausalFinancialAccountStateSnapshotResult:
        result = _normalize(payload)
        return CausalFinancialAccountStateSnapshotResult(
            _hash_id("financial_account_state_snapshot_", result), result)


CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT = CausalFinancialAccountStateSnapshotAnalyzer()


def validate_causal_financial_account_state_snapshot(value: Any, snapshot_input: Any) -> dict[str, Any]:
    """Reconstruct owned content, without authenticating source assertions."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(snapshot_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Account snapshot content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized account snapshot.") from exc
