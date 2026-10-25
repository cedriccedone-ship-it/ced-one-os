"""Through-K, source-relative applicability; no governing or financial authority."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot as metadata
from ced_one.business_divisions.trading import causal_instrument_specification_lifecycle_evidence_snapshot as lifecycle
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id

CONTRACT = "trading.causal_instrument_specification_applicability_resolver.v1"
RULE_VERSION = "causal_instrument_specification_applicability_resolver_v1"
REFERENCE_FIELDS = ("source_id", "source_contract", "source_contract_version", "source_snapshot_id")
REASON_CODES = (
    "COVERAGE_LIMITED", "COVERAGE_UNKNOWN", "COVERAGE_CUTOFF_BEFORE_KNOWLEDGE_BOUNDARY",
    "CORRECTION_OF_CORRECTION", "MULTIPLE_CORRECTIONS_FOR_ASSERTION",
    "ACTIVE_SUPERSESSION_CYCLE", "POSITIVE_APPLICABILITY_WITHDRAWAL_CONFLICT",
    "SPECIFICATION_EFFECTIVE_START_CONFLICT", "MULTIPLE_APPLICABLE_CANDIDATES",
    "UNIQUE_APPLICABLE_REVISION_ESTABLISHED", "NO_APPLICABLE_CANDIDATE_ESTABLISHED",
)
LIMITATIONS = (
    "COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED", "GLOBAL_GOVERNING_SELECTION_NOT_PERFORMED",
    "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED",
    "VALUATION_NOT_PERFORMED", "PRICE_SELECTION_NOT_PERFORMED", "PRICE_SUITABILITY_NOT_EVALUATED",
    "FRESHNESS_NOT_EVALUATED", "FINANCIAL_EXPOSURE_NOT_CALCULATED", "POSITION_SIZING_NOT_PERFORMED",
)


def _keys(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Object requires exactly its declared fields.")


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


def _revision(reference: dict[str, Any]) -> tuple[str, ...]:
    return tuple(reference[key] for key in REFERENCE_FIELDS)


def _references(statement: dict[str, Any]) -> set[tuple[str, ...]]:
    if statement["kind"] == "CORRECTS":
        statement = statement["replacement_statement"]
        if statement is None:
            return set()
    fields = ("predecessor_revision", "successor_revision") if statement["kind"] == "SUPERSEDES" else ("revision",)
    return {_revision(statement[key]) for key in fields}


def _available(timing: dict[str, Any], boundary: str) -> None:
    if timing["observed_at"] > boundary or (
        timing["source_available_at"] is not None and timing["source_available_at"] > boundary
    ):
        raise ValueError("Consumed evidence was not causally available by K.")


def _artifact_reference(artifact: dict[str, Any]) -> dict[str, Any]:
    return {**{key: artifact[key] for key in ("contract", "rule_version", "snapshot_id")},
            "content_fingerprint": _hash_id("validated_owner_content_", artifact)}


def _has_cycle(edges: set[tuple[tuple[str, ...], tuple[str, ...]]]) -> bool:
    # Kahn traversal avoids recursion limits and collapses repeated evidence edges.
    successors: dict[tuple[str, ...], set[tuple[str, ...]]] = {}
    indegree: dict[tuple[str, ...], int] = {}
    for before, after in edges:
        successors.setdefault(before, set()).add(after)
        indegree.setdefault(before, 0)
        indegree[after] = indegree.get(after, 0) + 1
    ready = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for successor in successors.get(node, ()):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    return visited != len(indegree)


def _resolve(evidence: dict[str, Any], revisions: dict, economic: str, boundary: str):
    coverage = evidence["coverage"]
    if coverage["completeness"] == "LIMITED":
        return "UNRESOLVED", None, ["COVERAGE_LIMITED"]
    if coverage["completeness"] == "UNKNOWN":
        return "UNRESOLVED", None, ["COVERAGE_UNKNOWN"]
    if coverage["source_information_cutoff"] < boundary:
        return "UNRESOLVED", None, ["COVERAGE_CUTOFF_BEFORE_KNOWLEDGE_BOUNDARY"]

    assertions = {row["assertion_id"]: row for row in evidence["assertions"]}
    corrections: dict[str, list[dict[str, Any]]] = {}
    nested = False
    for row in assertions.values():
        statement = row["statement"]
        if statement["kind"] == "CORRECTS":
            target = statement["target_assertion_id"]
            corrections.setdefault(target, []).append(row)
            nested |= assertions[target]["statement"]["kind"] == "CORRECTS"
    reasons = []
    if nested:
        reasons.append("CORRECTION_OF_CORRECTION")
    if any(len(rows) > 1 for rows in corrections.values()):
        reasons.append("MULTIPLE_CORRECTIONS_FOR_ASSERTION")
    if reasons:
        return "UNRESOLVED", None, reasons

    positive, displaced, withdrawn, edges = set(), set(), set(), set()
    for identifier, row in assertions.items():
        statement = row["statement"]
        if statement["kind"] == "CORRECTS":
            continue
        if identifier in corrections:
            # The entire original is displaced, even when replacement is inactive.
            statement = corrections[identifier][0]["statement"]["replacement_statement"]
        if statement is None:
            continue
        scope = statement["economic_scope"]
        if economic < scope["effective_from"] or (
            scope["effective_until"] is not None and economic >= scope["effective_until"]
        ):
            continue
        if statement["kind"] == "SUPERSEDES":
            before, after = (_revision(statement[key]) for key in ("predecessor_revision", "successor_revision"))
            positive.add(after)
            displaced.add(before)
            edges.add((before, after))
        elif statement["kind"] == "APPLIES":
            positive.add(_revision(statement["revision"]))
        else:
            withdrawn.add(_revision(statement["revision"]))
    if _has_cycle(edges):
        reasons.append("ACTIVE_SUPERSESSION_CYCLE")
    if positive & withdrawn:
        reasons.append("POSITIVE_APPLICABILITY_WITHDRAWAL_CONFLICT")
    if any(revisions[key]["specification"]["timing"]["effective_at"] > economic for key in positive):
        reasons.append("SPECIFICATION_EFFECTIVE_START_CONFLICT")
    if reasons:
        return "UNRESOLVED", None, reasons
    candidates = positive - displaced
    if len(candidates) > 1:
        return "UNRESOLVED", None, ["MULTIPLE_APPLICABLE_CANDIDATES"]
    if candidates:
        return "UNIQUE_APPLICABLE_REVISION", next(iter(candidates)), ["UNIQUE_APPLICABLE_REVISION_ESTABLISHED"]
    return "NO_APPLICABLE_REVISION_ESTABLISHED", None, ["NO_APPLICABLE_CANDIDATE_ESTABLISHED"]


def _normalize(payload: Any) -> dict[str, Any]:
    _keys(payload, {"contract", "rule_version", "requested_knowledge_boundary", "economic_timestamp",
                    "lifecycle_evidence", "specification_revisions"})
    for key, expected in (("contract", CONTRACT), ("rule_version", RULE_VERSION)):
        if type(payload[key]) is not str or payload[key] != expected:
            raise ValueError("Unsupported resolver contract or rule.")
    boundary = _timestamp(payload["requested_knowledge_boundary"])
    economic = _timestamp(payload["economic_timestamp"])
    supplied = payload["lifecycle_evidence"]
    _keys(supplied, {"snapshot", "snapshot_input"})
    if type(payload["specification_revisions"]) is not list:
        raise ValueError("Specification revisions must be a list.")
    evidence_artifact = lifecycle.validate_causal_instrument_specification_lifecycle_evidence_snapshot(
        supplied["snapshot"], supplied["snapshot_input"])
    evidence = evidence_artifact["evidence"]
    validated = []
    for entry in payload["specification_revisions"]:
        _keys(entry, {"snapshot", "snapshot_input"})
        validated.append(metadata.validate_causal_financial_instrument_contract_metadata_snapshot(
            entry["snapshot"], entry["snapshot_input"]))
    required = set()
    for row in evidence["assertions"]:
        required.update(_references(row["statement"]))
    revisions = {}
    for artifact in validated:
        spec = artifact["specification"]
        key = _revision(spec["source"])
        if key in revisions:
            raise ValueError("Duplicate or incompatible specification revision representation.")
        if spec["position_namespace"] != evidence["target_namespace"]:
            raise ValueError("Specification namespace differs from lifecycle target.")
        revisions[key] = artifact
    if set(revisions) != required:
        raise ValueError("Specification collection must match every and only referenced revision.")
    for timing in [evidence["timing"], evidence["coverage"]["timing"]]:
        _available(timing, boundary)
    for row in evidence["assertions"]:
        _available(row["timing"], boundary)
    for artifact in validated:
        _available(artifact["specification"]["timing"], boundary)
    cutoff = evidence["coverage"]["source_information_cutoff"]
    if cutoff is not None and cutoff > boundary:
        raise ValueError("Coverage cutoff exceeds K.")

    outcome, selected, reasons = _resolve(evidence, revisions, economic, boundary)
    references = [{"revision": deepcopy(revisions[key]["specification"]["source"]),
                   "snapshot_reference": _artifact_reference(revisions[key])} for key in sorted(revisions)]
    return {
        "contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
        "requested_knowledge_boundary": boundary, "economic_timestamp": economic,
        "target_namespace": deepcopy(evidence["target_namespace"]),
        "reporting_source": deepcopy(evidence["source"]),
        "coverage": {"completeness": evidence["coverage"]["completeness"], "source_information_cutoff": cutoff},
        "lifecycle_evidence_reference": _artifact_reference(evidence_artifact),
        "specification_revision_references": references, "outcome": outcome,
        "selected_revision": None if selected is None else deepcopy(revisions[selected]["specification"]["source"]),
        "selected_specification_snapshot_reference": None if selected is None else _artifact_reference(revisions[selected]),
        "reason_codes": reasons, "source_authentication": "NOT_VERIFIED_BY_THIS_CAPABILITY",
        "limitations": list(LIMITATIONS),
        "authority": {"trade_decision": False, "financial_risk": False, "execution": False},
    }


@dataclass(frozen=True)
class CausalInstrumentSpecificationApplicabilityResolverResult:
    resolution_id: str
    _payload: dict[str, Any]

    @property
    def payload(self) -> dict[str, Any]:
        return deepcopy(self._payload)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": "snapshot_deterministic",
                         "resolution_id": self.resolution_id, **self._payload})


class CausalInstrumentSpecificationApplicabilityResolverAnalyzer:
    def analyze(self, payload: Any) -> CausalInstrumentSpecificationApplicabilityResolverResult:
        result = _normalize(payload)
        return CausalInstrumentSpecificationApplicabilityResolverResult(
            _hash_id("instrument_specification_applicability_resolution_", result), result)


CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER = CausalInstrumentSpecificationApplicabilityResolverAnalyzer()


def validate_causal_instrument_specification_applicability_resolver(value: Any, resolver_input: Any) -> dict[str, Any]:
    """Reconstruct all owned content and bindings without authenticating evidence."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER.analyze(resolver_input).to_dict()
        if json.dumps(supplied, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError("Applicability resolution content or input binding mismatch.")
        return expected
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed serialized applicability resolution.") from exc
