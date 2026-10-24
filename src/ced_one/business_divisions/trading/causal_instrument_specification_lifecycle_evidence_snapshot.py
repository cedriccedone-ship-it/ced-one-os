"""Source-relative lifecycle assertions and coverage, without applicability resolution."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_instrument_specification_lifecycle_evidence_snapshot.v1"
RULE_VERSION = "causal_instrument_specification_lifecycle_evidence_snapshot_v1"
KINDS = ("APPLIES", "SUPERSEDES", "WITHDRAWS", "CORRECTS")


def _keys(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Object requires exactly its declared fields.")


def _opaque(value: Any) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("Identifier must contain a non-whitespace character.")


def _enum(value: Any, allowed: set[str]) -> None:
    if type(value) is not str or value not in allowed:
        raise ValueError("Unsupported contract value.")


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


def _reference(value: Any) -> dict[str, Any]:
    _keys(value, {"source_id", "source_contract", "source_contract_version", "source_snapshot_id"})
    for identifier in value.values():
        _opaque(identifier)
    return deepcopy(value)


def _timing(value: Any, boundary: str) -> dict[str, Any]:
    _keys(value, {"observed_at", "source_available_at"})
    observed = _timestamp(value["observed_at"])
    available = None if value["source_available_at"] is None else _timestamp(value["source_available_at"])
    if observed > boundary or (available is not None and available > observed):
        raise ValueError("Evidence was not causally available at the supplied boundary.")
    return {"observed_at": observed, "source_available_at": available}


def _statement(value: Any, *, replacement: bool = False) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Statement must be an object.")
    kind = value.get("kind")
    _enum(kind, set(KINDS[:-1] if replacement else KINDS))
    if kind == "CORRECTS":
        _keys(value, {"kind", "target_assertion_id", "replacement_statement"})
        _opaque(value["target_assertion_id"])
        new = value["replacement_statement"]
        return {"kind": kind, "target_assertion_id": value["target_assertion_id"],
                "replacement_statement": None if new is None else _statement(new, replacement=True)}
    references = ("predecessor_revision", "successor_revision") if kind == "SUPERSEDES" else ("revision",)
    _keys(value, {"kind", "economic_scope", *references})
    normalized = {"kind": kind, **{key: _reference(value[key]) for key in references}}
    if kind == "SUPERSEDES" and normalized["predecessor_revision"] == normalized["successor_revision"]:
        raise ValueError("Supersession requires distinct revisions.")
    scope = value["economic_scope"]
    _keys(scope, {"effective_from", "effective_until"})
    start = _timestamp(scope["effective_from"])
    end = None if scope["effective_until"] is None else _timestamp(scope["effective_until"])
    if end is not None and end <= start:
        raise ValueError("Economic interval must have positive duration.")
    normalized["economic_scope"] = {"effective_from": start, "effective_until": end}
    return normalized


def _coverage(value: Any, boundary: str) -> dict[str, Any]:
    _keys(value, {"declaration_id", "timing", "completeness", "assertion_kinds", "economic_domain",
                  "source_information_cutoff", "starting_basis", "omissions"})
    _opaque(value["declaration_id"])
    _enum(value["completeness"], {"COMPLETE", "LIMITED", "UNKNOWN"})
    if type(value["assertion_kinds"]) is not list or value["assertion_kinds"] != list(KINDS):
        raise ValueError("Coverage requires the exact ordered assertion families.")
    _enum(value["economic_domain"], {"ALL_ECONOMIC_TIMES"})
    omissions = value["omissions"]
    _keys(omissions, {"assertions_omitted", "history_truncated"})
    timing = _timing(value["timing"], boundary)
    if value["completeness"] == "UNKNOWN":
        _enum(value["starting_basis"], {"UNKNOWN"})
        if value["source_information_cutoff"] is not None or any(flag is not None for flag in omissions.values()):
            raise ValueError("Unknown coverage cannot claim a cutoff or known omissions.")
        cutoff = None
    else:
        _enum(value["starting_basis"], {"FROM_INCEPTION"})
        cutoff = _timestamp(value["source_information_cutoff"])
        if any(type(flag) is not bool for flag in omissions.values()):
            raise ValueError("Known coverage requires boolean omission flags.")
        if any(omissions.values()) != (value["completeness"] == "LIMITED"):
            raise ValueError("Coverage completeness contradicts declared omissions.")
        if timing["source_available_at"] is None or cutoff > timing["source_available_at"]:
            raise ValueError("Known coverage requires publication at or after its cutoff.")
    result = deepcopy(value)
    result.update(timing=timing, source_information_cutoff=cutoff)
    return result


def _corrections(assertions: list[dict[str, Any]]) -> None:
    by_id = {item["assertion_id"]: item for item in assertions}
    targets = {}
    for item in assertions:
        statement = item["statement"]
        if statement["kind"] != "CORRECTS":
            continue
        identifier, target_id = item["assertion_id"], statement["target_assertion_id"]
        if target_id not in by_id or target_id == identifier:
            raise ValueError("Correction requires another assertion in this collection.")
        target, correction = by_id[target_id]["timing"], item["timing"]
        if target["observed_at"] > correction["observed_at"]:
            raise ValueError("Correction precedes target observation.")
        if (target["source_available_at"] is not None and correction["source_available_at"] is not None
                and target["source_available_at"] > correction["source_available_at"]):
            raise ValueError("Correction precedes target publication.")
        targets[identifier] = target_id
    # Only correction-reference cycles are structural errors; revision supersession is evidence.
    complete = set()
    for identifier in targets:
        visiting = set()
        current = identifier
        while current in targets and current not in complete:
            if current in visiting:
                raise ValueError("Cyclic correction references.")
            visiting.add(current)
            current = targets[current]
        complete.update(visiting)


def _normalize(payload: Any) -> dict[str, Any]:
    _keys(payload, {"contract", "rule_version", "requested_evaluation_timestamp", "evidence"})
    _enum(payload["contract"], {CONTRACT})
    _enum(payload["rule_version"], {RULE_VERSION})
    boundary = _timestamp(payload["requested_evaluation_timestamp"])
    evidence = payload["evidence"]
    _keys(evidence, {"source", "target_namespace", "timing", "coverage", "assertions"})
    source = _reference(evidence["source"])
    namespace = evidence["target_namespace"]
    _keys(namespace, {"source_id", "source_contract", "source_contract_version", "environment", "instrument_id", "quantity_unit"})
    for key, value in namespace.items():
        if key == "environment":
            _enum(value, {"DEMO", "LIVE"})
        else:
            _opaque(value)
    report = _timing(evidence["timing"], boundary)
    coverage = _coverage(evidence["coverage"], boundary)
    if coverage["timing"]["observed_at"] > report["observed_at"]:
        raise ValueError("Report precedes coverage observation.")
    if type(evidence["assertions"]) is not list:
        raise ValueError("Assertions must be a list.")
    assertions, identifiers = [], set()
    for item in evidence["assertions"]:
        _keys(item, {"assertion_id", "timing", "statement"})
        identifier = item["assertion_id"]
        _opaque(identifier)
        if identifier in identifiers:
            raise ValueError("Duplicate assertion identity.")
        identifiers.add(identifier)
        timing = _timing(item["timing"], boundary)
        if timing["observed_at"] > report["observed_at"]:
            raise ValueError("Report precedes assertion observation.")
        if coverage["completeness"] != "UNKNOWN":
            if timing["source_available_at"] is None or timing["source_available_at"] > coverage["source_information_cutoff"]:
                raise ValueError("Assertion publication exceeds known coverage or is unavailable.")
        assertions.append({"assertion_id": identifier, "timing": timing, "statement": _statement(item["statement"])})
    _corrections(assertions)
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "requested_evaluation_timestamp": boundary,
        "evidence": {"source": source, "target_namespace": deepcopy(namespace), "timing": report,
                     "coverage": coverage, "assertions": sorted(assertions, key=lambda item: item["assertion_id"])},
        "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "limitations": ["GOVERNING_SELECTION_NOT_PERFORMED", "APPLICABILITY_RESOLUTION_NOT_PERFORMED",
                        "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED",
                        "SPECIFICATION_REFERENCES_NOT_VALIDATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED"],
        "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
    }


@dataclass(frozen=True)
class CausalInstrumentSpecificationLifecycleEvidenceSnapshotResult:
    snapshot_id: str
    _payload: dict[str, Any]

    @property
    def payload(self) -> dict[str, Any]:
        return deepcopy(self._payload)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
                         "snapshot_id": self.snapshot_id, **self._payload})


class CausalInstrumentSpecificationLifecycleEvidenceSnapshotAnalyzer:
    def analyze(self, payload: Any) -> CausalInstrumentSpecificationLifecycleEvidenceSnapshotResult:
        result = _normalize(payload)
        return CausalInstrumentSpecificationLifecycleEvidenceSnapshotResult(
            _hash_id("instrument_specification_lifecycle_evidence_snapshot_", result), result)


CAUSAL_INSTRUMENT_SPECIFICATION_LIFECYCLE_EVIDENCE_SNAPSHOT = CausalInstrumentSpecificationLifecycleEvidenceSnapshotAnalyzer()


def validate_causal_instrument_specification_lifecycle_evidence_snapshot(value: Any, snapshot_input: Any) -> dict[str, Any]:
    """Reconstruct supplied evidence, without authenticating or resolving its claims."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_INSTRUMENT_SPECIFICATION_LIFECYCLE_EVIDENCE_SNAPSHOT.analyze(snapshot_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Lifecycle evidence content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized lifecycle evidence.") from exc
