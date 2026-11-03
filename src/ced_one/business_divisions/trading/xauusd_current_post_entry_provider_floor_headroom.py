"""Conditional settled-endpoint native static floors; no selection or authority.

The host independently controls admission. Hashes and synthetic receipts do not
establish provider authentication or an independently controlled host mandate.
"""
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

from .xauusd_current_entry_provider_measure_projection_basis import (
    validate_current_entry_provider_measure_projection_basis,
)

CONTRACT = "trading.xauusd_current_post_entry_provider_floor_headroom.v1"
RULE_VERSION = "xauusd_current_post_entry_provider_floor_headroom_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_post_entry_provider_floor_headroom.admission.v1"
ADMISSION_RULE_VERSION = "xauusd_current_post_entry_provider_floor_headroom_admission_v1"
ADMISSION_PURPOSE = "PROVIDER_FLOOR_FACT_ADMISSION_ONLY"
IDENTITY_PREFIX = "current_post_entry_provider_floor_headroom_"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
CONDITIONS = ("C6_SCENARIO_CONDITIONS_RETAINED",
              "SUPPORTED_NATIVE_FLOOR_INTERPRETATIONS_APPLY_AT_ENDPOINT", "NO_UNMODELED_RELEVANT_RULE_CHANGE")
LIMITATIONS = ("CONDITIONAL_SETTLED_ENDPOINT_ONLY", "STATIC_IDENTICAL_BALANCE_FLOORS_ONLY",
              "SOURCE_AUTHENTICITY_NOT_VERIFIED", "CONTINUOUS_AND_ACTUAL_PROVIDER_COMPLIANCE_NOT_ESTABLISHED",
              "NO_AUTHORIZATION_LEASE", "NO_SELECTION_OR_CAPITAL_APPROVAL", "NO_ASSERTION_OUTSIDE_NATIVE_C",
              "NO_VACUOUS_NO_FLOOR_POSITIVE")
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
ENTRY_MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
_NAMESPACE = "source_id source_contract source_contract_version"
_COMPLETENESS = ("COMPLETE", "LIMITED", "UNKNOWN")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
TOPIC_KINDS = {
    "RULES": ("RULE",),
    "EXCEPTIONS_AND_WAIVERS": ("EXCEPTION", "WAIVER"),
    "OVERRIDES_AND_PRECEDENCE": ("OVERRIDE", "PRECEDENCE"),
    "REVISIONS_AND_WITHDRAWALS": ("AMENDMENT", "WITHDRAWAL"),
    "SCHEDULED_RULE_CHANGES": ("THRESHOLD_CHANGE", "COMPARATOR_CHANGE", "MEASURE_CHANGE", "FORCE_CHANGE"),
    "ACCOUNT_PHASE_AND_PACKAGE_CHANGES": ("PACKAGE_CHANGE", "PHASE_CHANGE"),
}
ENTRY_DISPOSITIONS = ("MAPPED_NATIVE_RULE", "SUPPORTING_RULE_EVIDENCE", "HISTORICAL_NON_GOVERNING",
                      "PROVEN_OUTSIDE_SCOPE", "OTHER_OBLIGATION", "UNRESOLVED")
RULE_TOPICS = ("RULE_DISPOSITION", "RULE_ENDPOINT_FORCE", "RULE_EXCEPTIONS", "RULE_MEASURE",
               "RULE_THRESHOLD", "RULE_HORIZON")
FINDING_CODES = frozenset("""OWNER_MISSING OWNER_UNKNOWN EVIDENCE_MISSING SOURCE_AVAILABILITY_UNKNOWN
NATIVE_SUPPORT_MISSING ADMISSION_MISSING ADMISSION_NOT_CURRENT RECEIPT_MISSING RECEIPT_UNRESOLVED
RECEIPT_SUPPORT_MISMATCH DECLARATION_COVERAGE_INCOMPLETE REVISION_HISTORY_INCOMPLETE
REVISION_ORDER_UNSUPPORTED COMPETING_DECLARATIONS NO_CURRENT_DECLARATION DECLARATION_WITHDRAWN
DECLARATION_EXPIRED HORIZON_CHANGE SOURCE_UNIVERSE_INCOMPLETE REPORT_MISSING REPORT_COVERAGE_INCOMPLETE
NATIVE_COVERAGE_INCOMPLETE UNMAPPED_SOURCE_ENTRY SOURCE_ENTRY_UNRESOLVED RULE_BINDING_MISSING
RULE_SOURCE_BINDING_MISSING RULE_DISPOSITION_UNRESOLVED POPULATION_UNRESOLVED ENDPOINT_UNRESOLVED
FORCE_UNRESOLVED EXCEPTIONS_UNRESOLVED RULE_MODEL_UNSUPPORTED MEASURE_UNSUPPORTED
MEASURE_IDENTITY_UNRESOLVED THRESHOLD_OPERAND_UNRESOLVED HORIZON_UNRESOLVED
NO_SUPPORTED_APPLICABLE_FLOOR""".split())
REASON_CODES = FINDING_CODES | {"ALL_C_EXCLUDED", "SUFFIX_EXCLUDED", "STATIC_ENDPOINT_DOMAIN_ESTABLISHED"}
_CONTEXT_KEYS = tuple("trusted_" + name + "_context_sha256" for name in
                      ("planning", "quantity", "feasibility", "position_effect", "position_limit", "financial_projection"))
_E = "/floor_evidence"
_C = "TRUSTED_PROVIDER_FLOOR_CONTEXT"

DOWNSTREAM_OBLIGATIONS = sorted((
    "ACCOUNT_PROFIT_LOCK_AND_PAYOUT_ELIGIBILITY", "ACTUAL_SETTLEMENT_AND_ACCOUNT_REVALIDATION",
    "ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL", "CANDIDATE_VALIDITY",
    "CONTINUOUS_PROVIDER_MEASURE_AND_DRAWDOWN_COMPLIANCE", "CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION",
    "ENTRY_QUANTITY_DOMAIN_MEMBERSHIP", "EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE",
    "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY", "MARKET_ORDER_AND_FILL_FEASIBILITY",
    "MISSION_CONTROL_CURRENT_AUTHORIZATION", "ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES",
    "OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE", "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE",
    "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM", "QUANTITY_SELECTION_POLICY_AND_SELECTION",
    "RISK_BUDGET_QUANTITY_FEASIBILITY",
))

def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields.")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty opaque text.")
    value.encode("utf-8")
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported closed value.")


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected JSON array.")
    return value


def _integer_text(value):
    if value == 0:
        return "0"
    sign, value = ("-" if value < 0 else ""), abs(value)
    chunks = []
    while value:
        value, chunk = divmod(value, 10 ** 9)
        chunks.append(chunk)
    return sign + str(chunks[-1]) + "".join(str(chunk).zfill(9) for chunk in reversed(chunks[:-1]))


def _canonical_unbounded(value):
    """Native JSON numbers are provenance only; no financial arithmetic uses floats."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON keys must be strings.")
        return "{" + ",".join(_canonical_unbounded(key) + ":" + _canonical_unbounded(value[key]) for key in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical_unbounded(item) for item in value) + "]"
    if type(value) is str:
        value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return _integer_text(value)
    if type(value) is float and math.isfinite(value):
        return json.dumps(value, allow_nan=False)
    raise ValueError("Expected finite serialized JSON.")


def _canonical(value):
    """Strict, type-preserving JSON; retain unbounded integer serialization."""
    seen, large_integer = set(), False

    def check(node):
        nonlocal large_integer
        kind = type(node)
        if kind in (dict, list):
            if id(node) in seen:
                return
            seen.add(id(node))
            if kind is dict:
                for key, item in node.items():
                    if type(key) is not str:
                        raise ValueError("JSON keys must be strings.")
                    key.encode("utf-8")
                    check(item)
            else:
                for item in node:
                    check(item)
        elif kind is str:
            node.encode("utf-8")
        elif node is None or kind is bool:
            return
        elif kind is int:
            large_integer |= node.bit_length() > 512
        elif kind is not float or not math.isfinite(node):
            raise ValueError("Expected finite serialized JSON.")

    check(value)
    if large_integer:
        return _canonical_unbounded(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _detached(value):
    """Copy each occurrence, including aliases within otherwise valid JSON input."""
    if type(value) is dict:
        return {key: _detached(item) for key, item in value.items()}
    if type(value) is list:
        return [_detached(item) for item in value]
    return value


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " mismatch.")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA-256.")


def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Expected explicitly zoned timestamp with seconds, at most microseconds.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _optional_time(value):
    return None if value is None else _time(value)


def _decimal(value):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Expected plain decimal string.")
    value = value.rstrip("0").rstrip(".") if "." in value else value
    return "0" if value in ("0", "-0") else value


def _unique(value, key):
    rows = _list(value)
    ids = [key(row) for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate identity/reference.")
    return sorted(rows, key=key)


def _namespace(value, snapshot=False):
    _keys(value, _NAMESPACE + (" source_snapshot_id" if snapshot else ""))
    for item in value.values():
        _text(item)


def _scope(value):
    _keys(value, "account provider_namespace provider_id venue_id instrument entry_direction entry_mechanism quantity_unit")
    _keys(value["account"], _NAMESPACE + " account_id environment currency")
    _keys(value["instrument"], _NAMESPACE + " environment instrument_id")
    _namespace(value["provider_namespace"])
    for key in ("account", "instrument"):
        for item in value[key].values():
            _text(item)
        _enum(value[key]["environment"], ("DEMO", "LIVE"))
    if re.fullmatch(r"[A-Z]{3}", value["account"]["currency"]) is None:
        raise ValueError("Currency requires three uppercase ASCII letters.")
    _same(value["account"]["environment"], value["instrument"]["environment"], "Environment")
    for key in ("provider_id", "venue_id", "quantity_unit"):
        _text(value[key])
    _enum(value["entry_direction"], ("LONG", "SHORT"))
    _enum(value["entry_mechanism"], (ENTRY_MECHANISM,))


def _interval(value):
    for key in ("economic_from", "economic_until"):
        value[key] = _time(value[key])
    if value["economic_from"] >= value["economic_until"]:
        raise ValueError("Economic interval must be finite and nonempty.")


def _chronology(value, deadline):
    value["observed_at"] = _time(value["observed_at"])
    value["source_available_at"] = _optional_time(value["source_available_at"])
    if value["observed_at"] > deadline or (value["source_available_at"] is not None and
                                           value["source_available_at"] > value["observed_at"]):
        raise ValueError("Impossible source chronology.")


def _cutoff(value, deadline):
    value["source_information_cutoff"] = _optional_time(value["source_information_cutoff"])
    if value["source_information_cutoff"] is not None and value["source_information_cutoff"] > deadline:
        raise ValueError("Information cutoff postdates observation.")


def _refs(rows, catalog, deadline):
    for ref in _list(rows):
        _keys(ref, "evidence_id envelope_sha256")
        _text(ref["evidence_id"])
        _hash(ref["envelope_sha256"])
        original = catalog.get(ref["evidence_id"])
        if original is None or _digest(original) != ref["envelope_sha256"]:
            raise ValueError("Missing or mismatched original envelope.")
        if original["observed_at"] > deadline:
            raise ValueError("Original postdates its containing assertion.")
    return _unique(rows, _canonical)


def _union(rows):
    return sorted({_canonical(row): row for row in rows}.values(), key=_canonical)


def _get(value, *path):
    for key in path:
        if value is None:
            return None
        value = value.get(key)
    return value


class _Native:
    """Closed catalogue of already replayed owners and their preserved original nodes."""

    def __init__(self, pair):
        self.bundles = {"COMPOSITION_BUNDLE": pair}
        fr = _get(pair, "request", "risk_budget_feasibility", "request")
        pb, rb = _get(fr, "risk_policy"), _get(fr, "risk_basis")
        self.bundles.update(POLICY_BUNDLE=pb, RISK_BASIS_BUNDLE=rb,
                            ACCOUNT_BUNDLE=_get(pb, "request", "account_state"),
                            REGIME_BUNDLE=_get(pb, "request", "account_rule_regime"))
        self.nodes, self.deadlines, self.refs = {}, {}, {}
        for kind, bundle in self.bundles.items():
            if bundle is not None:
                deadline = None
                if kind == "ACCOUNT_BUNDLE":
                    deadline = _time(bundle["snapshot"]["observation"]["timing"]["observed_at"])
                self.add(kind, None, bundle, kind, deadline)
        self.function = _get(rb, "assessment", "risk_function")
        if self.function is not None:
            self.add("RISK_FUNCTION", None, self.function, "RISK_BASIS_BUNDLE")
            for charge in self.function["charges"]:
                self.add("RISK_CHARGE", dict(charge_id=charge["charge_id"]), charge, "RISK_BASIS_BUNDLE")
        if pb is not None:
            for i, operand in enumerate(pb["request"]["provider_operands"]):
                self.add("POLICY_OPERAND", dict(operand_index=i), operand, "POLICY_BUNDLE", _time(operand["available_at"]))
                for j, support in enumerate(operand["supporting_evidence"]):
                    self.add("POLICY_OPERAND_SUPPORT", dict(operand_index=i, evidence_index=j), support,
                             "POLICY_BUNDLE", _time(support["available_at"]))
        gb = self.bundles["REGIME_BUNDLE"]
        self.selected = _get(gb, "assessment", "selected_regime")
        if gb is None:
            return
        original = gb["assessment_input"]
        manifest = original["manifest"]
        observed = _time(manifest["timing"]["observed_at"])
        for node in manifest["evidence"]:
            self.add("REGIME_DOCUMENT", dict(evidence_id=node["evidence_id"]), node, "REGIME_BUNDLE",
                     _time(node["timing"]["observed_at"]))
        for node in manifest["assignments"]:
            ref = self.add("REGIME_ASSIGNMENT", dict(assignment_id=node["assignment_id"]), node, "REGIME_BUNDLE", observed)
            self.clauses(ref, "EVIDENCE_REFS", node["evidence_refs"], observed)
            for i, binding in enumerate(node["package_bindings"]):
                ref = self.add("REGIME_BINDING", dict(assignment_id=node["assignment_id"], binding_index=i),
                               binding, "REGIME_BUNDLE", observed)
                self.clauses(ref, "EVIDENCE_REFS", binding["evidence_refs"], observed)
        for node in manifest["packages"]:
            selector = {key: node[key] for key in ("package_id", "package_revision")}
            deadline = _time(node["interpretation"]["interpreted_at"])
            ref = self.add("REGIME_PACKAGE", selector, node, "REGIME_BUNDLE", deadline)
            self.clauses(ref, "EVIDENCE_REFS", node["evidence_refs"], deadline)
            self.clauses(ref, "COVERAGE_EVIDENCE_REFS", node["coverage"]["evidence_refs"], deadline)
            for rule in node["rules"]:
                selector = dict(selector, rule_id=rule["rule_id"])
                ref = self.add("REGIME_RULE", selector, rule, "REGIME_BUNDLE", deadline)
                self.clauses(ref, "EVIDENCE_REFS", rule["evidence_refs"], deadline)
                if rule["body"]["type"] in ("STATIC_FLOOR", "DAILY_RESET_FLOOR"):
                    ref = self.add("REGIME_MEASURE", selector, rule["body"]["measure"], "REGIME_BUNDLE", deadline)
                    self.clauses(ref, "DEFINITION_REFS", rule["body"]["measure"]["definition_refs"], deadline)
        for i, node in enumerate(original["approvals"]):
            self.add("REGIME_APPROVAL", dict(approval_index=i), node, "REGIME_BUNDLE", _time(node["observed_at"]))

    def add(self, kind, selector, node, owner, deadline=None):
        key = kind, _canonical(selector)
        if key in self.nodes:
            raise ValueError("Ambiguous native identity.")
        ref = dict(kind=kind, owner_bundle_sha256=_digest(self.bundles[owner]),
                   selector=deepcopy(selector), content_sha256=_digest(node))
        self.nodes[key], self.deadlines[key], self.refs[key] = node, deadline, ref
        return ref

    def clauses(self, container, field, rows, deadline):
        for i, row in enumerate(rows):
            self.add("REGIME_CLAUSE", dict(container=container, field=field, clause_index=i), row, "REGIME_BUNDLE", deadline)

    def reference(self, kind, selector=None):
        return self.refs.get((kind, _canonical(selector)))

    def resolve(self, ref, kind=None):
        _keys(ref, "kind owner_bundle_sha256 selector content_sha256")
        _hash(ref["owner_bundle_sha256"])
        _hash(ref["content_sha256"])
        if kind is not None and ref["kind"] != kind:
            raise ValueError("Wrong native reference kind.")
        selector, k = ref["selector"], ref["kind"]
        fields = {"POLICY_OPERAND": "operand_index", "POLICY_OPERAND_SUPPORT": "operand_index evidence_index", "RISK_CHARGE": "charge_id", "REGIME_ASSIGNMENT": "assignment_id",
                  "REGIME_PACKAGE": "package_id package_revision", "REGIME_BINDING": "assignment_id binding_index",
                  "REGIME_RULE": "package_id package_revision rule_id", "REGIME_MEASURE": "package_id package_revision rule_id",
                  "REGIME_DOCUMENT": "evidence_id", "REGIME_APPROVAL": "approval_index"}
        if k == "REGIME_CLAUSE":
            _keys(selector, "container field clause_index")
            container = selector["container"]
            if type(container) is not dict or container.get("kind") not in (
                "REGIME_ASSIGNMENT", "REGIME_BINDING", "REGIME_PACKAGE", "REGIME_RULE", "REGIME_MEASURE"
            ):
                raise ValueError("Clause container is outside bounded catalogue.")
            self.resolve(container)
            _enum(selector["field"], ("EVIDENCE_REFS", "COVERAGE_EVIDENCE_REFS", "DEFINITION_REFS"))
            if type(selector["clause_index"]) is not int or selector["clause_index"] < 0:
                raise ValueError("Clause index requires nonnegative integer.")
        elif k in fields:
            _keys(selector, fields[k])
            for name, value in selector.items():
                if name.endswith("_index"):
                    if type(value) is not int or value < 0:
                        raise ValueError("Native index requires nonnegative integer.")
                else:
                    _text(value)
        elif k in self.bundles or k == "RISK_FUNCTION":
            if selector is not None:
                raise ValueError("Bundle/function selector must be null.")
        else:
            raise ValueError("Unknown native kind.")
        key = k, _canonical(selector)
        expected = self.refs.get(key)
        if expected is None:
            raise ValueError("Native target is missing/outside catalogue.")
        _same(ref, expected, "Native content/owner binding")
        return self.nodes[key]

    def under(self, container):
        return [ref for (kind, _), ref in self.refs.items() if kind == "REGIME_CLAUSE" and
                ref["selector"]["container"] == container]

    def scope_references(self, target, at, end=None):
        if target is None or self.selected is None:
            return []
        scope = [target["assignment"], target["package"]]
        for ref in list(scope):
            scope += self.under(ref)
        assignment = self.resolve(target["assignment"])
        package = self.resolve(target["package"])
        for i, binding in enumerate(assignment["package_bindings"]):
            period = binding["effective_period"]
            if binding["package"] == {key: package[key] for key in ("package_id", "package_revision")} and (
                period["effective_from"] is not None and
                (_time(period["effective_from"]) <= at if end is None else _time(period["effective_from"]) < end) and
                period["end_status"] != "UNKNOWN" and
                (period["effective_until"] is None or at < _time(period["effective_until"]))
            ):
                ref = self.reference("REGIME_BINDING", dict(assignment_id=assignment["assignment_id"], binding_index=i))
                scope += [ref] + self.under(ref)
        for (kind, _), ref in self.refs.items():
            if kind == "REGIME_APPROVAL" and any(self.resolve(ref)["approval_reference"] == a["approval_reference"]
                                                 for a in self.selected["approval_references"]):
                scope.append(ref)
        return scope



def _integer(digits):
    sign = -1 if digits.startswith("-") else 1
    digits = digits.lstrip("-")
    result = 0
    for offset in range(0, len(digits), 9):
        part = digits[offset:offset + 9]
        result = result * 10 ** len(part) + int(part)
    return sign * result


def _number(value):
    value = _decimal(value)
    whole, _, part = value.lstrip("-").partition(".")
    return Fraction((-1 if value.startswith("-") else 1) * _integer(whole + part), 10 ** len(part))


def _plain(value):
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("Nonterminating native decimal result.")
    scale = max(twos, fives)
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = _integer_text(abs(coefficient)).zfill(scale + 1)
    text = digits if not scale else digits[:-scale] + "." + digits[-scale:]
    return _decimal(("-" if coefficient < 0 else "") + text)


def _strings(rows, choices=None):
    for value in _list(rows):
        _text(value)
        if choices is not None:
            _enum(value, choices)
    return _unique(rows, lambda value: value)


def _nullable_flags(value, fields):
    for key in fields:
        if value[key] is not None and type(value[key]) is not bool:
            raise ValueError("Omission flags require Boolean or null.")


def _nref_schema(ref, kind=None):
    """Validate historical reference grammar without rebinding historical owners."""
    _keys(ref, "kind owner_bundle_sha256 selector content_sha256")
    _hash(ref["owner_bundle_sha256"])
    _hash(ref["content_sha256"])
    if kind is not None:
        _enum(ref["kind"], (kind,))
    selectors = {
        "RISK_CHARGE": "charge_id", "REGIME_ASSIGNMENT": "assignment_id",
        "REGIME_PACKAGE": "package_id package_revision", "REGIME_BINDING": "assignment_id binding_index",
        "REGIME_RULE": "package_id package_revision rule_id", "REGIME_MEASURE": "package_id package_revision rule_id",
        "REGIME_DOCUMENT": "evidence_id", "REGIME_APPROVAL": "approval_index",
        "POLICY_OPERAND": "operand_index", "POLICY_OPERAND_SUPPORT": "operand_index evidence_index",
    }
    kind, selector = ref["kind"], ref["selector"]
    if kind in selectors:
        _keys(selector, selectors[kind])
        for key, value in selector.items():
            if key.endswith("_index"):
                if type(value) is not int or value < 0:
                    raise ValueError("Native array index requires nonnegative integer.")
            else:
                _text(value)
    elif kind == "REGIME_CLAUSE":
        _keys(selector, "container field clause_index")
        _nref_schema(selector["container"])
        allowed = {"REGIME_ASSIGNMENT": ("EVIDENCE_REFS",), "REGIME_BINDING": ("EVIDENCE_REFS",),
                   "REGIME_PACKAGE": ("EVIDENCE_REFS", "COVERAGE_EVIDENCE_REFS"),
                   "REGIME_RULE": ("EVIDENCE_REFS",), "REGIME_MEASURE": ("DEFINITION_REFS",)}
        _enum(selector["field"], allowed.get(selector["container"]["kind"], ()))
        if type(selector["clause_index"]) is not int or selector["clause_index"] < 0:
            raise ValueError("Clause index requires nonnegative integer.")
    elif kind in ("COMPOSITION_BUNDLE", "ACCOUNT_BUNDLE", "POLICY_BUNDLE", "REGIME_BUNDLE",
                  "RISK_BASIS_BUNDLE", "RISK_FUNCTION"):
        if selector is not None:
            raise ValueError("Bundle/function selector must be null.")
    else:
        raise ValueError("Unknown native reference kind.")


def _record_ref(ref):
    _keys(ref, "record_id content_sha256")
    _text(ref["record_id"])
    _hash(ref["content_sha256"])


def _entry_ref(ref, entries):
    _keys(ref, "entry_id content_sha256")
    _text(ref["entry_id"])
    _hash(ref["content_sha256"])
    if ref["entry_id"] not in entries:
        raise ValueError("Dangling entry reference.")
    _same(ref["content_sha256"], _digest(entries[ref["entry_id"]]), "Entry content")


def _report_key(key):
    _keys(key, "inventory_id actor_id topic")
    _text(key["inventory_id"])
    _text(key["actor_id"])
    _enum(key["topic"], TOPIC_KINDS)


def _period(value):
    _keys(value, "effective_from effective_until end_status")
    for key in ("effective_from", "effective_until"):
        value[key] = _optional_time(value[key])
    _enum(value["end_status"], ("KNOWN", "OPEN_ENDED", "UNKNOWN"))
    if (value["end_status"] == "KNOWN") != (value["effective_until"] is not None):
        raise ValueError("Period end status contradicts its timestamp.")
    if value["effective_from"] is not None and value["effective_until"] is not None and (
        value["effective_from"] >= value["effective_until"]
    ):
        raise ValueError("Empty effective period.")


def _assertion(value, choices, catalog, observed):
    if value is None:
        return
    _keys(value, "status evidence_refs")
    _enum(value["status"], choices)
    value["evidence_refs"] = _refs(value["evidence_refs"], catalog, observed)


def _universe(value, catalog, observed):
    _keys(value, "state_at source_information_cutoff economic_from economic_until source_universe_completeness actor_universe_completeness actors sources reports entries evidence_refs")
    _interval(value)
    value["state_at"] = _time(value["state_at"])
    if value["state_at"] > observed:
        raise ValueError("Universe state postdates observation.")
    _cutoff(value, observed)
    for key in ("source_universe_completeness", "actor_universe_completeness"):
        _enum(value[key], _COMPLETENESS)
    value["evidence_refs"] = _refs(value["evidence_refs"], catalog, observed)
    for actor in _list(value["actors"]):
        _keys(actor, "actor_id namespace role topics evidence_refs")
        _text(actor["actor_id"])
        _namespace(actor["namespace"])
        _enum(actor["role"], ("PROVIDER", "ACCOUNT_AUTHORITY", "GOVERNANCE", "OTHER"))
        actor["topics"] = _strings(actor["topics"], TOPIC_KINDS)
        actor["evidence_refs"] = _refs(actor["evidence_refs"], catalog, observed)
    value["actors"] = _unique(value["actors"], lambda row: row["actor_id"])
    actors = {row["actor_id"]: row for row in value["actors"]}
    for source in _list(value["sources"]):
        _keys(source, "inventory_id namespace role responsibilities evidence_refs")
        _text(source["inventory_id"])
        _namespace(source["namespace"])
        _enum(source["role"], ("RULEBOOK", "AGREEMENT", "SUPPLEMENTAL", "REVISION_LEDGER", "OTHER"))
        for responsibility in _list(source["responsibilities"]):
            _keys(responsibility, "actor_id topics")
            if responsibility["actor_id"] not in actors:
                raise ValueError("Unknown responsible actor.")
            responsibility["topics"] = _strings(responsibility["topics"], TOPIC_KINDS)
            if not responsibility["topics"] or not set(responsibility["topics"]) <= set(actors[responsibility["actor_id"]]["topics"]):
                raise ValueError("Invalid actor responsibility topics.")
        source["responsibilities"] = _unique(source["responsibilities"], lambda row: row["actor_id"])
        source["evidence_refs"] = _refs(source["evidence_refs"], catalog, observed)
    value["sources"] = _unique(value["sources"], lambda row: row["inventory_id"])
    sources = {row["inventory_id"]: row for row in value["sources"]}
    for report in _list(value["reports"]):
        _keys(report, "key source state_at source_information_cutoff economic_from economic_until source_available_at observed_at inventory_completeness revision_completeness starting_basis entry_ids missing_entry_ids entries_omitted history_truncated evidence_refs")
        _report_key(report["key"])
        key = report["key"]
        source = sources.get(key["inventory_id"])
        if source is None or not any(r["actor_id"] == key["actor_id"] and key["topic"] in r["topics"] for r in source["responsibilities"]):
            raise ValueError("Report outside actual responsibility.")
        _namespace(report["source"], True)
        _same({k: report["source"][k] for k in _NAMESPACE.split()}, source["namespace"], "Report source namespace")
        _chronology(report, observed)
        report["state_at"] = _time(report["state_at"])
        if report["state_at"] > report["observed_at"]:
            raise ValueError("Report state postdates observation.")
        _cutoff(report, report["observed_at"])
        _interval(report)
        for name in ("inventory_completeness", "revision_completeness"):
            _enum(report[name], _COMPLETENESS)
        _enum(report["starting_basis"], ("FROM_INCEPTION", "INCOMPLETE_OR_UNKNOWN"))
        _nullable_flags(report, ("entries_omitted", "history_truncated"))
        for name in ("entry_ids", "missing_entry_ids"):
            report[name] = _strings(report[name])
        gaps = bool(report["missing_entry_ids"]) or report["entries_omitted"] is not False
        if report["inventory_completeness"] == "COMPLETE" and gaps:
            raise ValueError("Complete source inventory contradicts omissions.")
        if report["revision_completeness"] == "COMPLETE" and (gaps or report["history_truncated"] is not False or report["starting_basis"] != "FROM_INCEPTION"):
            raise ValueError("Complete source revisions contradict gaps.")
        report["evidence_refs"] = _refs(report["evidence_refs"], catalog, report["observed_at"])
    value["reports"] = _unique(value["reports"], lambda row: _canonical(row["key"]))
    reports = {_canonical(row["key"]): row for row in value["reports"]}
    for entry in _list(value["entries"]):
        _keys(entry, "entry_id report_key source_record_id kind effective_period source_available_at observed_at disposition native_rule_refs related_entry_ids evidence_refs")
        for key in ("entry_id", "source_record_id"):
            _text(entry[key])
        _report_key(entry["report_key"])
        report = reports.get(_canonical(entry["report_key"]))
        if report is None:
            raise ValueError("Source entry has no containing report.")
        _enum(entry["kind"], TOPIC_KINDS[entry["report_key"]["topic"]])
        _enum(entry["disposition"], ENTRY_DISPOSITIONS)
        _period(entry["effective_period"])
        _chronology(entry, report["observed_at"])
        for ref in _list(entry["native_rule_refs"]):
            _nref_schema(ref, "REGIME_RULE")
        entry["native_rule_refs"] = _unique(entry["native_rule_refs"], _canonical)
        if entry["disposition"] == "MAPPED_NATIVE_RULE" and (entry["kind"] != "RULE" or not entry["native_rule_refs"]):
            raise ValueError("Mapped rule requires RULE entry and native rules.")
        if entry["disposition"] == "SUPPORTING_RULE_EVIDENCE" and not entry["native_rule_refs"]:
            raise ValueError("Supporting source entry requires a native rule.")
        entry["related_entry_ids"] = _strings(entry["related_entry_ids"])
        entry["evidence_refs"] = _refs(entry["evidence_refs"], catalog, entry["observed_at"])
    value["entries"] = _unique(value["entries"], lambda row: row["entry_id"])
    entries = {row["entry_id"]: row for row in value["entries"]}
    for key, report in reports.items():
        rows = [row for row in entries.values() if _canonical(row["report_key"]) == key]
        _same(report["entry_ids"], sorted(row["entry_id"] for row in rows), "Exact report membership")
        _unique(rows, lambda row: row["source_record_id"])
        if set(report["missing_entry_ids"]) & entries.keys():
            raise ValueError("Missing source entry is actually supplied.")
        for entry in rows:
            for related in entry["related_entry_ids"]:
                if related == entry["entry_id"] or (related not in entries and related not in report["missing_entry_ids"]):
                    raise ValueError("Unexplained or self-related source entry.")


def _closure(value, universe, catalog, observed):
    _keys(value, "source_universe_completeness revision_completeness source_information_cutoff report_keys entry_refs evidence_refs")
    for key in ("source_universe_completeness", "revision_completeness"):
        _enum(value[key], _COMPLETENESS)
    _cutoff(value, observed)
    reports = {_canonical(row["key"]): row for row in universe["reports"]}
    entries = {row["entry_id"]: row for row in universe["entries"]}
    for key in _list(value["report_keys"]):
        _report_key(key)
        if _canonical(key) not in reports:
            raise ValueError("Closure references an absent report.")
    value["report_keys"] = _unique(value["report_keys"], _canonical)
    for ref in _list(value["entry_refs"]):
        _entry_ref(ref, entries)
    value["entry_refs"] = _unique(value["entry_refs"], lambda ref: ref["entry_id"])
    value["evidence_refs"] = _refs(value["evidence_refs"], catalog, observed)


def _body(value, catalog, observed):
    _keys(value, "subjects source_information_cutoff economic_from economic_until universe rule_bindings")
    _keys(value["subjects"], "projection_bundle_sha256 projection_basis_sha256 policy_bundle_sha256 account_bundle_sha256 regime_bundle_sha256")
    for item in value["subjects"].values():
        if item is not None:
            _hash(item)
    _cutoff(value, observed)
    _interval(value)
    _universe(value["universe"], catalog, observed)
    entries = {row["entry_id"]: row for row in value["universe"]["entries"]}
    actors = {row["actor_id"] for row in value["universe"]["actors"]}
    for binding in _list(value["rule_bindings"]):
        _keys(binding, "rule_reference source_entries population endpoint force exceptions measure threshold horizon evidence_refs")
        _nref_schema(binding["rule_reference"], "REGIME_RULE")
        for ref in _list(binding["source_entries"]):
            _entry_ref(ref, entries)
        binding["source_entries"] = _unique(binding["source_entries"], lambda ref: ref["entry_id"])
        if binding["population"] is None:
            raise ValueError("Population assertion is not nullable.")
        for key, choices in (
            ("population", ("CONTAINS_SCENARIO", "DISJOINT", "UNKNOWN")),
            ("endpoint", ("EXPLICIT_SETTLED_ENDPOINT", "CONTINUOUS_INCLUDES_SETTLED_ENDPOINT", "OUTSIDE_SETTLED_ENDPOINT", "UNKNOWN")),
            ("force", ("MANDATORY_UNCHANGED", "NOT_MANDATORY", "UNKNOWN")),
            ("measure", ("IDENTICAL", "INCOMPATIBLE", "UNKNOWN")),
        ):
            _assertion(binding[key], choices, catalog, observed)
        exception = binding["exceptions"]
        if exception is not None:
            _keys(exception, "resolution closure authority_actor_ids authority_evidence_refs precedence_evidence_refs evidence_refs")
            _enum(exception["resolution"], ("NONE_APPLICABLE", "RESOLVED_WITH_PREDICATE_UNCHANGED", "WAIVED_THROUGHOUT", "MODIFIES_NATIVE_PREDICATE", "UNKNOWN"))
            _closure(exception["closure"], value["universe"], catalog, observed)
            exception["authority_actor_ids"] = _strings(exception["authority_actor_ids"])
            if not set(exception["authority_actor_ids"]) <= actors:
                raise ValueError("Exception authority actor absent.")
            for key in ("authority_evidence_refs", "precedence_evidence_refs", "evidence_refs"):
                exception[key] = _refs(exception[key], catalog, observed)
            if exception["resolution"] == "WAIVED_THROUGHOUT" and _get(binding["force"], "status") == "MANDATORY_UNCHANGED":
                raise ValueError("Mandatory unchanged force contradicts whole-horizon waiver.")
        threshold = binding["threshold"]
        if threshold is not None:
            _keys(threshold, "relationship initial_reference_operand evidence_refs")
            _enum(threshold["relationship"], ("NATIVE_COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"))
            if threshold["initial_reference_operand"] is not None:
                _nref_schema(threshold["initial_reference_operand"], "POLICY_OPERAND")
            threshold["evidence_refs"] = _refs(threshold["evidence_refs"], catalog, observed)
        horizon = binding["horizon"]
        if horizon is not None:
            _keys(horizon, "status closure evidence_refs")
            _enum(horizon["status"], ("INVARIANT_AS_KNOWN_ON_T_H", "KNOWN_RELEVANT_CHANGE_BEFORE_H", "UNKNOWN"))
            _closure(horizon["closure"], value["universe"], catalog, observed)
            horizon["evidence_refs"] = _refs(horizon["evidence_refs"], catalog, observed)
        binding["evidence_refs"] = _refs(binding["evidence_refs"], catalog, observed)
    value["rule_bindings"] = _unique(value["rule_bindings"], lambda row: _canonical(row["rule_reference"]))


def _evidence(value, native, scope, at):
    if value is None:
        return {}, []
    _keys(value, "source scope source_available_at observed_at originals native_mappings coverage records")
    _namespace(value["source"], True)
    _scope(value["scope"])
    _same(value["scope"], scope, "Evidence scope")
    _chronology(value, at)
    observed = value["observed_at"]
    for original in _list(value["originals"]):
        _keys(original, "evidence_id source media_type content_base64 content_sha256 source_available_at observed_at")
        for key in ("evidence_id", "media_type", "content_base64"):
            _text(original[key])
        _namespace(original["source"], True)
        _hash(original["content_sha256"])
        raw = base64.b64decode(original["content_base64"], validate=True)
        if not raw or base64.b64encode(raw).decode("ascii") != original["content_base64"]:
            raise ValueError("Original requires nonempty canonical padded base64.")
        if hashlib.sha256(raw).hexdigest() != original["content_sha256"]:
            raise ValueError("Original raw-byte hash mismatch.")
        _chronology(original, observed)
    value["originals"] = _unique(value["originals"], lambda row: row["evidence_id"])
    catalog = {row["evidence_id"]: row for row in value["originals"]}
    for mapping in _list(value["native_mappings"]):
        _keys(mapping, "native_reference original_reference original_locator relationship")
        ref = mapping["native_reference"]
        _nref_schema(ref)
        node = native.resolve(ref)
        _text(mapping["original_locator"])
        _enum(mapping["relationship"], ({"REGIME_DOCUMENT": "EXACT_DOCUMENT", "REGIME_CLAUSE": "CLAUSE_SUPPORT"}.get(ref["kind"], "ASSERTION_SUPPORT"),))
        deadline = native.deadlines[ref["kind"], _canonical(ref["selector"])] or observed
        _refs([mapping["original_reference"]], catalog, min(deadline, observed))
        original = catalog[mapping["original_reference"]["evidence_id"]]
        if ref["kind"] == "REGIME_DOCUMENT":
            _same(original["source"], node["source"], "Native document source")
            if node["document_sha256"] is not None:
                _same(original["content_sha256"], node["document_sha256"], "Native document bytes")
            if node["timing"]["source_available_at"] is not None and original["source_available_at"] is not None:
                _same(original["source_available_at"], _time(node["timing"]["source_available_at"]), "Native publication")
    value["native_mappings"] = _unique(value["native_mappings"], _canonical)
    for mapping in value["native_mappings"]:
        ref = mapping["native_reference"]
        if ref["kind"] == "REGIME_CLAUSE":
            clause = native.resolve(ref)
            document = native.reference("REGIME_DOCUMENT", dict(evidence_id=clause["evidence_id"]))
            documents = [m for m in value["native_mappings"] if m["native_reference"] == document]
            if documents and not any(m["original_reference"] == mapping["original_reference"] for m in documents):
                raise ValueError("Clause/document original mismatch.")
    coverage = value["coverage"]
    _keys(coverage, "economic_from economic_until source_information_cutoff declaration_completeness revision_completeness starting_basis root_records missing_record_ids records_omitted history_truncated source_available_at observed_at evidence_refs")
    _interval(coverage)
    _chronology(coverage, observed)
    _cutoff(coverage, coverage["observed_at"])
    for key in ("declaration_completeness", "revision_completeness"):
        _enum(coverage[key], _COMPLETENESS)
    _enum(coverage["starting_basis"], ("FROM_INCEPTION", "INCOMPLETE_OR_UNKNOWN"))
    for key in ("records_omitted", "history_truncated"):
        if coverage[key] is not None and type(coverage[key]) is not bool:
            raise ValueError("Omission indicator must be boolean or null.")
    for ref in _list(coverage["root_records"]):
        _record_ref(ref)
    coverage["root_records"] = _unique(coverage["root_records"], lambda row: row["record_id"])
    for identifier in _list(coverage["missing_record_ids"]):
        _text(identifier)
    coverage["missing_record_ids"] = _unique(coverage["missing_record_ids"], lambda row: row)
    coverage["evidence_refs"] = _refs(coverage["evidence_refs"], catalog, coverage["observed_at"])
    for record in _list(value["records"]):
        kind = record.get("kind") if type(record) is dict else None
        _enum(kind, ("DECLARE", "WITHDRAW"))
        _keys(record, "record_id kind predecessor effective_from source_available_at observed_at evidence_refs" +
              (" effective_until body" if kind == "DECLARE" else ""))
        _text(record["record_id"])
        record["effective_from"] = _time(record["effective_from"])
        _chronology(record, observed)
        previous = record["predecessor"]
        if type(previous) is not dict:
            raise ValueError("Invalid predecessor.")
        _enum(previous.get("kind"), ("ROOT", "UNKNOWN", "RECORD"))
        _keys(previous, "kind record" if previous["kind"] == "RECORD" else "kind")
        if previous["kind"] == "RECORD":
            _record_ref(previous["record"])
        if kind == "WITHDRAW" and previous["kind"] == "ROOT":
            raise ValueError("Withdrawal cannot be a root.")
        record["evidence_refs"] = _refs(record["evidence_refs"], catalog, record["observed_at"])
        if kind == "DECLARE":
            record["effective_until"] = _optional_time(record["effective_until"])
            if record["effective_until"] is not None and record["effective_until"] <= record["effective_from"]:
                raise ValueError("Declaration interval must be nonempty.")
            _body(record["body"], catalog, record["observed_at"])
    value["records"] = _unique(value["records"], lambda row: row["record_id"])
    return catalog, value["native_mappings"]


def _history(evidence):
    coverage = evidence["coverage"]
    records = {row["record_id"]: row for row in evidence["records"]}
    missing = set(coverage["missing_record_ids"])
    if missing & records.keys():
        raise ValueError("Declared missing record is supplied.")

    def resolve(ref):
        row = records.get(ref["record_id"])
        if row is None and ref["record_id"] not in missing:
            raise ValueError("Unexplained dangling revision reference.")
        if row is not None and _digest(row) != ref["content_sha256"]:
            raise ValueError("Revision content hash mismatch.")
        return row

    roots = {ref["record_id"] for ref in coverage["root_records"]}
    for ref in coverage["root_records"]:
        row = resolve(ref)
        if row is not None and row["predecessor"]["kind"] != "ROOT":
            raise ValueError("Declared root is not a root.")
    children, backwards = {}, False
    for row in records.values():
        pred = row["predecessor"]
        if pred["kind"] == "ROOT" and row["record_id"] not in roots:
            raise ValueError("Supplied root omitted from coverage.")
        if pred["kind"] == "RECORD":
            parent = resolve(pred["record"])
            if parent is not None:
                children.setdefault(parent["record_id"], []).append(row)
                backwards |= any(row[key] < parent[key] for key in ("effective_from", "observed_at")) or (
                    row["source_available_at"] is not None and parent["source_available_at"] is not None and
                    row["source_available_at"] < parent["source_available_at"])
    finished = set()
    for identifier in records:
        path, current = set(), identifier
        while current in records and current not in finished:
            if current in path:
                raise ValueError("Cyclic/self revision reference.")
            path.add(current)
            pred = records[current]["predecessor"]
            current = pred["record"]["record_id"] if pred["kind"] == "RECORD" else None
        finished.update(path)
    gaps = bool(missing) or coverage["starting_basis"] != "FROM_INCEPTION" or any(
        coverage[key] is not False for key in ("records_omitted", "history_truncated")) or any(
        row["predecessor"]["kind"] == "UNKNOWN" for row in records.values())
    if coverage["revision_completeness"] == "COMPLETE" and gaps:
        raise ValueError("Complete revision history contradicts declared gaps.")
    competing = len(roots) > 1 or any(len(rows) > 1 for rows in children.values())
    chain = []
    if len(roots) == 1 and not competing and not missing:
        row = records.get(next(iter(roots)))
        while row is not None:
            chain.append(row)
            row = next(iter(children.get(row["record_id"], [])), None)
        if len(chain) != len(records):
            chain = []
    incomplete = gaps or coverage["revision_completeness"] != "COMPLETE" or (bool(records) and not chain)
    return chain, incomplete, competing, backwards



def _observations(value):
    if type(value) is dict:
        for key, item in value.items():
            if key == "observed_at":
                yield _time(item)
            else:
                yield from _observations(item)
    elif type(value) is list:
        for item in value:
            yield from _observations(item)


def _selected_rules(native):
    if native.selected is None:
        return []
    p = native.selected["package"]
    return [(ref, native.resolve(ref)) for (kind, _), ref in native.refs.items() if kind == "REGIME_RULE" and
            all(ref["selector"][key] == p[key] for key in ("package_id", "package_revision"))]


def _current_pins(record, q, owner, native):
    if record is None or record["kind"] != "DECLARE" or (
        record["effective_until"] is not None and record["effective_until"] <= q["knowledge_boundary"]
    ):
        return
    expected = dict(projection_bundle_sha256=q["provider_measure_projection"],
                    projection_basis_sha256=None if owner is None else owner["projection_basis"],
                    policy_bundle_sha256=native.bundles["POLICY_BUNDLE"],
                    account_bundle_sha256=native.bundles["ACCOUNT_BUNDLE"],
                    regime_bundle_sha256=native.bundles["REGIME_BUNDLE"])
    for field, node in expected.items():
        pin = record["body"]["subjects"][field]
        if node is None and pin is not None:
            raise ValueError("Unavailable subject must have a null pin.")
        if node is not None and pin is not None:
            _same(pin, _digest(node), "Current declaration subject")
    selected = {_canonical(ref) for ref, _ in _selected_rules(native)}
    for entry in record["body"]["universe"]["entries"]:
        for ref in entry["native_rule_refs"]:
            native.resolve(ref, "REGIME_RULE")
            if native.selected is not None and _canonical(ref) not in selected:
                raise ValueError("Current source entry references unselected package.")
    # Native identity remains known even when a different projection obligation
    # is unresolved; UNKNOWN must not hide a false IDENTICAL assertion.
    target = None if owner is None else _get(owner["measure_target"], "measure")
    for binding in record["body"]["rule_bindings"]:
        ref = binding["rule_reference"]
        rule = native.resolve(ref, "REGIME_RULE")
        if native.selected is not None and _canonical(ref) not in selected:
            raise ValueError("Current binding references unselected package.")
        if _get(binding["measure"], "status") == "IDENTICAL" and target is not None:
            _same(rule["body"].get("measure"), native.resolve(target), "Claimed exact native measure")
        threshold = binding["threshold"]
        nt = rule["body"].get("threshold")
        if threshold is None:
            continue
        operand_ref = threshold["initial_reference_operand"]
        if nt is not None and nt["kind"] == "ABSOLUTE" and operand_ref is not None:
            raise ValueError("Absolute floor cannot substitute an initial operand.")
        if operand_ref is not None:
            operand = native.resolve(operand_ref, "POLICY_OPERAND")
            if nt is None or nt["kind"] != "INITIAL_REFERENCE_FRACTION" or operand["tag"] != "INITIAL_REFERENCE" or (
                operand["rule_reference"]["rule_id"] != rule["rule_id"] or operand["body"]["reference"] != nt["reference"]
            ):
                raise ValueError("Wrong original threshold operand.")
            if threshold["relationship"] == "NATIVE_COMPATIBLE" and operand["body"]["currency"] != rule["body"]["measure"]["currency"]:
                raise ValueError("Claimed compatible operand has another denomination.")


def _target(target, records):
    if type(target) is not dict:
        raise ValueError("Receipt target requires object.")
    kind = target.get("kind")
    if kind in ("REGIME_SCOPE", "DECLARATION_REVISION_COVERAGE", "RULE_SOURCE_UNIVERSE"):
        _keys(target, "kind")
        return
    if kind == "SOURCE_REPORT":
        _keys(target, "kind record_id report_key")
    elif kind == "SOURCE_ENTRY_DISPOSITION":
        _keys(target, "kind record_id entry_reference")
    elif kind in RULE_TOPICS:
        _keys(target, "kind record_id rule_reference")
    else:
        raise ValueError("Unknown receipt target.")
    _text(target["record_id"])
    record = records.get(target["record_id"])
    if record is None or record["kind"] != "DECLARE":
        raise ValueError("Receipt target declaration missing.")
    body = record["body"]
    if kind == "SOURCE_REPORT":
        _report_key(target["report_key"])
        if not any(row["key"] == target["report_key"] for row in body["universe"]["reports"]):
            raise ValueError("Receipt report absent.")
    elif kind == "SOURCE_ENTRY_DISPOSITION":
        _entry_ref(target["entry_reference"], {row["entry_id"]: row for row in body["universe"]["entries"]})
    else:
        _nref_schema(target["rule_reference"], "REGIME_RULE")
        if not any(row["rule_reference"] == target["rule_reference"] for row in body["rule_bindings"]):
            raise ValueError("Receipt rule binding absent.")


def _context(context, q, catalog, fingerprints):
    if context is None:
        return None
    if q["provider_measure_projection"] is None or q["floor_evidence"] is None:
        raise ValueError("Orphaned floor admission.")
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision purpose request_content_sha256 knowledge_boundary effective_from effective_until admitted_at available_at admissions")
    for key, literal in (("contract", ADMISSION_CONTRACT), ("rule_version", ADMISSION_RULE_VERSION), ("purpose", ADMISSION_PURPOSE)):
        _enum(context[key], (literal,))
    _namespace(context["authority_namespace"])
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(context[key])
    if type(context["mandate_revision"]) is not int or context["mandate_revision"] < 1:
        raise ValueError("Mandate revision requires positive integer.")
    _hash(context["request_content_sha256"])
    request_hash = _digest(q)
    _same(context["request_content_sha256"], request_hash, "Admission request content")
    for key in ("knowledge_boundary", "effective_from", "admitted_at", "available_at"):
        context[key] = _time(context[key])
    context["effective_until"] = _optional_time(context["effective_until"])
    if context["effective_until"] is not None and context["effective_from"] >= context["effective_until"]:
        raise ValueError("Empty admission mandate interval.")
    _same(context["knowledge_boundary"], q["knowledge_boundary"], "Admission knowledge boundary")
    if not context["admitted_at"] <= context["available_at"] <= q["knowledge_boundary"] or any(
        observed > context["admitted_at"] for observed in _observations(q["floor_evidence"])
    ):
        raise ValueError("Admission chronology violates supplied evidence or K.")
    records = {row["record_id"]: row for row in q["floor_evidence"]["records"]}
    for receipt in _list(context["admissions"]):
        _keys(receipt, "target subject_content_sha256 status evidence_refs")
        _target(receipt["target"], records)
        _hash(receipt["subject_content_sha256"])
        _same(receipt["subject_content_sha256"], _digest(dict(request_content_sha256=request_hash,
              native_context_fingerprints=fingerprints, target=receipt["target"])), "Receipt subject")
        _enum(receipt["status"], ("ADMITTED", "UNRESOLVED"))
        receipt["evidence_refs"] = _refs(receipt["evidence_refs"], catalog, context["admitted_at"])
        if receipt["status"] == "ADMITTED" and not receipt["evidence_refs"]:
            raise ValueError("Admitted receipt requires nonempty original support.")
    context["admissions"] = _unique(context["admissions"], lambda row: _canonical(row["target"]))
    return context


def _e(value):
    if value is None:
        return []
    return _union([ref for key in ("evidence_refs", "authority_evidence_refs", "precedence_evidence_refs")
                   for ref in value.get(key, [])])


def _eref(entry):
    return dict(entry_id=entry["entry_id"], content_sha256=_digest(entry))


class _Support:
    """Deterministic topic-specific support plans, independent of receipt contents."""

    def __init__(self, q, owner, native, record, mappings):
        self.q, self.owner, self.native, self.record = q, owner, native, record
        self.mappings = mappings
        self.body = None if record is None or record["kind"] != "DECLARE" else record["body"]
        u = None if self.body is None else self.body["universe"]
        self.reports = {} if u is None else {_canonical(r["key"]): r for r in u["reports"]}
        self.entries = {} if u is None else {r["entry_id"]: r for r in u["entries"]}
        self.sources = {} if u is None else {r["inventory_id"]: r for r in u["sources"]}
        self.actors = {} if u is None else {r["actor_id"]: r for r in u["actors"]}
        self.bindings = {} if self.body is None else {_canonical(r["rule_reference"]): r for r in self.body["rule_bindings"]}
        self.record_pointer = _E + "/records" if record is None else _E + "/records/" + str(q["floor_evidence"]["records"].index(record))
        self.body_pointer = self.record_pointer + "/body"

    def report_pointer(self, key):
        return self.body_pointer + "/universe/reports/" + str(self.body["universe"]["reports"].index(self.reports[_canonical(key)]))

    def entry_pointer(self, identifier):
        return self.body_pointer + "/universe/entries/" + str(self.body["universe"]["entries"].index(self.entries[identifier]))

    def binding_pointer(self, ref):
        row = self.bindings.get(_canonical(ref))
        base = self.body_pointer + "/rule_bindings"
        return base if row is None else base + "/" + str(self.body["rule_bindings"].index(row))

    def target(self, kind, **fields):
        if kind not in ("REGIME_SCOPE", "DECLARATION_REVISION_COVERAGE", "RULE_SOURCE_UNIVERSE"):
            fields = dict(record_id=self.record["record_id"], **fields)
        return dict(kind=kind, **fields)

    def mapped(self, refs):
        pending, seen, originals, missing = list(refs), set(), [], False
        while pending:
            ref = pending.pop()
            if ref is None:
                missing = True
                continue
            key = _canonical(ref)
            if key in seen:
                continue
            seen.add(key)
            matches = [row["original_reference"] for row in self.mappings if row["native_reference"] == ref]
            missing |= not bool(matches)
            originals += matches
            pending += self.native.under(ref)
            if ref["kind"] == "REGIME_CLAUSE":
                clause = self.native.resolve(ref)
                pending.append(self.native.reference("REGIME_DOCUMENT", dict(evidence_id=clause["evidence_id"])))
        return _union(originals), missing

    def scope_native(self, horizon=False):
        if self.owner is None or self.native.selected is None:
            return []
        target = self.owner["measure_target"]
        if target is None:
            return []
        end = self.owner["scenario"]["settlement_before"] if horizon else None
        return [self.native.reference("ACCOUNT_BUNDLE"), *self.native.scope_references(target, self.q["knowledge_boundary"], end)]

    def report_evidence(self, key):
        report = self.reports[_canonical(key)]
        return _union(_e(report) + _e(self.sources[key["inventory_id"]]) + _e(self.actors[key["actor_id"]]) +
                      [ref for entry in self.entries.values() if entry["report_key"] == key for ref in _e(entry)])

    def entry_evidence(self, entry):
        key = entry["report_key"]
        refs, missing = self.mapped(entry["native_rule_refs"])
        return _union(_e(entry) + _e(self.reports[_canonical(key)]) + _e(self.sources[key["inventory_id"]]) +
                      _e(self.actors[key["actor_id"]]) + refs), missing

    def closure_evidence(self, closure):
        refs, missing = _e(closure), False
        for key in closure["report_keys"]:
            refs += self.report_evidence(key)
        for ref in closure["entry_refs"]:
            support, gap = self.entry_evidence(self.entries[ref["entry_id"]])
            refs += support
            missing |= gap
        return _union(refs), missing

    def required(self, target):
        kind, refs, missing = target["kind"], [], False
        evidence = self.q["floor_evidence"]
        if kind == "DECLARATION_REVISION_COVERAGE":
            return _union(_e(evidence["coverage"]) + [ref for record in evidence["records"] for ref in _e(record)]), False
        if kind == "REGIME_SCOPE":
            refs, missing = self.mapped(self.scope_native())
            return _union(refs + _e(self.record)), missing or not bool(self.scope_native())
        if kind == "RULE_SOURCE_UNIVERSE":
            u = self.body["universe"]
            refs = _e(u) + [ref for row in u["actors"] + u["sources"] for ref in _e(row)]
            package = self.native.reference("REGIME_PACKAGE", {k: self.native.selected["package"][k] for k in ("package_id", "package_revision")}) if self.native.selected else None
            clauses = [] if package is None else [r for r in self.native.under(package) if r["selector"]["field"] == "COVERAGE_EVIDENCE_REFS"]
            mapped, missing = self.mapped(clauses)
            return _union(refs + mapped), missing or package is None
        if kind == "SOURCE_REPORT":
            return self.report_evidence(target["report_key"]), False
        if kind == "SOURCE_ENTRY_DISPOSITION":
            return self.entry_evidence(self.entries[target["entry_reference"]["entry_id"]])
        binding = self.bindings[_canonical(target["rule_reference"])]
        native_refs = [binding["rule_reference"]]
        refs = _e(binding) + _e(binding["population"])
        for entry_ref in binding["source_entries"]:
            entry_refs, gap = self.entry_evidence(self.entries[entry_ref["entry_id"]])
            refs += entry_refs
            missing |= gap
        if kind == "RULE_ENDPOINT_FORCE":
            refs += _e(binding["endpoint"]) + _e(binding["force"])
        elif kind in ("RULE_EXCEPTIONS", "RULE_HORIZON"):
            node = binding["exceptions" if kind == "RULE_EXCEPTIONS" else "horizon"]
            refs += _e(node)
            if node is not None:
                closure_refs, gap = self.closure_evidence(node["closure"])
                refs += closure_refs
                missing |= gap
            if kind == "RULE_HORIZON":
                native_refs += self.scope_native(horizon=True)
        elif kind == "RULE_MEASURE":
            refs += _e(binding["measure"])
            native_refs += [self.native.reference("REGIME_MEASURE", binding["rule_reference"]["selector"]),
                            self.native.reference("ACCOUNT_BUNDLE")]
            if self.owner is not None and self.owner["measure_target"] is not None:
                native_refs.append(self.owner["measure_target"]["measure"])
            else:
                missing = True
        elif kind == "RULE_THRESHOLD":
            node = binding["threshold"]
            refs += _e(node)
            operand_ref = None if node is None else node["initial_reference_operand"]
            if operand_ref is not None:
                native_refs.append(operand_ref)
                operand = self.native.resolve(operand_ref)
                native_refs += [self.native.reference("POLICY_OPERAND_SUPPORT", dict(
                    operand_index=operand_ref["selector"]["operand_index"], evidence_index=j))
                    for j in range(len(operand["supporting_evidence"]))]
        mapped, gap = self.mapped(native_refs)
        return _union(refs + mapped), missing or gap

    def dependencies(self, target):
        kind = target["kind"]
        if kind == "SOURCE_ENTRY_DISPOSITION":
            entry = self.entries[target["entry_reference"]["entry_id"]]
            return [self.target("SOURCE_REPORT", report_key=entry["report_key"])]
        if kind not in RULE_TOPICS:
            return []
        binding = self.bindings[_canonical(target["rule_reference"])]
        targets = [self.target("SOURCE_ENTRY_DISPOSITION", entry_reference=ref) for ref in binding["source_entries"]]
        if kind in ("RULE_EXCEPTIONS", "RULE_HORIZON"):
            node = binding["exceptions" if kind == "RULE_EXCEPTIONS" else "horizon"]
            if node is not None:
                targets += [self.target("SOURCE_REPORT", report_key=key) for key in node["closure"]["report_keys"]]
                targets += [self.target("SOURCE_ENTRY_DISPOSITION", entry_reference=ref) for ref in node["closure"]["entry_refs"]]
        return sorted({_canonical(t): t for t in targets}.values(), key=_canonical)


class _Proof:
    def __init__(self, support, context, catalog):
        self.s, self.context, self.catalog = support, context, catalog
        self.findings, self.used = [], {}
        at = support.q["knowledge_boundary"]
        self.current = context is not None and context["effective_from"] <= at and (
            context["effective_until"] is None or at < context["effective_until"])
        self.receipts = {} if context is None else {_canonical(r["target"]): (i, r) for i, r in enumerate(context["admissions"])}

    def unknown(self, code, pointer, root="REQUEST"):
        if code not in FINDING_CODES:
            raise ValueError("Internal unknown finding code.")
        self.findings.append(dict(reason_code=code, subject=dict(root=root, pointer=pointer)))
        return False

    def test(self, condition, code, pointer):
        return True if condition else self.unknown(code, pointer)

    def originals(self, refs, pointer):
        good = True
        if not refs:
            good = self.unknown("NATIVE_SUPPORT_MISSING", pointer)
        for ref in refs:
            if self.catalog[ref["evidence_id"]]["source_available_at"] is None:
                good = self.unknown("SOURCE_AVAILABILITY_UNKNOWN", pointer)
        return good

    def report(self, key):
        report = self.s.reports[_canonical(key)]
        at = self.s.q["knowledge_boundary"]
        end = None if self.s.owner is None else self.s.owner["scenario"]["settlement_before"]
        good = self.test(all(report[k] == "COMPLETE" for k in ("inventory_completeness", "revision_completeness")) and
            report["state_at"] == at and report["source_information_cutoff"] == at and
            report["economic_from"] <= at and end is not None and report["economic_until"] >= end and
            report["starting_basis"] == "FROM_INCEPTION" and not report["missing_entry_ids"] and
            report["entries_omitted"] is False and report["history_truncated"] is False,
            "REPORT_COVERAGE_INCOMPLETE", self.s.report_pointer(key))
        if report["source_available_at"] is None:
            good = self.unknown("SOURCE_AVAILABILITY_UNKNOWN", self.s.report_pointer(key) + "/source_available_at")
        return good

    def require(self, target):
        key = _canonical(target)
        self.used[key] = target
        required, missing = self.s.required(target)
        good = self.originals(required, _E)
        if missing:
            good = self.unknown("NATIVE_SUPPORT_MISSING", _E + "/native_mappings")
        for dependency in self.s.dependencies(target):
            good = self.require(dependency) and good
        if target["kind"] == "SOURCE_REPORT":
            good = self.report(target["report_key"]) and good
        if target["kind"] == "SOURCE_ENTRY_DISPOSITION":
            entry = self.s.entries[target["entry_reference"]["entry_id"]]
            pointer = self.s.entry_pointer(entry["entry_id"])
            if entry["kind"] == "RULE" and not entry["native_rule_refs"] and entry["disposition"] not in (
                "HISTORICAL_NON_GOVERNING", "PROVEN_OUTSIDE_SCOPE", "OTHER_OBLIGATION"
            ):
                good = self.unknown("UNMAPPED_SOURCE_ENTRY", pointer + "/native_rule_refs")
            if entry["disposition"] == "UNRESOLVED":
                good = self.unknown("SOURCE_ENTRY_UNRESOLVED", pointer + "/disposition")
            if entry["source_available_at"] is None:
                good = self.unknown("SOURCE_AVAILABILITY_UNKNOWN", pointer + "/source_available_at")
        if not self.current:
            return False
        found = self.receipts.get(key)
        if found is None:
            return self.unknown("RECEIPT_MISSING", "/admissions", _C)
        i, receipt = found
        pointer = "/admissions/" + str(i)
        if receipt["status"] != "ADMITTED":
            good = self.unknown("RECEIPT_UNRESOLVED", pointer + "/status", _C)
        if _canonical(receipt["evidence_refs"]) != _canonical(required):
            good = self.unknown("RECEIPT_SUPPORT_MISMATCH", pointer + "/evidence_refs", _C)
        return good

    def closure(self, value, code, pointer):
        if value is None:
            return self.unknown(code, pointer)
        return self.test(all(value[k] == "COMPLETE" for k in ("source_universe_completeness", "revision_completeness")) and
                         value["source_information_cutoff"] == self.s.q["knowledge_boundary"] and bool(value["report_keys"]), code, pointer)


def _slice(support, first, last):
    grid = support["domain"]
    domain = dict(kind="EMPTY") if first > last else dict(kind="REGULAR_GRID", origin=grid["origin"],
        increment=grid["increment"], first_index=_integer_text(first), last_index=_integer_text(last))
    return dict(quantity_unit=support["quantity_unit"], domain=domain)


def _prefix(basis, floor, comparator):
    support, function = basis["support"], basis["risk_function"]
    grid = support["domain"]
    first, last = _integer(grid["first_index"]), _integer(grid["last_index"])
    origin, step = _number(grid["origin"]), _number(grid["increment"])
    a, balance = _number(function["price_loss_per_quantity_unit"]), _number(basis["baseline_amount"])
    charges = [tuple(_number(c[k]) for k in ("minimum", "fixed", "per_unit")) for c in function["charges"]]
    if first < 0 or last < first or step <= 0 or origin + first * step <= 0 or a <= 0 or any(
        v < 0 for charge in charges for v in charge
    ):
        raise ValueError("Established native projection violated its sign/grid contract.")

    def passes(n):
        q = origin + n * step
        h = balance - a * q - sum((max(m, f + p * q) for m, f, p in charges), Fraction(0)) - floor
        return h > 0 if comparator == "GREATER_THAN" else h >= 0

    if not passes(first):
        upper = first - 1
    elif passes(last):
        upper = last
    else:
        lo, hi = first, last
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if passes(mid):
                lo = mid
            else:
                hi = mid - 1
        upper = lo
    return _slice(support, first, upper), _slice(support, upper + 1, last)


def _known_changes(proof, ref):
    at, end = proof.s.q["knowledge_boundary"], proof.s.owner["scenario"]["settlement_before"]
    good = True
    # Related source records establish possible relevance, never provider
    # precedence. Resolve the entire bounded component before claiming closure.
    neighbors = {identifier: set() for identifier in proof.s.entries}
    relevant = set()
    for entry in proof.s.entries.values():
        identifier = entry["entry_id"]
        if ref in entry["native_rule_refs"] or entry["kind"] in ("PACKAGE_CHANGE", "PHASE_CHANGE"):
            relevant.add(identifier)
        for related in entry["related_entry_ids"]:
            if related in neighbors:
                neighbors[identifier].add(related)
                neighbors[related].add(identifier)
    pending = list(relevant)
    while pending:
        for identifier in neighbors[pending.pop()]:
            if identifier not in relevant:
                relevant.add(identifier)
                pending.append(identifier)
    for entry in proof.s.entries.values():
        if entry["entry_id"] not in relevant:
            continue
        admitted = proof.require(proof.s.target("SOURCE_ENTRY_DISPOSITION", entry_reference=_eref(entry)))
        good = admitted and good
        if entry["disposition"] in ("HISTORICAL_NON_GOVERNING", "PROVEN_OUTSIDE_SCOPE", "OTHER_OBLIGATION"):
            # An unsupported declaration of irrelevance cannot defeat known changes.
            if admitted:
                continue
        period = entry["effective_period"]
        transitions = (period["effective_from"], period["effective_until"])
        if any(x is not None and at < x < end for x in transitions):
            good = proof.unknown("HORIZON_CHANGE", proof.s.entry_pointer(entry["entry_id"]))
        if period["effective_from"] is None or period["end_status"] == "UNKNOWN":
            good = proof.unknown("HORIZON_UNRESOLVED", proof.s.entry_pointer(entry["entry_id"]))
    return good


def _source_horizon(support, entries):
    """Required source predicates must cover the entire half-open horizon."""
    if support.owner is None:
        return False
    cursor, end = support.q["knowledge_boundary"], support.owner["scenario"]["settlement_before"]
    intervals = []
    for entry in entries:
        p = entry["effective_period"]
        if p["effective_from"] is not None and p["end_status"] != "UNKNOWN":
            intervals.append((p["effective_from"], p["effective_until"]))
    for lo, hi in sorted(intervals, key=lambda pair: pair[0]):
        if lo > cursor:
            break
        if hi is None:
            return True
        cursor = max(cursor, hi)
        if cursor >= end:
            return True
    return False


def _source_rule_horizon(support, ref):
    """A future or expired source RULE cannot establish present mandatory force."""
    return _source_horizon(support, [entry for entry in support.entries.values()
        if entry["kind"] == "RULE" and entry["disposition"] == "MAPPED_NATIVE_RULE" and ref in entry["native_rule_refs"]])


def _rule_result(ref, rule, support, context, catalog, shared_good, shared_findings, shared_targets):
    proof = _Proof(support, context, catalog)
    proof.findings = list(shared_findings)
    proof.used = dict(shared_targets)
    row = dict(rule_reference=ref, disposition="UNRESOLVED", reason_codes=[], headroom=None,
               rule_passing_domain=None, rule_excluded_domain=None)
    pointer = support.binding_pointer(ref)
    binding = support.bindings.get(_canonical(ref))
    if binding is None:
        proof.unknown("RULE_BINDING_MISSING", pointer)
    else:
        source_entries = [support.entries[r["entry_id"]] for r in binding["source_entries"]]
        proof.test(any(e["kind"] == "RULE" and e["disposition"] == "MAPPED_NATIVE_RULE" and
                       ref in e["native_rule_refs"] for e in source_entries), "RULE_SOURCE_BINDING_MISSING", pointer)
        proof.require(support.target("RULE_DISPOSITION", rule_reference=ref))
        horizon = binding["horizon"]
        proof.test(_get(horizon, "status") == "INVARIANT_AS_KNOWN_ON_T_H",
                   "HORIZON_CHANGE" if _get(horizon, "status") == "KNOWN_RELEVANT_CHANGE_BEFORE_H" else "HORIZON_UNRESOLVED", pointer)
        proof.closure(None if horizon is None else horizon["closure"], "HORIZON_UNRESOLVED", pointer)
        proof.require(support.target("RULE_HORIZON", rule_reference=ref))
        if support.owner is not None:
            _known_changes(proof, ref)
        population = binding["population"]["status"]
        proof.test(population in ("CONTAINS_SCENARIO", "DISJOINT"), "POPULATION_UNRESOLVED", pointer)
        endpoint = _get(binding["endpoint"], "status")
        if population == "DISJOINT":
            desired = "DISJOINT_POPULATION"
        else:
            proof.require(support.target("RULE_ENDPOINT_FORCE", rule_reference=ref))
            proof.test(endpoint in ("EXPLICIT_SETTLED_ENDPOINT", "CONTINUOUS_INCLUDES_SETTLED_ENDPOINT", "OUTSIDE_SETTLED_ENDPOINT"),
                       "ENDPOINT_UNRESOLVED", pointer)
            if endpoint == "OUTSIDE_SETTLED_ENDPOINT":
                desired = "OTHER_OBLIGATION" if rule["representation"] == "SUPPORTED" and rule["body"]["type"] in (
                    "ACCOUNT_STATE_REQUIREMENT", "INSTRUMENT_ACTION_PERMISSION", "AUTOMATION_PERMISSION", "POSITION_LIMIT", "ACTION_WINDOW"
                ) else "OUTSIDE_SETTLED_ENDPOINT"
            else:
                exception = binding["exceptions"]
                resolution = _get(exception, "resolution")
                proof.closure(None if exception is None else exception["closure"], "EXCEPTIONS_UNRESOLVED", pointer)
                proof.require(support.target("RULE_EXCEPTIONS", rule_reference=ref))
                if resolution == "WAIVED_THROUGHOUT":
                    proof.test(_get(binding["force"], "status") == "NOT_MANDATORY", "FORCE_UNRESOLVED", pointer)
                    closure_entries = [] if exception is None else [support.entries[r["entry_id"]] for r in exception["closure"]["entry_refs"]]
                    waivers = [entry for entry in closure_entries if entry["kind"] == "WAIVER" and
                               entry["disposition"] == "SUPPORTING_RULE_EVIDENCE"]
                    proof.test(bool(exception["authority_actor_ids"]) and bool(exception["authority_evidence_refs"]) and
                               bool(exception["precedence_evidence_refs"]) and bool(waivers),
                               "EXCEPTIONS_UNRESOLVED", pointer)
                    proof.test(_source_horizon(support, waivers), "HORIZON_UNRESOLVED", pointer)
                    desired = "WAIVED_THROUGHOUT"
                else:
                    desired = "SUPPORTED_STATIC_FLOOR"
                    proof.test(_get(binding["force"], "status") == "MANDATORY_UNCHANGED", "FORCE_UNRESOLVED", pointer)
                    proof.test(_source_rule_horizon(support, ref), "HORIZON_UNRESOLVED", pointer)
                    proof.test(resolution in ("NONE_APPLICABLE", "RESOLVED_WITH_PREDICATE_UNCHANGED"), "EXCEPTIONS_UNRESOLVED", pointer)
                    body = rule["body"]
                    model_good = rule["representation"] == "SUPPORTED" and body["type"] == "STATIC_FLOOR"
                    proof.test(model_good, "RULE_MODEL_UNSUPPORTED", pointer)
                    if model_good:
                        measure = body["measure"]
                        proof.test(measure["kind"] == "BALANCE" and all(v != "SUBTRACT_SEPARATELY" for v in measure["cost_treatment"].values()),
                                   "MEASURE_UNSUPPORTED", pointer)
                        proof.test(_get(binding["measure"], "status") == "IDENTICAL", "MEASURE_IDENTITY_UNRESOLVED", pointer)
                        proof.require(support.target("RULE_MEASURE", rule_reference=ref))
                        threshold = binding["threshold"]
                        proof.test(_get(threshold, "relationship") == "NATIVE_COMPATIBLE", "THRESHOLD_OPERAND_UNRESOLVED", pointer)
                        proof.require(support.target("RULE_THRESHOLD", rule_reference=ref))
                        nt = body["threshold"]
                        operand_ref = None if threshold is None else threshold["initial_reference_operand"]
                        floor = None
                        if nt["kind"] == "ABSOLUTE":
                            floor = _number(nt["amount"])
                        elif operand_ref is None:
                            proof.unknown("THRESHOLD_OPERAND_UNRESOLVED", pointer)
                        else:
                            operand = support.native.resolve(operand_ref)
                            end = None if support.owner is None else support.owner["scenario"]["settlement_before"]
                            proof.test(_time(operand["effective_from"]) <= support.q["knowledge_boundary"] and
                                       end is not None and _time(operand["effective_until"]) >= end,
                                       "THRESHOLD_OPERAND_UNRESOLVED", pointer)
                            floor = _number(operand["body"]["amount"]) * _number(nt["fraction"])
                        if shared_good and not proof.findings and floor is not None:
                            basis = support.owner["projection_basis"]
                            row["headroom"] = dict(kind="C6_BALANCE_MINUS_NATIVE_STATIC_FLOOR", projection_basis_sha256=_digest(basis),
                                rule_reference=ref, threshold_amount=_plain(floor), currency=measure["currency"],
                                compliant_when=body["compliant_when"], initial_reference_operand=operand_ref)
                            row["rule_passing_domain"], row["rule_excluded_domain"] = _prefix(basis, floor, body["compliant_when"])
        if shared_good and not proof.findings:
            row["disposition"] = desired
    if row["disposition"] == "UNRESOLVED":
        proof.unknown("RULE_DISPOSITION_UNRESOLVED", pointer)
    row["reason_codes"] = sorted({f["reason_code"] for f in proof.findings})
    if row["rule_excluded_domain"] is not None and row["rule_excluded_domain"]["domain"]["kind"] != "EMPTY":
        row["reason_codes"] = sorted(set(row["reason_codes"]) | {
            "ALL_C_EXCLUDED" if row["rule_passing_domain"]["domain"]["kind"] == "EMPTY" else "SUFFIX_EXCLUDED"})
    return row, proof


def _economic_horizon(native, at, end):
    if native.selected is None or end is None:
        return "HORIZON_UNRESOLVED"
    assignment, package = native.selected["assignment"], native.selected["package"]

    def overlaps(periods):
        # Distinguish provable disjointness from unknown applicability. Known
        # future native assertions remain relevant even when today's selected
        # assignment/package has an open end.
        starts = [at] + [_time(p["effective_from"]) for p in periods if p["effective_from"] is not None]
        stops = [end] + [_time(p["effective_until"]) for p in periods if p["effective_until"] is not None]
        if max(starts) >= min(stops):
            return False
        if any(p["effective_from"] is None or p["end_status"] == "UNKNOWN" for p in periods):
            return None
        return True

    manifest = native.bundles["REGIME_BUNDLE"]["assessment_input"]["manifest"]
    competitors = [overlaps([a["enrollment_period"], a["phase_period"]])
                   for a in manifest["assignments"] if a["assignment_id"] != assignment["assignment_id"]]
    packages = {(p["package_id"], p["package_revision"]): p for p in manifest["packages"]}
    selected = package["package_id"], package["package_revision"]
    for binding in assignment["package_bindings"]:
        key = binding["package"]["package_id"], binding["package"]["package_revision"]
        if key != selected:
            competitors.append(overlaps([binding["effective_period"], packages[key]["effective_period"]]))
    if any(state is True for state in competitors):
        return "HORIZON_CHANGE"
    if any(state is None for state in competitors):
        return "HORIZON_UNRESOLVED"
    periods = [assignment["enrollment_period"], assignment["phase_period"], package["effective_period"]]
    for p in periods:
        if p["effective_from"] is None or _time(p["effective_from"]) > at or p["end_status"] == "UNKNOWN":
            return "HORIZON_UNRESOLVED"
        if p["effective_until"] is not None and _time(p["effective_until"]) < end:
            return "HORIZON_CHANGE"
    intervals = []
    for binding in assignment["package_bindings"]:
        p = binding["effective_period"]
        if binding["package"] == {k: package[k] for k in ("package_id", "package_revision")} and p["effective_from"] is not None and p["end_status"] != "UNKNOWN":
            intervals.append((_time(p["effective_from"]), None if p["effective_until"] is None else _time(p["effective_until"])))
    cursor = at
    for lo, hi in sorted(intervals, key=lambda pair: pair[0]):
        if lo > cursor:
            break
        if hi is None:
            return None
        cursor = max(cursor, hi)
        if cursor >= end:
            return None
    return "HORIZON_CHANGE" if cursor > at else "HORIZON_UNRESOLVED"


def _evaluate(request, contexts):
    _canonical(request)
    for context in contexts:
        _canonical(context)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope provider_measure_projection floor_evidence")
    # Normalize owned assertions without changing a preserved native original
    # through a caller-created alias to an owned object.
    q = _detached(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    _same(q["assessment_economic_time"], at, "Current T=K")
    _scope(q["scope"])
    pair, owner = q["provider_measure_projection"], None
    if pair is None:
        if any(context is not None for context in contexts):
            raise ValueError("Orphaned context for absent owner.")
    else:
        _keys(pair, "assessment request")
        owner = validate_current_entry_provider_measure_projection_basis(pair["assessment"], pair["request"],
            trusted_planning_context=contexts[0], trusted_quantity_context=contexts[1], trusted_feasibility_context=contexts[2],
            trusted_position_effect_context=contexts[3], trusted_position_limit_context=contexts[4], trusted_financial_projection_context=contexts[5])
        _same(q["scope"], owner["scope"], "Native scope")
        for key in ("assessment_economic_time", "knowledge_boundary"):
            _same(at, _time(owner[key]), "Native current boundary")
    fingerprints = {key: None for key in _CONTEXT_KEYS}
    if owner is not None:
        fingerprints.update(owner["reconstruction_evidence"]["native_context_fingerprints"])
        fingerprints[_CONTEXT_KEYS[-1]] = owner["reconstruction_evidence"][_CONTEXT_KEYS[-1]]
    native = _Native(None if pair is None else pair["request"]["quantity_composition"])
    catalog, mappings = _evidence(q["floor_evidence"], native, q["scope"], at)
    evidence = q["floor_evidence"]
    chain, incomplete, competing, backwards = ([], False, False, False) if evidence is None else _history(evidence)
    candidates = [r for r in chain if r["effective_from"] <= at]
    record = candidates[-1] if candidates and not competing and not backwards else None
    _current_pins(record, q, owner, native)
    context = _context(deepcopy(contexts[6]), q, catalog, fingerprints)
    support = _Support(q, owner, native, record, mappings)
    shared = _Proof(support, context, catalog)
    if owner is None:
        shared.unknown("OWNER_MISSING", "/provider_measure_projection")
    elif owner["outcome"] != "ESTABLISHED":
        shared.unknown("OWNER_UNKNOWN", "", "UPSTREAM_ASSESSMENT")
    if evidence is None:
        shared.unknown("EVIDENCE_MISSING", _E)
    else:
        if evidence["source_available_at"] is None or evidence["coverage"]["source_available_at"] is None:
            shared.unknown("SOURCE_AVAILABILITY_UNKNOWN", _E)
        coverage = evidence["coverage"]
        end = None if owner is None else owner["scenario"]["settlement_before"]
        shared.test(coverage["declaration_completeness"] == "COMPLETE" and coverage["source_information_cutoff"] == at and
                    coverage["economic_from"] <= at and end is not None and coverage["economic_until"] >= end,
                    "DECLARATION_COVERAGE_INCOMPLETE", _E + "/coverage")
        if incomplete:
            shared.unknown("REVISION_HISTORY_INCOMPLETE", _E + "/coverage")
        if competing:
            shared.unknown("COMPETING_DECLARATIONS", _E + "/records")
        if backwards:
            shared.unknown("REVISION_ORDER_UNSUPPORTED", _E + "/records")
        if any(r["source_available_at"] is None for r in chain):
            shared.unknown("SOURCE_AVAILABILITY_UNKNOWN", _E + "/records")
        if record is None:
            shared.unknown("NO_CURRENT_DECLARATION", _E + "/records")
        elif record["kind"] == "WITHDRAW":
            shared.unknown("DECLARATION_WITHDRAWN", _E + "/records")
        elif record["effective_until"] is not None and record["effective_until"] <= at:
            shared.unknown("DECLARATION_EXPIRED", _E + "/records")
        else:
            if record["source_available_at"] is None:
                shared.unknown("SOURCE_AVAILABILITY_UNKNOWN", _E + "/records")
            b = record["body"]
            shared.test(b["source_information_cutoff"] == at and b["economic_from"] <= at and end is not None and b["economic_until"] >= end,
                        "DECLARATION_COVERAGE_INCOMPLETE", _E + "/records")
            if any(value is None for value in b["subjects"].values()):
                shared.unknown("NATIVE_SUPPORT_MISSING", _E + "/records")
            if end is not None and ((record["effective_until"] is not None and record["effective_until"] < end) or
                                   any(at < r["effective_from"] < end for r in chain)):
                shared.unknown("HORIZON_CHANGE", _E + "/records")
            economic_finding = _economic_horizon(native, at, end)
            if economic_finding is not None:
                shared.unknown(economic_finding, support.record_pointer)
    if context is None:
        shared.unknown("ADMISSION_MISSING", "", _C)
    elif not shared.current:
        shared.unknown("ADMISSION_NOT_CURRENT", "/effective_from", _C)
    usable_record = record is not None and record["kind"] == "DECLARE" and (
        record["effective_until"] is None or at < record["effective_until"])
    if evidence is not None:
        shared.require(support.target("DECLARATION_REVISION_COVERAGE"))
    if usable_record:
        shared.require(support.target("REGIME_SCOPE"))
    shared_good = not shared.findings
    rules, proofs, findings = [], [], list(shared.findings)
    for ref, rule in _selected_rules(native):
        if usable_record:
            row, p = _rule_result(ref, rule, support, context, catalog, shared_good, shared.findings, shared.used)
        else:
            p = _Proof(support, context, catalog)
            p.findings = list(shared.findings)
            p.unknown("RULE_BINDING_MISSING", _E if evidence is None else _E + "/records")
            row = dict(rule_reference=ref, disposition="UNRESOLVED", reason_codes=sorted({f["reason_code"] for f in p.findings}),
                       headroom=None, rule_passing_domain=None, rule_excluded_domain=None)
        rules.append(row)
        findings += p.findings
        excluded = row["rule_excluded_domain"]
        if excluded is not None and excluded["domain"]["kind"] != "EMPTY":
            targets = sorted(p.used.values(), key=_canonical)
            proof_refs = _union([r for t in targets for r in support.required(t)[0]])
            proofs.append(dict(kind="ALL_C_EXCLUDED" if row["rule_passing_domain"]["domain"]["kind"] == "EMPTY" else "SUFFIX_EXCLUDED",
                scope="CONDITIONAL_SETTLED_ENDPOINT_ON_C", rule_reference=ref,
                declaration=dict(record_id=record["record_id"], content_sha256=_digest(record)),
                headroom_sha256=_digest(row["headroom"]), excluded_domain=excluded,
                admission_targets=targets, evidence_refs=proof_refs))
    global_proof = _Proof(support, context, catalog)
    sources = []
    if usable_record:
        u = record["body"]["universe"]
        end = None if owner is None else owner["scenario"]["settlement_before"]
        expected_reports = {_canonical(dict(inventory_id=s["inventory_id"], actor_id=r["actor_id"], topic=t))
                            for s in u["sources"] for r in s["responsibilities"] for t in r["topics"]}
        covered = {(r["actor_id"], t) for s in u["sources"] for r in s["responsibilities"] for t in r["topics"]}
        actor_topics = {(a["actor_id"], t) for a in u["actors"] for t in a["topics"]}
        global_proof.test(u["source_universe_completeness"] == u["actor_universe_completeness"] == "COMPLETE" and
            u["state_at"] == u["source_information_cutoff"] == at and u["economic_from"] <= at and
            end is not None and u["economic_until"] >= end and any(a["role"] == "PROVIDER" for a in u["actors"]) and
            {t for _, t in covered} == set(TOPIC_KINDS) and covered == actor_topics,
            "SOURCE_UNIVERSE_INCOMPLETE", support.body_pointer + "/universe")
        for key in sorted(expected_reports - support.reports.keys()):
            global_proof.unknown("REPORT_MISSING", support.body_pointer + "/universe/reports")
        for report in u["reports"]:
            global_proof.require(support.target("SOURCE_REPORT", report_key=report["key"]))
        for entry in u["entries"]:
            start = len(global_proof.findings)
            ok = global_proof.require(support.target("SOURCE_ENTRY_DISPOSITION", entry_reference=_eref(entry)))
            if not shared_good:
                ok = False
            if not ok:
                global_proof.unknown("SOURCE_ENTRY_UNRESOLVED", support.entry_pointer(entry["entry_id"]))
            sources.append(dict(entry_reference=_eref(entry), disposition=entry["disposition"] if ok else "UNRESOLVED",
                reason_codes=sorted({f["reason_code"] for f in global_proof.findings[start:]} |
                                    (set() if shared_good else {f["reason_code"] for f in shared.findings}))))
        global_proof.require(support.target("RULE_SOURCE_UNIVERSE"))
        if native.selected is None or native.selected["package"]["coverage"]["completeness"] != "COMPLETE":
            global_proof.unknown("NATIVE_COVERAGE_INCOMPLETE", _E + "/records")
    findings += global_proof.findings
    floors = [row for row in rules if row["disposition"] == "SUPPORTED_STATIC_FLOOR"]
    if not floors:
        findings.append(dict(reason_code="NO_SUPPORTED_APPLICABLE_FLOOR", subject=dict(
            root="REQUEST", pointer=_E if evidence is None else _E + "/records")))
    findings = sorted({_canonical(f): f for f in findings}.values(), key=lambda f: (
        f["subject"]["root"], f["subject"]["pointer"], f["reason_code"]))
    complete = bool(floors) and not findings
    conjunction, passing = None, None
    native_grid = owner["projection_basis"]["support"] if owner is not None and owner["outcome"] == "ESTABLISHED" else None
    all_excluded = any(p["kind"] == "ALL_C_EXCLUDED" for p in proofs)
    if complete:
        conjunction = dict(kind="STATIC_SETTLED_ENDPOINT_FLOOR_CONJUNCTION", support=native_grid,
                           rule_references=sorted([row["rule_reference"] for row in floors], key=_canonical))
        first = _integer(native_grid["domain"]["first_index"])
        upper = min(first - 1 if row["rule_passing_domain"]["domain"]["kind"] == "EMPTY" else
                    _integer(row["rule_passing_domain"]["domain"]["last_index"]) for row in floors)
        passing = _slice(native_grid, first, upper)
    elif all_excluded:
        passing = dict(quantity_unit=native_grid["quantity_unit"], domain=dict(kind="EMPTY"))
    outcome = "NOT_SUITABLE" if all_excluded else "UNKNOWN" if not complete else "ESTABLISHED"
    reasons = {f["reason_code"] for f in findings} | {p["kind"] for p in proofs}
    if outcome == "ESTABLISHED":
        reasons.add("STATIC_ENDPOINT_DOMAIN_ESTABLISHED")
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
        scope=q["scope"], scenario=None if owner is None else owner["scenario"], outcome=outcome,
        reason_codes=sorted(reasons), owner_reference=None if owner is None else dict(
            assessment_identity=owner["assessment_identity"], owner_bundle_sha256=_digest(pair), outcome=owner["outcome"]),
        resolved_record=None if record is None else dict(record_id=record["record_id"], kind=record["kind"], content_sha256=_digest(record)),
        supported_domain=native_grid, rule_results=sorted(rules, key=lambda row: _canonical(row["rule_reference"])),
        source_dispositions=sorted(sources, key=lambda row: _canonical(row["entry_reference"])), complete_predicate=conjunction,
        passing_domain=passing, negative_proofs=sorted(proofs, key=lambda row: (_canonical(row["rule_reference"]), row["kind"])),
        unresolved_findings=findings, native_diagnostics=None if owner is None else owner["native_diagnostics"],
        native_unresolved_findings=None if owner is None else owner["unresolved_findings"],
        native_conditions=None if owner is None else owner["conditions"], native_limitations=None if owner is None else owner["limitations"],
        conditions=list(CONDITIONS), limitations=list(LIMITATIONS), reconstruction_evidence=dict(request=q,
            native_context_fingerprints=fingerprints, floor_evidence_sha256=None if evidence is None else _digest(evidence),
            trusted_provider_floor_context_sha256=None if context is None else _digest(context)),
        downstream_obligations=list(DOWNSTREAM_OBLIGATIONS), source_authentication=SOURCE_AUTHENTICATION,
        authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_current_post_entry_provider_floor_headroom(
    request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None, trusted_provider_floor_context=None,
) -> dict:
    """Replay native owners and assess conditional static floors under host admission."""
    try:
        return _detached(_evaluate(request, (trusted_planning_context, trusted_quantity_context,
            trusted_feasibility_context, trusted_position_effect_context, trusted_position_limit_context,
            trusted_financial_projection_context, trusted_provider_floor_context)))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed current post-entry provider floor/headroom request.") from exc


def validate_current_post_entry_provider_floor_headroom(
    assessment: dict, request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None, trusted_provider_floor_context=None,
) -> dict:
    """Recompute every detached result field; a rehashed output grants no authority."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be JSON object.")
        _canonical(assessment)
        expected = evaluate_current_post_entry_provider_floor_headroom(request,
            trusted_planning_context=trusted_planning_context, trusted_quantity_context=trusted_quantity_context,
            trusted_feasibility_context=trusted_feasibility_context, trusted_position_effect_context=trusted_position_effect_context,
            trusted_position_limit_context=trusted_position_limit_context, trusted_financial_projection_context=trusted_financial_projection_context,
            trusted_provider_floor_context=trusted_provider_floor_context)
        _same(assessment, expected, "Complete post-entry provider floor/headroom assessment")
        return _detached(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized post-entry provider floor/headroom assessment.") from exc
