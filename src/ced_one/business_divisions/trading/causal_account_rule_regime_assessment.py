"""Account-specific interpreted rule applicability; no financial or execution authority."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import json
import re
from typing import Any

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _hash_id
from ced_one.business_divisions.trading.causal_financial_account_state_snapshot import _timestamp, _decimal

CONTRACT = "trading.causal_account_rule_regime_assessment.v1"
RULE_VERSION = "causal_account_rule_regime_assessment_v1"
REFERENCE_FIELDS = ("source_id", "source_contract", "source_contract_version", "source_snapshot_id")
REASON_CODES = (
    "MANIFEST_COVERAGE_LIMITED", "MANIFEST_COVERAGE_UNKNOWN", "MANIFEST_CUTOFF_BEFORE_K",
    "T_OUTSIDE_MANIFEST_COVERAGE", "ACCOUNT_ASSIGNMENT_NOT_ESTABLISHED",
    "ACCOUNT_ASSIGNMENT_IDENTITY_UNKNOWN", "APPLICABILITY_TIMING_UNKNOWN",
    "MULTIPLE_ACCOUNT_ASSIGNMENTS", "MULTIPLE_APPLICABLE_PACKAGES", "NO_APPLICABLE_PACKAGE",
    "APPROVAL_NOT_ESTABLISHED", "APPROVAL_NOT_EFFECTIVE_AT_T", "APPROVAL_REJECTED",
    "APPROVAL_CONFLICT", "UNIQUE_APPLICABLE_APPROVED_REGIME_ESTABLISHED",
    "RULE_COVERAGE_LIMITED", "RULE_COVERAGE_UNKNOWN", "UNSUPPORTED_RULES_PRESENT",
)
LIMITATIONS = (
    "SOURCE_CLAIMS_NOT_INDEPENDENTLY_AUTHENTICATED",
    "OPERATIONAL_APPROVAL_CLAIMS_NOT_INDEPENDENTLY_AUTHENTICATED",
    "PROVIDER_AGREEMENT_WITH_INTERPRETATION_NOT_ESTABLISHED",
    "COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED", "RULE_COMPLETENESS_RELATIVE_TO_DECLARED_SCOPE",
    "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "SOURCE_CALENDAR_TRANSLATION_NOT_INDEPENDENTLY_VERIFIED",
    "CANDIDATE_COMPLIANCE_NOT_EVALUATED", "FINANCIAL_RISK_NOT_EVALUATED",
    "ACCOUNT_STATE_AND_HEADROOM_NOT_EVALUATED", "TRADE_AUTHORIZATION_NOT_PERFORMED",
    "EXECUTION_NOT_PERFORMED",
)
EFFECTS = ("ENTRY", "HOLDING", "EXIT", "ACCOUNT_ELIGIBILITY", "PHASE_TRANSITION", "PAYOUT", "UNKNOWN")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split() if isinstance(fields, str) else fields):
        raise ValueError("Object requires exactly its declared fields.")


def _opaque(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty opaque string.")
    return value


def _enum(value, values):
    if type(value) is not str or value not in values:
        raise ValueError("Unsupported contract value.")
    return value


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected list.")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(rows, key):
    seen = set()
    for row in rows:
        identity = key(row)
        if identity in seen:
            raise ValueError("Duplicate identity.")
        seen.add(identity)
    return sorted(rows, key=key)


def _strings(value, allowed=None, nonempty=False):
    rows = _list(value)
    if nonempty and not rows:
        raise ValueError("Nonempty collection required.")
    for item in rows:
        _opaque(item) if allowed is None else _enum(item, allowed)
    rows = _unique(rows, lambda x: x)
    return rows if allowed is None else sorted(rows, key=list(allowed).index)


def _reference(value):
    _keys(value, REFERENCE_FIELDS)
    for field in REFERENCE_FIELDS:
        _opaque(value[field])
    return value


def _package_key(value):
    _keys(value, "package_id package_revision")
    return (_opaque(value["package_id"]), _opaque(value["package_revision"]))


def _account(value):
    _keys(value, "source_id source_contract source_contract_version account_id environment")
    for field in value:
        _opaque(value[field])
    _enum(value["environment"], ("DEMO", "LIVE"))


def _period(value, finite=False):
    _keys(value, "effective_from effective_until end_status")
    _enum(value["end_status"], ("KNOWN", "OPEN_ENDED", "UNKNOWN"))
    if value["effective_from"] is not None:
        value["effective_from"] = _timestamp(value["effective_from"])
    if value["end_status"] == "KNOWN":
        value["effective_until"] = _timestamp(value["effective_until"])
        if value["effective_from"] is not None and value["effective_from"] >= value["effective_until"]:
            raise ValueError("Empty or reversed period.")
    elif value["effective_until"] is not None:
        raise ValueError("Unknown/open end must be null.")
    if finite and (value["effective_from"] is None or value["end_status"] != "KNOWN"):
        raise ValueError("Finite known period required.")
    return value


def _contains(period, t):
    # False means demonstrably inactive; None means potentially active but unknown.
    if period["effective_from"] is not None and t < period["effective_from"]:
        return False
    if period["end_status"] == "KNOWN" and t >= period["effective_until"]:
        return False
    if period["effective_from"] is None or period["end_status"] == "UNKNOWN":
        return None
    return True


def _timing(value, k):
    _keys(value, "observed_at source_available_at")
    value["observed_at"] = _timestamp(value["observed_at"])
    if value["observed_at"] > k:
        raise ValueError("Evidence unavailable by K.")
    if value["source_available_at"] is not None:
        value["source_available_at"] = _timestamp(value["source_available_at"])
        if value["source_available_at"] > value["observed_at"]:
            raise ValueError("Publication after observation.")


def _number(value, minimum=None, maximum=None, positive=False):
    result = _decimal(value)
    number = Decimal(result)
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum) or (positive and number <= 0):
        raise ValueError("Decimal outside supported range.")
    return result


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid integer.")


def _clauses(value, evidence, used, deadline=None):
    rows = _list(value)
    if not rows:
        raise ValueError("Supporting clauses required.")
    for row in rows:
        _keys(row, "evidence_id clause_locator")
        _opaque(row["clause_locator"])
        identifier = _opaque(row["evidence_id"])
        if identifier not in evidence:
            raise ValueError("Dangling evidence reference.")
        if deadline is not None and evidence[identifier]["timing"]["observed_at"] > deadline:
            raise ValueError("Supporting evidence postdates interpretation.")
        used.add(identifier)
    return _unique(rows, lambda r: (r["evidence_id"], r["clause_locator"]))


def _rule(row, clauses):
    _keys(row, "rule_id representation effects instrument_scope evidence_refs body")
    _opaque(row["rule_id"])
    _enum(row["representation"], ("SUPPORTED", "UNSUPPORTED"))
    row["effects"] = _strings(row["effects"], EFFECTS, True)
    if "UNKNOWN" in row["effects"] and len(row["effects"]) != 1:
        raise ValueError("Unknown effects cannot be combined.")
    scope = row["instrument_scope"]
    if type(scope) is not dict:
        raise ValueError("Invalid instrument scope.")
    if scope.get("kind") == "ALL_ACCOUNT_INSTRUMENTS":
        _keys(scope, "kind")
    else:
        _keys(scope, "kind instruments")
        _enum(scope["kind"], ("EXACT_INSTRUMENTS",))
        instruments = _list(scope["instruments"])
        if not instruments:
            raise ValueError("Empty exact scope.")
        for item in instruments:
            _keys(item, "source_id source_contract source_contract_version environment instrument_id")
            for v in item.values():
                _opaque(v)
            _enum(item["environment"], ("DEMO", "LIVE"))
        scope["instruments"] = _unique(instruments, _canonical)
    row["evidence_refs"] = clauses(row["evidence_refs"])
    body = row["body"]
    if type(body) is not dict:
        raise ValueError("Invalid rule body.")
    kind = body.get("type")
    if row["representation"] == "UNSUPPORTED":
        _keys(body, "type source_rule_label unsupported_reason description")
        _enum(kind, ("UNSUPPORTED",))
        _opaque(body["source_rule_label"])
        _opaque(body["description"])
        _enum(body["unsupported_reason"], ("SEMANTICS_NOT_SUPPORTED", "SEMANTICS_AMBIGUOUS", "REQUIRED_TIMING_UNKNOWN", "REQUIRED_PARAMETERS_UNKNOWN"))
    elif kind == "ACCOUNT_STATE_REQUIREMENT":
        _keys(body, "type required_facts")
        body["required_facts"] = _strings(body["required_facts"], ("ACCOUNT_ACTIVE", "PHASE_OPEN_FOR_TRADING", "NO_PRIOR_DISQUALIFYING_BREACH"), True)
    elif kind in ("INSTRUMENT_ACTION_PERMISSION", "AUTOMATION_PERMISSION"):
        if kind == "INSTRUMENT_ACTION_PERMISSION":
            _keys(body, "type actions permission")
            body["actions"] = _strings(body["actions"], ("ENTRY_LONG", "ENTRY_SHORT", "HOLD", "EXIT"), True)
        else:
            _keys(body, "type operation_mode permission")
            _enum(body["operation_mode"], ("MANUAL", "AUTOMATED"))
        _enum(body["permission"], ("PERMITTED", "PROHIBITED"))
    elif kind == "POSITION_LIMIT":
        if body.get("limit_kind") == "PER_POSITION_QUANTITY":
            _keys(body, "type limit_kind quantity_unit maximum")
            _opaque(body["quantity_unit"])
            body["maximum"] = _number(body["maximum"], positive=True)
            if scope["kind"] != "EXACT_INSTRUMENTS" or len(scope["instruments"]) != 1:
                raise ValueError("Quantity limit requires one exact instrument.")
        else:
            _keys(body, "type limit_kind maximum")
            _enum(body["limit_kind"], ("CONCURRENT_POSITION_COUNT",))
            _integer(body["maximum"])
    elif kind in ("STATIC_FLOOR", "DAILY_RESET_FLOOR"):
        fields = "type measure threshold compliant_when" if kind == "STATIC_FLOOR" else "type measure reset_anchor deduction compliant_when reset_schedule adjustment_policy"
        _keys(body, fields)
        measure = body["measure"]
        _keys(measure, "kind currency definition_refs cost_treatment")
        _enum(measure["kind"], ("BALANCE", "EQUITY"))
        if type(measure["currency"]) is not str or re.fullmatch(r"[A-Z]{3}", measure["currency"]) is None:
            raise ValueError("Invalid currency.")
        measure["definition_refs"] = clauses(measure["definition_refs"])
        costs = measure["cost_treatment"]
        _keys(costs, "commissions financing other_charges")
        for treatment in costs.values():
            _enum(treatment, ("IN_MEASURE", "SUBTRACT_SEPARATELY", "NOT_APPLICABLE"))
        _enum(body["compliant_when"], ("GREATER_THAN", "GREATER_THAN_OR_EQUAL"))
        threshold = body["threshold" if kind == "STATIC_FLOOR" else "deduction"]
        if type(threshold) is not dict:
            raise ValueError("Invalid threshold.")
        if threshold.get("kind") == "ABSOLUTE":
            _keys(threshold, "kind amount")
            threshold["amount"] = _number(threshold["amount"], minimum=0 if kind == "DAILY_RESET_FLOOR" else None)
        else:
            _keys(threshold, "kind reference fraction")
            _enum(threshold["kind"], ("INITIAL_REFERENCE_FRACTION",))
            _enum(threshold["reference"], ("INITIAL_BALANCE", "INITIAL_EQUITY"))
            threshold["fraction"] = _number(threshold["fraction"], 0, 1)
        if kind == "DAILY_RESET_FLOOR":
            _enum(body["reset_anchor"], ("BALANCE", "EQUITY"))
            _enum(body["adjustment_policy"], ("NO_UNREPRESENTED_CAPITAL_OR_PHASE_ADJUSTMENTS",))
            schedule = body["reset_schedule"]
            _keys(schedule, "source_timezone source_local_reset_time schedule_period boundaries evidence_refs")
            _opaque(schedule["source_timezone"])
            if type(schedule["source_local_reset_time"]) is not str or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", schedule["source_local_reset_time"]) is None:
                raise ValueError("Invalid reset time.")
            period = _period(schedule["schedule_period"], True)
            boundaries = [_timestamp(v) for v in _list(schedule["boundaries"])]
            boundaries = _unique(boundaries, lambda x: x)
            if len(boundaries) < 2 or boundaries[0] != period["effective_from"] or boundaries[-1] != period["effective_until"]:
                raise ValueError("Reset boundaries must span schedule exactly.")
            schedule["boundaries"] = boundaries
            schedule["evidence_refs"] = clauses(schedule["evidence_refs"])
    elif kind == "ACTION_WINDOW":
        _keys(body, "type actions mode source_timezone schedule_period intervals evidence_refs")
        body["actions"] = _strings(body["actions"], ("ENTRY_LONG", "ENTRY_SHORT", "HOLD"), True)
        _enum(body["mode"], ("PERMITTED_ONLY_WITHIN", "PROHIBITED_WITHIN"))
        _opaque(body["source_timezone"])
        period = _period(body["schedule_period"], True)
        intervals = [_period(v, True) for v in _list(body["intervals"])]
        intervals = _unique(intervals, lambda v: (v["effective_from"], v["effective_until"]))
        end = period["effective_from"]
        for interval in intervals:
            if interval["effective_from"] < end or interval["effective_until"] > period["effective_until"]:
                raise ValueError("Overlapping or out-of-coverage window.")
            end = interval["effective_until"]
        body["intervals"] = intervals
        body["evidence_refs"] = clauses(body["evidence_refs"])
    else:
        raise ValueError("Unsupported typed rule; use explicit unsupported representation.")


def _normalize_input(payload):
    value = deepcopy(payload)
    _keys(value, "contract rule_version requested_knowledge_boundary economic_timestamp account manifest approvals")
    _enum(value["contract"], (CONTRACT,))
    _enum(value["rule_version"], (RULE_VERSION,))
    k = value["requested_knowledge_boundary"] = _timestamp(value["requested_knowledge_boundary"])
    value["economic_timestamp"] = _timestamp(value["economic_timestamp"])
    _account(value["account"])
    manifest = value["manifest"]
    _keys(manifest, "source timing coverage evidence assignments packages")
    _reference(manifest["source"])
    _timing(manifest["timing"], k)
    report_time = manifest["timing"]["observed_at"]
    coverage = manifest["coverage"]
    _keys(coverage, "completeness economic_period source_information_cutoff limitations")
    _enum(coverage["completeness"], ("COMPLETE", "LIMITED", "UNKNOWN"))
    _period(coverage["economic_period"], True)
    coverage["limitations"] = _strings(coverage["limitations"])
    if coverage["completeness"] == "COMPLETE" and coverage["limitations"]:
        raise ValueError("Complete inventory cannot declare omissions.")
    cutoff = coverage["source_information_cutoff"]
    if cutoff is None:
        if coverage["completeness"] != "UNKNOWN":
            raise ValueError("Known coverage requires cutoff.")
    else:
        cutoff = coverage["source_information_cutoff"] = _timestamp(cutoff)
        if cutoff > report_time:
            raise ValueError("Coverage cutoff after report observation.")
    evidence = {}
    for row in _list(manifest["evidence"]):
        _keys(row, "evidence_id source acquisition document_reference document_revision document_date document_sha256 timing captured_by limitations")
        identifier = _opaque(row["evidence_id"])
        if identifier in evidence:
            raise ValueError("Duplicate evidence identity.")
        evidence[identifier] = row
        _reference(row["source"])
        _enum(row["acquisition"], ("SOURCE_OBSERVED", "MANUAL_TRANSCRIPTION"))
        _opaque(row["document_reference"])
        _opaque(row["captured_by"])
        if row["document_revision"] is not None:
            _opaque(row["document_revision"])
        if row["document_date"] is not None:
            if type(row["document_date"]) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["document_date"]) is None:
                raise ValueError("Invalid document date.")
            _timestamp(row["document_date"] + "T00:00:00Z")
        if row["document_sha256"] is not None and (type(row["document_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", row["document_sha256"]) is None):
            raise ValueError("Invalid document hash.")
        _timing(row["timing"], report_time)
        row["limitations"] = _strings(row["limitations"])
    used = set()
    packages = {}
    for package in _list(manifest["packages"]):
        _keys(package, "package_id package_revision provider_id program_id account_type_id phase_id effective_period evidence_refs interpretation coverage rules")
        key = _package_key({f: package[f] for f in ("package_id", "package_revision")})
        if key in packages:
            raise ValueError("Duplicate package identity.")
        packages[key] = package
        for field in SCOPE_FIELDS:
            _opaque(package[field])
        _period(package["effective_period"])
        interpretation = package["interpretation"]
        _keys(interpretation, "interpretation_id interpretation_version interpreted_at interpreter_ref limitations")
        for field in ("interpretation_id", "interpretation_version", "interpreter_ref"):
            _opaque(interpretation[field])
        interpretation["interpreted_at"] = _timestamp(interpretation["interpreted_at"])
        if interpretation["interpreted_at"] > report_time:
            raise ValueError("Interpretation unavailable at report.")
        interpretation["limitations"] = _strings(interpretation["limitations"])
        def clauses(refs):
            return _clauses(refs, evidence, used, interpretation["interpreted_at"])
        package["evidence_refs"] = clauses(package["evidence_refs"])
        cov = package["coverage"]
        _keys(cov, "completeness scope evidence_refs limitations")
        _enum(cov["completeness"], ("COMPLETE", "LIMITED", "UNKNOWN"))
        _enum(cov["scope"], ("ACCOUNT_TRADING_AND_ELIGIBILITY",))
        cov["evidence_refs"] = clauses(cov["evidence_refs"])
        cov["limitations"] = _strings(cov["limitations"])
        if cov["completeness"] == "COMPLETE" and cov["limitations"]:
            raise ValueError("Complete rule inventory cannot declare omissions.")
        for rule in _list(package["rules"]):
            _rule(rule, clauses)
        package["rules"] = _unique(package["rules"], lambda r: r["rule_id"])
    assignments = {}
    referenced_packages = set()
    for assignment in _list(manifest["assignments"]):
        _keys(assignment, "assignment_id account provider_id program_id account_type_id phase_id agreement enrollment_period phase_period package_bindings evidence_refs")
        identifier = _opaque(assignment["assignment_id"])
        if identifier in assignments:
            raise ValueError("Duplicate assignment identity.")
        assignments[identifier] = assignment
        _account(assignment["account"])
        if assignment["account"] != value["account"]:
            raise ValueError("Exact account mismatch.")
        for field in SCOPE_FIELDS:
            if assignment[field] is not None:
                _opaque(assignment[field])
        agreement = assignment["agreement"]
        _keys(agreement, "status agreement_id")
        _enum(agreement["status"], ("IDENTIFIED", "NOT_APPLICABLE", "UNKNOWN"))
        if agreement["status"] == "IDENTIFIED":
            _opaque(agreement["agreement_id"])
        elif agreement["agreement_id"] is not None:
            raise ValueError("Nonidentified agreement must have null identity.")
        _period(assignment["enrollment_period"])
        _period(assignment["phase_period"])
        assignment["evidence_refs"] = _clauses(assignment["evidence_refs"], evidence, used)
        for binding in _list(assignment["package_bindings"]):
            _keys(binding, "package effective_period evidence_refs")
            key = _package_key(binding["package"])
            if key not in packages:
                raise ValueError("Dangling package reference.")
            referenced_packages.add(key)
            for field in SCOPE_FIELDS:
                if assignment[field] is not None and assignment[field] != packages[key][field]:
                    raise ValueError("Package scope mismatch.")
            _period(binding["effective_period"])
            binding["evidence_refs"] = _clauses(binding["evidence_refs"], evidence, used)
        assignment["package_bindings"] = _unique(assignment["package_bindings"], lambda b: (*_package_key(b["package"]), _canonical(b["effective_period"])))
    if referenced_packages != set(packages) or used != set(evidence):
        raise ValueError("Unreferenced package or evidence.")
    manifest["evidence"] = sorted(evidence.values(), key=lambda r: r["evidence_id"])
    manifest["packages"] = [packages[key] for key in sorted(packages)]
    manifest["assignments"] = [assignments[key] for key in sorted(assignments)]
    for approval in _list(value["approvals"]):
        _keys(approval, "approval_reference authority_role policy_id policy_version context_fingerprint assignment_id assignment_content_fingerprint package package_content_fingerprint decision decided_at observed_at effective_period")
        _reference(approval["approval_reference"])
        _enum(approval["authority_role"], ("mission_control", "governance"))
        _opaque(approval["policy_id"])
        _integer(approval["policy_version"], 1)
        _opaque(approval["context_fingerprint"])
        identifier = _opaque(approval["assignment_id"])
        key = _package_key(approval["package"])
        if identifier not in assignments or key not in {_package_key(b["package"]) for b in assignments[identifier]["package_bindings"]}:
            raise ValueError("Unrelated approval.")
        if approval["assignment_content_fingerprint"] != _hash_id("account_rule_assignment_", assignments[identifier]) or approval["package_content_fingerprint"] != _hash_id("account_rule_package_", packages[key]):
            raise ValueError("Approval content binding mismatch.")
        _enum(approval["decision"], ("APPROVED", "REJECTED"))
        approval["decided_at"] = _timestamp(approval["decided_at"])
        approval["observed_at"] = _timestamp(approval["observed_at"])
        if not approval["decided_at"] <= approval["observed_at"] <= k:
            raise ValueError("Approval unavailable by K.")
        if approval["decided_at"] < packages[key]["interpretation"]["interpreted_at"]:
            raise ValueError("Approval predates interpreted content.")
        _period(approval["effective_period"])
    value["approvals"] = _unique(value["approvals"], lambda a: tuple(a["approval_reference"][f] for f in REFERENCE_FIELDS))
    return value


def _intersection(periods):
    start = max(p["effective_from"] for p in periods)
    ends = [p["effective_until"] for p in periods if p["end_status"] == "KNOWN"]
    return dict(effective_from=start, effective_until=min(ends) if ends else None, end_status="KNOWN" if ends else "OPEN_ENDED")


def _resolve(value):
    manifest, t, k = value["manifest"], value["economic_timestamp"], value["requested_knowledge_boundary"]
    coverage = manifest["coverage"]
    reasons = []
    if coverage["completeness"] != "COMPLETE":
        reasons.append("MANIFEST_COVERAGE_" + coverage["completeness"])
    if coverage["source_information_cutoff"] is not None and coverage["source_information_cutoff"] < k:
        reasons.append("MANIFEST_CUTOFF_BEFORE_K")
    if not _contains(coverage["economic_period"], t):
        reasons.append("T_OUTSIDE_MANIFEST_COVERAGE")
    if reasons:
        return "UNRESOLVED", None, reasons
    active = []
    for assignment in manifest["assignments"]:
        states = [_contains(assignment[f], t) for f in ("enrollment_period", "phase_period")]
        if False in states:
            continue
        if None in states:
            reasons.append("APPLICABILITY_TIMING_UNKNOWN")
        if any(assignment[f] is None for f in SCOPE_FIELDS) or assignment["agreement"]["status"] == "UNKNOWN":
            reasons.append("ACCOUNT_ASSIGNMENT_IDENTITY_UNKNOWN")
        active.append(assignment)
    if len(active) > 1:
        reasons.append("MULTIPLE_ACCOUNT_ASSIGNMENTS")
    if reasons:
        return "UNRESOLVED", None, reasons
    if not active:
        return "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED", None, ["ACCOUNT_ASSIGNMENT_NOT_ESTABLISHED"]
    assignment = active[0]
    packages = {(p["package_id"], p["package_revision"]): p for p in manifest["packages"]}
    candidates = []
    for binding in assignment["package_bindings"]:
        package = packages[_package_key(binding["package"])]
        states = [_contains(p, t) for p in (binding["effective_period"], package["effective_period"])]
        if False in states:
            continue
        if None in states:
            reasons.append("APPLICABILITY_TIMING_UNKNOWN")
        candidates.append((binding, package))
    # Distinct overlapping assertions for the same immutable package do not
    # establish competing regimes. All known active intervals contain T.
    grouped = {}
    for binding, package in candidates:
        key = (package["package_id"], package["package_revision"])
        grouped.setdefault(key, []).append((binding, package))
    if len(grouped) > 1:
        reasons.append("MULTIPLE_APPLICABLE_PACKAGES")
    if reasons:
        return "UNRESOLVED", None, reasons
    if not candidates:
        return "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED", None, ["NO_APPLICABLE_PACKAGE"]
    binding, package = candidates[0]
    if len(candidates) > 1:
        periods = [b["effective_period"] for b, _ in candidates]
        ends = [p["effective_until"] for p in periods]
        binding = {**binding, "effective_period": dict(
            effective_from=min(p["effective_from"] for p in periods),
            effective_until=None if None in ends else max(ends),
            end_status="OPEN_ENDED" if None in ends else "KNOWN")}
    key = (package["package_id"], package["package_revision"])
    approvals = [a for a in value["approvals"] if a["assignment_id"] == assignment["assignment_id"] and _package_key(a["package"]) == key]
    if not approvals:
        return "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED", None, ["APPROVAL_NOT_ESTABLISHED"]
    if any(_contains(a["effective_period"], t) is None for a in approvals):
        return "UNRESOLVED", None, ["APPLICABILITY_TIMING_UNKNOWN"]
    current = [a for a in approvals if _contains(a["effective_period"], t)]
    decisions = {a["decision"] for a in current}
    if len(decisions) > 1:
        return "UNRESOLVED", None, ["APPROVAL_CONFLICT"]
    if decisions != {"APPROVED"}:
        return "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED", None, ["APPROVAL_REJECTED" if decisions else "APPROVAL_NOT_EFFECTIVE_AT_T"]
    # Include connected approved intervals so the returned horizon is the actual union component.
    component = [a for a in approvals if a["decision"] == "APPROVED" and _contains(a["effective_period"], t)]
    remaining = [a for a in approvals if a["decision"] == "APPROVED" and a not in component and a["effective_period"]["effective_from"] is not None and a["effective_period"]["end_status"] != "UNKNOWN"]
    while True:
        starts = [a["effective_period"]["effective_from"] for a in component]
        ends = [a["effective_period"]["effective_until"] for a in component]
        start, end = min(starts), None if None in ends else max(ends)
        connected = [a for a in remaining if (end is None or a["effective_period"]["effective_from"] <= end) and (a["effective_period"]["effective_until"] is None or a["effective_period"]["effective_until"] >= start)]
        if not connected:
            break
        component.extend(connected)
        remaining = [a for a in remaining if a not in connected]
    approval_period = dict(effective_from=start, effective_until=end, end_status="OPEN_ENDED" if end is None else "KNOWN")
    applicable = _intersection([assignment["enrollment_period"], assignment["phase_period"], binding["effective_period"], package["effective_period"], approval_period])
    evidence_ids = set()
    def collect(obj):
        if isinstance(obj, dict):
            if set(obj) == {"evidence_id", "clause_locator"}:
                evidence_ids.add(obj["evidence_id"])
            for item in obj.values():
                collect(item)
        elif isinstance(obj, list):
            for item in obj:
                collect(item)
    collect(assignment)
    collect(package)
    selected = dict(
        regime_id=_hash_id("account_rule_regime_", {"account": value["account"], "assignment": assignment, "package": package}),
        assignment=assignment, assignment_content_fingerprint=_hash_id("account_rule_assignment_", assignment),
        package=package, package_content_fingerprint=_hash_id("account_rule_package_", package),
        approval_references=sorted(component, key=lambda a: tuple(a["approval_reference"][f] for f in REFERENCE_FIELDS)),
        applicable_period=applicable, evidence=[e for e in manifest["evidence"] if e["evidence_id"] in evidence_ids])
    reasons = ["UNIQUE_APPLICABLE_APPROVED_REGIME_ESTABLISHED"]
    if package["coverage"]["completeness"] != "COMPLETE":
        reasons.append("RULE_COVERAGE_" + package["coverage"]["completeness"])
    if any(r["representation"] == "UNSUPPORTED" for r in package["rules"]):
        reasons.append("UNSUPPORTED_RULES_PRESENT")
    return "UNIQUE_APPLICABLE_APPROVED_REGIME", selected, reasons


def _assess(payload):
    value = _normalize_input(payload)
    outcome, selected, reasons = _resolve(value)
    support = "NOT_ASSESSED" if selected is None else ("UNSUPPORTED_RULES_PRESENT" if "UNSUPPORTED_RULES_PRESENT" in reasons else "ALL_DECLARED_RULES_SUPPORTED")
    return dict(contract=CONTRACT, rule_version=RULE_VERSION, identity_scope="snapshot_deterministic",
                requested_knowledge_boundary=value["requested_knowledge_boundary"], economic_timestamp=value["economic_timestamp"],
                account=value["account"], manifest_reference=value["manifest"]["source"],
                manifest_content_fingerprint=_hash_id("account_rule_manifest_", value["manifest"]),
                manifest_coverage=value["manifest"]["coverage"], outcome=outcome, selected_regime=selected,
                interpretation_support=support, reason_codes=[r for r in REASON_CODES if r in reasons],
                source_authentication="NOT_VERIFIED_BY_THIS_CAPABILITY", limitations=list(LIMITATIONS),
                authority={"trade_decision": False, "financial_risk": False, "execution": False})


@dataclass(frozen=True)
class CausalAccountRuleRegimeAssessmentResult:
    assessment_id: str
    _payload: dict[str, Any]

    @property
    def payload(self):
        return deepcopy(self._payload)

    def to_dict(self):
        return deepcopy({**self._payload, "assessment_id": self.assessment_id})


class CausalAccountRuleRegimeAssessmentAnalyzer:
    def analyze(self, payload):
        try:
            result = _assess(payload)
            return CausalAccountRuleRegimeAssessmentResult(_hash_id("account_rule_regime_assessment_", result), result)
        except (KeyError, TypeError, AttributeError, RecursionError) as exc:
            raise ValueError("Malformed account rule regime input.") from exc


CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT = CausalAccountRuleRegimeAssessmentAnalyzer()


def validate_causal_account_rule_regime_assessment(value, assessment_input):
    """Reconstruct the complete artifact; structural validation does not authenticate claims."""
    try:
        supplied = value.to_dict() if hasattr(value, "to_dict") else value
        expected = CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT.analyze(assessment_input).to_dict()
        if _canonical(supplied) != _canonical(expected):
            raise ValueError("Assessment content or input binding mismatch.")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("Malformed assessment artifact.") from exc
