"""Exact conditional settled-balance descriptor; independent admission belongs to the host."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re

from .xauusd_current_entry_quantity_constraint_composition import (
    validate_current_entry_quantity_constraint_composition,
)


CONTRACT = "trading.xauusd_current_entry_provider_measure_projection_basis.v1"
RULE_VERSION = "xauusd_current_entry_provider_measure_projection_basis_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_entry_provider_measure_projection_basis.admission.v1"
ADMISSION_RULE_VERSION = "xauusd_current_entry_provider_measure_projection_basis_admission_v1"
ADMISSION_PURPOSE = "PROVIDER_MEASURE_PROJECTION_FACT_ADMISSION_ONLY"
IDENTITY_PREFIX = "current_entry_provider_measure_projection_basis_"
DESCRIPTOR_KIND = "EXACT_MODELED_SETTLED_BALANCE_V1"
ENDPOINT = "FULLY_SETTLED_MODELED_STOP"
ENTRY_MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
CONDITIONS = (
    "NATIVE_MODELED_ENTRY_AND_STOP_COORDINATES_ASSUMED", "COMPLETE_MODELED_ENTRY_AND_STOP_CLOSE",
    "ALL_SCENARIO_AMOUNTS_RECOGNIZED_EXACTLY_ONCE", "SETTLEMENT_STRICTLY_BEFORE_DEADLINE",
    "NO_RELATED_UNSETTLED_AMOUNT_OR_POSITION_AT_ENDPOINT", "NO_UNRELATED_INTERVENING_FINANCIAL_EVENT",
    "ADMITTED_ACCOUNTING_AND_CHARGE_TERMS_REMAIN_APPLICABLE", "NATIVE_RISK_BASIS_CONDITIONS_RETAINED",
)
LIMITATIONS = (
    "CONDITIONAL_PLANNING_ASSUMPTIONS", "REALIZED_LOSS_CEILING_NOT_GUARANTEED",
    "FILL_AND_STOP_EXECUTION_NOT_GUARANTEED", "SOURCE_AUTHENTICITY_NOT_VERIFIED",
    "FUTURE_MARKET_AND_SPECIFICATION_CHANGES_NOT_COVERED", "NO_AUTHORIZATION_LEASE",
    "MODELED_SETTLEMENT_NOT_OBSERVED", "BALANCE_ONLY_EXACT_MODEL", "NO_PROJECTION_OUTSIDE_COMPOSED_SUPPORT",
    "PROVIDER_FLOOR_AND_HEADROOM_NOT_ASSESSED", "CONTINUOUS_DRAWDOWN_COMPLIANCE_NOT_ASSESSED",
)
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
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
FINANCIAL_CATEGORIES = (
    "UNPOSTED_CHARGES", "CASH_TRANSFERS_AND_WITHDRAWALS", "PAYOUT_ADJUSTMENTS",
    "PHASE_OR_CAPITAL_ADJUSTMENTS", "MONETARY_RESERVATIONS", "KNOWN_SCHEDULED_FINANCIAL_EVENTS",
    "OTHER_MEASURE_AFFECTING_OBLIGATIONS",
)
ADMISSION_TARGETS = (
    "SCOPE_AND_NATIVE_BINDINGS", "MEASURE_DEFINITION_AND_BASELINE", "PRICE_LOSS_RECOGNITION",
    "COST_COVERAGE_AND_ROUNDING", "FINANCIAL_SOURCE_COVERAGE", "INTERPRETATION_REVISION_COVERAGE",
    "SCENARIO_AND_SETTLEMENT_SEMANTICS",
)
REASON_CODES = frozenset((
    "CONDITIONAL_BALANCE_PROJECTION_ESTABLISHED", "OWNER_MISSING", "OWNER_UNKNOWN", "OWNER_NOT_SUITABLE",
    "NATIVE_UNRESOLVED", "MEASURE_TARGET_MISSING", "PROJECTION_EVIDENCE_MISSING", "ADMISSION_MISSING",
    "ADMISSION_NOT_CURRENT", "RECEIPT_MISSING", "RECEIPT_UNRESOLVED", "ORIGINAL_SUPPORT_MISSING",
    "SOURCE_AVAILABILITY_UNKNOWN", "CURRENT_BASELINE_UNESTABLISHED", "MEASURE_BINDING_UNRESOLVED",
    "MEASURE_MODEL_UNSUPPORTED", "DENOMINATION_UNRESOLVED", "INTERPRETATION_COVERAGE_UNRESOLVED",
    "REVISION_HISTORY_INCOMPLETE", "REVISION_ORDER_UNSUPPORTED", "COMPETING_INTERPRETATIONS",
    "NO_CURRENT_INTERPRETATION", "INTERPRETATION_WITHDRAWN", "INTERPRETATION_EXPIRED",
    "HORIZON_INTERPRETATION_CHANGE", "PRICE_RECOGNITION_UNRESOLVED", "CHARGE_RECOGNITION_MISSING",
    "CHARGE_RECOGNITION_UNRESOLVED", "CHARGE_ALREADY_REFLECTED", "CHARGE_AGGREGATION_UNRESOLVED",
    "COST_COVERAGE_UNRESOLVED", "EXACT_DEBIT_UNESTABLISHED", "ROUNDING_SEMANTICS_UNRESOLVED",
    "FINANCING_HORIZON_UNRESOLVED", "FINANCIAL_COVERAGE_UNRESOLVED", "FINANCIAL_REPORT_MISSING",
    "ADDITIONAL_FINANCIAL_EFFECT_PRESENT", "SCENARIO_CONTINUITY_UNRESOLVED",
))
_NAMESPACE = "source_id source_contract source_contract_version"
_CONTEXT_KEYS = tuple("trusted_" + name + "_context_sha256" for name in
                      ("planning", "quantity", "feasibility", "position_effect", "position_limit"))
_COMPLETENESS = ("COMPLETE", "LIMITED", "UNKNOWN")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
_E = "/request/projection_evidence"
_C = "/trusted_financial_projection_context"


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


def _canonical(value):
    """Native JSON numbers are provenance only; no financial arithmetic uses floats."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON keys must be strings.")
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
    if type(value) is float and math.isfinite(value):
        return json.dumps(value, allow_nan=False)
    raise ValueError("Expected finite serialized JSON.")


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
        fields = {"RISK_CHARGE": "charge_id", "REGIME_ASSIGNMENT": "assignment_id",
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

    def target(self, target):
        if target is None:
            return
        _keys(target, "assignment package rule measure")
        for field, kind in (("assignment", "REGIME_ASSIGNMENT"), ("package", "REGIME_PACKAGE"),
                            ("rule", "REGIME_RULE"), ("measure", "REGIME_MEASURE")):
            self.resolve(target[field], kind)
        a, p, r, m = (self.resolve(target[key]) for key in ("assignment", "package", "rule", "measure"))
        for key in ("package_id", "package_revision"):
            _same(p[key], target["rule"]["selector"][key], "Target package")
        _same(target["rule"]["selector"], target["measure"]["selector"], "Target rule/measure")
        if self.selected is not None:
            _same(a["assignment_id"], self.selected["assignment"]["assignment_id"], "Selected assignment")
            for key in ("package_id", "package_revision"):
                _same(p[key], self.selected["package"][key], "Selected package")
        _same(r["body"]["measure"], m, "Native measure")

    def required(self, target, at):
        if target is None or self.selected is None:
            return [], [], []
        scope = [target["assignment"], target["package"]]
        for ref in list(scope):
            scope += self.under(ref)
        assignment = self.resolve(target["assignment"])
        package = self.resolve(target["package"])
        for i, binding in enumerate(assignment["package_bindings"]):
            period = binding["effective_period"]
            if binding["package"] == {key: package[key] for key in ("package_id", "package_revision")} and (
                period["effective_from"] is not None and _time(period["effective_from"]) <= at and
                period["end_status"] != "UNKNOWN" and
                (period["effective_until"] is None or at < _time(period["effective_until"]))
            ):
                ref = self.reference("REGIME_BINDING", dict(assignment_id=assignment["assignment_id"], binding_index=i))
                scope += [ref] + self.under(ref)
        for (kind, _), ref in self.refs.items():
            if kind == "REGIME_APPROVAL" and any(self.resolve(ref)["approval_reference"] == a["approval_reference"]
                                                 for a in self.selected["approval_references"]):
                scope.append(ref)
        measure = [ref for ref in (self.reference("ACCOUNT_BUNDLE"), target["rule"], target["measure"]) if ref is not None]
        for ref in (target["rule"], target["measure"]):
            measure += self.under(ref)
        risk = [ref for ref in (self.reference("RISK_BASIS_BUNDLE"), self.reference("RISK_FUNCTION")) if ref is not None]
        return scope, measure, risk


def _financial(value, catalog, observed):
    _keys(value, "state_at source_information_cutoff economic_from economic_until source_universe_completeness actor_completeness actors source_roster reports evidence_refs")
    value["state_at"] = _time(value["state_at"])
    if value["state_at"] > observed:
        raise ValueError("Financial state postdates declaration observation.")
    _cutoff(value, observed)
    _interval(value)
    for key in ("source_universe_completeness", "actor_completeness"):
        _enum(value[key], _COMPLETENESS)
    value["evidence_refs"] = _refs(value["evidence_refs"], catalog, observed)
    for actor in _list(value["actors"]):
        _keys(actor, "actor_id namespace role evidence_refs")
        _text(actor["actor_id"])
        _namespace(actor["namespace"])
        _enum(actor["role"], ("PROVIDER", "ACCOUNT_OWNER", "AUTOMATION", "OTHER"))
        actor["evidence_refs"] = _refs(actor["evidence_refs"], catalog, observed)
    value["actors"] = _unique(value["actors"], lambda row: row["actor_id"])
    actors = {row["actor_id"] for row in value["actors"]}
    for source in _list(value["source_roster"]):
        _keys(source, "inventory_id source_namespace role actor_ids evidence_refs")
        _text(source["inventory_id"])
        _namespace(source["source_namespace"])
        _enum(source["role"], ("PROVIDER", "ACCOUNT_LEDGER", "RESERVATION_LEDGER", "OTHER"))
        for identifier in _list(source["actor_ids"]):
            _text(identifier)
            if identifier not in actors:
                raise ValueError("Source references unknown actor.")
        source["actor_ids"] = _unique(source["actor_ids"], lambda row: row)
        source["evidence_refs"] = _refs(source["evidence_refs"], catalog, observed)
    value["source_roster"] = _unique(value["source_roster"], lambda row: row["inventory_id"])
    roster = {row["inventory_id"]: row for row in value["source_roster"]}
    for report in _list(value["reports"]):
        _keys(report, "inventory_id source state_at source_information_cutoff economic_from economic_until source_available_at observed_at inventory_completeness revision_completeness categories evidence_refs")
        _text(report["inventory_id"])
        source = roster.get(report["inventory_id"])
        if source is None:
            raise ValueError("Report not in source roster.")
        _namespace(report["source"], True)
        _same({key: report["source"][key] for key in _NAMESPACE.split()}, source["source_namespace"], "Report source")
        _chronology(report, observed)
        report["state_at"] = _time(report["state_at"])
        if report["state_at"] > report["observed_at"]:
            raise ValueError("Report state postdates observation.")
        _cutoff(report, report["observed_at"])
        _interval(report)
        for key in ("inventory_completeness", "revision_completeness"):
            _enum(report[key], _COMPLETENESS)
        report["evidence_refs"] = _refs(report["evidence_refs"], catalog, report["observed_at"])
        _keys(report["categories"], " ".join(FINANCIAL_CATEGORIES))
        effects = set()
        for category in report["categories"].values():
            _keys(category, "status effects evidence_refs")
            _enum(category["status"], ("ABSENT", "PRESENT", "UNKNOWN"))
            if bool(_list(category["effects"])) != (category["status"] == "PRESENT"):
                raise ValueError("Category presence contradicts its effects.")
            category["evidence_refs"] = _refs(category["evidence_refs"], catalog, report["observed_at"])
            for effect in category["effects"]:
                _keys(effect, "effect_id actor_id known_effective_at evidence_refs")
                _text(effect["effect_id"])
                _text(effect["actor_id"])
                if effect["effect_id"] in effects or effect["actor_id"] not in source["actor_ids"]:
                    raise ValueError("Duplicate effect or actor outside source responsibility.")
                effects.add(effect["effect_id"])
                effect["known_effective_at"] = _optional_time(effect["known_effective_at"])
                effect["evidence_refs"] = _refs(effect["evidence_refs"], catalog, report["observed_at"])
            category["effects"] = _unique(category["effects"], lambda row: row["effect_id"])
    value["reports"] = _unique(value["reports"], lambda row: row["inventory_id"])


def _body(value, catalog, observed):
    _keys(value, "subjects baseline_binding price_loss_recognition charge_recognition cost_coverage_and_rounding financial_coverage scenario_compatibility")
    _keys(value["subjects"], "quantity_composition_bundle_sha256 account_bundle_sha256 regime_bundle_sha256 risk_basis_bundle_sha256 measure_target_sha256")
    for item in value["subjects"].values():
        if item is not None:
            _hash(item)
    baseline = value["baseline_binding"]
    _keys(baseline, "state_at source_information_cutoff relationship evidence_refs")
    baseline["state_at"] = _time(baseline["state_at"])
    if baseline["state_at"] > observed:
        raise ValueError("Baseline state postdates observation.")
    _cutoff(baseline, observed)
    _enum(baseline["relationship"], ("DIRECT_NATIVE_BALANCE", "OTHER", "UNKNOWN"))
    baseline["evidence_refs"] = _refs(baseline["evidence_refs"], catalog, observed)
    price = value["price_loss_recognition"]
    _keys(price, "recognition evidence_refs")
    _enum(price["recognition"], ("EXACT_ONCE_AFTER_BASELINE", "OTHER", "UNKNOWN"))
    price["evidence_refs"] = _refs(price["evidence_refs"], catalog, observed)
    for charge in _list(value["charge_recognition"]):
        _keys(charge, "charge_id charge_content_sha256 recognition aggregation evidence_refs")
        _text(charge["charge_id"])
        _hash(charge["charge_content_sha256"])
        _enum(charge["recognition"], ("EXACT_ONCE_AFTER_BASELINE", "ALREADY_REFLECTED", "OTHER", "UNKNOWN"))
        _enum(charge["aggregation"], ("EXACT_NATIVE_AGGREGATE", "OTHER", "UNKNOWN"))
        charge["evidence_refs"] = _refs(charge["evidence_refs"], catalog, observed)
    value["charge_recognition"] = _unique(value["charge_recognition"], lambda row: row["charge_id"])
    costs = value["cost_coverage_and_rounding"]
    _keys(costs, "completeness rounding financing evidence_refs")
    _enum(costs["completeness"], _COMPLETENESS)
    _enum(costs["rounding"], ("EXACT_NATIVE_EXPRESSION_ON_C", "OTHER", "UNKNOWN"))
    _enum(costs["financing"], ("EXACT_NATIVE_SCENARIO_THROUGH_DEADLINE", "NOT_APPLICABLE", "OTHER", "UNKNOWN"))
    costs["evidence_refs"] = _refs(costs["evidence_refs"], catalog, observed)
    _financial(value["financial_coverage"], catalog, observed)
    scenario = value["scenario_compatibility"]
    _keys(scenario, "endpoint settlement_before economic_from economic_until source_information_cutoff accounting_continuity settlement_meaning evidence_refs")
    _enum(scenario["endpoint"], (ENDPOINT,))
    scenario["settlement_before"] = _time(scenario["settlement_before"])
    _interval(scenario)
    _cutoff(scenario, observed)
    for key in ("accounting_continuity", "settlement_meaning"):
        _enum(scenario[key], ("SUPPORTED", "OTHER", "UNKNOWN"))
    scenario["evidence_refs"] = _refs(scenario["evidence_refs"], catalog, observed)


def _record_ref(ref):
    _keys(ref, "record_id content_sha256")
    _text(ref["record_id"])
    _hash(ref["content_sha256"])


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


def _all_observations(value):
    if type(value) is dict:
        for key, item in value.items():
            if key == "observed_at" and item is not None:
                yield _time(item)
            else:
                yield from _all_observations(item)
    elif type(value) is list:
        for item in value:
            yield from _all_observations(item)


def _context(context, q, native, catalog, fingerprints):
    if context is None:
        return None
    if q["quantity_composition"] is None or q["projection_evidence"] is None:
        raise ValueError("Orphaned projection admission.")
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision purpose request_content_sha256 knowledge_boundary effective_from effective_until admitted_at available_at admissions")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _enum(context["purpose"], (ADMISSION_PURPOSE,))
    _namespace(context["authority_namespace"])
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(context[key])
    if type(context["mandate_revision"]) is not int or context["mandate_revision"] < 1:
        raise ValueError("Mandate revision must be a positive integer.")
    _hash(context["request_content_sha256"])
    request_hash = _digest(q)
    _same(context["request_content_sha256"], request_hash, "Admission request pin")
    for key in ("knowledge_boundary", "effective_from", "admitted_at", "available_at"):
        context[key] = _time(context[key])
    context["effective_until"] = _optional_time(context["effective_until"])
    if context["effective_until"] is not None and context["effective_from"] >= context["effective_until"]:
        raise ValueError("Mandate interval must be nonempty.")
    _same(context["knowledge_boundary"], q["knowledge_boundary"], "Admission knowledge boundary")
    if not context["admitted_at"] <= context["available_at"] <= q["knowledge_boundary"]:
        raise ValueError("Admission unavailable by K.")
    if any(observed > context["admitted_at"] for observed in _all_observations(q)):
        raise ValueError("Admission predates supplied observations.")
    for receipt in _list(context["admissions"]):
        _keys(receipt, "target subject_content_sha256 status evidence_refs")
        target = receipt["target"]
        if type(target) is not dict:
            raise ValueError("Invalid receipt target.")
        if target.get("kind") == "CHARGE_RECOGNITION":
            _keys(target, "kind charge_id charge_content_sha256")
            _text(target["charge_id"])
            _hash(target["charge_content_sha256"])
            node = native.resolve(native.reference("RISK_CHARGE", dict(charge_id=target["charge_id"])))
            _same(target["charge_content_sha256"], _digest(node), "Admission charge pin")
        else:
            _keys(target, "kind")
            _enum(target["kind"], ADMISSION_TARGETS)
        _hash(receipt["subject_content_sha256"])
        _same(receipt["subject_content_sha256"], _digest(dict(request_content_sha256=request_hash,
              native_context_fingerprints=fingerprints, target=target)), "Receipt subject pin")
        _enum(receipt["status"], ("ADMITTED", "UNRESOLVED"))
        receipt["evidence_refs"] = _refs(receipt["evidence_refs"], catalog, context["admitted_at"])
        if receipt["status"] == "ADMITTED" and not receipt["evidence_refs"]:
            raise ValueError("Admitted receipt requires original evidence.")
    context["admissions"] = _unique(context["admissions"], lambda row: _canonical(row["target"]))
    return context


class _Proof:
    def __init__(self, q, context, catalog, mappings, native):
        self.q, self.context, self.catalog, self.mappings, self.native = q, context, catalog, mappings, native
        self.findings = []
        self.current = context is not None and context["effective_from"] <= q["knowledge_boundary"] and (
            context["effective_until"] is None or q["knowledge_boundary"] < context["effective_until"])

    def unknown(self, code, subject):
        self.findings.append(dict(reason_code=code, subject=subject))
        return False

    def originals(self, refs, path):
        good = True
        if not refs:
            good = self.unknown("ORIGINAL_SUPPORT_MISSING", path)
        for ref in refs:
            if self.catalog[ref["evidence_id"]]["source_available_at"] is None:
                good = self.unknown("SOURCE_AVAILABILITY_UNKNOWN", path)
        return good

    def tree(self, value, path):
        refs, good = [], True
        if type(value) is dict:
            for key, item in value.items():
                if key == "evidence_refs":
                    good = self.originals(item, path + "/evidence_refs") and good
                    refs += item
                else:
                    nested, ok = self.tree(item, path + "/" + key)
                    refs += nested
                    good = ok and good
        elif type(value) is list:
            for i, item in enumerate(value):
                nested, ok = self.tree(item, path + "/" + str(i))
                refs += nested
                good = ok and good
        return _union(refs), good

    def mapped(self, refs):
        originals, good = [], True
        for ref in refs:
            matches = [m for m in self.mappings if m["native_reference"] == ref]
            if not matches:
                good = self.unknown("ORIGINAL_SUPPORT_MISSING", _E + "/native_mappings")
            for match in matches:
                originals.append(match["original_reference"])
            if ref["kind"] == "REGIME_CLAUSE":
                clause = self.native.resolve(ref)
                document = self.native.reference("REGIME_DOCUMENT", dict(evidence_id=clause["evidence_id"]))
                document_refs, ok = self.mapped([document])
                originals += document_refs
                good = ok and good
        if originals:
            good = self.originals(originals, _E + "/native_mappings") and good
        return _union(originals), good

    def receipt(self, target, required):
        if not self.current:
            return False
        receipt = next((r for r in self.context["admissions"] if r["target"] == target), None)
        if receipt is None:
            return self.unknown("RECEIPT_MISSING", _C + "/admissions/" + _canonical(target))
        index = self.context["admissions"].index(receipt)
        path = _C + "/admissions/" + str(index)
        good = True
        if receipt["status"] != "ADMITTED":
            good = self.unknown("RECEIPT_UNRESOLVED", path + "/status")
        actual = {_canonical(ref) for ref in receipt["evidence_refs"]}
        if any(_canonical(ref) not in actual for ref in required):
            good = self.unknown("ORIGINAL_SUPPORT_MISSING", path + "/evidence_refs")
        return self.originals(receipt["evidence_refs"], path + "/evidence_refs") and good


def _governing_pins(record, q, native):
    """Only structurally selected current bodies are compared to today's originals."""
    if record is None or record["kind"] != "DECLARE" or (
        record["effective_until"] is not None and record["effective_until"] <= q["knowledge_boundary"]
    ):
        return
    subjects = record["body"]["subjects"]
    owners = {"quantity_composition_bundle_sha256": "COMPOSITION_BUNDLE", "account_bundle_sha256": "ACCOUNT_BUNDLE",
              "regime_bundle_sha256": "REGIME_BUNDLE", "risk_basis_bundle_sha256": "RISK_BASIS_BUNDLE"}
    for field, kind in owners.items():
        bundle = native.bundles[kind]
        if subjects[field] is not None and bundle is not None:
            _same(subjects[field], _digest(bundle), "Governing original subject")
    if subjects["measure_target_sha256"] is not None and q["measure_target"] is not None:
        _same(subjects["measure_target_sha256"], _digest(q["measure_target"]), "Governing measure subject")
    if native.function is not None:
        charges = {row["charge_id"]: row for row in native.function["charges"]}
        for row in record["body"]["charge_recognition"]:
            if row["charge_id"] not in charges:
                raise ValueError("Governing declaration references nonexistent charge.")
            _same(row["charge_content_sha256"], _digest(charges[row["charge_id"]]), "Governing charge content")


def _financial_proof(value, proof, at, end, path):
    if any(value[key] != "COMPLETE" for key in ("source_universe_completeness", "actor_completeness")) or (
        value["state_at"] != at or value["source_information_cutoff"] != at or
        value["economic_from"] != at or value["economic_until"] != end
    ):
        proof.unknown("FINANCIAL_COVERAGE_UNRESOLVED", path)
    providers = {a["actor_id"] for a in value["actors"] if a["role"] == "PROVIDER"}
    actors = {a["actor_id"] for a in value["actors"]}
    covered = {a for source in value["source_roster"] for a in source["actor_ids"]}
    if not providers or not value["source_roster"] or actors != covered or not any(
        s["role"] == "PROVIDER" and providers & set(s["actor_ids"]) for s in value["source_roster"]
    ) or any(not s["actor_ids"] for s in value["source_roster"]):
        proof.unknown("FINANCIAL_COVERAGE_UNRESOLVED", path)
    reports = {r["inventory_id"]: r for r in value["reports"]}
    for source in value["source_roster"]:
        if source["inventory_id"] not in reports:
            proof.unknown("FINANCIAL_REPORT_MISSING", path + "/reports/" + source["inventory_id"])
    for i, report in enumerate(value["reports"]):
        rp = path + "/reports/" + str(i)
        if any(report[key] != "COMPLETE" for key in ("inventory_completeness", "revision_completeness")) or any(
            report[key] != expected for key, expected in (("state_at", at), ("source_information_cutoff", at),
                                                         ("economic_from", at), ("economic_until", end))
        ):
            proof.unknown("FINANCIAL_COVERAGE_UNRESOLVED", rp)
        if report["source_available_at"] is None:
            proof.unknown("SOURCE_AVAILABILITY_UNKNOWN", rp + "/source_available_at")
        for name, category in report["categories"].items():
            if category["status"] == "PRESENT":
                proof.unknown("ADDITIONAL_FINANCIAL_EFFECT_PRESENT", rp + "/categories/" + name)
            elif category["status"] == "UNKNOWN":
                proof.unknown("FINANCIAL_COVERAGE_UNRESOLVED", rp + "/categories/" + name)


def _accounting(record, q, native, proof, topic_refs):
    body = record["body"]
    path = _E + "/records/" + str(q["projection_evidence"]["records"].index(record)) + "/body"
    at, end = q["knowledge_boundary"], q["scenario"]["settlement_before"]
    if q["measure_target"] is not None:
        assignment = native.resolve(q["measure_target"]["assignment"])
        package = native.resolve(q["measure_target"]["package"])
        # Known accounting applicability expiry is distinct from a candidate's
        # entry expiry or a governance approval's authorization interval.
        for period in (assignment["enrollment_period"], assignment["phase_period"], package["effective_period"]):
            if period["end_status"] == "KNOWN" and _time(period["effective_until"]) < end:
                proof.unknown("HORIZON_INTERPRETATION_CHANGE", "/request/measure_target")
    for field, value in body["subjects"].items():
        if value is None:
            proof.unknown("MEASURE_BINDING_UNRESOLVED", path + "/subjects/" + field)
    baseline = body["baseline_binding"]
    if baseline["state_at"] != at or baseline["source_information_cutoff"] != at:
        proof.unknown("CURRENT_BASELINE_UNESTABLISHED", path + "/baseline_binding")
    if baseline["relationship"] != "DIRECT_NATIVE_BALANCE":
        proof.unknown("MEASURE_MODEL_UNSUPPORTED" if baseline["relationship"] == "OTHER" else "MEASURE_BINDING_UNRESOLVED",
                      path + "/baseline_binding/relationship")
    if body["price_loss_recognition"]["recognition"] != "EXACT_ONCE_AFTER_BASELINE":
        proof.unknown("PRICE_RECOGNITION_UNRESOLVED", path + "/price_loss_recognition")
    components = (("MEASURE_DEFINITION_AND_BASELINE", "baseline_binding"),
                  ("PRICE_LOSS_RECOGNITION", "price_loss_recognition"),
                  ("COST_COVERAGE_AND_ROUNDING", "cost_coverage_and_rounding"),
                  ("FINANCIAL_SOURCE_COVERAGE", "financial_coverage"),
                  ("SCENARIO_AND_SETTLEMENT_SEMANTICS", "scenario_compatibility"))
    for target, field in components:
        refs, _ = proof.tree(body[field], path + "/" + field)
        topic_refs[target] += refs
    rows = {row["charge_id"]: row for row in body["charge_recognition"]}
    if native.function is not None:
        for charge in native.function["charges"]:
            row = rows.get(charge["charge_id"])
            target = dict(kind="CHARGE_RECOGNITION", charge_id=charge["charge_id"], charge_content_sha256=_digest(charge))
            required, _ = proof.mapped([native.reference("RISK_CHARGE", dict(charge_id=charge["charge_id"]))])
            if row is None:
                proof.unknown("CHARGE_RECOGNITION_MISSING", path + "/charge_recognition/" + charge["charge_id"])
            else:
                rp = path + "/charge_recognition/" + str(body["charge_recognition"].index(row))
                refs, _ = proof.tree(row, rp)
                required += refs
                if row["recognition"] != "EXACT_ONCE_AFTER_BASELINE":
                    proof.unknown("CHARGE_ALREADY_REFLECTED" if row["recognition"] == "ALREADY_REFLECTED" else
                                  "CHARGE_RECOGNITION_UNRESOLVED", rp + "/recognition")
                if row["aggregation"] != "EXACT_NATIVE_AGGREGATE":
                    proof.unknown("CHARGE_AGGREGATION_UNRESOLVED", rp + "/aggregation")
                topic_refs["COST_COVERAGE_AND_ROUNDING"] += refs
            proof.receipt(target, _union(required))
            topic_refs["COST_COVERAGE_AND_ROUNDING"] += required
    costs = body["cost_coverage_and_rounding"]
    if costs["completeness"] != "COMPLETE":
        proof.unknown("COST_COVERAGE_UNRESOLVED", path + "/cost_coverage_and_rounding/completeness")
    if costs["rounding"] != "EXACT_NATIVE_EXPRESSION_ON_C":
        proof.unknown("ROUNDING_SEMANTICS_UNRESOLVED", path + "/cost_coverage_and_rounding/rounding")
    rb = native.bundles["RISK_BASIS_BUNDLE"]
    active = [] if rb is None else [row for row in rb["assessment"]["reconstruction_evidence"]["scenario_evidence"] if
        _time(row["effective_from"]) <= at and (row["effective_until"] is None or at < _time(row["effective_until"]))]
    terms = active[0]["terms"] if active else None
    financing_na = terms is not None and terms["cost_coverage"]["financing"] == "NOT_APPLICABLE"
    if costs["financing"] not in ("EXACT_NATIVE_SCENARIO_THROUGH_DEADLINE", "NOT_APPLICABLE") or (
        costs["financing"] == "NOT_APPLICABLE" and not financing_na
    ):
        proof.unknown("FINANCING_HORIZON_UNRESOLVED", path + "/cost_coverage_and_rounding/financing")
    if terms is None or terms["cost_scope"] != "WHOLE_ENTRY_TO_TERMINAL_STOP" or any(
        state not in ("INCLUDED", "NOT_APPLICABLE") for state in terms["cost_coverage"].values()
    ):
        proof.unknown("COST_COVERAGE_UNRESOLVED", path + "/cost_coverage_and_rounding")
    if q["measure_target"] is not None and terms is not None:
        treatments = native.resolve(q["measure_target"]["measure"])["cost_treatment"]
        groups = dict(commissions=("opening_commission", "closing_commission"), financing=("financing",), other_charges=("other_charges",))
        if any(treatments[key] == "NOT_APPLICABLE" and any(terms["cost_coverage"][category] != "NOT_APPLICABLE"
                                                         for category in categories) for key, categories in groups.items()):
            proof.unknown("COST_COVERAGE_UNRESOLVED", path + "/cost_coverage_and_rounding")
    _financial_proof(body["financial_coverage"], proof, at, end, path + "/financial_coverage")
    scenario = body["scenario_compatibility"]
    if scenario["settlement_before"] != end or scenario["economic_from"] > at or scenario["economic_until"] < end or (
        scenario["source_information_cutoff"] != at or scenario["accounting_continuity"] != "SUPPORTED" or
        scenario["settlement_meaning"] != "SUPPORTED"
    ):
        proof.unknown("SCENARIO_CONTINUITY_UNRESOLVED", path + "/scenario_compatibility")


def _evaluate(request, contexts):
    _canonical(request)
    for context in contexts:
        _canonical(context)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope quantity_composition measure_target scenario projection_evidence")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    _same(q["assessment_economic_time"], at, "Current T/K")
    _scope(q["scope"])
    _keys(q["scenario"], "endpoint settlement_before")
    _enum(q["scenario"]["endpoint"], (ENDPOINT,))
    end = q["scenario"]["settlement_before"] = _time(q["scenario"]["settlement_before"])
    if end <= at:
        raise ValueError("Settlement deadline must exceed T.")
    pair, owner = q["quantity_composition"], None
    if pair is None:
        if any(context is not None for context in contexts):
            raise ValueError("Orphaned contexts for absent composition owner.")
    else:
        _keys(pair, "assessment request")
        if type(pair["assessment"]) is not dict or type(pair["request"]) is not dict:
            raise ValueError("Composition pair requires JSON objects.")
        owner = validate_current_entry_quantity_constraint_composition(pair["assessment"], pair["request"],
            trusted_planning_context=contexts[0], trusted_quantity_context=contexts[1],
            trusted_feasibility_context=contexts[2], trusted_position_effect_context=contexts[3],
            trusted_position_limit_context=contexts[4])
        _same(q["scope"], owner["scope"], "Composition scope")
        for key in ("assessment_economic_time", "knowledge_boundary"):
            _same(at, _time(owner[key]), "Composition boundary")
    fingerprints = {key: None if owner is None else owner["reconstruction_evidence"][key] for key in _CONTEXT_KEYS}
    native = _Native(pair)
    native.target(q["measure_target"])
    if q["measure_target"] is not None:
        measure = native.resolve(q["measure_target"]["measure"])
        _same(measure["currency"], q["scope"]["account"]["currency"], "Measure denomination")
        if native.function is not None:
            _same(measure["currency"], native.function["pnl_currency"], "Risk denomination")
    catalog, mappings = _evidence(q["projection_evidence"], native, q["scope"], at)
    chain, incomplete, competing, backwards = ([], False, False, False) if q["projection_evidence"] is None else _history(q["projection_evidence"])
    candidates = [r for r in chain if r["effective_from"] <= at]
    candidate = candidates[-1] if candidates and not incomplete and not competing and not backwards else None
    _governing_pins(candidate, q, native)
    context = _context(deepcopy(contexts[5]), q, native, catalog, fingerprints)
    # All supplied independent structures have been checked before semantic decisions.
    proof = _Proof(q, context, catalog, mappings, native)
    if owner is None:
        proof.unknown("OWNER_MISSING", "/request/quantity_composition")
    else:
        if owner["outcome"] != "ESTABLISHED":
            proof.unknown("OWNER_UNKNOWN" if owner["outcome"] == "UNKNOWN" else "OWNER_NOT_SUITABLE",
                          "/request/quantity_composition/assessment/outcome")
        if owner["unresolved_findings"]:
            proof.unknown("NATIVE_UNRESOLVED", "/request/quantity_composition/assessment/unresolved_findings")
    if q["measure_target"] is None:
        proof.unknown("MEASURE_TARGET_MISSING", "/request/measure_target")
    else:
        if native.selected is None:
            proof.unknown("MEASURE_BINDING_UNRESOLVED", "/request/measure_target")
        measure = native.resolve(q["measure_target"]["measure"])
        if measure["kind"] != "BALANCE" or "SUBTRACT_SEPARATELY" in measure["cost_treatment"].values():
            proof.unknown("MEASURE_MODEL_UNSUPPORTED", "/request/measure_target/measure")
    ab = native.bundles["ACCOUNT_BUNDLE"]
    observation = None if ab is None else ab["snapshot"]["observation"]
    if owner is not None and (observation is None or observation["account_measures"]["balance"] is None or
        _time(observation["timing"]["effective_at"]) != at or observation["timing"]["source_available_at"] is None
    ):
        proof.unknown("CURRENT_BASELINE_UNESTABLISHED", "/request/quantity_composition")
    if native.function is not None:
        for charge in native.function["charges"]:
            if charge["basis"] != "SOURCE_SCHEDULE":
                proof.unknown("EXACT_DEBIT_UNESTABLISHED", "/request/quantity_composition/" + charge["charge_id"])
    if context is None:
        proof.unknown("ADMISSION_MISSING", _C)
    elif not proof.current:
        proof.unknown("ADMISSION_NOT_CURRENT", _C)
    evidence = q["projection_evidence"]
    topics = {name: [] for name in ADMISSION_TARGETS}
    resolved = None
    if evidence is None:
        proof.unknown("PROJECTION_EVIDENCE_MISSING", _E)
    else:
        for value, path in ((evidence, _E), (evidence["coverage"], _E + "/coverage")):
            if value["source_available_at"] is None:
                proof.unknown("SOURCE_AVAILABILITY_UNKNOWN", path + "/source_available_at")
        coverage = evidence["coverage"]
        coverage_good = (coverage["declaration_completeness"] == "COMPLETE" and
                         coverage["source_information_cutoff"] == at and coverage["economic_from"] <= at and
                         coverage["economic_until"] >= end)
        if not coverage_good:
            proof.unknown("INTERPRETATION_COVERAGE_UNRESOLVED", _E + "/coverage")
        if incomplete:
            proof.unknown("REVISION_HISTORY_INCOMPLETE", _E + "/coverage")
        if competing:
            proof.unknown("COMPETING_INTERPRETATIONS", _E + "/records")
        if backwards:
            proof.unknown("REVISION_ORDER_UNSUPPORTED", _E + "/records")
        revision_refs, revision_support = proof.tree(coverage, _E + "/coverage")
        for i, row in enumerate(evidence["records"]):
            # Historical bodies are preserved, but do not supply today's facts.
            refs = row["evidence_refs"]
            revision_support = proof.originals(refs, _E + "/records/" + str(i) + "/evidence_refs") and revision_support
            revision_refs += refs
            if row["source_available_at"] is None:
                revision_support = proof.unknown("SOURCE_AVAILABILITY_UNKNOWN", _E + "/records/" + str(i))
        topics["INTERPRETATION_REVISION_COVERAGE"] = _union(revision_refs)
        revision_admitted = proof.receipt(dict(kind="INTERPRETATION_REVISION_COVERAGE"), _union(revision_refs))
        if candidate is not None and candidate["kind"] == "DECLARE" and (
            candidate["effective_until"] is None or at < candidate["effective_until"]
        ):
            # Explicit source-declared incompatibilities remain diagnostics even
            # without admission. They do not resolve a current interpretation or
            # establish a positive fact; resolved_record still requires admission.
            _accounting(candidate, q, native, proof, topics)
        if not incomplete and not competing and not backwards and coverage_good and revision_support and revision_admitted and (
            evidence["source_available_at"] is not None and coverage["source_available_at"] is not None
        ):
            if candidate is None:
                proof.unknown("NO_CURRENT_INTERPRETATION", _E + "/records")
            else:
                resolved = dict(record_id=candidate["record_id"], kind=candidate["kind"], content_sha256=_digest(candidate))
                if candidate["kind"] == "WITHDRAW":
                    proof.unknown("INTERPRETATION_WITHDRAWN", _E + "/records")
                elif candidate["effective_until"] is not None and candidate["effective_until"] <= at:
                    proof.unknown("INTERPRETATION_EXPIRED", _E + "/records")
                else:
                    if any(at < r["effective_from"] < end for r in chain) or (
                        candidate["effective_until"] is not None and candidate["effective_until"] < end
                    ):
                        proof.unknown("HORIZON_INTERPRETATION_CHANGE", _E + "/records")
        scope_refs, measure_refs, risk_refs = native.required(q["measure_target"], at)
        for name, references in (("SCOPE_AND_NATIVE_BINDINGS", scope_refs),
                                  ("MEASURE_DEFINITION_AND_BASELINE", measure_refs),
                                  ("PRICE_LOSS_RECOGNITION", risk_refs)):
            refs, _ = proof.mapped(references)
            topics[name] += refs
        # Native risk originals support both exact costs and settlement coordinate meaning.
        topics["COST_COVERAGE_AND_ROUNDING"] += topics["PRICE_LOSS_RECOGNITION"]
        topics["SCENARIO_AND_SETTLEMENT_SEMANTICS"] += topics["PRICE_LOSS_RECOGNITION"]
        for name in ADMISSION_TARGETS:
            if name != "INTERPRETATION_REVISION_COVERAGE":
                proof.receipt(dict(kind=name), _union(topics[name]))
        if proof.current:
            measure_receipt = next((r for r in context["admissions"] if r["target"] == dict(kind="MEASURE_DEFINITION_AND_BASELINE")), None)
            if measure_receipt is None or measure_receipt["status"] != "ADMITTED":
                proof.unknown("DENOMINATION_UNRESOLVED", "/request/measure_target")
    findings = sorted({_canonical(row): row for row in proof.findings}.values(), key=lambda row: (row["reason_code"], row["subject"]))
    support = deepcopy(owner["composed_domain"]) if owner is not None and owner["outcome"] == "ESTABLISHED" else None
    basis = None
    if not findings:
        if resolved is None or observation is None or native.function is None or support is None or q["measure_target"] is None:
            raise ValueError("Incomplete projection proof without an unresolved finding.")
        basis = dict(kind=DESCRIPTOR_KIND, baseline_amount=_decimal(observation["account_measures"]["balance"]),
                     currency=q["scope"]["account"]["currency"], risk_function=deepcopy(native.function),
                     support=deepcopy(support), measure_target=deepcopy(q["measure_target"]), scenario=deepcopy(q["scenario"]))
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
                  scope=q["scope"], measure_target=q["measure_target"], scenario=q["scenario"],
                  outcome="ESTABLISHED" if basis is not None else "UNKNOWN",
                  reason_codes=sorted({r["reason_code"] for r in findings}) if findings else ["CONDITIONAL_BALANCE_PROJECTION_ESTABLISHED"],
                  owner_reference=None if owner is None else dict(assessment_identity=owner["assessment_identity"],
                      owner_bundle_sha256=_digest(pair), outcome=owner["outcome"]),
                  resolved_record=resolved, supported_domain=support, projection_basis=basis,
                  native_diagnostics=None if owner is None else {key: deepcopy(owner[key]) for key in
                      ("negative_proofs", "native_negative_proof_references", "unresolved_findings")},
                  unresolved_findings=findings, conditions=list(CONDITIONS), limitations=list(LIMITATIONS),
                  reconstruction_evidence=dict(request=q, native_context_fingerprints=fingerprints,
                      projection_evidence_sha256=None if evidence is None else _digest(evidence),
                      trusted_financial_projection_context_sha256=None if context is None else _digest(context)),
                  downstream_obligations=list(DOWNSTREAM_OBLIGATIONS), source_authentication=SOURCE_AUTHENTICATION,
                  authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_current_entry_provider_measure_projection_basis(
    request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None,
) -> dict:
    """Reconstruct a conditional descriptor; the host independently controls admission."""
    try:
        return _detached(_evaluate(request, (trusted_planning_context, trusted_quantity_context,
            trusted_feasibility_context, trusted_position_effect_context, trusted_position_limit_context,
            trusted_financial_projection_context)))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed current provider-measure projection basis request.") from exc


def validate_current_entry_provider_measure_projection_basis(
    assessment: dict, request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None,
) -> dict:
    """Reevaluate every result field; a caller-recomputed digest grants no authority."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be a JSON object.")
        _canonical(assessment)
        expected = evaluate_current_entry_provider_measure_projection_basis(request,
            trusted_planning_context=trusted_planning_context, trusted_quantity_context=trusted_quantity_context,
            trusted_feasibility_context=trusted_feasibility_context, trusted_position_effect_context=trusted_position_effect_context,
            trusted_position_limit_context=trusted_position_limit_context,
            trusted_financial_projection_context=trusted_financial_projection_context)
        _same(assessment, expected, "Complete projection assessment")
        return _detached(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized provider-measure projection assessment.") from exc
