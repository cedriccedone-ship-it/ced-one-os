"""Conditional terminal quantity/count proof; host admission is an external boundary."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re

from .causal_account_rule_regime_assessment import validate_causal_account_rule_regime_assessment
from .xauusd_current_entry_position_effect_basis import validate_current_entry_position_effect_basis


CONTRACT = "trading.xauusd_current_terminal_position_limits.v1"
RULE_VERSION = "xauusd_current_terminal_position_limits_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_terminal_position_limits.admission.v1"
ADMISSION_RULE = "xauusd_current_terminal_position_limits_admission_v1"
PURPOSE = "TERMINAL_POSITION_LIMIT_FACT_ADMISSION_ONLY"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
IDENTITY_PREFIX = "current_terminal_position_limits_"
PREDICATE_KIND = "TERMINAL_UPPER_BOUND_CONJUNCTION"
CONDITIONS = (
    "ACCEPTED_ENTRY_FULLY_FILLED", "ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS",
    "NO_UNRELATED_INTERVENING_STATE_CHANGE", "ADMITTED_MECHANICS_REMAIN_APPLICABLE",
    "ADMITTED_RULES_REMAIN_APPLICABLE_AT_TERMINAL_STATE",
)
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                           "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
DOWNSTREAM_OBLIGATIONS = sorted((
    "ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL", "CANDIDATE_VALIDITY",
    "CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION", "ENTRY_QUANTITY_DOMAIN_MEMBERSHIP",
    "EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE", "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY",
    "MARKET_ORDER_AND_FILL_FEASIBILITY", "MISSION_CONTROL_CURRENT_AUTHORIZATION",
    "ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES", "OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE",
    "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM", "QUANTITY_SELECTION_POLICY_AND_SELECTION",
    "RISK_BUDGET_QUANTITY_FEASIBILITY",
))
UNRESOLVED_REASONS = frozenset((
    "OWNER_MISSING", "OWNER_NOT_ESTABLISHED", "REGIME_NOT_UNIQUE", "RULE_SUPPORT_MISSING",
    "ADMISSION_MISSING", "ADMISSION_NOT_CURRENT", "RECEIPT_MISSING", "RECEIPT_UNRESOLVED",
    "ORIGINAL_SUPPORT_MISSING", "SOURCE_AVAILABILITY_UNKNOWN", "SCOPE_UNRESOLVED", "SCOPE_INCOMPATIBLE",
    "COVERAGE_INCOMPLETE", "COVERAGE_NOT_CURRENT", "RULE_BINDING_MISSING", "POPULATION_UNRESOLVED",
    "QUANTITY_SEMANTICS_UNRESOLVED", "QUANTITY_SEMANTICS_INCOMPATIBLE", "RULE_EFFECT_UNKNOWN",
    "RULE_UNSUPPORTED", "TERMINAL_PROJECTION_UNRESOLVED", "RULE_FORCE_UNRESOLVED", "EXCEPTIONS_UNRESOLVED",
))
NEGATIVE_REASONS = frozenset(("QUANTITY_LIMIT_EXCLUDES_ALL_P", "COUNT_LIMIT_EXCLUDES_ALL_P",
                              "QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL"))
REASON_CODES = UNRESOLVED_REASONS | NEGATIVE_REASONS | frozenset((
    "TERMINAL_RULE_ESTABLISHED", "DISJOINT_POPULATION_ESTABLISHED", "OTHER_OBLIGATION_RETAINED",
    "TERMINAL_DOMAIN_ESTABLISHED",
))
_COMPLETENESS = ("COMPLETE", "LIMITED", "UNKNOWN")
_PROJECTIONS = ("EXPLICIT_TERMINAL_STATE", "CONTINUOUS_NECESSARY_TERMINAL", "UNKNOWN")
_NAMESPACE = "source_id source_contract source_contract_version"
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
_SUPPORT_PATH = "/request/rule_support"
_CONTEXT_PATH = "/trusted_position_limit_context"


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
    return value


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected a JSON array.")
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


def _canonical(value):
    """Canonical JSON without changing process-wide integer conversion limits."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings.")
        return "{" + ",".join(_canonical(key) + ":" + _canonical(value[key]) for key in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if type(value) is str:
        value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return _integer_text(value)
    raise ValueError("Expected serialized JSON with exact declared numerical types.")


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " mismatch.")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA-256.")


def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Expected timezone-qualified timestamp with seconds and at most microseconds.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _optional_time(value):
    return None if value is None else _time(value)


def _decimal(value):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Expected plain decimal string.")
    result = value.rstrip("0").rstrip(".") if "." in value else value
    return "0" if result in ("0", "-0") else result


def _number(value):
    whole, _, part = value.lstrip("-").partition(".")
    coefficient = 0
    digits = whole + part
    for offset in range(0, len(digits), 9):
        chunk = digits[offset:offset + 9]
        coefficient = coefficient * 10 ** len(chunk) + int(chunk)
    return Fraction((-1 if value.startswith("-") else 1) * coefficient, 10 ** len(part))


def _unique(rows, key):
    rows = _list(rows)
    identities = [key(row) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate identity/reference.")
    return sorted(rows, key=key)


def _namespace(value, snapshot=False):
    _keys(value, _NAMESPACE + (" source_snapshot_id" if snapshot else ""))
    for item in value.values():
        _text(item)


def _scope(scope):
    _keys(scope, "account provider_namespace provider_id venue_id instrument entry_direction entry_mechanism quantity_unit")
    _keys(scope["account"], _NAMESPACE + " account_id environment currency")
    _keys(scope["instrument"], _NAMESPACE + " environment instrument_id")
    for node in (scope["account"], scope["instrument"]):
        for item in node.values():
            _text(item)
        _enum(node["environment"], ("DEMO", "LIVE"))
    if re.fullmatch(r"[A-Z]{3}", scope["account"]["currency"]) is None:
        raise ValueError("Currency requires three uppercase ASCII letters.")
    _same(scope["account"]["environment"], scope["instrument"]["environment"], "Environment")
    _namespace(scope["provider_namespace"])
    for key in ("provider_id", "venue_id", "quantity_unit"):
        _text(scope[key])
    _enum(scope["entry_direction"], ("LONG", "SHORT"))
    _enum(scope["entry_mechanism"], (MECHANISM,))


def _refs(value, catalog, deadline):
    for ref in _list(value):
        _keys(ref, "evidence_id envelope_sha256")
        _text(ref["evidence_id"])
        _hash(ref["envelope_sha256"])
        original = catalog.get(ref["evidence_id"])
        if original is None or _digest(original) != ref["envelope_sha256"]:
            raise ValueError("Missing or mismatched evidence envelope.")
        if original["observed_at"] > deadline:
            raise ValueError("Original observation postdates its containing assertion.")
    return _unique(value, lambda row: (row["evidence_id"]))


def _target_key(target):
    return (target["kind"], target.get("rule_reference", {}).get("pointer", ""))


def _native_key(ref):
    return ref["kind"], ref["pointer"]


class _Native:
    """A bounded index of owner-valid original nodes; never a generic pointer resolver."""

    def __init__(self, original, regime):
        self.original, self.regime = original, regime
        self.nodes, self.deadlines = {}, {}
        self.assignment = self.package = None
        self.approvals = []
        self.rules = []
        if original is None:
            return
        manifest = original["manifest"]
        observed = _time(manifest["timing"]["observed_at"])
        self._add("MANIFEST", "/manifest", manifest, observed)
        for i, evidence in enumerate(manifest["evidence"]):
            self._add("EVIDENCE", f"/manifest/evidence/{i}", evidence, _time(evidence["timing"]["observed_at"]))
        for i, assignment in enumerate(manifest["assignments"]):
            path = f"/manifest/assignments/{i}"
            self._add("ASSIGNMENT", path, assignment, observed)
            self._clauses(path + "/evidence_refs", assignment["evidence_refs"], observed)
            for j, binding in enumerate(assignment["package_bindings"]):
                self._clauses(path + f"/package_bindings/{j}/evidence_refs", binding["evidence_refs"], observed)
        for i, package in enumerate(manifest["packages"]):
            path = f"/manifest/packages/{i}"
            interpreted = _time(package["interpretation"]["interpreted_at"])
            self._add("PACKAGE", path, package, interpreted)
            self._clauses(path + "/evidence_refs", package["evidence_refs"], interpreted)
            self._clauses(path + "/coverage/evidence_refs", package["coverage"]["evidence_refs"], interpreted)
            for j, rule in enumerate(package["rules"]):
                rp = path + f"/rules/{j}"
                self._add("RULE", rp, rule, interpreted)
                self._clauses(rp + "/evidence_refs", rule["evidence_refs"], interpreted)
                body = rule["body"]
                if body["type"] in ("STATIC_FLOOR", "DAILY_RESET_FLOOR"):
                    self._clauses(rp + "/body/measure/definition_refs", body["measure"]["definition_refs"], interpreted)
                if body["type"] == "DAILY_RESET_FLOOR":
                    self._clauses(rp + "/body/reset_schedule/evidence_refs", body["reset_schedule"]["evidence_refs"], interpreted)
                if body["type"] == "ACTION_WINDOW":
                    self._clauses(rp + "/body/evidence_refs", body["evidence_refs"], interpreted)
        for i, approval in enumerate(original["approvals"]):
            self._add("APPROVAL", f"/approvals/{i}", approval, _time(approval["observed_at"]))
        selected = regime["selected_regime"]
        if selected is not None:
            for (kind, pointer), node in self.nodes.items():
                if kind == "ASSIGNMENT" and node["assignment_id"] == selected["assignment"]["assignment_id"]:
                    self.assignment = self.reference(kind, pointer)
                if kind == "PACKAGE" and all(node[key] == selected["package"][key] for key in ("package_id", "package_revision")):
                    self.package = self.reference(kind, pointer)
                if kind == "APPROVAL" and any(node["approval_reference"] == a["approval_reference"] for a in selected["approval_references"]):
                    self.approvals.append(self.reference(kind, pointer))
            normalized_rules = {row["rule_id"]: row for row in selected["package"]["rules"]}
            for (kind, pointer), node in self.nodes.items():
                if kind == "RULE" and pointer.startswith(self.package["pointer"] + "/rules/"):
                    self.rules.append((self.reference(kind, pointer), normalized_rules[node["rule_id"]]))

    def _add(self, kind, pointer, node, deadline):
        self.nodes[kind, pointer] = node
        self.deadlines[kind, pointer] = deadline

    def _clauses(self, pointer, clauses, deadline):
        for i, clause in enumerate(clauses):
            self._add("CLAUSE", pointer + f"/{i}", clause, deadline)

    def reference(self, kind, pointer):
        return dict(kind=kind, pointer=pointer, content_sha256=_digest(self.nodes[kind, pointer]))

    def resolve(self, ref, kind=None):
        _keys(ref, "kind pointer content_sha256")
        _enum(ref["kind"], ("MANIFEST", "ASSIGNMENT", "PACKAGE", "APPROVAL", "EVIDENCE", "RULE", "CLAUSE"))
        _text(ref["pointer"])
        _hash(ref["content_sha256"])
        if kind is not None and ref["kind"] != kind:
            raise ValueError("Wrong native reference kind.")
        node = self.nodes.get(_native_key(ref))
        if node is None or ref["content_sha256"] != _digest(node):
            raise ValueError("Native pointer is outside its whitelist, missing or mismatched.")
        return node

    def clauses_under(self, pointer):
        return [self.reference(kind, path) for kind, path in self.nodes
                if kind == "CLAUSE" and path.startswith(pointer + "/")]

    def evidence_reference(self, identifier):
        return next(self.reference(kind, path) for (kind, path), node in self.nodes.items()
                    if kind == "EVIDENCE" and node["evidence_id"] == identifier)


def _cutoff(value, observed):
    value["source_information_cutoff"] = _optional_time(value["source_information_cutoff"])
    if value["source_information_cutoff"] is not None and value["source_information_cutoff"] > observed:
        raise ValueError("Information cutoff postdates observation.")


def _population_contradictions(rule, binding, scope):
    population = rule["instrument_scope"]
    relation = binding["population"]["relation"]
    if population["kind"] == "ALL_ACCOUNT_INSTRUMENTS":
        if relation == "DISJOINT":
            raise ValueError("Account-wide population cannot be disjoint.")
    else:
        members = population["instruments"]
        contains = any(member == scope["instrument"] for member in members)
        same_namespace = all(all(member[key] == scope["instrument"][key] for key in
                                 ("source_id", "source_contract", "source_contract_version", "environment")) for member in members)
        if relation == "DISJOINT" and contains:
            raise ValueError("Disjoint claim contradicts explicit membership.")
        if relation == "CONTAINS_ENTRY_INSTRUMENT" and same_namespace and not contains:
            raise ValueError("Containing claim contradicts exact same-namespace population.")
    quantity = rule["body"].get("limit_kind") == "PER_POSITION_QUANTITY"
    meaning = binding["quantity_denomination"]["relation"]
    if quantity and meaning == "NOT_APPLICABLE":
        raise ValueError("Quantity limit requires denomination semantics.")
    if quantity and meaning == "IDENTICAL" and rule["body"]["quantity_unit"] != scope["quantity_unit"]:
        raise ValueError("Identical denomination contradicts unit spelling.")
    if binding["terminal_projection"]["kind"] != "UNKNOWN" and rule["body"]["type"] != "POSITION_LIMIT":
        raise ValueError("Only supported native position limits admit positive terminal projections.")


def _support(value, native, scope, at):
    if value is None:
        return {}, {}
    _keys(value, "observed_at evidence native_mappings scope_binding coverage rule_bindings")
    value["observed_at"] = _time(value["observed_at"])
    if value["observed_at"] > at:
        raise ValueError("Support packet observed after K.")
    observed = value["observed_at"]
    for item in _list(value["evidence"]):
        _keys(item, "evidence_id source media_type content_base64 content_sha256 source_available_at observed_at")
        _text(item["evidence_id"])
        _text(item["media_type"])
        _namespace(item["source"], True)
        _hash(item["content_sha256"])
        _text(item["content_base64"])
        raw = base64.b64decode(item["content_base64"], validate=True)
        if not raw or base64.b64encode(raw).decode("ascii") != item["content_base64"]:
            raise ValueError("Original bytes require nonempty canonical padded base64.")
        if hashlib.sha256(raw).hexdigest() != item["content_sha256"]:
            raise ValueError("Original raw-byte SHA-256 mismatch.")
        item["observed_at"] = _time(item["observed_at"])
        item["source_available_at"] = _optional_time(item["source_available_at"])
        if item["observed_at"] > observed or (item["source_available_at"] is not None and item["source_available_at"] > item["observed_at"]):
            raise ValueError("Impossible original chronology.")
    value["evidence"] = _unique(value["evidence"], lambda row: row["evidence_id"])
    catalog = {row["evidence_id"]: row for row in value["evidence"]}
    for mapping in _list(value["native_mappings"]):
        _keys(mapping, "native_reference original_reference original_locator relationship")
        ref = mapping["native_reference"]
        node = native.resolve(ref)
        _text(mapping["original_locator"])
        relationship = {"EVIDENCE": "EXACT_DOCUMENT", "CLAUSE": "CLAUSE_SUPPORT"}.get(ref["kind"], "ASSERTION_SUPPORT")
        _enum(mapping["relationship"], (relationship,))
        _refs([mapping["original_reference"]], catalog, native.deadlines[_native_key(ref)])
        original = catalog[mapping["original_reference"]["evidence_id"]]
        if ref["kind"] == "EVIDENCE":
            _same(original["source"], node["source"], "Native document source")
            if node["document_sha256"] is not None and node["document_sha256"] != original["content_sha256"]:
                raise ValueError("Known native document digest mismatch.")
            published = node["timing"]["source_available_at"]
            if published is not None and original["source_available_at"] is not None:
                _same(_time(published), original["source_available_at"], "Native document publication")
    value["native_mappings"] = _unique(value["native_mappings"], lambda row: _native_key(row["native_reference"]))
    value["native_mappings"].sort(key=lambda row: _canonical(row["native_reference"]))
    mappings = {_native_key(row["native_reference"]): row for row in value["native_mappings"]}
    for mapping in value["native_mappings"]:
        if mapping["native_reference"]["kind"] == "CLAUSE":
            clause = native.resolve(mapping["native_reference"])
            document = mappings.get(_native_key(native.evidence_reference(clause["evidence_id"])))
            if document is not None:
                _same(document["original_reference"], mapping["original_reference"], "Clause/document original")
    scope_binding, coverage = value["scope_binding"], value["coverage"]
    _keys(scope_binding, "status evidence_refs")
    _enum(scope_binding["status"], ("COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"))
    scope_binding["evidence_refs"] = _refs(scope_binding["evidence_refs"], catalog, observed)
    _keys(coverage, "terminal_limit_inventory exceptions_and_overrides source_information_cutoff evidence_refs")
    for key in ("terminal_limit_inventory", "exceptions_and_overrides"):
        _enum(coverage[key], _COMPLETENESS)
    _cutoff(coverage, observed)
    coverage["evidence_refs"] = _refs(coverage["evidence_refs"], catalog, observed)
    for binding in _list(value["rule_bindings"]):
        _keys(binding, "rule_reference population quantity_denomination terminal_projection force")
        rule = native.resolve(binding["rule_reference"], "RULE")
        for name, field, choices in (
            ("population", "relation", ("CONTAINS_ENTRY_INSTRUMENT", "DISJOINT", "UNKNOWN")),
            ("quantity_denomination", "relation", ("IDENTICAL", "INCOMPATIBLE", "UNKNOWN", "NOT_APPLICABLE")),
            ("terminal_projection", "kind", _PROJECTIONS),
        ):
            claim = binding[name]
            _keys(claim, field + " evidence_refs")
            _enum(claim[field], choices)
            claim["evidence_refs"] = _refs(claim["evidence_refs"], catalog, observed)
        force = binding["force"]
        _keys(force, "status exception_coverage exception_resolution source_information_cutoff evidence_refs")
        _enum(force["status"], ("MANDATORY_THROUGHOUT_P", "UNKNOWN"))
        _enum(force["exception_coverage"], _COMPLETENESS)
        _enum(force["exception_resolution"], ("NONE_APPLICABLE", "RESOLVED_WITH_BOUND_UNCHANGED", "UNKNOWN"))
        _cutoff(force, observed)
        force["evidence_refs"] = _refs(force["evidence_refs"], catalog, observed)
        _population_contradictions(rule, binding, scope)
    value["rule_bindings"] = _unique(value["rule_bindings"], lambda row: _native_key(row["rule_reference"]))
    value["rule_bindings"].sort(key=lambda row: _canonical(row["rule_reference"]))
    return catalog, mappings


def _target(target, native):
    if type(target) is not dict:
        raise ValueError("Expected tagged admission target.")
    kind = _enum(target.get("kind"), ("REGIME", "SCOPE", "COVERAGE", "RULE"))
    _keys(target, "kind rule_reference" if kind == "RULE" else "kind")
    if kind == "RULE":
        native.resolve(target["rule_reference"], "RULE")


def _context(value, q, native, catalog):
    if value is None:
        return None
    support = q["rule_support"]
    if support is None:
        raise ValueError("Terminal admission has no support packet.")
    _keys(value, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision purpose request_content_sha256 knowledge_boundary effective_from effective_until admitted_at available_at applicable_approval_refs admissions")
    _enum(value["contract"], (ADMISSION_CONTRACT,))
    _enum(value["rule_version"], (ADMISSION_RULE,))
    _enum(value["purpose"], (PURPOSE,))
    _namespace(value["authority_namespace"])
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(value[key])
    if type(value["mandate_revision"]) is not int or value["mandate_revision"] < 1:
        raise ValueError("Mandate revision must be a positive integer.")
    _hash(value["request_content_sha256"])
    if value["request_content_sha256"] != _digest(q):
        raise ValueError("Independent admission request pin mismatch.")
    for key in ("knowledge_boundary", "effective_from", "admitted_at", "available_at"):
        value[key] = _time(value[key])
    value["effective_until"] = _optional_time(value["effective_until"])
    if value["effective_until"] is not None and value["effective_from"] >= value["effective_until"]:
        raise ValueError("Admission interval must be nonempty.")
    at = q["knowledge_boundary"]
    if value["knowledge_boundary"] != at or not support["observed_at"] <= value["admitted_at"] <= value["available_at"] <= at:
        raise ValueError("Admission boundary/timing mismatch.")
    if native.original is not None:
        observations = [native.original["manifest"]["timing"]["observed_at"]]
        observations.extend(row["observed_at"] for row in native.original["approvals"])
        if any(_time(item) > value["admitted_at"] for item in observations):
            raise ValueError("Admission predates consumed native observations.")
    for ref in _list(value["applicable_approval_refs"]):
        native.resolve(ref, "APPROVAL")
    value["applicable_approval_refs"] = _unique(value["applicable_approval_refs"], _native_key)
    value["applicable_approval_refs"].sort(key=_canonical)
    _same(value["applicable_approval_refs"], sorted(native.approvals, key=_canonical), "Selected native approvals")
    for receipt in _list(value["admissions"]):
        _keys(receipt, "target status evidence_refs")
        _target(receipt["target"], native)
        _enum(receipt["status"], ("ADMITTED", "UNRESOLVED"))
        receipt["evidence_refs"] = _refs(receipt["evidence_refs"], catalog, value["admitted_at"])
        if receipt["status"] == "ADMITTED" and not receipt["evidence_refs"]:
            raise ValueError("Admitted receipt requires nonempty original references.")
    value["admissions"] = _unique(value["admissions"], lambda row: _target_key(row["target"]))
    value["admissions"].sort(key=lambda row: _canonical(row["target"]))
    return value


class _Proof:
    """Collect independent unresolved gates and original-support closures."""

    def __init__(self, native, support, context, catalog, mappings, at):
        self.native, self.support, self.context = native, support, context
        self.catalog, self.mappings, self.at = catalog, mappings, at
        self.findings = []
        self.current = context is not None and context["effective_from"] <= at and (
            context["effective_until"] is None or at < context["effective_until"])

    def unknown(self, code, subject):
        self.findings.append(dict(reason_code=code, subject=subject))
        return False

    def originals(self, refs, subject):
        if not refs:
            return self.unknown("ORIGINAL_SUPPORT_MISSING", subject)
        good = True
        for ref in refs:
            if self.catalog[ref["evidence_id"]]["source_available_at"] is None:
                self.unknown("SOURCE_AVAILABILITY_UNKNOWN", _SUPPORT_PATH + "/evidence/" + str(
                    next(i for i, item in enumerate(self.support["evidence"]) if item["evidence_id"] == ref["evidence_id"])) + "/source_available_at")
                good = False
        return good

    def mapped(self, references):
        refs, good = [], True
        for reference in references:
            mapping = self.mappings.get(_native_key(reference))
            if mapping is None:
                self.unknown("ORIGINAL_SUPPORT_MISSING", _SUPPORT_PATH + "/native_mappings")
                good = False
                continue
            refs.append(mapping["original_reference"])
            if reference["kind"] == "CLAUSE":
                clause = self.native.resolve(reference)
                document = self.mappings.get(_native_key(self.native.evidence_reference(clause["evidence_id"])))
                if document is None:
                    self.unknown("ORIGINAL_SUPPORT_MISSING", _SUPPORT_PATH + "/native_mappings")
                    good = False
                else:
                    refs.append(document["original_reference"])
        if refs:
            good = self.originals(refs, _SUPPORT_PATH + "/native_mappings") and good
        return _union_refs(refs), good

    def receipt(self, target, required):
        if not self.current:
            return [], False
        matches = [(i, row) for i, row in enumerate(self.context["admissions"]) if _target_key(row["target"]) == _target_key(target)]
        if not matches:
            return [], self.unknown("RECEIPT_MISSING", _CONTEXT_PATH + "/admissions")
        index, receipt = matches[0]
        path = _CONTEXT_PATH + f"/admissions/{index}"
        good = True
        if receipt["status"] != "ADMITTED":
            self.unknown("RECEIPT_UNRESOLVED", path + "/status")
            good = False
        actual = {_canonical(ref) for ref in receipt["evidence_refs"]}
        if any(_canonical(ref) not in actual for ref in required):
            self.unknown("ORIGINAL_SUPPORT_MISSING", path + "/evidence_refs")
            good = False
        good = self.originals(receipt["evidence_refs"], path + "/evidence_refs") and good
        return _union_refs(required + receipt["evidence_refs"]), good


def _union_refs(refs):
    return sorted({_canonical(ref): ref for ref in refs}.values(), key=lambda ref: (ref["evidence_id"], ref["envelope_sha256"]))


def _population_supported(rule, binding, scope):
    population = rule["instrument_scope"]
    relation = binding["population"]["relation"]
    if relation == "UNKNOWN":
        return False
    if population["kind"] == "ALL_ACCOUNT_INSTRUMENTS":
        return relation == "CONTAINS_ENTRY_INSTRUMENT"
    members = population["instruments"]
    if relation == "CONTAINS_ENTRY_INSTRUMENT":
        return any(member == scope["instrument"] for member in members)
    return all(all(member[key] == scope["instrument"][key] for key in
                   ("source_id", "source_contract", "source_contract_version", "environment")) and
               member["instrument_id"] != scope["instrument"]["instrument_id"] for member in members)


def _evaluate(request, position_context, limit_context):
    # Reject non-JSON material before copying, including cycles and invalid Unicode.
    _canonical(request)
    _canonical(position_context)
    _canonical(limit_context)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope position_effect account_rule_regime rule_support")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    if q["assessment_economic_time"] != at:
        raise ValueError("Current terminal assessment requires T = K.")
    _scope(q["scope"])
    position = regime = None
    pair = q["position_effect"]
    if pair is None:
        if position_context is not None:
            raise ValueError("Orphaned native position-effect context.")
    else:
        _keys(pair, "assessment request")
        if type(pair["assessment"]) is not dict or type(pair["request"]) is not dict:
            raise ValueError("Native position pair requires serialized objects.")
        position = validate_current_entry_position_effect_basis(pair["assessment"], pair["request"],
                                                               trusted_position_effect_context=position_context)
        _same(position["scope"], q["scope"], "Native position-effect scope")
        for key in ("assessment_economic_time", "knowledge_boundary"):
            _same(_time(position[key]), at, "Native position-effect time")
    pair = q["account_rule_regime"]
    if pair is not None:
        _keys(pair, "assessment assessment_input")
        if type(pair["assessment"]) is not dict or type(pair["assessment_input"]) is not dict:
            raise ValueError("Native regime pair requires serialized objects.")
        regime = validate_causal_account_rule_regime_assessment(pair["assessment"], pair["assessment_input"])
        for key in ("requested_knowledge_boundary", "economic_timestamp"):
            _same(_time(regime[key]), at, "Native regime time")
        _same(regime["account"], {key: q["scope"]["account"][key] for key in regime["account"]}, "Native regime account")
        if regime["selected_regime"] is not None:
            for key in ("assignment", "package"):
                _same(regime["selected_regime"][key]["provider_id"], q["scope"]["provider_id"], "Selected provider")
    native = _Native(None if pair is None else pair["assessment_input"], regime)
    catalog, mappings = _support(q["rule_support"], native, q["scope"], at)
    context = _context(deepcopy(limit_context), q, native, catalog)
    # No semantic return precedes complete structural and owner validation.
    proof = _Proof(native, q["rule_support"], context, catalog, mappings, at)
    support = None
    if position is None:
        proof.unknown("OWNER_MISSING", "/request/position_effect")
    elif position["outcome"] != "ESTABLISHED":
        proof.unknown("OWNER_NOT_ESTABLISHED", "/request/position_effect/assessment")
    else:
        interval = {key: _decimal(value) for key, value in position["effect_basis"]["quantity_range"].items()}
        support = dict(position_effect_identity=position["assessment_identity"], quantity_unit=q["scope"]["quantity_unit"], interval=interval)
    if regime is None:
        proof.unknown("OWNER_MISSING", "/request/account_rule_regime")
    elif native.package is None:
        proof.unknown("REGIME_NOT_UNIQUE", "/request/account_rule_regime/assessment")
    if q["rule_support"] is None:
        proof.unknown("RULE_SUPPORT_MISSING", _SUPPORT_PATH)
    if context is None:
        proof.unknown("ADMISSION_MISSING", _CONTEXT_PATH)
    elif not proof.current:
        proof.unknown("ADMISSION_NOT_CURRENT", _CONTEXT_PATH)

    regime_refs, scope_refs = [], []
    regime_good = scope_good = False
    if native.package is not None and q["rule_support"] is not None:
        references = [native.reference("MANIFEST", "/manifest"), native.assignment, native.package] + native.approvals
        references += native.clauses_under(native.assignment["pointer"])
        references += [ref for ref in native.clauses_under(native.package["pointer"])
                       if ref["pointer"].startswith(native.package["pointer"] + "/evidence_refs/")]
        required, mapped_good = proof.mapped(references)
        regime_refs, admitted = proof.receipt(dict(kind="REGIME"), required)
        regime_good = mapped_good and admitted
    if q["rule_support"] is not None:
        binding = q["rule_support"]["scope_binding"]
        originals_good = proof.originals(binding["evidence_refs"], _SUPPORT_PATH + "/scope_binding/evidence_refs")
        scope_refs, admitted = proof.receipt(dict(kind="SCOPE"), binding["evidence_refs"])
        if binding["status"] != "COMPATIBLE":
            proof.unknown("SCOPE_INCOMPATIBLE" if binding["status"] == "INCOMPATIBLE" else "SCOPE_UNRESOLVED",
                          _SUPPORT_PATH + "/scope_binding/status")
        scope_good = binding["status"] == "COMPATIBLE" and originals_good and admitted

    shared_codes = {finding["reason_code"] for finding in proof.findings}
    # Coverage is deliberately outside the shared gates of a self-contained negative.
    if q["rule_support"] is not None:
        coverage = q["rule_support"]["coverage"]
        for key in ("terminal_limit_inventory", "exceptions_and_overrides"):
            if coverage[key] != "COMPLETE":
                proof.unknown("COVERAGE_INCOMPLETE", _SUPPORT_PATH + "/coverage/" + key)
        if coverage["source_information_cutoff"] != at:
            proof.unknown("COVERAGE_NOT_CURRENT", _SUPPORT_PATH + "/coverage/source_information_cutoff")
        coverage_refs = list(coverage["evidence_refs"])
        proof.originals(coverage_refs, _SUPPORT_PATH + "/coverage/evidence_refs")
        if native.package is not None:
            package = regime["selected_regime"]["package"]
            if package["coverage"]["completeness"] != "COMPLETE":
                proof.unknown("COVERAGE_INCOMPLETE", "/request/account_rule_regime/assessment/selected_regime/package/coverage/completeness")
            refs, _ = proof.mapped([ref for ref in native.clauses_under(native.package["pointer"])
                                   if ref["pointer"].startswith(native.package["pointer"] + "/coverage/")])
            coverage_refs += refs
        proof.receipt(dict(kind="COVERAGE"), _union_refs(coverage_refs))

    dispositions, constraints, negatives = [], [], []
    bindings = {} if q["rule_support"] is None else {
        _native_key(row["rule_reference"]): (i, row) for i, row in enumerate(q["rule_support"]["rule_bindings"])}
    for reference, rule in native.rules:
        start = len(proof.findings)
        row = dict(rule_reference=reference, disposition="UNRESOLVED", terminal_count=None, reason_codes=[])
        dispositions.append(row)
        if q["rule_support"] is None:
            row["reason_codes"] = sorted(shared_codes)
            continue
        found = bindings.get(_native_key(reference))
        if found is None:
            proof.unknown("RULE_BINDING_MISSING", _SUPPORT_PATH + "/rule_bindings")
            row["reason_codes"] = sorted(shared_codes | {"RULE_BINDING_MISSING"})
            continue
        index, binding = found
        path = _SUPPORT_PATH + f"/rule_bindings/{index}"
        population = binding["population"]
        population_good = _population_supported(rule, binding, q["scope"])
        if not population_good:
            proof.unknown("POPULATION_UNRESOLVED", path + "/population/relation")
        population_originals = proof.originals(population["evidence_refs"], path + "/population/evidence_refs")
        required, mapped_good = proof.mapped([reference] + native.clauses_under(reference["pointer"]))
        required += population["evidence_refs"]
        effects = set(rule["effects"])
        disjoint = population_good and population["relation"] == "DISJOINT"
        future_only = effects <= {"EXIT", "PHASE_TRANSITION", "PAYOUT"}
        numeric = (not disjoint and not future_only and effects != {"UNKNOWN"} and
                   rule["body"]["type"] == "POSITION_LIMIT")
        numeric_good = True
        if not disjoint and not future_only:
            if effects == {"UNKNOWN"}:
                proof.unknown("RULE_EFFECT_UNKNOWN", "/request/account_rule_regime/assessment_input" + reference["pointer"] + "/effects")
            elif rule["representation"] == "UNSUPPORTED":
                proof.unknown("RULE_UNSUPPORTED", "/request/account_rule_regime/assessment_input" + reference["pointer"] + "/representation")
        if numeric:
            if rule["body"]["limit_kind"] == "PER_POSITION_QUANTITY":
                meaning = binding["quantity_denomination"]
                if meaning["relation"] != "IDENTICAL":
                    proof.unknown("QUANTITY_SEMANTICS_INCOMPATIBLE" if meaning["relation"] == "INCOMPATIBLE" else "QUANTITY_SEMANTICS_UNRESOLVED",
                                  path + "/quantity_denomination/relation")
                    numeric_good = False
                numeric_good = proof.originals(meaning["evidence_refs"], path + "/quantity_denomination/evidence_refs") and numeric_good
                required += meaning["evidence_refs"]
            projection, force = binding["terminal_projection"], binding["force"]
            if projection["kind"] == "UNKNOWN":
                proof.unknown("TERMINAL_PROJECTION_UNRESOLVED", path + "/terminal_projection/kind")
                numeric_good = False
            if force["status"] != "MANDATORY_THROUGHOUT_P":
                proof.unknown("RULE_FORCE_UNRESOLVED", path + "/force/status")
                numeric_good = False
            if force["exception_coverage"] != "COMPLETE" or force["exception_resolution"] == "UNKNOWN" or force["source_information_cutoff"] != at:
                proof.unknown("EXCEPTIONS_UNRESOLVED", path + "/force")
                numeric_good = False
            for name in ("terminal_projection", "force"):
                numeric_good = proof.originals(binding[name]["evidence_refs"], path + "/" + name + "/evidence_refs") and numeric_good
                required += binding[name]["evidence_refs"]
        rule_refs, admitted = proof.receipt(dict(kind="RULE", rule_reference=reference), _union_refs(required))
        base_good = regime_good and scope_good and mapped_good and admitted and population_good and population_originals
        if base_good and support is not None and rule["body"].get("limit_kind") == "CONCURRENT_POSITION_COUNT":
            row["terminal_count"] = 0 if disjoint else 1
        if base_good:
            if disjoint:
                row.update(disposition="DISJOINT_POPULATION", reason_codes=["DISJOINT_POPULATION_ESTABLISHED"])
            elif effects != {"UNKNOWN"} and (future_only or rule["representation"] == "SUPPORTED" and rule["body"]["type"] != "POSITION_LIMIT"):
                row.update(disposition="OTHER_OBLIGATION", reason_codes=["OTHER_OBLIGATION_RETAINED"])
            elif numeric and numeric_good and support is not None:
                row.update(disposition="TERMINAL_LIMIT", reason_codes=["TERMINAL_RULE_ESTABLISHED"])
                body = rule["body"]
                constraint = dict(kind="PER_POSITION_QUANTITY" if body["limit_kind"] == "PER_POSITION_QUANTITY" else "TERMINAL_POSITION_COUNT",
                                  rule_reference=reference, maximum=_decimal(body["maximum"]) if body["limit_kind"] == "PER_POSITION_QUANTITY" else body["maximum"],
                                  projection=binding["terminal_projection"]["kind"])
                if constraint["kind"] == "TERMINAL_POSITION_COUNT":
                    constraint["terminal_count"] = row["terminal_count"]
                constraints.append(constraint)
                a, b = (support["interval"][key] for key in ("minimum", "maximum"))
                excluded = reason = None
                if constraint["kind"] == "TERMINAL_POSITION_COUNT":
                    if constraint["terminal_count"] > constraint["maximum"]:
                        reason, excluded = "COUNT_LIMIT_EXCLUDES_ALL_P", dict(kind="ALL_SUPPORT")
                elif _number(constraint["maximum"]) < _number(a):
                    reason, excluded = "QUANTITY_LIMIT_EXCLUDES_ALL_P", dict(kind="ALL_SUPPORT")
                elif _number(constraint["maximum"]) < _number(b):
                    reason = "QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL"
                    excluded = dict(kind="UPPER_TAIL", lower_exclusive=constraint["maximum"], upper_inclusive=b)
                if excluded is not None:
                    negatives.append(dict(rule_reference=reference, reason_code=reason, excluded_domain=excluded,
                                          admission_targets=sorted([dict(kind="REGIME"), dict(kind="SCOPE"), dict(kind="RULE", rule_reference=reference)], key=_canonical),
                                          evidence_refs=_union_refs(regime_refs + scope_refs + rule_refs)))
        if row["disposition"] == "UNRESOLVED":
            row["reason_codes"] = sorted(shared_codes | {finding["reason_code"] for finding in proof.findings[start:]})
    findings = sorted({_canonical(row): row for row in proof.findings}.values(), key=_canonical)
    all_excluded = any(row["excluded_domain"]["kind"] == "ALL_SUPPORT" for row in negatives)
    predicate = domain = None
    if not findings:
        if support is None or any(row["disposition"] == "UNRESOLVED" for row in dispositions):
            raise ValueError("Incomplete terminal proof without unresolved findings.")
        predicate = dict(kind=PREDICATE_KIND, support=deepcopy(support["interval"]), quantity_unit=q["scope"]["quantity_unit"],
                         constraints=sorted(constraints, key=_canonical))
        a, b = (support["interval"][key] for key in ("minimum", "maximum"))
        upper = min([b] + [row["maximum"] for row in constraints if row["kind"] == "PER_POSITION_QUANTITY"], key=_number)
        domain = dict(kind="EMPTY") if all_excluded or _number(upper) < _number(a) else dict(kind="CLOSED_INTERVAL", minimum=a, maximum=upper)
    if all_excluded:
        outcome, domain = "NOT_SUITABLE", dict(kind="EMPTY")
    elif findings:
        outcome = "UNKNOWN"
    else:
        outcome = "ESTABLISHED"
    reasons = {row["reason_code"] for row in findings} | {row["reason_code"] for row in negatives}
    if outcome == "ESTABLISHED":
        reasons.add("TERMINAL_DOMAIN_ESTABLISHED")
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
                  scope=deepcopy(q["scope"]), outcome=outcome, reason_codes=sorted(reasons), position_effect_support=support,
                  rule_dispositions=sorted(dispositions, key=_canonical), terminal_limit_predicate=predicate,
                  terminal_satisfying_domain=domain, negative_proofs=sorted(negatives, key=_canonical), unresolved_findings=findings,
                  conditions=list(CONDITIONS), reconstruction_evidence=dict(request=q,
                      trusted_position_effect_context_sha256=None if position is None else position["reconstruction_evidence"]["trusted_position_effect_context_sha256"],
                      trusted_position_limit_context_sha256=None if context is None else _digest(context)),
                  downstream_obligations=list(DOWNSTREAM_OBLIGATIONS), source_authentication=SOURCE_AUTHENTICATION,
                  authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_current_terminal_position_limits(request: dict, *, trusted_position_effect_context=None,
                                             trusted_position_limit_context=None) -> dict:
    """Replay native facts and host-admitted rules; no source authentication is performed."""
    try:
        return deepcopy(_evaluate(request, trusted_position_effect_context, trusted_position_limit_context))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError, binascii.Error, StopIteration) as exc:
        raise ValueError("Malformed current terminal position-limit request.") from exc


def validate_current_terminal_position_limits(assessment: dict, request: dict, *, trusted_position_effect_context=None,
                                             trusted_position_limit_context=None) -> dict:
    """Reconstruct every field; a caller-recomputed assessment identity is never proof."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be a serialized JSON object.")
        expected = evaluate_current_terminal_position_limits(request,
            trusted_position_effect_context=trusted_position_effect_context,
            trusted_position_limit_context=trusted_position_limit_context)
        _same(assessment, expected, "Terminal position-limit assessment")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized terminal position-limit assessment.") from exc
