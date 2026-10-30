"""Current conditional entry-to-original-stop loss function for Strategy #1.

This module reconstructs facts and an explicitly host-admitted planning inventory.
It neither authenticates sources nor decides a trade or a quantity.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any

from .causal_financial_account_state_snapshot import validate_causal_financial_account_state_snapshot
from .causal_financial_instrument_contract_metadata_snapshot import (
    CONTRACT as METADATA_V1_CONTRACT,
    validate_causal_financial_instrument_contract_metadata_snapshot,
)
from .causal_financial_instrument_contract_metadata_snapshot_v2 import (
    CONTRACT as PAYOFF_CONTRACT,
    MODEL as PAYOFF_MODEL,
    validate_causal_financial_instrument_contract_metadata_snapshot_v2,
)
from .causal_financial_price_observation_snapshot import validate_causal_financial_price_observation_snapshot
from .causal_instrument_specification_applicability_resolver import (
    validate_causal_instrument_specification_applicability_resolver_v2,
)
from .xauusd_technical_trade_candidate import (
    validate_technical_candidate_formulation,
    validate_technical_candidate_validity,
)

CONTRACT = "trading.xauusd_current_entry_to_stop_risk_basis.v1"
RULE_VERSION = "xauusd_current_entry_to_stop_risk_basis_v1"
SCENARIO_CONTRACT = "trading.xauusd_current_entry_to_stop_risk_basis.scenario_evidence.v1"
PLANNING_CONTRACT = "trading.xauusd_current_entry_to_stop_risk_basis.planning_evidence.v1"
PLANNING_RULE = "APPROVED_CONDITIONAL_PLANNING_SCENARIO_V1"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
RISK_MODEL = "POSITIVE_QUANTITY_LINEAR_PLUS_MINIMUM_AFFINE_CHARGES_V1"
AUTHORITY = {"trade_decision": False, "financial_risk": False, "execution": False}
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
LIMITATIONS = (
    "CONDITIONAL_PLANNING_ASSUMPTIONS",
    "REALIZED_LOSS_CEILING_NOT_GUARANTEED",
    "FILL_AND_STOP_EXECUTION_NOT_GUARANTEED",
    "SOURCE_AUTHENTICITY_NOT_VERIFIED",
    "FUTURE_MARKET_AND_SPECIFICATION_CHANGES_NOT_COVERED",
    "NO_AUTHORIZATION_LEASE",
)
EXCLUSIONS = (
    "QUANTITY_SELECTION", "BUDGET_COMPARISON", "PROVIDER_COMPLIANCE", "FX_CONVERSION",
    "MARGIN_CALCULATION", "ACTUAL_FILLS", "REALIZED_PNL", "STOP_MANAGEMENT",
    "BUY_SELL_AUTHORIZATION", "EXECUTION",
)
REQUEST_FIELDS = {
    "contract", "rule_version", "assessment_economic_time", "knowledge_boundary",
    "candidate", "validity", "applicability", "price_observations",
    "scenario_evidence", "planning_evidence", "account_state",
}
SCENARIO_FIELDS = {
    "entry_mechanism", "account_scope", "price_domain_relationship", "quote_event_id",
    "maximum_age_microseconds", "maximum_supported_quantity", "stop_trigger_side",
    "stop_trigger_comparator", "price_tick", "price_grid_origin",
    "minimum_trigger_distance", "adverse_entry_allowance", "adverse_stop_allowance",
    "continuation_assumption", "cost_scope", "cost_coverage", "charges",
}
SOURCE_TERMS = {
    "entry_mechanism", "account_scope", "price_domain_relationship",
    "maximum_supported_quantity", "stop_trigger_side", "stop_trigger_comparator",
    "price_tick", "price_grid_origin", "minimum_trigger_distance",
    "cost_scope", "cost_coverage", "charges",
}
CHARGE_CATEGORIES = {"opening_commission", "closing_commission", "other_charges", "financing"}
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def _keys(value: Any, fields: set[str] | tuple[str, ...]) -> None:
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("Object requires exactly its declared fields.")


def _list(value: Any) -> list:
    if type(value) is not list:
        raise ValueError("Expected a list.")
    return value


def _text(value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("Expected a nonblank identifier.")
    return value


def _enum(value: Any, values: set[str]) -> str:
    if type(value) is not str or value not in values:
        raise ValueError("Unsupported closed value.")
    return value


def _time(value: Any) -> str:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Timestamp requires seconds, timezone and at most six fractional digits.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid calendar timestamp.") from exc


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(_time(value).replace("Z", "+00:00"))


def _optional_time(value: Any) -> str | None:
    return None if value is None else _time(value)


def _decimal(value: Any, *, nonnegative: bool = False, positive: bool = False) -> str:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Financial terms require plain decimal strings.")
    fraction = Fraction(value)
    if (positive and fraction <= 0) or (nonnegative and fraction < 0):
        raise ValueError("Financial term has an inadmissible sign.")
    return _plain(fraction)


def _plain(value: Fraction) -> str:
    value = Fraction(value)
    if not value:
        return "0"
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("Nonterminating decimal is outside this model.")
    scale = max(twos, fives)
    coefficient = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(coefficient).zfill(scale + 1)
    if scale:
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if value < 0 else "") + digits


def _candidate_price(value: Any) -> Fraction | None:
    if type(value) is bool:
        raise ValueError("Boolean candidate price is malformed.")
    if type(value) is int:
        return Fraction(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite candidate price.")
        return Fraction(repr(value))
    return None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ref(value: dict) -> dict:
    return {"contract": value["contract"], "rule_version": value["rule_version"],
            "content_sha256": _digest(value)}


def _check_ref(value: Any, actual: dict | None) -> None:
    if actual is None:
        if value is not None:
            raise ValueError("Reference names an absent artifact.")
    else:
        _keys(value, {"contract", "rule_version", "content_sha256"})
        if _canonical(value) != _canonical(_ref(actual)):
            raise ValueError("Full-content reference mismatch.")


def _source(value: Any, *, revision: bool = False) -> dict:
    fields = {"source_id", "source_contract", "source_contract_version"}
    if revision:
        fields.add("source_snapshot_id")
    _keys(value, fields)
    for item in value.values():
        _text(item)
    return deepcopy(value)


def _scope(value: Any) -> dict | None:
    if value is None:
        return None
    _keys(value, {"environment", "account_id", "currency"})
    _enum(value["environment"], {"DEMO", "LIVE"})
    _text(value["account_id"])
    if type(value["currency"]) is not str or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None:
        raise ValueError("Account scope currency must be three uppercase letters.")
    return deepcopy(value)


def _interval(start: Any, end: Any) -> tuple[str, str | None]:
    first, last = _time(start), _optional_time(end)
    if last is not None and last <= first:
        raise ValueError("Effective interval must be nonempty.")
    return first, last


def _contains(start: str, end: str | None, when: str) -> bool:
    return start <= when and (end is None or when < end)


def _charge(value: Any) -> dict:
    _keys(value, {"charge_id", "category", "basis", "currency", "quantity_unit", "fixed", "per_unit", "minimum"})
    _text(value["charge_id"])
    _enum(value["category"], CHARGE_CATEGORIES)
    _enum(value["basis"], {"SOURCE_SCHEDULE", "SUPPORTED_SCENARIO_ENVELOPE"})
    _text(value["quantity_unit"])
    if type(value["currency"]) is not str or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None:
        raise ValueError("Charge currency must be three uppercase letters.")
    out = deepcopy(value)
    for key in ("fixed", "per_unit", "minimum"):
        out[key] = _decimal(value[key], nonnegative=True)
    return out


def _terms(value: Any) -> dict:
    _keys(value, SCENARIO_FIELDS)
    out = deepcopy(value)
    _text(value["entry_mechanism"])
    out["account_scope"] = _scope(value["account_scope"])
    _enum(value["price_domain_relationship"], {"DIRECT_UNTRANSFORMED", "INCOMPATIBLE", "UNKNOWN"})
    _text(value["quote_event_id"])
    age = value["maximum_age_microseconds"]
    if type(age) is not int or age < 0:
        raise ValueError("Freshness bound requires nonnegative integer microseconds.")
    out["maximum_supported_quantity"] = _decimal(value["maximum_supported_quantity"], positive=True)
    _enum(value["stop_trigger_side"], {"BID", "ASK", "UNSUPPORTED", "UNKNOWN"})
    _enum(value["stop_trigger_comparator"], {"LESS_THAN_OR_EQUAL", "GREATER_THAN_OR_EQUAL", "UNSUPPORTED", "UNKNOWN"})
    for key in ("price_tick", "minimum_trigger_distance"):
        out[key] = _decimal(value[key], positive=key == "price_tick", nonnegative=True)
    for key in ("price_grid_origin", "adverse_entry_allowance", "adverse_stop_allowance"):
        out[key] = _decimal(value[key], nonnegative=key != "price_grid_origin")
    _text(value["continuation_assumption"])
    _enum(value["cost_scope"], {"WHOLE_ENTRY_TO_TERMINAL_STOP", "INCOMPLETE", "UNKNOWN"})
    coverage = value["cost_coverage"]
    _keys(coverage, CHARGE_CATEGORIES)
    for state in coverage.values():
        _enum(state, {"INCLUDED", "NOT_APPLICABLE", "UNKNOWN", "UNSUPPORTED"})
    charges = [_charge(row) for row in _list(value["charges"])]
    ids = set()
    for row in charges:
        if row["charge_id"] in ids:
            raise ValueError("Duplicate charge ID.")
        ids.add(row["charge_id"])
        if coverage[row["category"]] != "INCLUDED":
            raise ValueError("Charge contradicts its category coverage.")
    out["charges"] = sorted(charges, key=lambda row: row["charge_id"])
    return out


def _static_terms(terms: dict) -> dict:
    return {key: deepcopy(terms[key]) for key in SCENARIO_FIELDS if key != "quote_event_id"}


def _source_terms(terms: dict) -> dict:
    return {key: deepcopy(terms[key]) for key in SOURCE_TERMS}


def _normalized_source_terms(value: Any) -> dict:
    _keys(value, SOURCE_TERMS)
    projected = {**value, "quote_event_id": "SOURCE_TERM_PROJECTION", "maximum_age_microseconds": 0,
                 "adverse_entry_allowance": "0", "adverse_stop_allowance": "0",
                 "continuation_assumption": "CURRENT_PAYOFF_AND_EXECUTION_TERMS_THROUGH_STOP"}
    return _source_terms(_terms(projected))


def _support_rows(value: Any, *, boundary: str) -> list[dict]:
    """Validate typed source claims; their provenance is not authentication."""
    result: dict[str, dict] = {}
    revisions: dict[tuple, str] = {}
    for raw in _list(value):
        _keys(raw, {"kind", "source", "observed_at", "source_available_at", "locator", "content"})
        kind = _enum(raw["kind"], {"SOURCE_DECLARED_TERM", "PLANNING_ASSUMPTION", "BROKER_CONSTRAINT"})
        source = _source(raw["source"])
        observed = _time(raw["observed_at"])
        available = _optional_time(raw["source_available_at"])
        if observed > boundary or (available is not None and available > observed):
            raise ValueError("Supporting evidence is unavailable by K.")
        locator = _text(raw["locator"])
        content = raw["content"]
        _keys(content, {"term", "value", "subjects"})
        term = _enum(content["term"], {"STATIC_SOURCE_TERMS", "COHERENT_BID_ASK_EVENT", "SPECIFICATION_ARTIFACT"})
        subjects = _list(content["subjects"])
        for subject in subjects:
            _keys(subject, {"contract", "rule_version", "content_sha256"})
            _text(subject["contract"])
            _text(subject["rule_version"])
            if type(subject["content_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", subject["content_sha256"]) is None:
                raise ValueError("Supporting subject requires full SHA-256.")
        if term == "SPECIFICATION_ARTIFACT":
            pair = content["value"]
            _keys(pair, {"snapshot", "snapshot_input"})
            artifact = (validate_causal_financial_instrument_contract_metadata_snapshot_v2(
                pair["snapshot"], pair["snapshot_input"]
            ) if pair["snapshot"]["contract"] == PAYOFF_CONTRACT else
                validate_causal_financial_instrument_contract_metadata_snapshot(
                    pair["snapshot"], pair["snapshot_input"]
                ) if pair["snapshot"]["contract"] == METADATA_V1_CONTRACT else None)
            if artifact is None:
                raise ValueError("Unsupported historical specification owner.")
            timing = artifact["specification"]["timing"]
            if timing["observed_at"] > boundary or (
                timing["source_available_at"] is not None and timing["source_available_at"] > boundary
            ):
                raise ValueError("Historical specification evidence is unavailable by K.")
            if timing["observed_at"] > observed or (
                timing["source_available_at"] is not None and timing["source_available_at"] > observed
            ):
                raise ValueError("Supporting row predates its specification evidence.")
            if subjects != [_ref(artifact)]:
                raise ValueError("Historical specification subject mismatch.")
            normalized_value = {"snapshot": artifact, "snapshot_input": deepcopy(pair["snapshot_input"])}
        elif term == "COHERENT_BID_ASK_EVENT":
            event = content["value"]
            _keys(event, {"quote_event_id", "venue_id", "bid_reference", "ask_reference"})
            _text(event["quote_event_id"])
            _text(event["venue_id"])
            for field in ("bid_reference", "ask_reference"):
                _keys(event[field], {"contract", "rule_version", "content_sha256"})
            if subjects != [event["bid_reference"], event["ask_reference"]]:
                raise ValueError("Coherent quote subjects do not match declared pair.")
            normalized_value = deepcopy(event)
        else:
            normalized_value = _normalized_source_terms(content["value"])
        row = {"kind": kind, "source": source, "observed_at": observed,
               "source_available_at": available, "locator": locator,
               "content": {"term": term, "value": normalized_value, "subjects": deepcopy(subjects)}}
        revision_key = (kind, _canonical(source), locator, term)
        encoded = _canonical(row)
        previous = revisions.setdefault(revision_key, encoded)
        if previous != encoded:
            raise ValueError("Conflicting supporting evidence revision.")
        result[encoded] = row
    return [result[key] for key in sorted(result)]


def _subjects(value: Any, *, candidate: dict, validity: dict, applicability: dict,
              selected: dict | None, prices: list[dict], account: dict | None) -> dict:
    fields = {"candidate", "validity", "applicability", "specification", "bid", "ask", "account"}
    _keys(value, fields)
    _check_ref(value["candidate"], candidate)
    _check_ref(value["validity"], validity)
    _check_ref(value["applicability"], applicability)
    _check_ref(value["specification"], selected)
    _check_ref(value["account"], account)
    for side in ("bid", "ask"):
        if value[side] is not None:
            _keys(value[side], {"contract", "rule_version", "content_sha256"})
            matches = [item for item in prices if _canonical(_ref(item)) == _canonical(value[side])
                       and item["observation"]["price_type"] == side.upper()]
            if len(matches) != 1:
                raise ValueError("Scenario price reference is absent or ambiguous.")
    return deepcopy(value)


def _scenario_rows(value: Any, *, boundary: str, candidate: dict, validity: dict,
                   applicability: dict, selected: dict | None, prices: list[dict],
                   account: dict | None) -> list[dict]:
    rows: dict[str, dict] = {}
    revisions: dict[tuple, str] = {}
    for raw in _list(value):
        _keys(raw, {"contract", "rule_version", "declaration_id", "declaration_revision", "source",
                    "observed_at", "source_available_at", "effective_from", "effective_until",
                    "subjects", "status", "terms", "reason", "supporting_evidence"})
        _enum(raw["contract"], {SCENARIO_CONTRACT})
        _enum(raw["rule_version"], {RULE_VERSION})
        _text(raw["declaration_id"])
        revision = raw["declaration_revision"]
        if type(revision) is not int or revision < 1:
            raise ValueError("Scenario revision must be a positive integer.")
        source = _source(raw["source"])
        observed = _time(raw["observed_at"])
        available = _optional_time(raw["source_available_at"])
        first, last = _interval(raw["effective_from"], raw["effective_until"])
        if observed > boundary or (available is not None and available > observed):
            raise ValueError("Scenario declaration is unavailable by K.")
        status = _enum(raw["status"], {"DECLARED", "INCOMPATIBLE", "UNSUPPORTED", "UNKNOWN"})
        if status == "DECLARED":
            if raw["reason"] is not None:
                raise ValueError("Declared scenario cannot carry a failure reason.")
            terms = _terms(raw["terms"])
        else:
            if raw["terms"] is not None:
                raise ValueError("Nondeclared scenario cannot carry terms.")
            _text(raw["reason"])
            terms = None
        subjects = _subjects(raw["subjects"], candidate=candidate, validity=validity,
                             applicability=applicability, selected=selected, prices=prices, account=account)
        support = _support_rows(raw["supporting_evidence"], boundary=boundary)
        events = {}
        for evidence in support:
            content = evidence["content"]
            if content["term"] == "COHERENT_BID_ASK_EVENT":
                event_id = content["value"]["quote_event_id"]
                encoded_event = _canonical(content["value"])
                if event_id in events and events[event_id] != encoded_event:
                    raise ValueError("Contradictory coherent quote-event evidence.")
                events[event_id] = encoded_event
                for side, field in (("BID", "bid_reference"), ("ASK", "ask_reference")):
                    matches = [price for price in prices if _ref(price) == content["value"][field]
                               and price["observation"]["price_type"] == side]
                    if len(matches) != 1:
                        raise ValueError("Coherent event references missing owner-valid prices.")
        row = {**deepcopy(raw), "source": source, "observed_at": observed,
               "source_available_at": available, "effective_from": first, "effective_until": last,
               "subjects": subjects, "terms": terms, "supporting_evidence": support}
        revision_key = (row["declaration_id"], revision)
        encoded = _canonical(row)
        previous = revisions.setdefault(revision_key, encoded)
        if previous != encoded:
            raise ValueError("Conflicting scenario declaration revision.")
        rows[encoded] = row
    result = [rows[key] for key in sorted(rows)]
    active = [row for row in result if _contains(row["effective_from"], row["effective_until"], boundary)]
    if len({_canonical((row["status"], row["terms"], row["subjects"])) for row in active}) > 1:
        raise ValueError("Contradictory active scenario declarations.")
    return result


def _context(value: Any, *, boundary: str) -> dict | None:
    if value is None:
        return None
    fields = {"authority_id", "authority_role", "mandate_id", "mandate_revision", "purpose",
              "policy_id", "scope", "effective_from", "effective_until", "available_at",
              "inventory_source", "inventory_content_sha256", "knowledge_boundary"}
    _keys(value, fields)
    for key in ("authority_id", "mandate_id", "policy_id"):
        _text(value[key])
    for key in ("mandate_revision",):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError("Mandate revision must be positive integer.")
    _enum(value["authority_role"], {"governance", "mission_control"})
    _enum(value["purpose"], {"CONDITIONAL_PLANNING_ASSUMPTION_USE_ONLY"})
    scope = value["scope"]
    _keys(scope, {"candidate_formulation_reference", "financial_namespace", "venue_id", "account_scope"})
    _keys(scope["candidate_formulation_reference"], {"contract", "rule_version", "content_sha256"})
    for key in ("contract", "rule_version"):
        _text(scope["candidate_formulation_reference"][key])
    if type(scope["candidate_formulation_reference"]["content_sha256"]) is not str or re.fullmatch(
        r"[0-9a-f]{64}", scope["candidate_formulation_reference"]["content_sha256"]
    ) is None:
        raise ValueError("Trusted candidate scope requires complete content digest.")
    namespace = scope["financial_namespace"]
    _keys(namespace, {"source_id", "source_contract", "source_contract_version",
                      "environment", "instrument_id", "quantity_unit"})
    for key in ("source_id", "source_contract", "source_contract_version", "instrument_id", "quantity_unit"):
        _text(namespace[key])
    _enum(namespace["environment"], {"DEMO", "LIVE"})
    _text(scope["venue_id"])
    _scope(scope["account_scope"])
    first, last = _interval(value["effective_from"], value["effective_until"])
    available = _time(value["available_at"])
    if available > boundary or _time(value["knowledge_boundary"]) != boundary:
        raise ValueError("Trusted dependency is unavailable or bound to another K.")
    _source(value["inventory_source"], revision=True)
    if type(value["inventory_content_sha256"]) is not str or re.fullmatch(
        r"[0-9a-f]{64}", value["inventory_content_sha256"]
    ) is None:
        raise ValueError("Inventory pin requires a complete SHA-256 digest.")
    return {**deepcopy(value), "effective_from": first, "effective_until": last,
            "available_at": available, "knowledge_boundary": boundary,
            "scope": {**deepcopy(scope), "account_scope": _scope(scope["account_scope"])}}


def _policy_definition(value: Any, *, boundary: str) -> dict:
    _keys(value, {"candidate_formulation_reference", "specification_reference", "venue_id",
                  "account_scope", "quote_source_binding", "terms", "source_term_evidence", "limitations"})
    for key in ("candidate_formulation_reference", "specification_reference"):
        _keys(value[key], {"contract", "rule_version", "content_sha256"})
        for field in ("contract", "rule_version"):
            _text(value[key][field])
        if type(value[key]["content_sha256"]) is not str or re.fullmatch(
            r"[0-9a-f]{64}", value[key]["content_sha256"]
        ) is None:
            raise ValueError("Policy subject needs full content digest.")
    _text(value["venue_id"])
    scope = _scope(value["account_scope"])
    source = _source(value["quote_source_binding"])
    _keys(value["terms"], SCENARIO_FIELDS - {"quote_event_id"})
    terms = _static_terms(_terms({**value["terms"], "quote_event_id": "STATIC_POLICY_PROJECTION"}))
    limitations = _list(value["limitations"])
    if type(limitations) is not list or set(limitations) != set(LIMITATIONS) or len(limitations) != len(LIMITATIONS):
        raise ValueError("Planning policy must retain all non-guarantee limitations.")
    support = _support_rows(value["source_term_evidence"], boundary=boundary)
    return {**deepcopy(value), "account_scope": scope, "quote_source_binding": source,
            "terms": terms, "source_term_evidence": support, "limitations": list(LIMITATIONS)}


def _record(value: Any, *, boundary: str) -> dict:
    _keys(value, {"approval_id", "approval_revision", "policy_version", "decision", "decided_at",
                  "observed_at", "source_available_at", "effective_from", "effective_until",
                  "supersedes", "policy_definition", "source", "authority"})
    _text(value["approval_id"])
    for key in ("approval_revision", "policy_version"):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError("Approval and policy versions must be positive integers.")
    decision = _enum(value["decision"], {"APPROVED", "REJECTED", "REVOKED"})
    decided, observed = _time(value["decided_at"]), _time(value["observed_at"])
    available = _optional_time(value["source_available_at"])
    first, last = _interval(value["effective_from"], value["effective_until"])
    if decided > observed or observed > boundary or (
        available is not None and not decided <= available <= observed
    ) or first < decided:
        raise ValueError("Approval has inadmissible decision, observation or effective time.")
    if decision in {"REJECTED", "REVOKED"} and last is not None:
        raise ValueError("Rejection and revocation persist until explicit successor.")
    predecessor = value["supersedes"]
    if predecessor is not None:
        _keys(predecessor, {"approval_id", "approval_revision", "content_sha256"})
        _text(predecessor["approval_id"])
        if type(predecessor["approval_revision"]) is not int or predecessor["approval_revision"] < 1:
            raise ValueError("Predecessor revision must be positive integer.")
        if type(predecessor["content_sha256"]) is not str or re.fullmatch(
            r"[0-9a-f]{64}", predecessor["content_sha256"]
        ) is None:
            raise ValueError("Predecessor needs complete digest.")
    source = _source(value["source"], revision=True)
    authority = value["authority"]
    _keys(authority, {"authority_id", "authority_role", "mandate_id", "mandate_revision", "purpose"})
    for key in ("authority_id", "mandate_id"):
        _text(authority[key])
    if type(authority["mandate_revision"]) is not int or authority["mandate_revision"] < 1:
        raise ValueError("Approval authority mandate revision must be positive.")
    _enum(authority["authority_role"], {"governance", "mission_control"})
    _enum(authority["purpose"], {"CONDITIONAL_PLANNING_ASSUMPTION_USE_ONLY"})
    definition = _policy_definition(value["policy_definition"], boundary=boundary)
    if decision == "APPROVED" and any(
        row["observed_at"] > decided or (
            row["source_available_at"] is not None and row["source_available_at"] > decided
        ) for row in definition["source_term_evidence"]
    ):
        raise ValueError("Approval adopts source evidence not yet available at decision time.")
    return {**deepcopy(value), "decided_at": decided, "observed_at": observed,
            "source_available_at": available, "effective_from": first, "effective_until": last,
            "source": source, "policy_definition": definition}


def _planning_inventory(value: Any, *, boundary: str) -> dict | None:
    if value is None:
        return None
    _keys(value, {"contract", "rule_version", "source", "observed_at", "source_available_at",
                  "authority_id", "authority_role", "mandate_id", "mandate_revision", "policy_id",
                  "coverage", "records"})
    _enum(value["contract"], {PLANNING_CONTRACT})
    _enum(value["rule_version"], {PLANNING_RULE})
    source = _source(value["source"], revision=True)
    observed, available = _time(value["observed_at"]), _optional_time(value["source_available_at"])
    if observed > boundary or (available is not None and available > observed):
        raise ValueError("Planning inventory was unavailable by K.")
    for key in ("authority_id", "mandate_id", "policy_id"):
        _text(value[key])
    _enum(value["authority_role"], {"governance", "mission_control"})
    if type(value["mandate_revision"]) is not int or value["mandate_revision"] < 1:
        raise ValueError("Inventory mandate revision must be positive integer.")
    coverage = value["coverage"]
    _keys(coverage, {"completeness", "economic_from", "economic_until", "source_information_cutoff"})
    _enum(coverage["completeness"], {"COMPLETE", "LIMITED", "UNKNOWN"})
    economic_from, economic_until = _interval(coverage["economic_from"], coverage["economic_until"])
    cutoff = _optional_time(coverage["source_information_cutoff"])
    if cutoff is not None and cutoff > boundary:
        raise ValueError("Planning coverage claims post-K information.")
    rows: dict[str, dict] = {}
    revisions: dict[tuple[str, int], str] = {}
    policy_versions: dict[int, str] = {}
    for raw in _list(value["records"]):
        row = _record(raw, boundary=boundary)
        if row["authority"]["authority_id"] != value["authority_id"] or (
            row["authority"]["authority_role"] != value["authority_role"] or
            row["authority"]["mandate_id"] != value["mandate_id"] or
            row["authority"]["mandate_revision"] != value["mandate_revision"]
        ):
            raise ValueError("Approval authority differs from inventory authority.")
        key = (row["approval_id"], row["approval_revision"])
        encoded = _canonical(row)
        if key in revisions and revisions[key] != encoded:
            raise ValueError("Conflicting approval revision.")
        revisions[key] = encoded
        version = row["policy_version"]
        definition = _canonical(row["policy_definition"])
        if version in policy_versions and policy_versions[version] != definition:
            raise ValueError("Policy version has conflicting definitions.")
        policy_versions[version] = definition
        rows[encoded] = row
    result = [rows[key] for key in sorted(rows)]
    return {**deepcopy(value), "source": source, "observed_at": observed,
            "source_available_at": available,
            "coverage": {"completeness": coverage["completeness"], "economic_from": economic_from,
                         "economic_until": economic_until, "source_information_cutoff": cutoff},
            "records": result}


def _history(inventory: dict, *, boundary: str) -> tuple[dict | None, str | None]:
    """Return governing explicit-chain decision and a coverage uncertainty."""
    records = inventory["records"]
    by_id = {(row["approval_id"], row["approval_revision"]): row for row in records}
    children: dict[tuple[str, int], dict] = {}
    roots = []
    for row in records:
        preceding = row["supersedes"]
        if preceding is None:
            roots.append(row)
            continue
        key = preceding["approval_id"], preceding["approval_revision"]
        parent = by_id.get(key)
        if parent is None or _digest(parent) != preceding["content_sha256"]:
            raise ValueError("Missing or mismatched exact approval predecessor.")
        if key in children:
            raise ValueError("Branching approval replacements.")
        if row["decided_at"] < parent["decided_at"] or row["observed_at"] < parent["observed_at"]:
            raise ValueError("Replacement precedes its predecessor.")
        if row["policy_version"] < parent["policy_version"]:
            raise ValueError("Policy version cannot go backwards.")
        if row["policy_definition"] != parent["policy_definition"] and (
            row["policy_version"] <= parent["policy_version"] or
            row["decision"] != "APPROVED"
        ):
            raise ValueError("Changed policy definition requires an approved newer version.")
        if row["decision"] == "REVOKED" and (
            row["policy_version"] != parent["policy_version"] or
            row["policy_definition"] != parent["policy_definition"]
        ):
            raise ValueError("Revocation must name the exact preceding policy.")
        children[key] = row
    if records and len(roots) != 1:
        raise ValueError("Approval history has a cycle or multiple roots.")
    chain = []
    if roots:
        current = roots[0]
        seen = set()
        while current is not None:
            key = current["approval_id"], current["approval_revision"]
            if key in seen:
                raise ValueError("Approval replacement cycle.")
            seen.add(key)
            chain.append(current)
            current = children.get(key)
        if len(chain) != len(records):
            raise ValueError("Disconnected approval history.")
    coverage = inventory["coverage"]
    if coverage["completeness"] != "COMPLETE" or coverage["source_information_cutoff"] != boundary or not _contains(
        coverage["economic_from"], coverage["economic_until"], boundary
    ):
        return None, "INCOMPLETE_PLANNING_HISTORY_COVERAGE"
    governing = None
    for row in chain:
        if row["effective_from"] <= boundary:
            governing = row
    return governing, None


def _selected_specification(resolved: dict, resolver_input: dict) -> dict | None:
    source = resolved["selected_revision"]
    if source is None:
        return None
    rows = [row for row in resolver_input["specification_revisions"]
            if row["snapshot"]["specification"]["source"] == source]
    if len(rows) != 1:
        raise ValueError("Selected revision has no unique owner input.")
    row = rows[0]
    if row["snapshot"]["contract"] != PAYOFF_CONTRACT:
        # #28 has already reconstructed the v1 artifact. It cannot supply v2 payoff.
        return deepcopy(row["snapshot"])
    selected = validate_causal_financial_instrument_contract_metadata_snapshot_v2(
        row["snapshot"], row["snapshot_input"]
    )
    reference = resolved["selected_specification_snapshot_reference"]
    if any(selected[key] != reference[key] for key in ("contract", "rule_version", "snapshot_id")):
        raise ValueError("Selected specification reference differs from owner artifact.")
    if {"revision": source, "snapshot_reference": reference} not in resolved["specification_revision_references"]:
        raise ValueError("Selected specification is absent from resolver references.")
    return selected


def _append_once(items: list[str], reason: str) -> None:
    if reason not in items:
        items.append(reason)


def _find_price(reference: dict | None, observations: list[dict]) -> dict | None:
    if reference is None:
        return None
    return next((item for item in observations if _ref(item) == reference), None)


def _match_static_support(definition: dict, formulation: dict, selected: dict) -> bool:
    expected_subjects = [_ref(formulation), _ref(selected)]
    static = definition["terms"]
    has_source = has_specification = False
    for row in definition["source_term_evidence"]:
        content = row["content"]
        if row["kind"] != "SOURCE_DECLARED_TERM":
            continue
        if content["term"] == "STATIC_SOURCE_TERMS" and content["subjects"] == expected_subjects:
            if _instant(row["observed_at"]) < _instant(formulation["candidate"]["valid_from"]):
                raise ValueError("Static source claim predates the formulated candidate.")
            if content["value"] != _source_terms(static):
                raise ValueError("Source-declared static terms contradict approved definition.")
            has_source = True
        if content["term"] == "SPECIFICATION_ARTIFACT" and content["subjects"] == [_ref(selected)]:
            has_specification = True
    return has_source and has_specification


def _quote_proof(rows: list[dict], *, bid: dict, ask: dict, event_id: str,
                 source: dict) -> bool:
    expected = {"quote_event_id": event_id, "bid_reference": _ref(bid),
                "ask_reference": _ref(ask)}
    for row in rows:
        content = row["content"]
        if content["term"] == "COHERENT_BID_ASK_EVENT":
            comparable = {key: content["value"][key] for key in expected}
            if content["value"]["quote_event_id"] == event_id and comparable != expected:
                raise ValueError("Conflicting coherent quote-event declaration.")
            if comparable == expected and row["kind"] == "SOURCE_DECLARED_TERM" and row["source"] == source:
                return True
    return False


def _evaluate(request: dict, trusted_planning_context: dict | None) -> dict:
    _keys(request, REQUEST_FIELDS)
    _enum(request["contract"], {CONTRACT})
    _enum(request["rule_version"], {RULE_VERSION})
    economic, boundary = _time(request["assessment_economic_time"]), _time(request["knowledge_boundary"])
    if economic != boundary:
        raise ValueError("Current economic time and knowledge boundary must be K.")

    _keys(request["candidate"], {"formulation", "formulation_input"})
    formulation = validate_technical_candidate_formulation(
        request["candidate"]["formulation"], request["candidate"]["formulation_input"]
    )
    candidate = formulation["candidate"]
    if candidate is None:
        raise ValueError("Current assessment requires a formed candidate.")
    if _instant(formulation["upstream_formulation"]["knowledge_boundary"]) > _instant(boundary):
        raise ValueError("Frozen candidate was not known by K.")

    _keys(request["validity"], {"assessment", "validity_input"})
    validity = validate_technical_candidate_validity(
        request["validity"]["assessment"], request["validity"]["validity_input"]
    )
    validity_input = request["validity"]["validity_input"]
    if _canonical(validity_input["candidate_formulation"]) != _canonical(formulation) or (
        _canonical(validity_input["formulation_input"]) != _canonical(request["candidate"]["formulation_input"])
    ) or validity["candidate_identity"] != candidate["candidate_identity"] or (
        _instant(validity["evaluation_boundary"]) != _instant(boundary)
    ):
        raise ValueError("Candidate validity does not bind this candidate at K.")

    _keys(request["applicability"], {"assessment", "resolver_input"})
    resolved = validate_causal_instrument_specification_applicability_resolver_v2(
        request["applicability"]["assessment"], request["applicability"]["resolver_input"]
    )
    if _instant(resolved["requested_knowledge_boundary"]) != _instant(boundary) or (
        _instant(resolved["economic_timestamp"]) != _instant(economic)
    ):
        raise ValueError("Applicability resolver must evaluate current T=K.")
    selected = _selected_specification(resolved, request["applicability"]["resolver_input"])

    price_pairs = []
    revisions = {}
    for pair in _list(request["price_observations"]):
        _keys(pair, {"snapshot", "snapshot_input"})
        artifact = validate_causal_financial_price_observation_snapshot(pair["snapshot"], pair["snapshot_input"])
        timing = artifact["observation"]["timing"]
        if _instant(artifact["requested_evaluation_timestamp"]) > _instant(boundary) or (
            _instant(timing["observed_at"]) > _instant(boundary)
        ) or (timing["source_available_at"] is not None and
              _instant(timing["source_available_at"]) > _instant(boundary)):
            raise ValueError("Price artifact was not causally admissible by K.")
        revision_key = (_canonical(artifact["observation"]["source"]), artifact["observation"]["price_type"])
        encoded = _canonical(artifact)
        if revision_key in revisions and revisions[revision_key] != encoded:
            raise ValueError("Conflicting price revision content.")
        revisions[revision_key] = encoded
        price_pairs.append({"snapshot": artifact, "snapshot_input": deepcopy(pair["snapshot_input"])})
    price_pairs.sort(key=lambda pair: _canonical(_ref(pair["snapshot"])))
    observations = [pair["snapshot"] for pair in price_pairs]
    if len({_canonical(_ref(item)) for item in observations}) != len(observations):
        raise ValueError("Duplicate price artifacts are ambiguous.")
    account = None
    if request["account_state"] is not None:
        _keys(request["account_state"], {"snapshot", "snapshot_input"})
        pair = request["account_state"]
        account = validate_causal_financial_account_state_snapshot(pair["snapshot"], pair["snapshot_input"])
        if _instant(account["requested_evaluation_timestamp"]) > _instant(boundary) or (
            _instant(account["observation"]["timing"]["observed_at"]) > _instant(boundary)
        ):
            raise ValueError("Account evidence was not causally available by K.")

    scenario_rows = _scenario_rows(request["scenario_evidence"], boundary=boundary,
                                   candidate=formulation, validity=validity, applicability=resolved,
                                   selected=selected, prices=observations, account=account)
    inventory = _planning_inventory(request["planning_evidence"], boundary=boundary)
    context = _context(trusted_planning_context, boundary=boundary)
    if context is not None and inventory is not None:
        if context["inventory_content_sha256"] != _digest(inventory) or (
            context["inventory_source"] != inventory["source"] or
            context["authority_id"] != inventory["authority_id"] or
            context["authority_role"] != inventory["authority_role"] or
            context["mandate_id"] != inventory["mandate_id"] or
            context["mandate_revision"] != inventory["mandate_revision"] or
            context["policy_id"] != inventory["policy_id"]
        ):
            raise ValueError("Trusted planning pin or issuer differs from complete inventory.")

    negative: list[str] = []
    uncertain: list[str] = []
    status = validity["status"]
    if status in {"INVALIDATED", "EXPIRED"}:
        _append_once(negative, "CANDIDATE_" + status)
    elif status == "UNKNOWN":
        _append_once(uncertain, "CANDIDATE_VALIDITY_UNKNOWN")
    if resolved["outcome"] != "UNIQUE_APPLICABLE_REVISION":
        _append_once(uncertain, "CURRENT_SPECIFICATION_NOT_UNIQUELY_ESTABLISHED")
    if selected is not None:
        if selected["contract"] != PAYOFF_CONTRACT:
            _append_once(negative, "SELECTED_METADATA_HAS_NO_PAYOFF")
        else:
            payoff = selected["specification"]["payoff"]
            if payoff["model"] is not None and payoff["model"] != PAYOFF_MODEL:
                _append_once(negative, "UNSUPPORTED_PAYOFF_MODEL")
            if payoff["uniformity"] == "NONUNIFORM":
                _append_once(negative, "NONUNIFORM_PAYOFF")
            if selected["payoff_model_support"] == "UNSUPPORTED":
                _append_once(negative, "UNSUPPORTED_PAYOFF_MODEL")
            elif selected["payoff_completeness"] != "COMPLETE" or payoff["model"] is None:
                _append_once(uncertain, "INCOMPLETE_PAYOFF_EVIDENCE")

    active = [row for row in scenario_rows if _contains(row["effective_from"], row["effective_until"], boundary)]
    declaration = active[0] if active else None
    terms = declaration["terms"] if declaration is not None else None
    if declaration is None:
        _append_once(uncertain, "MISSING_CURRENT_SCENARIO_DECLARATION")
    elif declaration["status"] in {"INCOMPATIBLE", "UNSUPPORTED"}:
        _append_once(negative, "SCENARIO_" + declaration["status"])
    elif declaration["status"] == "UNKNOWN":
        _append_once(uncertain, "SCENARIO_UNKNOWN")

    governing = None
    if inventory is None:
        _append_once(uncertain, "MISSING_PLANNING_INVENTORY")
    else:
        governing, coverage_reason = _history(inventory, boundary=boundary)
        if coverage_reason is not None:
            _append_once(uncertain, coverage_reason)
        elif governing is None:
            _append_once(uncertain, "MISSING_ACTIVE_PLANNING_APPROVAL")
        elif governing["decision"] != "APPROVED":
            _append_once(negative, "PLANNING_" + governing["decision"])
        elif not _contains(governing["effective_from"], governing["effective_until"], boundary):
            _append_once(negative, "PLANNING_APPROVAL_EXPIRED")
    if context is None:
        _append_once(uncertain, "MISSING_TRUSTED_PLANNING_CONTEXT")
    elif not _contains(context["effective_from"], context["effective_until"], boundary):
        _append_once(negative, "TRUSTED_PLANNING_MANDATE_EXPIRED")

    bid = ask = None
    if terms is not None:
        subject = declaration["subjects"]
        bid = _find_price(subject["bid"], observations)
        ask = _find_price(subject["ask"], observations)
        if terms["entry_mechanism"] != MECHANISM:
            _append_once(negative, "UNSUPPORTED_ENTRY_MECHANISM")
        if terms["price_domain_relationship"] == "INCOMPATIBLE":
            _append_once(negative, "DIRECT_PRICE_DOMAIN_INCOMPATIBLE")
        elif terms["price_domain_relationship"] == "UNKNOWN":
            _append_once(uncertain, "PRICE_DOMAIN_UNKNOWN")
        if terms["continuation_assumption"] != "CURRENT_PAYOFF_AND_EXECUTION_TERMS_THROUGH_STOP":
            _append_once(uncertain, "CONTINUATION_NOT_ESTABLISHED")
        if terms["cost_scope"] == "INCOMPLETE":
            _append_once(negative, "COST_SCOPE_INCOMPLETE")
        elif terms["cost_scope"] == "UNKNOWN":
            _append_once(uncertain, "COST_SCOPE_UNKNOWN")
        for category, coverage in terms["cost_coverage"].items():
            matching = [row for row in terms["charges"] if row["category"] == category]
            if coverage == "UNSUPPORTED":
                _append_once(negative, "UNSUPPORTED_COST_" + category.upper())
            elif coverage == "UNKNOWN" or (coverage == "INCLUDED" and not matching):
                _append_once(uncertain, "COST_COVERAGE_UNKNOWN_" + category.upper())
        if bid is None or ask is None:
            _append_once(uncertain, "MISSING_BID_ASK_PAIR")

    if selected is not None and terms is not None and selected["contract"] == PAYOFF_CONTRACT:
        spec = selected["specification"]
        if spec["position_namespace"]["instrument_id"] != candidate["instrument"]:
            _append_once(negative, "CANDIDATE_INSTRUMENT_NAMESPACE_MISMATCH")
        if terms["account_scope"] is not None:
            if account is None:
                _append_once(uncertain, "MISSING_SCOPED_ACCOUNT_EVIDENCE")
            else:
                actual_account = account["observation"]["account"]
                if any(actual_account[key] != terms["account_scope"][key] for key in
                       ("environment", "account_id", "currency")):
                    _append_once(negative, "ACCOUNT_SCOPE_MISMATCH")
                if spec["payoff"]["pnl_currency"] is not None and (
                    actual_account["currency"] != spec["payoff"]["pnl_currency"]
                ):
                    _append_once(negative, "ACCOUNT_PNL_CURRENCY_MISMATCH")
        elif account is not None and spec["payoff"]["pnl_currency"] is not None and (
            account["observation"]["account"]["currency"] != spec["payoff"]["pnl_currency"]
        ):
            _append_once(negative, "ACCOUNT_PNL_CURRENCY_MISMATCH")
        for charge in terms["charges"]:
            if charge["quantity_unit"] != spec["position_namespace"]["quantity_unit"] or (
                spec["payoff"]["pnl_currency"] is not None and
                charge["currency"] != spec["payoff"]["pnl_currency"]
            ):
                _append_once(negative, "COST_DIMENSION_MISMATCH")

    if bid is not None and ask is not None and terms is not None:
        b, a = bid["observation"], ask["observation"]
        if b["availability"] != "AVAILABLE" or a["availability"] != "AVAILABLE":
            _append_once(uncertain, "BID_ASK_UNAVAILABLE")
        elif Fraction(b["price"]) <= 0 or Fraction(a["price"]) <= 0 or Fraction(b["price"]) > Fraction(a["price"]):
            _append_once(negative, "INADMISSIBLE_CURRENT_QUOTE_GEOMETRY")
        if b["timing"]["price_time"] != a["timing"]["price_time"]:
            _append_once(negative, "BID_ASK_ECONOMIC_TIME_MISMATCH")
        if {key: b["source"][key] for key in ("source_id", "source_contract", "source_contract_version")} != (
            {key: a["source"][key] for key in ("source_id", "source_contract", "source_contract_version")}
        ):
            _append_once(negative, "BID_ASK_SUPPLIER_MISMATCH")
        if selected is not None:
            spec = selected["specification"]
            namespace = {key: spec["position_namespace"][key] for key in
                         ("source_id", "source_contract", "source_contract_version", "environment", "instrument_id")}
            denomination = {"specification_source": spec["source"],
                            "reference_asset_id": spec["economics"]["reference_asset_id"],
                            "reference_unit": spec["economics"]["reference_unit"],
                            "price_currency": spec["economics"]["price_currency"]}
            for observation in (b, a):
                if observation["target_namespace"] != namespace or observation["denomination"] != denomination:
                    _append_once(negative, "PRICE_SPECIFICATION_DIMENSION_MISMATCH")
        if b["target_namespace"]["instrument_id"] != candidate["instrument"]:
            _append_once(negative, "CANDIDATE_PRICE_INSTRUMENT_MISMATCH")
        quote_source = {key: b["source"][key] for key in
                        ("source_id", "source_contract", "source_contract_version")}
        for evidence in declaration["supporting_evidence"]:
            if evidence["content"]["term"] == "COHERENT_BID_ASK_EVENT" and evidence["content"]["value"]["quote_event_id"] == terms["quote_event_id"]:
                if evidence["observed_at"] < max(b["timing"]["observed_at"], a["timing"]["observed_at"]):
                    raise ValueError("Coherent-event evidence predates its referenced observations.")
        if not _quote_proof(declaration["supporting_evidence"], bid=bid, ask=ask,
                            event_id=terms["quote_event_id"], source=quote_source):
            _append_once(uncertain, "COHERENT_QUOTE_EVENT_NOT_ESTABLISHED")
        if governing is not None:
            for evidence in declaration["supporting_evidence"]:
                content = evidence["content"]
                if content["term"] == "COHERENT_BID_ASK_EVENT" and (
                    content["value"]["quote_event_id"] == terms["quote_event_id"] and
                    content["value"]["venue_id"] != governing["policy_definition"]["venue_id"]
                ):
                    _append_once(negative, "QUOTE_VENUE_MISMATCH")
        for observation in (b, a):
            elapsed = _instant(boundary) - _instant(observation["timing"]["price_time"])
            age = ((elapsed.days * 86_400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds)
            if age < 0:
                raise ValueError("Future price occurrence is inadmissible.")
            if age > terms["maximum_age_microseconds"]:
                _append_once(uncertain, "CURRENT_QUOTE_STALE")

    stop = _candidate_price(candidate["stop_reference"]["value"])
    if stop is None:
        _append_once(negative, "UNSUPPORTED_STOP_PRICE_REPRESENTATION")
    if stop is not None and terms is not None:
        tick, origin = Fraction(terms["price_tick"]), Fraction(terms["price_grid_origin"])
        if (stop - origin) / tick % 1:
            _append_once(negative, "ORIGINAL_STOP_OFF_TICK_GRID")
        direction = candidate["direction"]
        correct_side = "BID" if direction == "LONG" else "ASK"
        correct_comparator = "LESS_THAN_OR_EQUAL" if direction == "LONG" else "GREATER_THAN_OR_EQUAL"
        if terms["stop_trigger_side"] == "UNKNOWN" or terms["stop_trigger_comparator"] == "UNKNOWN":
            _append_once(uncertain, "STOP_TRIGGER_UNKNOWN")
        elif terms["stop_trigger_side"] != correct_side or terms["stop_trigger_comparator"] != correct_comparator:
            _append_once(negative, "STOP_TRIGGER_INCOMPATIBLE")
        if bid is not None and ask is not None and bid["observation"]["price"] is not None and (
            ask["observation"]["price"] is not None
        ):
            current_side = Fraction(bid["observation"]["price"] if direction == "LONG" else ask["observation"]["price"])
            clearance = current_side - stop if direction == "LONG" else stop - current_side
            if clearance <= 0:
                _append_once(negative, "ORIGINAL_STOP_ALREADY_TRIGGERED")
            elif clearance < Fraction(terms["minimum_trigger_distance"]):
                _append_once(negative, "MINIMUM_TRIGGER_DISTANCE_NOT_MET")

    if context is not None:
        if context["scope"]["candidate_formulation_reference"] != _ref(formulation):
            _append_once(negative, "TRUSTED_CANDIDATE_SCOPE_MISMATCH")
        if selected is not None and context["scope"]["financial_namespace"] != selected["specification"]["position_namespace"]:
            _append_once(negative, "TRUSTED_FINANCIAL_NAMESPACE_MISMATCH")
        if context["scope"]["account_scope"] is not None and account is None:
            _append_once(uncertain, "MISSING_TRUSTED_SCOPED_ACCOUNT")
        if account is not None and context["scope"]["account_scope"] is not None and any(
            account["observation"]["account"][key] != context["scope"]["account_scope"][key]
            for key in ("account_id", "environment", "currency")
        ):
            _append_once(negative, "TRUSTED_ACCOUNT_SCOPE_MISMATCH")

    if governing is not None and governing["decision"] == "APPROVED" and terms is not None:
        policy = governing["policy_definition"]
        if policy["candidate_formulation_reference"] != _ref(formulation) or (
            selected is not None and policy["specification_reference"] != _ref(selected)
        ) or policy["terms"] != _static_terms(terms) or policy["account_scope"] != terms["account_scope"]:
            _append_once(negative, "APPROVED_SCENARIO_SCOPE_OR_TERMS_MISMATCH")
        if context is not None and (policy["venue_id"] != context["scope"]["venue_id"] or
                                    policy["account_scope"] != context["scope"]["account_scope"]):
            _append_once(negative, "APPROVED_VENUE_OR_ACCOUNT_SCOPE_MISMATCH")
        if bid is not None:
            actual_source = {key: bid["observation"]["source"][key] for key in
                             ("source_id", "source_contract", "source_contract_version")}
            if policy["quote_source_binding"] != actual_source:
                _append_once(negative, "APPROVED_QUOTE_SOURCE_MISMATCH")
        if selected is not None and selected["contract"] == PAYOFF_CONTRACT and not _match_static_support(
            policy, formulation, selected
        ):
            _append_once(uncertain, "SOURCE_DECLARED_STATIC_TERMS_NOT_ESTABLISHED")

    if terms is not None and bid is not None and ask is not None and stop is not None and (
        bid["observation"]["price"] is not None and ask["observation"]["price"] is not None
    ):
        direction = candidate["direction"]
        entry_side = Fraction(ask["observation"]["price"] if direction == "LONG" else bid["observation"]["price"])
        entry_allowance = Fraction(terms["adverse_entry_allowance"])
        stop_allowance = Fraction(terms["adverse_stop_allowance"])
        entry = entry_side + entry_allowance if direction == "LONG" else entry_side - entry_allowance
        fill = stop - stop_allowance if direction == "LONG" else stop + stop_allowance
        distance = entry - fill if direction == "LONG" else fill - entry
        if entry <= 0 or fill <= 0 or distance <= 0:
            _append_once(negative, "ADVERSE_EXECUTION_GEOMETRY_INCOMPATIBLE")
    else:
        entry = fill = distance = None

    if negative:
        outcome, reasons = "NOT_SUITABLE", negative + uncertain
    elif uncertain:
        outcome, reasons = "UNKNOWN", uncertain
    else:
        outcome, reasons = "ESTABLISHED", ["CURRENT_ENTRY_TO_STOP_RISK_BASIS_ESTABLISHED"]
    scenario = risk_function = None
    if outcome == "ESTABLISHED":
        payoff = selected["specification"]["payoff"]
        coefficient = Fraction(payoff["payoff_units_per_quantity_unit"])
        scenario = {"mechanism": MECHANISM, "direction": candidate["direction"],
                    "entry_reference": _plain(entry_side), "order_entry_constraint": "NONE",
                    "original_stop": deepcopy(candidate["stop_reference"]["value"]),
                    "trigger_side": terms["stop_trigger_side"],
                    "trigger_comparator": terms["stop_trigger_comparator"],
                    "assessed_entry": _plain(entry), "assessed_stop_fill": _plain(fill),
                    "price_distance": _plain(distance)}
        risk_function = {"model": RISK_MODEL,
                         "quantity_unit": selected["specification"]["position_namespace"]["quantity_unit"],
                         "pnl_currency": payoff["pnl_currency"],
                         "maximum_supported_quantity": terms["maximum_supported_quantity"],
                         "zero_quantity_loss": "0", "price_loss_per_quantity_unit": _plain(coefficient * distance),
                         "charges": deepcopy(terms["charges"])}

    reconstruction = {
        "candidate": {"formulation": formulation, "formulation_input": deepcopy(request["candidate"]["formulation_input"])},
        "validity": {"assessment": validity, "validity_input": deepcopy(validity_input)},
        "applicability": {"assessment": resolved, "resolver_input": deepcopy(request["applicability"]["resolver_input"])},
        "selected_specification": selected,
        "price_observations": price_pairs,
        "scenario_evidence": scenario_rows,
        "planning_evidence": inventory,
        "trusted_planning_context_reference": None if context is None else _digest(context),
        "limitations": list(LIMITATIONS),
        "account_state": None if account is None else {"snapshot": account,
                                                         "snapshot_input": deepcopy(request["account_state"]["snapshot_input"])},
    }
    result = {"contract": CONTRACT, "rule_version": RULE_VERSION,
              "assessment_economic_time": economic, "knowledge_boundary": boundary,
              "candidate_identity": candidate["candidate_identity"],
              "reconstruction_evidence": reconstruction, "outcome": outcome, "reasons": reasons,
              "scenario": scenario, "risk_function": risk_function, "uncertainties": uncertain,
              "source_authentication": SOURCE_AUTHENTICATION, "authority": dict(AUTHORITY),
              "execution": False, "exclusions": list(EXCLUSIONS)}
    result["assessment_identity"] = "current_entry_to_stop_risk_basis_" + _digest(result)
    return result


def evaluate_current_entry_to_stop_risk_basis(
    request: dict, *, trusted_planning_context=None,
) -> dict:
    """Reconstruct the point-in-time conditional loss expression, if established."""
    try:
        return deepcopy(_evaluate(request, trusted_planning_context))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed current entry-to-stop risk-basis request.") from exc


def validate_current_entry_to_stop_risk_basis(
    assessment: dict, request: dict, *, trusted_planning_context=None,
) -> dict:
    """Independently reconstruct and compare complete assessment content."""
    try:
        expected = evaluate_current_entry_to_stop_risk_basis(
            request, trusted_planning_context=trusted_planning_context
        )
        if _canonical(assessment) != _canonical(expected):
            raise ValueError("Assessment differs from complete independent reconstruction.")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed serialized current risk-basis assessment.") from exc
