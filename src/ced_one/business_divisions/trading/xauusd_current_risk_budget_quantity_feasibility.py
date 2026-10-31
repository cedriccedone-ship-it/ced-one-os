"""Current, independently admitted quantity feasibility; no quantity selection."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any

from .xauusd_account_specific_risk_policy_evaluation import validate_account_specific_risk_policy
from .xauusd_current_entry_to_stop_risk_basis import validate_current_entry_to_stop_risk_basis
from .xauusd_current_entry_quantity_domain import validate_current_entry_quantity_domain


CONTRACT = "trading.xauusd_current_risk_budget_quantity_feasibility.v1"
RULE_VERSION = "xauusd_current_risk_budget_quantity_feasibility_v1"
BINDING_CONTRACT = "trading.xauusd_current_risk_budget_quantity_feasibility.binding.v1"
BINDING_RULE = "xauusd_current_risk_budget_quantity_feasibility_binding_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_risk_budget_quantity_feasibility.admission.v1"
ADMISSION_RULE = "xauusd_current_risk_budget_quantity_feasibility_admission_v1"
PURPOSE = "FEASIBILITY_FACT_AND_BINDING_ADMISSION_ONLY"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
DOWNSTREAM_OBLIGATIONS = sorted((
    "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY", "MARKET_ORDER_AND_FILL_FEASIBILITY",
    "MISSION_CONTROL_CURRENT_AUTHORIZATION", "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE",
    "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM", "QUANTITY_SELECTION_POLICY_AND_SELECTION",
))
CLAIMS = ("account_provider_venue", "instrument_namespace", "quantity_denomination", "monetary_denomination")
ASSURANCES = ("source_authority", "fact_and_policy_semantics", "coverage_for_proposition", "causal_availability")
REASON_CODES = frozenset((
    "SUPPORTED_FEASIBLE_DOMAIN_ESTABLISHED", "CANDIDATE_NOT_CURRENTLY_VALID", "PRE_QUANTITY_POLICY_BLOCKED",
    "RISK_BASIS_UNUSABLE", "BINDING_INCOMPATIBLE", "ENTRY_DOMAIN_EMPTY", "NO_SUPPORTED_POSITIVE_QUANTITY",
    "BUDGET_BELOW_FIRST_SUPPORTED_QUANTITY_RISK", "OWNER_MISSING", "OWNER_UNKNOWN", "ADMISSION_MISSING",
    "ADMISSION_UNRESOLVED", "ADMISSION_NOT_CURRENT", "NEGATIVE_NOT_ADMITTED", "BINDING_MISSING",
    "BINDING_SUPPORT_MISSING", "BINDING_NOT_CURRENT", "BINDING_UNRESOLVED",
    "ACCOUNT_APPLICABILITY_UNRESOLVED", "POLICY_INSTRUMENT_NAMESPACE_UNRESOLVED",
))
NATIVE_RISK_NEGATIVES = frozenset("""
    CANDIDATE_INVALIDATED CANDIDATE_EXPIRED SELECTED_METADATA_HAS_NO_PAYOFF UNSUPPORTED_PAYOFF_MODEL
    NONUNIFORM_PAYOFF SCENARIO_INCOMPATIBLE SCENARIO_UNSUPPORTED PLANNING_REJECTED PLANNING_REVOKED
    PLANNING_APPROVAL_EXPIRED TRUSTED_PLANNING_MANDATE_EXPIRED UNSUPPORTED_ENTRY_MECHANISM
    DIRECT_PRICE_DOMAIN_INCOMPATIBLE COST_SCOPE_INCOMPLETE UNSUPPORTED_COST_OPENING_COMMISSION
    UNSUPPORTED_COST_CLOSING_COMMISSION UNSUPPORTED_COST_OTHER_CHARGES UNSUPPORTED_COST_FINANCING
    CANDIDATE_INSTRUMENT_NAMESPACE_MISMATCH ACCOUNT_SCOPE_MISMATCH ACCOUNT_PNL_CURRENCY_MISMATCH
    COST_DIMENSION_MISMATCH INADMISSIBLE_CURRENT_QUOTE_GEOMETRY BID_ASK_ECONOMIC_TIME_MISMATCH
    BID_ASK_SUPPLIER_MISMATCH PRICE_SPECIFICATION_DIMENSION_MISMATCH CANDIDATE_PRICE_INSTRUMENT_MISMATCH
    QUOTE_VENUE_MISMATCH UNSUPPORTED_STOP_PRICE_REPRESENTATION ORIGINAL_STOP_OFF_TICK_GRID
    STOP_TRIGGER_INCOMPATIBLE ORIGINAL_STOP_ALREADY_TRIGGERED MINIMUM_TRIGGER_DISTANCE_NOT_MET
    TRUSTED_CANDIDATE_SCOPE_MISMATCH TRUSTED_FINANCIAL_NAMESPACE_MISMATCH TRUSTED_ACCOUNT_SCOPE_MISMATCH
    APPROVED_SCENARIO_SCOPE_OR_TERMS_MISMATCH APPROVED_VENUE_OR_ACCOUNT_SCOPE_MISMATCH
    APPROVED_QUOTE_SOURCE_MISMATCH ADVERSE_EXECUTION_GEOMETRY_INCOMPATIBLE
""".split())
_OWNERS = ("risk_policy", "risk_basis", "quantity_domain")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields.")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Identifier requires nonblank text.")
    value.encode("utf-8")
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported closed value.")
    return value


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected a JSON array.")
    return value


def _serialized(value):
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("JSON object keys must be strings.")
            key.encode("utf-8")
            _serialized(item)
    elif type(value) is list:
        for item in value:
            _serialized(item)
    elif type(value) is str:
        value.encode("utf-8")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite native JSON number.")
    elif value is not None and type(value) not in (bool, int):
        raise ValueError("Serialized inputs require exact JSON types.")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA-256 digest.")
    return value


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " differs from its co-reference.")


def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Timestamp requires seconds, timezone and microsecond precision.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _interval(value):
    value["effective_from"] = _time(value["effective_from"])
    if value["effective_until"] is not None:
        value["effective_until"] = _time(value["effective_until"])
        if value["effective_until"] <= value["effective_from"]:
            raise ValueError("Effective interval must be nonempty.")


def _current(value, at):
    return value["effective_from"] <= at and (value["effective_until"] is None or at < value["effective_until"])


def _unique(items, key):
    if len({key(item) for item in items}) != len(items):
        raise ValueError("Duplicate local identity or target.")
    return sorted(items, key=key)


def _timing(value, at):
    value["observed_at"] = _time(value["observed_at"])
    if value["source_available_at"] is not None:
        value["source_available_at"] = _time(value["source_available_at"])
        if value["source_available_at"] > value["observed_at"]:
            raise ValueError("Observation precedes source availability.")
    if value["observed_at"] > at:
        raise ValueError("Post-K observation.")


def _source(value):
    _keys(value, "source_id source_contract source_contract_version source_snapshot_id")
    for item in value.values():
        _text(item)


def _catalog(value, at):
    result = []
    for row in _list(value):
        _keys(row, "evidence_id source media_type content_base64 source_available_at observed_at")
        _text(row["evidence_id"])
        _text(row["media_type"])
        _source(row["source"])
        if type(row["content_base64"]) is not str:
            raise ValueError("Original evidence requires base64 text.")
        raw = base64.b64decode(row["content_base64"], validate=True)
        if not raw or base64.b64encode(raw).decode("ascii") != row["content_base64"]:
            raise ValueError("Original evidence requires canonical nonempty base64.")
        _timing(row, at)
        result.append(row)
    return _unique(result, lambda item: item["evidence_id"])


def _refs(value, catalog):
    result = []
    by_id = {row["evidence_id"]: row for row in catalog}
    for ref in _list(value):
        _keys(ref, "evidence_id content_sha256")
        _text(ref["evidence_id"])
        _hash(ref["content_sha256"])
        item = by_id.get(ref["evidence_id"])
        if item is None or _digest(item) != ref["content_sha256"]:
            raise ValueError("Original evidence reference mismatch.")
        result.append(ref)
    return _unique(result, lambda ref: (ref["evidence_id"], ref["content_sha256"]))


def _available(refs, catalog):
    by_id = {row["evidence_id"]: row for row in catalog}
    return bool(refs) and all(by_id[ref["evidence_id"]]["source_available_at"] is not None for ref in refs)


def _gate_nodes(policy):
    if policy is None:
        return []
    result = [(dict(kind="POLICY_GATE", gate=label), node) for label, node in (
        ("EQUITY", policy["own_policy"]["equity_gate"]),
        ("DAILY_LOSS", policy["own_policy"]["daily_loss_gate"]),
        ("FINANCIAL_COMPATIBILITY", policy["financial_compatibility"]),
        ("REGIME", policy["provider_policy"]["regime_gate"]))]
    result.extend((dict(kind="PROVIDER_RULE", rule_reference=deepcopy(row["rule_reference"])), row)
                  for row in policy["provider_policy"]["rule_results"])
    return result


def _negative_reasons(risk):
    if risk is None or risk["outcome"] != "NOT_SUITABLE":
        return []
    return sorted(set(risk["reasons"]) - set(risk["uncertainties"]))


def _target(value, q, owners):
    if type(value) is not dict:
        raise ValueError("Admission requires a tagged target.")
    kind = value.get("kind")
    if kind == "POLICY_GATE":
        _keys(value, "kind gate")
        _enum(value["gate"], ("EQUITY", "DAILY_LOSS", "FINANCIAL_COMPATIBILITY", "REGIME"))
    elif kind == "PROVIDER_RULE":
        _keys(value, "kind rule_reference")
        _keys(value["rule_reference"], "rule_id full_content_sha256")
        _text(value["rule_reference"]["rule_id"])
        _hash(value["rule_reference"]["full_content_sha256"])
    elif kind == "RISK_FUNCTION_INPUTS":
        _keys(value, "kind")
    elif kind == "RISK_NEGATIVE":
        _keys(value, "kind reason_code")
        _enum(value["reason_code"], NATIVE_RISK_NEGATIVES)
        if value["reason_code"] not in _negative_reasons(owners["risk_basis"]):
            raise ValueError("Admission names no reconstructed negative predicate.")
    elif kind == "BINDING":
        _keys(value, "kind claim")
        _enum(value["claim"], CLAIMS)
        if q["binding_evidence"] is None:
            raise ValueError("Admission has no binding target.")
    else:
        raise ValueError("Unsupported admission target.")
    if kind in ("POLICY_GATE", "PROVIDER_RULE") and not any(
        _canonical(t) == _canonical(value) for t, _ in _gate_nodes(owners["risk_policy"])
    ):
        raise ValueError("Admission has no policy gate target.")
    if kind in ("RISK_FUNCTION_INPUTS", "RISK_NEGATIVE") and q["risk_basis"] is None:
        raise ValueError("Admission has no risk target.")
    return value


def _projection(target, q, planning):
    kind = target["kind"]
    if kind in ("POLICY_GATE", "PROVIDER_RULE"):
        return dict(target=target, owner_bundle=q["risk_policy"])
    if kind in ("RISK_FUNCTION_INPUTS", "RISK_NEGATIVE"):
        return dict(target=target, owner_bundle=q["risk_basis"],
                    trusted_planning_context_sha256=None if planning is None else _digest(planning))
    return dict(target=target, binding_evidence=q["binding_evidence"])


def _binding(value, q, at):
    if value is None:
        return None
    _keys(value, "contract rule_version binding_id source assessment_economic_time knowledge_boundary effective_from effective_until source_available_at observed_at subjects claims evidence")
    _enum(value["contract"], (BINDING_CONTRACT,))
    _enum(value["rule_version"], (BINDING_RULE,))
    _text(value["binding_id"])
    _source(value["source"])
    for key in ("assessment_economic_time", "knowledge_boundary"):
        value[key] = _time(value[key])
        if value[key] != at:
            raise ValueError("Binding T/K mismatch.")
    _interval(value)
    _timing(value, at)
    _keys(value["subjects"], "risk_policy_bundle_sha256 risk_basis_bundle_sha256 quantity_domain_bundle_sha256")
    for owner in _OWNERS:
        expected = None if q[owner] is None else _digest(q[owner])
        _same(value["subjects"][owner + "_bundle_sha256"], expected, "Binding subject")
    value["evidence"] = _catalog(value["evidence"], at)
    _keys(value["claims"], " ".join(CLAIMS))
    for name, claim in value["claims"].items():
        _keys(claim, "status evidence_refs")
        _enum(claim["status"], ("COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"))
        claim["evidence_refs"] = _refs(claim["evidence_refs"], value["evidence"])
        addressed = ("risk_basis", "risk_policy" if name == "monetary_denomination" else "quantity_domain")
        if claim["status"] != "UNKNOWN" and any(q[key] is None for key in addressed):
            raise ValueError("Binding assertion has absent subjects.")
    return value


def _context(value, q, owners, planning, at):
    if value is None:
        return None
    _keys(value, "contract rule_version admission_id authority_id mandate_id mandate_revision purpose knowledge_boundary effective_from effective_until admitted_at available_at evidence admissions")
    _enum(value["contract"], (ADMISSION_CONTRACT,))
    _enum(value["rule_version"], (ADMISSION_RULE,))
    _enum(value["purpose"], (PURPOSE,))
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(value[key])
    if type(value["mandate_revision"]) is not int or value["mandate_revision"] < 1:
        raise ValueError("Mandate revision must be a positive integer.")
    for key in ("knowledge_boundary", "admitted_at", "available_at"):
        value[key] = _time(value[key])
    if value["knowledge_boundary"] != at or not value["admitted_at"] <= value["available_at"] <= at:
        raise ValueError("Feasibility context K or admission timing mismatch.")
    _interval(value)
    value["evidence"] = _catalog(value["evidence"], at)
    by_id = {row["evidence_id"]: row for row in value["evidence"]}
    rows = []
    for receipt in _list(value["admissions"]):
        _keys(receipt, "target subject_content_sha256 assurances")
        target = _target(receipt["target"], q, owners)
        _hash(receipt["subject_content_sha256"])
        if receipt["subject_content_sha256"] != _digest(_projection(target, q, planning)):
            raise ValueError("Independent admission subject pin mismatch.")
        _keys(receipt["assurances"], " ".join(ASSURANCES))
        for assurance in receipt["assurances"].values():
            _keys(assurance, "status evidence_refs")
            _enum(assurance["status"], ("ADMITTED", "UNRESOLVED"))
            assurance["evidence_refs"] = _refs(assurance["evidence_refs"], value["evidence"])
            if assurance["status"] == "ADMITTED":
                if not _available(assurance["evidence_refs"], value["evidence"]):
                    raise ValueError("Admitted assurance lacks causally available original evidence.")
                if any(by_id[ref["evidence_id"]]["observed_at"] > value["admitted_at"]
                       for ref in assurance["evidence_refs"]):
                    raise ValueError("Admission precedes its supporting evidence.")
        rows.append(receipt)
    value["admissions"] = _unique(rows, lambda row: _canonical(row["target"]))
    return value


def _integer(digits):
    result = 0
    for offset in range(0, len(digits), 9):
        part = digits[offset:offset + 9]
        result = result * 10 ** len(part) + int(part)
    return result


def _integer_text(value):
    if value == 0:
        return "0"
    if value < 0:
        raise ValueError("Negative grid index.")
    parts = []
    while value:
        value, part = divmod(value, 10 ** 9)
        parts.append(part)
    return str(parts[-1]) + "".join(str(part).zfill(9) for part in reversed(parts[:-1]))


def _number(value):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Arithmetic requires finite plain decimals from reconstructed owners.")
    whole, _, part = value.lstrip("-").partition(".")
    return Fraction((-1 if value.startswith("-") else 1) * _integer(whole + part), 10 ** len(part))


def _domain_slice(domain, first, last):
    if last is not None and last < first:
        return dict(kind="EMPTY")
    return dict(kind="REGULAR_GRID", origin=domain["origin"], increment=domain["increment"],
                first_index=_integer_text(first), last_index=None if last is None else _integer_text(last))


def _intersection(domain, maximum):
    if domain["kind"] == "EMPTY":
        return dict(kind="EMPTY"), dict(kind="EMPTY")
    origin, increment = _number(domain["origin"]), _number(domain["increment"])
    first = _integer(domain["first_index"])
    last = None if domain["last_index"] is None else _integer(domain["last_index"])
    bound = (maximum - origin) // increment
    supported_last = bound if last is None else min(last, bound)
    return (_domain_slice(domain, first, supported_last),
            _domain_slice(domain, max(first, bound + 1), last))


def _loss(function, quantity):
    return _number(function["price_loss_per_quantity_unit"]) * quantity + sum(
        (max(_number(row["minimum"]), _number(row["fixed"]) + _number(row["per_unit"]) * quantity)
         for row in function["charges"]), Fraction(0))


def _feasible(domain, function, budget):
    if domain["kind"] == "EMPTY":
        return dict(kind="EMPTY")
    origin, increment = _number(domain["origin"]), _number(domain["increment"])
    lo, hi = _integer(domain["first_index"]), _integer(domain["last_index"])
    if _loss(function, origin + lo * increment) > budget:
        return dict(kind="EMPTY")
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _loss(function, origin + mid * increment) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return _domain_slice(domain, _integer(domain["first_index"]), lo)


def _coreferences(q, owners, planning, at):
    policy, risk, quantity = (owners[key] for key in _OWNERS)
    for value in owners.values():
        if value is not None and any(_time(value[key]) != at for key in
                                     ("assessment_economic_time", "knowledge_boundary")):
            raise ValueError("Current owner T/K mismatch.")
    if policy is not None and risk is not None:
        _same(q["risk_policy"]["request"]["candidate"], q["risk_basis"]["request"]["candidate"], "Candidate pair")
        risk_account = q["risk_basis"]["request"]["account_state"]
        if risk_account is not None:
            _same(q["risk_policy"]["request"]["account_state"], risk_account, "Account pair")
    if quantity is not None:
        candidate = None
        if risk is not None:
            candidate = risk["reconstruction_evidence"]["candidate"]["formulation"]["candidate"]
        elif policy is not None:
            candidate = q["risk_policy"]["request"]["candidate"]["formulation"]["candidate"]
        if candidate is not None and candidate["direction"] != quantity["scope"]["entry_direction"]:
            raise ValueError("Quantity direction differs from the common candidate.")
        if risk is not None and risk["scenario"] is not None and risk["scenario"]["mechanism"] != quantity["scope"]["entry_mechanism"]:
            raise ValueError("Established entry mechanism differs from quantity scope.")


def _comparands(q, owners, planning, at):
    """Only recover native subjects; do not repeat applicability or policy selection."""
    policy, risk, quantity = (owners[key] for key in _OWNERS)
    result = {name: [] for name in CLAIMS}
    if risk is None:
        return result
    reconstruction = risk["reconstruction_evidence"]
    candidate = reconstruction["candidate"]["formulation"]["candidate"]
    selected = reconstruction["selected_specification"]
    spec = None if selected is None else selected["specification"]
    active = [row for row in reconstruction["scenario_evidence"] if
              _time(row["effective_from"]) <= at and
              (row["effective_until"] is None or at < _time(row["effective_until"]))]
    # The native owner has already proved all active rows have identical
    # status, terms and subjects. Distinct equivalent source declarations do
    # not introduce a new selection obligation in this consumer.
    terms = active[0]["terms"] if active else None
    account_pair = reconstruction["account_state"]
    account = None if account_pair is None else account_pair["snapshot"]["observation"]["account"]
    if quantity is not None:
        scope = quantity["scope"]
        result["account_provider_venue"] = [
            [None if account is None else account["account_id"], scope["account_id"]],
            [None if account is None else account["environment"], scope["environment"]],
            [None if planning is None else planning["scope"]["venue_id"], scope["venue_id"]]]
        result["instrument_namespace"] = [
            [candidate["instrument"], None if spec is None else spec["position_namespace"]["instrument_id"], scope["instrument_id"]],
            [None if spec is None else spec["position_namespace"]["environment"], scope["environment"]]]
        units = [scope["quantity_unit"], None if spec is None else spec["position_namespace"]["quantity_unit"]]
        if terms is None:
            units.append(None)
        else:
            units.extend(row["quantity_unit"] for row in terms["charges"])
        result["quantity_denomination"] = [units]
    if policy is not None:
        currencies = [policy["own_policy"]["currency"],
                      None if spec is None else spec.get("payoff", {}).get("pnl_currency")]
        if terms is None:
            currencies.append(None)
        else:
            currencies.extend(row["currency"] for row in terms["charges"])
        result["monetary_denomination"] = [currencies]
    return result


def _account_bound(owners, planning, at):
    risk = owners["risk_basis"]
    if risk is None or risk["outcome"] != "ESTABLISHED" or planning is None:
        return False
    evidence = risk["reconstruction_evidence"]
    if evidence["account_state"] is None:
        return False
    actual = evidence["account_state"]["snapshot"]["observation"]["account"]
    expected = {key: actual[key] for key in ("environment", "account_id", "currency")}
    rows = [row for row in evidence["scenario_evidence"] if _time(row["effective_from"]) <= at and
            (row["effective_until"] is None or at < _time(row["effective_until"]))]
    return (bool(rows) and rows[0]["terms"] is not None and
            rows[0]["terms"]["account_scope"] == expected and planning["scope"]["account_scope"] == expected)


def _policy_namespace(q, owners, at):
    policy, risk = owners["risk_policy"], owners["risk_basis"]
    if policy is None or risk is None or risk["reconstruction_evidence"]["selected_specification"] is None:
        return True  # Missing native operands have their own findings; invent no mismatch.
    namespace = risk["reconstruction_evidence"]["selected_specification"]["specification"]["position_namespace"]
    selected = q["risk_policy"]["request"]["account_rule_regime"]["assessment"]["selected_regime"]
    if selected is None:
        return True
    relevant = {rule["rule_id"] for rule in selected["package"]["rules"]
                if set(rule["effects"]) & {"ENTRY", "ACCOUNT_ELIGIBILITY"}}
    for row in q["risk_policy"]["request"]["provider_operands"]:
        if (row["tag"] == "INSTRUMENT_BINDING" and row["rule_reference"]["rule_id"] in relevant and
                _time(row["effective_from"]) <= at < _time(row["effective_until"])):
            actual = row["body"]["provider_instrument"]
            if any(actual[key] != namespace[key] for key in actual):
                return False
    return True


def _evaluate(request, planning, quantity_context, feasibility_context):
    _serialized(request)
    for value in (planning, quantity_context, feasibility_context):
        if value is not None:
            _serialized(value)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary risk_policy risk_basis quantity_domain binding_evidence")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    if q["assessment_economic_time"] != at:
        raise ValueError("Current composition requires T = K.")
    if (q["risk_basis"] is None and planning is not None) or (q["quantity_domain"] is None and quantity_context is not None):
        raise ValueError("Orphaned native context.")
    owners = dict.fromkeys(_OWNERS)
    for name in _OWNERS:
        pair = q[name]
        if pair is None:
            continue
        _keys(pair, "assessment request")
        if type(pair["assessment"]) is not dict or type(pair["request"]) is not dict:
            raise ValueError("Native owner envelopes require JSON objects.")
        if name == "risk_policy":
            owners[name] = validate_account_specific_risk_policy(pair["assessment"], pair["request"])
        elif name == "risk_basis":
            owners[name] = validate_current_entry_to_stop_risk_basis(pair["assessment"], pair["request"], trusted_planning_context=planning)
        else:
            owners[name] = validate_current_entry_quantity_domain(pair["assessment"], pair["request"], trusted_quantity_context=quantity_context)
    _coreferences(q, owners, planning, at)
    q["binding_evidence"] = binding = _binding(q["binding_evidence"], q, at)
    context = _context(deepcopy(feasibility_context), q, owners, planning, at)
    comparisons = _comparands(q, owners, planning, at)
    if binding is not None:
        for name, groups in comparisons.items():
            if binding["claims"][name]["status"] == "COMPATIBLE":
                if any(len({value for value in group if value is not None}) > 1 for group in groups):
                    raise ValueError("Compatibility assertion contradicts literal subjects.")
    # Structural validation of all supplied material finishes before any outcome.
    proofs, unresolved = [], []

    def unknown(reason, target):
        unresolved.append(dict(reason_code=reason, target=deepcopy(target)))

    def negative(reason, target, scope):
        proofs.append(dict(reason_code=reason, target=deepcopy(target), scope=scope))

    receipts = {} if context is None else {_canonical(row["target"]): row for row in context["admissions"]}

    def admitted(target):
        receipt = receipts.get(_canonical(target))
        if receipt is None:
            unknown("ADMISSION_MISSING", target)
            return False
        if not _current(context, at):
            unknown("ADMISSION_NOT_CURRENT", target)
            return False
        if any(row["status"] != "ADMITTED" for row in receipt["assurances"].values()):
            unknown("ADMISSION_UNRESOLVED", target)
            return False
        return True

    for name, owner in owners.items():
        if owner is None:
            unknown("OWNER_MISSING", dict(kind="OWNER", owner=name.upper()))
    policy, risk, quantity = (owners[key] for key in _OWNERS)
    policy_ok = policy is not None
    for target, node in _gate_nodes(policy):
        if node["outcome"] == "UNKNOWN":
            unknown("OWNER_UNKNOWN", target)
            policy_ok = False
            continue
        trusted = admitted(target)
        policy_ok = policy_ok and trusted and node["outcome"] == "SATISFIED"
        if node["outcome"] == "NOT_SATISFIED":
            if trusted:
                negative("PRE_QUANTITY_POLICY_BLOCKED", target, "POLICY_GATE_AT_K")
            else:
                unknown("NEGATIVE_NOT_ADMITTED", target)
    risk_ok = False
    if risk is not None:
        if risk["outcome"] == "UNKNOWN" or risk["uncertainties"]:
            unknown("OWNER_UNKNOWN", dict(kind="OWNER", owner="RISK_BASIS"))
        if risk["outcome"] == "ESTABLISHED":
            risk_ok = admitted(dict(kind="RISK_FUNCTION_INPUTS"))
        for reason in _negative_reasons(risk):
            target = dict(kind="RISK_NEGATIVE", reason_code=reason)
            trusted = admitted(target)
            planning_required = reason.startswith(("PLANNING_", "APPROVED_", "TRUSTED_")) or reason == "QUOTE_VENUE_MISMATCH"
            if planning_required and (planning is None or (reason != "TRUSTED_PLANNING_MANDATE_EXPIRED" and not _current(
                dict(effective_from=_time(planning["effective_from"]), effective_until=None if planning["effective_until"] is None else _time(planning["effective_until"])), at
            ))):
                trusted = False
            if trusted:
                candidate = reason in ("CANDIDATE_INVALIDATED", "CANDIDATE_EXPIRED")
                negative("CANDIDATE_NOT_CURRENTLY_VALID" if candidate else "RISK_BASIS_UNUSABLE", target,
                         "CANDIDATE_AT_K" if candidate else "RISK_INPUT_BUNDLE")
            else:
                unknown("NEGATIVE_NOT_ADMITTED", target)
    entry = None
    if quantity is not None:
        if quantity["outcome"] == "UNKNOWN":
            unknown("OWNER_UNKNOWN", dict(kind="OWNER", owner="QUANTITY_DOMAIN"))
        else:
            entry = dict(quantity_unit=quantity["scope"]["quantity_unit"], domain=deepcopy(quantity["domain"]))
            if entry["domain"]["kind"] == "EMPTY":
                negative("ENTRY_DOMAIN_EMPTY", dict(kind="ENTRY_DOMAIN"), "ENTRY_DOMAIN")
    bindings_ok = dict.fromkeys(CLAIMS, False)
    if binding is None:
        unknown("BINDING_MISSING", dict(kind="COMPOSITION"))
    else:
        for name, claim in binding["claims"].items():
            target = dict(kind="BINDING", claim=name)
            usable = True
            if not _current(binding, at):
                unknown("BINDING_NOT_CURRENT", target)
                usable = False
            if binding["source_available_at"] is None or not _available(claim["evidence_refs"], binding["evidence"]):
                unknown("BINDING_SUPPORT_MISSING", target)
                usable = False
            if claim["status"] == "UNKNOWN":
                unknown("BINDING_UNRESOLVED", target)
                continue
            trusted = admitted(target)
            if claim["status"] == "INCOMPATIBLE":
                if usable and trusted:
                    negative("BINDING_INCOMPATIBLE", target, "BINDING_RELATION")
            else:
                groups = comparisons[name]
                complete = bool(groups) and all(all(value is not None for value in group) for group in groups)
                if not complete:
                    unknown("BINDING_UNRESOLVED", target)
                bindings_ok[name] = usable and trusted and complete
    account_ok = _account_bound(owners, planning, at)
    if risk is not None and risk["outcome"] == "ESTABLISHED" and not account_ok:
        unknown("ACCOUNT_APPLICABILITY_UNRESOLVED", dict(kind="COMPOSITION"))
    namespace_ok = _policy_namespace(q, owners, at)
    if not namespace_ok:
        unknown("POLICY_INSTRUMENT_NAMESPACE_UNRESOLVED", dict(kind="COMPOSITION"))
    budget = None if not policy_ok else dict(amount=policy["own_policy"]["maximum_monetary_risk"], currency=policy["own_policy"]["currency"])
    function = risk["risk_function"] if risk_ok else None
    support = None if function is None else dict(maximum_quantity=function["maximum_supported_quantity"], quantity_unit=function["quantity_unit"])
    supported = tail = feasible = None
    if entry is not None and support is not None and account_ok and all(bindings_ok[key] for key in CLAIMS[:3]):
        inside, outside = _intersection(entry["domain"], _number(support["maximum_quantity"]))
        supported = dict(quantity_unit=entry["quantity_unit"], domain=inside)
        tail = dict(quantity_unit=entry["quantity_unit"], domain=outside)
        if inside["kind"] == "EMPTY":
            negative("NO_SUPPORTED_POSITIVE_QUANTITY", dict(kind="SUPPORTED_DOMAIN"), "SUPPORTED_DOMAIN")
        if budget is not None and bindings_ok["monetary_denomination"] and namespace_ok:
            domain = _feasible(inside, function, _number(budget["amount"]))
            feasible = dict(quantity_unit=entry["quantity_unit"], domain=domain)
            if domain["kind"] == "EMPTY" and inside["kind"] != "EMPTY":
                negative("BUDGET_BELOW_FIRST_SUPPORTED_QUANTITY_RISK", dict(kind="FEASIBLE_DOMAIN"), "SUPPORTED_DOMAIN")
    proofs = sorted({_canonical(row): row for row in proofs}.values(), key=_canonical)
    unresolved = sorted({_canonical(row): row for row in unresolved}.values(), key=_canonical)
    if proofs:
        outcome = "NOT_SUITABLE"
    elif unresolved:
        outcome = "UNKNOWN"
    elif feasible is not None and feasible["domain"]["kind"] == "REGULAR_GRID":
        outcome = "ESTABLISHED"
    else:
        raise ValueError("Incomplete feasibility proof without an unresolved obligation.")
    reasons = sorted({row["reason_code"] for row in [*proofs, *unresolved]})
    if outcome == "ESTABLISHED":
        reasons = ["SUPPORTED_FEASIBLE_DOMAIN_ESTABLISHED"]
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
                  outcome=outcome, reason_codes=reasons, negative_proofs=proofs, unresolved_findings=unresolved,
                  budget=budget, risk_support=support, entry_domain=entry, supported_entry_domain=supported,
                  feasible_domain=feasible, outside_risk_support=tail,
                  reconstruction_evidence=dict(request=q,
                      trusted_planning_context_sha256=None if planning is None else _digest(planning),
                      trusted_quantity_context_sha256=None if quantity_context is None else _digest(quantity_context),
                      trusted_feasibility_context_sha256=None if context is None else _digest(context)),
                  downstream_obligations=list(DOWNSTREAM_OBLIGATIONS), source_authentication=SOURCE_AUTHENTICATION,
                  authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = "current_risk_budget_quantity_feasibility_" + _digest(result)
    return result


def evaluate_current_risk_budget_quantity_feasibility(
    request: dict, *, trusted_planning_context=None, trusted_quantity_context=None, trusted_feasibility_context=None,
) -> dict:
    """Reconstruct native owners and exact supported feasible sets under host admission."""
    try:
        return deepcopy(_evaluate(request, trusted_planning_context, trusted_quantity_context, trusted_feasibility_context))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed current risk-budget quantity-feasibility request.") from exc


def validate_current_risk_budget_quantity_feasibility(
    assessment: dict, request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None,
) -> dict:
    """Rebuild complete detached output; self-consistent caller hashes grant no trust."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be a serialized JSON object.")
        _serialized(assessment)
        expected = evaluate_current_risk_budget_quantity_feasibility(
            request, trusted_planning_context=trusted_planning_context, trusted_quantity_context=trusted_quantity_context,
            trusted_feasibility_context=trusted_feasibility_context)
        _same(assessment, expected, "Feasibility assessment")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized quantity-feasibility assessment.") from exc
