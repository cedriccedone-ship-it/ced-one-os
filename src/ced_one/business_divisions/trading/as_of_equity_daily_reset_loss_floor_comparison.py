"""Independently admitted historical equity versus the public C10 daily floor.

Source authenticity and semantic admission belong to the independently trusted
host. No live eligibility or trading authority is granted. The separate
FROZEN_AWAITING_PAYOUT veto remains mandatory.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re

from ced_one.business_divisions.trading import as_of_daily_reset_loss_floor_state as c10_owner
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account_owner

CONTRACT = "trading.as_of_equity_daily_reset_loss_floor_comparison.v1"
RULE_VERSION = "as_of_equity_daily_reset_loss_floor_comparison_v1"
ADMISSION_CONTRACT = "trading.as_of_equity_daily_reset_loss_floor_comparison.admission.v1"
ADMISSION_RULE_VERSION = "as_of_equity_daily_reset_loss_floor_comparison_admission_v1"
IDENTITY_PREFIX = "as_of_equity_daily_reset_loss_floor_comparison_"
TEMPORAL_SCOPE = "AS_OF_T_USING_EVIDENCE_BY_K"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
LIMITATIONS = ("AS_OF_ONLY", "SOURCE_REVIEW_CUTOFFS_NOT_LATEST_AT_K", "NO_CONTINUOUS_COMPLIANCE",
               "NO_EARLIER_BREACH_ABSENCE", "NO_CURRENT_ELIGIBILITY", "NO_MARGIN_OR_EXECUTION_APPROVAL",
               "NO_PAYOUT_AUTHORIZATION", "SOURCE_AUTHENTICATION_EXTERNAL", "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL")
TARGETS = ("EQUITY_IDENTITY_BINDING", "EQUITY_AGGREGATE_MEANING", "EQUITY_ACCOUNT_WIDE_COMPLETENESS",
           "EQUITY_COST_COMPONENTS", "EQUITY_SOURCE_VERSION_VALIDITY")
OWNERS = ("C8", "C10", "C11")
ROLES = ("aggregate", "definition", "coverage")
COMPONENTS = ("balance", "floating_pnl", "commissions", "financing", "other_costs")
NAMESPACE_FIELDS = ("source_id", "source_contract", "source_contract_version")
SOURCE_FIELDS = (*NAMESPACE_FIELDS, "source_snapshot_id")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")
REASON_CODES = (
    "COMPARISON_ESTABLISHED", "C10_MISSING", "C8_CONTEXT_MISSING", "C10_CONTEXT_MISSING", "C10_NOT_ESTABLISHED",
    "EQUITY_SNAPSHOT_MISSING", "NATIVE_EQUITY_MISSING", "EQUITY_ASSERTION_MISSING", "EQUITY_AMOUNT_UNDECLARED",
    "AGGREGATE_ORIGINAL_MISSING", "DEFINITION_ORIGINAL_MISSING", "COVERAGE_ORIGINAL_MISSING",
    "ORIGINAL_ROLE_COVERAGE_INCOMPLETE", "DOCUMENT_REVISION_UNKNOWN", "DOCUMENT_VERSION_CONFLICT",
    "NATIVE_AVAILABILITY_UNKNOWN", "ORIGINAL_AVAILABILITY_UNKNOWN", "EQUITY_SOURCE_CUTOFF_INSUFFICIENT",
    "SOURCE_REVISIONS_UNRESOLVED", "DEFINITION_NOT_APPLICABLE", "ACCOUNT_WIDE_UNRESOLVED",
    "RULE_MEASURE_EQUIVALENCE_UNRESOLVED", "COMPONENT_TREATMENT_UNSUPPORTED", "COMPONENT_INTEGRITY_UNRESOLVED",
    "SUPPORT_INCOMPLETE", "EQUITY_ADMISSION_MISSING", "EQUITY_ADMISSION_NOT_CURRENT", "RECEIPT_MISSING",
    "RECEIPT_UNRESOLVED", "RECEIPT_MEMBERSHIP_INCOMPLETE",
)


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split() if isinstance(fields, str) else fields):
        raise ValueError()


def _text(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError()
    value.encode("utf-8")
    return value


def _id(value):
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", _text(value)) is None:
        raise ValueError()
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError()
    return value


def _nat(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError()
    return value


def _time(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value) is None:
        raise ValueError()
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError()
    return value


def _integer_text(value):
    """Render arbitrary integers without changing Python's process-wide limits."""
    if value < 0:
        return "-" + _integer_text(-value)
    parts = []
    while value >= 10 ** 1000:
        value, part = divmod(value, 10 ** 1000)
        parts.append(str(part).zfill(1000))
    return str(value) + "".join(reversed(parts))


def _canonical(value):
    # Equivalent to the frozen json.dumps options, including for large Nats.
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise ValueError()
        for key in value:
            key.encode("utf-8")
        return "{" + ",".join(json.dumps(k, ensure_ascii=True) + ":" + _canonical(value[k]) for k in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical(x) for x in value) + "]"
    if type(value) is str:
        value.encode("utf-8")
        return json.dumps(value, ensure_ascii=True)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return _integer_text(value)
    raise ValueError()


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bytes(value):
    if type(value) is not str:
        raise ValueError()
    raw = base64.b64decode(value, validate=True)
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError()
    return raw


def _parse_integer(value):
    sign = -1 if value.startswith("-") else 1
    value = value.lstrip("-")
    total = 0
    for start in range(0, len(value), 1000):
        part = value[start:start + 1000]
        total = total * 10 ** len(part) + int(part)
    return sign * total


def _money(value):
    if type(value) is not str or re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?", value) is None or value == "-0":
        raise ValueError()
    whole, _, part = value.partition(".")
    return Fraction(_parse_integer(whole + part), 10 ** len(part))


def _decimal(value):
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError()
    scale = max(twos, fives)
    number = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    sign = "-" if number < 0 else ""
    digits = _integer_text(abs(number)).zfill(scale + 1)
    if scale:
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return sign + digits


def _ordered(rows, key):
    if type(rows) is not list:
        raise ValueError()
    keys = [key(row) for row in rows]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ValueError()
    return rows


def _namespace(value):
    _keys(value, NAMESPACE_FIELDS)
    return tuple(_text(value[f]) for f in NAMESPACE_FIELDS)


def _source(value):
    _keys(value, SOURCE_FIELDS)
    return tuple(_text(value[f]) for f in SOURCE_FIELDS)


def _ns(value):
    return tuple(value[f] for f in NAMESPACE_FIELDS)


def _currency(value):
    if type(value) is not str or re.fullmatch(r"[A-Z]{3}", value) is None:
        raise ValueError()


def _scope(scope):
    _keys(scope, ("account", "provider_namespace", *SCOPE_FIELDS, "lifecycle_id"))
    _namespace(scope["provider_namespace"])
    for field in SCOPE_FIELDS:
        _text(scope[field])
    _id(scope["lifecycle_id"])
    account = scope["account"]
    _keys(account, "namespace account_id environment currency")
    _namespace(account["namespace"])
    _text(account["account_id"])
    _enum(account["environment"], ("DEMO", "LIVE"))
    _currency(account["currency"])


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _decode(value):
    decoded = json.loads(_bytes(value).decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_int=_parse_integer, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    _canonical(decoded)
    if type(decoded) is not dict:
        raise ValueError()
    return decoded


def _same(left, right):
    if _canonical(left) != _canonical(right):
        raise ValueError()


def _document_keys(row):
    document = row["document"]
    family = (_ns(document["namespace"]), document["document_id"])
    version = (*family, document["document_revision"])
    capture = (tuple(row["source"][field] for field in SOURCE_FIELDS), version)
    return family, version, capture


def _originals(rows, boundary):
    def key(row):
        _keys(row, "evidence_id source document media_type content content_sha256 source_available_at observed_at")
        return _id(row["evidence_id"])
    _ordered(rows, key)
    if len(rows) > 3:
        raise ValueError()
    captures = set()
    for row in rows:
        _source(row["source"])
        document = row["document"]
        _keys(document, "namespace document_id document_revision")
        if _namespace(document["namespace"]) != _ns(row["source"]):
            raise ValueError()
        _text(document["document_id"])
        if document["document_revision"] is not None:
            _text(document["document_revision"])
        raw = _bytes(row["content"])
        if not raw or hashlib.sha256(raw).hexdigest() != _hash(row["content_sha256"]):
            raise ValueError()
        _text(row["media_type"])
        capture = _document_keys(row)[2]
        if capture in captures:
            raise ValueError()
        captures.add(capture)
        observed, publication = _time(row["observed_at"]), row["source_available_at"]
        if observed > boundary or (publication is not None and _time(publication) > observed):
            raise ValueError()
    return {row["evidence_id"]: row for row in rows}


def _replay(q, c8_context, c10_context):
    original = floor = q8 = account = None
    if q["c10"] is None:
        if c8_context is not None or c10_context is not None:
            raise ValueError()
    else:
        _keys(q["c10"], "request_json result_json")
        original = _decode(q["c10"]["request_json"])
        floor = c10_owner.validate_as_of_daily_reset_loss_floor_state(
            _decode(q["c10"]["result_json"]), original,
            trusted_c8_context=c8_context, trusted_context=c10_context)
        for field in ("scope", "economic_time", "knowledge_boundary"):
            _same(original[field], q[field])
        if original["c8"] is not None:
            q8 = _decode(original["c8"]["request_json"])
    bundle = q["account_snapshot"]
    if bundle is not None:
        _keys(bundle, "input_json result_json")
        account = account_owner.validate_causal_financial_account_state_snapshot(
            _decode(bundle["result_json"]), _decode(bundle["input_json"]))
        observation = account["observation"]
        _same(account["requested_evaluation_timestamp"], q["knowledge_boundary"])
        _same(observation["timing"]["effective_at"], q["economic_time"])
        if _ns(observation["source"]) != _ns(q["scope"]["account"]["namespace"]):
            raise ValueError()
        for field in ("account_id", "environment", "currency"):
            _same(observation["account"][field], q["scope"]["account"][field])
    return original, floor, q8, account


def _inventory(q, q10, q8):
    members, originals, locations, families, captures, versions = [], {}, {}, {}, {}, {}
    rows_by_owner = (("C8", [] if q8 is None else q8["originals"]),
                     ("C10", [] if q10 is None else q10["originals"]), ("C11", q["originals"]))
    roots = dict(C8="C8_REQUEST", C10="C10_REQUEST", C11="REQUEST")
    for owner, rows in rows_by_owner:
        for i, row in enumerate(rows):
            key = owner, row["evidence_id"]
            family, version, capture = _document_keys(row)
            content = _bytes(row["content"]), row["media_type"]
            # An unknown revision is never promoted to a known version identity.
            if row["document"]["document_revision"] is not None:
                if version in versions and versions[version] != content:
                    raise ValueError()
                versions[version] = content
            envelope = {k: v for k, v in row.items() if k != "evidence_id"}
            if capture in captures:
                _same(envelope, captures[capture])
            captures[capture] = envelope
            families.setdefault(family, set()).add(row["document"]["document_revision"])
            originals[key] = row
            locations[key] = roots[owner], f"/originals/{i}"
            members.append(dict(owner=owner, evidence_id=row["evidence_id"], original_sha256=_digest(row)))
    return members, originals, locations, families


def _daily_measure(q, q10, floor, members):
    if floor is None or floor["outcome"] != "ESTABLISHED":
        return None
    # C10 already selected and validated this exact original rule. No selection
    # from the native normalized arrays and no re-evaluation of the floor.
    native = _decode(q10["daily_regime"]["input_json"])
    selector = q10["daily_regime"]["selector"]
    package = native["manifest"]["packages"][selector["package_index"]]
    rule = package["rules"][selector["rule_index"]]
    measure = rule["body"]["measure"]
    index = {(m["owner"], m["evidence_id"]): m for m in members}
    mappings = {m["native_evidence_id"]: m["original"] for m in q10["native_mappings"]}
    definitions = [dict(index=i, native_evidence_id=clause["evidence_id"], clause_locator=clause["clause_locator"],
                        original=deepcopy(index[("C10", mappings[clause["evidence_id"]]["evidence_id"])]))
                   for i, clause in enumerate(measure["definition_refs"])]
    return dict(c10_assessment_identity=floor["assessment_identity"], c10_bundle_sha256=_digest(q["c10"]),
                daily_regime_bundle_sha256=_digest(q10["daily_regime"]), assignment_id=selector["assignment_id"],
                package_index=selector["package_index"], package_id=package["package_id"], package_revision=package["package_revision"],
                rule_index=selector["rule_index"], rule_id=rule["rule_id"], native_rule_sha256=selector["native_rule_sha256"],
                measure_sha256=_digest(measure), kind=measure["kind"], currency=measure["currency"],
                instrument_scope=rule["instrument_scope"]["kind"], cost_treatment=deepcopy(measure["cost_treatment"]),
                rule_original=deepcopy(index[("C10", q10["roles"]["daily_rule"]["evidence_id"])]), definition_bindings=definitions)


def _equity(q, originals, account, snapshot_reference, daily_measure):
    equity = q["equity"]
    if equity is None:
        return
    _keys(equity, "scope economic_time knowledge_boundary snapshot_reference daily_measure_sha256 amount currency roles "
                  "definition_period coverage measure_equivalence components component_integrity")
    _scope(equity["scope"])
    _same(equity["scope"], q["scope"])
    for field in ("economic_time", "knowledge_boundary"):
        _time(equity[field])
        _same(equity[field], q[field])
    _same(equity["snapshot_reference"], snapshot_reference)
    _same(equity["daily_measure_sha256"], None if daily_measure is None else _digest(daily_measure))
    if equity["amount"] is not None:
        _money(equity["amount"])
    _currency(equity["currency"])
    _same(equity["currency"], q["scope"]["account"]["currency"])
    if account is not None:
        native_amount = account["observation"]["account_measures"]["equity"]
        if native_amount is not None and equity["amount"] is not None:
            _same(equity["amount"], native_amount)
    _keys(equity["roles"], ROLES)
    for role in ROLES:
        ref = equity["roles"][role]
        if ref is None:
            continue
        _keys(ref, "evidence_id original_sha256")
        identifier = _id(ref["evidence_id"])
        if identifier not in originals or _hash(ref["original_sha256"]) != _digest(originals[identifier]):
            raise ValueError()
        original = originals[identifier]
        allowed = {_ns(q["scope"]["account"]["namespace"])}
        if role == "definition":
            allowed.add(_ns(q["scope"]["provider_namespace"]))
        if _ns(original["source"]) not in allowed:
            raise ValueError()
        if role == "aggregate" and account is not None:
            observation = account["observation"]
            _same(original["source"], observation["source"])
            publication = observation["timing"]["source_available_at"]
            if publication is not None and original["source_available_at"] is not None:
                _same(original["source_available_at"], publication)
    period = equity["definition_period"]
    _keys(period, "effective_from effective_until end_status")
    status = _enum(period["end_status"], ("KNOWN", "OPEN_ENDED", "UNKNOWN"))
    start, end = period["effective_from"], period["effective_until"]
    if start is not None:
        _time(start)
    if status == "KNOWN":
        _time(end)
        if start is not None and start >= end:
            raise ValueError()
    elif end is not None:
        raise ValueError()
    coverage = equity["coverage"]
    _keys(coverage, "economic_time source_information_cutoff account_wide source_revisions known_later_corrections")
    for field in ("economic_time", "source_information_cutoff"):
        _time(coverage[field])
        _same(coverage[field], q[field])
    _enum(coverage["account_wide"], ("COMPLETE", "UNKNOWN"))
    for field in ("source_revisions", "known_later_corrections"):
        _enum(coverage[field], ("NONE", "PRESENT", "UNKNOWN"))
    ref = equity["roles"]["coverage"]
    if ref is not None:
        report = originals[ref["evidence_id"]]
        cutoff = q["source_information_cutoff"]
        if report["observed_at"] < cutoff or (report["source_available_at"] is not None and report["source_available_at"] < cutoff):
            raise ValueError()
    _enum(equity["measure_equivalence"], ("EXACT", "DIFFERENT", "UNKNOWN"))
    _keys(equity["components"], COMPONENTS)
    for field in COMPONENTS:
        allowed = ("INCLUDED_ONCE", "OMITTED", "UNKNOWN")
        if field not in ("balance", "floating_pnl"):
            allowed = (*allowed, "NOT_APPLICABLE")
        _enum(equity["components"][field], allowed)
    _enum(equity["component_integrity"], ("COMPLETE_EXACTLY_ONCE", "OMISSION", "DUPLICATION", "UNKNOWN"))


def _support(q, originals):
    expected = None if q["equity"] is None else _digest(q["equity"])
    def key(row):
        _keys(row, "target equity_sha256 citations")
        target = _enum(row["target"], TARGETS)
        _same(row["equity_sha256"], expected)
        def citation_key(citation):
            _keys(citation, "owner evidence_id start end")
            owner = _enum(citation["owner"], OWNERS)
            identifier = _id(citation["evidence_id"])
            start, end = _nat(citation["start"]), _nat(citation["end"], 1)
            if (owner, identifier) not in originals or not start < end <= len(_bytes(originals[(owner, identifier)]["content"])):
                raise ValueError()
            return OWNERS.index(owner), identifier, start, end
        _ordered(row["citations"], citation_key)
        return TARGETS.index(target)
    _ordered(q["support_assertions"], key)
    return {row["target"]: row for row in q["support_assertions"]}


def _native_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _observations(q, q10, q8, account, c8_context, c10_context):
    observations = [row["observed_at"] for row in q["originals"]]
    if account is not None:
        observations.append(account["observation"]["timing"]["observed_at"])
    regimes = []
    if q10 is not None:
        observations.extend(row["observed_at"] for row in q10["originals"])
        if q10["daily_regime"] is not None:
            regimes.append(_decode(q10["daily_regime"]["input_json"]))
    if q8 is not None:
        observations.extend(row["observed_at"] for row in q8["originals"])
        if q8["account_snapshot"] is not None:
            reset = _decode(q8["account_snapshot"]["result_json"])
            observations.append(reset["observation"]["timing"]["observed_at"])
        if q8["provider_regime"] is not None:
            regimes.append(_decode(q8["provider_regime"]["input_json"]))
    for regime in regimes:
        observations.append(_native_time(regime["manifest"]["timing"]["observed_at"]))
        observations.extend(_native_time(row["timing"]["observed_at"]) for row in regime["manifest"]["evidence"])
        observations.extend(_native_time(row["observed_at"]) for row in regime["approvals"])
    for context in (c8_context, c10_context):
        if context is not None:
            observations.append(context["available_at"])
    return observations


def _context(context, q, c8_context, c10_context, observations, assertions, members):
    if context is None:
        return {}
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 "
                   "c8_context_sha256 c10_context_sha256 admitted_at available_at effective_from effective_until receipts")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _id(context["admission_id"])
    _namespace(context["authority_namespace"])
    for field in ("authority_id", "mandate_id"):
        _text(context[field])
    _nat(context["mandate_revision"], 1)
    request_hash = _digest(q)
    c8_hash = None if c8_context is None else _digest(c8_context)
    c10_hash = None if c10_context is None else _digest(c10_context)
    for field, expected in (("request_sha256", request_hash), ("c8_context_sha256", c8_hash), ("c10_context_sha256", c10_hash)):
        _same(context[field], expected)
    for field in ("admitted_at", "available_at", "effective_from"):
        _time(context[field])
    if context["effective_until"] is not None:
        _time(context["effective_until"])
    if context["admitted_at"] > context["available_at"] or any(o > context["admitted_at"] for o in observations):
        raise ValueError()
    expected_members = {(r["owner"], r["evidence_id"]): r for r in members}
    def key(receipt):
        _keys(receipt, "target request_sha256 c8_context_sha256 c10_context_sha256 assertion_sha256 originals decision")
        target = _enum(receipt["target"], TARGETS)
        for field in ("request_sha256", "c8_context_sha256", "c10_context_sha256"):
            _same(receipt[field], context[field])
        _same(receipt["assertion_sha256"], None if target not in assertions else _digest(assertions[target]))
        def member_key(row):
            _keys(row, "owner evidence_id original_sha256")
            owner = _enum(row["owner"], OWNERS)
            identifier = _id(row["evidence_id"])
            _hash(row["original_sha256"])
            if (owner, identifier) not in expected_members:
                raise ValueError()
            _same(row, expected_members[(owner, identifier)])
            return OWNERS.index(owner), identifier
        _ordered(receipt["originals"], member_key)
        _enum(receipt["decision"], ("ADMITTED", "UNRESOLVED"))
        return TARGETS.index(target)
    _ordered(context["receipts"], key)
    return {row["target"]: (i, row) for i, row in enumerate(context["receipts"])}


def _required_support(q, q10, measure):
    roles = {role: ("C11", q["equity"]["roles"][role]["evidence_id"]) for role in ROLES}
    a, d, c = (roles[role] for role in ROLES)
    enrollment = ("C10", q10["roles"]["enrollment"]["evidence_id"])
    rule = ("C10", measure["rule_original"]["evidence_id"])
    definitions = {(row["original"]["owner"], row["original"]["evidence_id"]) for row in measure["definition_bindings"]}
    coverage = ("C10", q10["roles"]["coverage"]["evidence_id"])
    return ({a, d, enrollment}, {a, d, rule} | definitions, {a, c}, {d, c, rule} | definitions,
            {a, d, c, rule, coverage} | definitions)


def _finding(reason, pointer, root="REQUEST"):
    return dict(reason_code=reason, subject=dict(root=root, pointer=pointer))


def _unknown(q, c8_context, c10_context, context, replay, inventory, measure, assertions, receipts):
    q10, floor, q8, account = replay
    members, originals, locations, families = inventory
    if q10 is None:
        return _finding("C10_MISSING", "/c10")
    if q8 is not None and c8_context is None:
        return _finding("C8_CONTEXT_MISSING", "", "TRUSTED_C8_CONTEXT")
    if c10_context is None:
        return _finding("C10_CONTEXT_MISSING", "", "TRUSTED_C10_CONTEXT")
    if floor["outcome"] != "ESTABLISHED":
        return _finding("C10_NOT_ESTABLISHED", "/c10")
    if account is None:
        return _finding("EQUITY_SNAPSHOT_MISSING", "/account_snapshot")
    if account["observation"]["account_measures"]["equity"] is None:
        return _finding("NATIVE_EQUITY_MISSING", "/account_snapshot")
    equity = q["equity"]
    if equity is None:
        return _finding("EQUITY_ASSERTION_MISSING", "/equity")
    if equity["amount"] is None:
        return _finding("EQUITY_AMOUNT_UNDECLARED", "/equity/amount")
    for role in ROLES:
        if equity["roles"][role] is None:
            return _finding(role.upper() + "_ORIGINAL_MISSING", "/equity/roles/" + role)
    used = {ref["evidence_id"] for ref in equity["roles"].values()}
    for i, row in enumerate(q["originals"]):
        if row["evidence_id"] not in used:
            return _finding("ORIGINAL_ROLE_COVERAGE_INCOMPLETE", f"/originals/{i}")
    for member in members:
        key = member["owner"], member["evidence_id"]
        if originals[key]["document"]["document_revision"] is None:
            root, pointer = locations[key]
            return _finding("DOCUMENT_REVISION_UNKNOWN", pointer + "/document/document_revision", root)
    for member in members:
        key = member["owner"], member["evidence_id"]
        if len(families[_document_keys(originals[key])[0]]) > 1:
            root, pointer = locations[key]
            return _finding("DOCUMENT_VERSION_CONFLICT", pointer + "/document", root)
    if account["observation"]["timing"]["source_available_at"] is None:
        return _finding("NATIVE_AVAILABILITY_UNKNOWN", "/account_snapshot")
    for i, row in enumerate(q["originals"]):
        if row["source_available_at"] is None:
            return _finding("ORIGINAL_AVAILABILITY_UNKNOWN", f"/originals/{i}/source_available_at")
    if any(originals[("C11", equity["roles"][role]["evidence_id"])]["source_available_at"] > q["source_information_cutoff"]
           for role in ("aggregate", "definition")):
        return _finding("EQUITY_SOURCE_CUTOFF_INSUFFICIENT", "/source_information_cutoff")
    for field in ("source_revisions", "known_later_corrections"):
        if equity["coverage"][field] != "NONE":
            return _finding("SOURCE_REVISIONS_UNRESOLVED", "/equity/coverage/" + field)
    period, t = equity["definition_period"], q["economic_time"]
    if (period["effective_from"] is None or period["effective_from"] > t or period["end_status"] == "UNKNOWN" or
            (period["end_status"] == "KNOWN" and period["effective_until"] <= t)):
        return _finding("DEFINITION_NOT_APPLICABLE", "/equity/definition_period")
    if equity["coverage"]["account_wide"] != "COMPLETE":
        return _finding("ACCOUNT_WIDE_UNRESOLVED", "/equity/coverage/account_wide")
    if equity["measure_equivalence"] != "EXACT":
        return _finding("RULE_MEASURE_EQUIVALENCE_UNRESOLVED", "/equity/measure_equivalence")
    for field in COMPONENTS:
        expected = "INCLUDED_ONCE"
        if field == "other_costs" and measure["cost_treatment"]["other_charges"] == "NOT_APPLICABLE":
            expected = "NOT_APPLICABLE"
        if equity["components"][field] != expected:
            return _finding("COMPONENT_TREATMENT_UNSUPPORTED", "/equity/components/" + field)
    if equity["component_integrity"] != "COMPLETE_EXACTLY_ONCE":
        return _finding("COMPONENT_INTEGRITY_UNRESOLVED", "/equity/component_integrity")
    for target, required in zip(TARGETS, _required_support(q, q10, measure)):
        assertion = assertions.get(target)
        cited = set() if assertion is None else {(c["owner"], c["evidence_id"]) for c in assertion["citations"]}
        if not required <= cited:
            return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
    if context is None:
        return _finding("EQUITY_ADMISSION_MISSING", "", "TRUSTED_CONTEXT")
    k = q["knowledge_boundary"]
    for field, failed in (("available_at", context["available_at"] > k),
                          ("effective_from", context["effective_from"] > min(context["admitted_at"], k)),
                          ("effective_until", context["effective_until"] is not None and
                           context["effective_until"] <= max(context["admitted_at"], k))):
        if failed:
            return _finding("EQUITY_ADMISSION_NOT_CURRENT", "/" + field, "TRUSTED_CONTEXT")
    if any(target not in receipts for target in TARGETS):
        return _finding("RECEIPT_MISSING", "/receipts", "TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["decision"] == "UNRESOLVED":
            return _finding("RECEIPT_UNRESOLVED", f"/receipts/{i}", "TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["originals"] != members:
            return _finding("RECEIPT_MEMBERSHIP_INCOMPLETE", f"/receipts/{i}/originals", "TRUSTED_CONTEXT")
    return None


def _evaluate(request, trusted_c8_context, trusted_c10_context, trusted_context):
    for value in (request, trusted_c8_context, trusted_c10_context, trusted_context):
        _canonical(value)
    q, ctx8, ctx10, context = deepcopy((request, trusted_c8_context, trusted_c10_context, trusted_context))
    _keys(q, "contract rule_version economic_time knowledge_boundary source_information_cutoff scope c10 account_snapshot equity originals support_assertions")
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    if not _time(q["economic_time"]) <= _time(q["source_information_cutoff"]) <= _time(q["knowledge_boundary"]):
        raise ValueError()
    _scope(q["scope"])
    local_originals = _originals(q["originals"], q["knowledge_boundary"])
    replay = _replay(q, ctx8, ctx10)
    q10, floor, q8, account = replay
    inventory = _inventory(q, q10, q8)
    members, originals, _, _ = inventory
    references = dict(c10=None if floor is None else dict(assessment_identity=floor["assessment_identity"], outcome=floor["outcome"], bundle_sha256=_digest(q["c10"])),
                      account_snapshot=None if account is None else dict(snapshot_id=account["snapshot_id"], bundle_sha256=_digest(q["account_snapshot"])))
    measure = _daily_measure(q, q10, floor, members)
    _equity(q, local_originals, account, references["account_snapshot"], measure)
    assertions = _support(q, originals)
    observations = _observations(q, q10, q8, account, ctx8, ctx10)
    receipts = _context(context, q, ctx8, ctx10, observations, assertions, members)
    finding = _unknown(q, ctx8, ctx10, context, replay, inventory, measure, assertions, receipts)
    state = None
    if finding is None:
        equity = _money(account["observation"]["account_measures"]["equity"])
        daily_floor = _money(floor["state"]["daily_loss_floor"])
        difference = equity - daily_floor
        state = dict(as_of=q["economic_time"], reset_boundary=floor["state"]["reset_boundary"],
                     next_reset_boundary=floor["state"]["next_reset_boundary"], currency=q["scope"]["account"]["currency"],
                     equity=_decimal(equity), daily_loss_floor=_decimal(daily_floor), difference=_decimal(difference),
                     relation="BELOW" if difference < 0 else "ABOVE" if difference > 0 else "EQUAL")
    bindings = [dict(target=t, assertion_sha256=None if t not in assertions else _digest(assertions[t]),
                     receipt_sha256=None if t not in receipts else _digest(receipts[t][1]), originals=deepcopy(members)) for t in TARGETS]
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, temporal_scope=TEMPORAL_SCOPE,
                  economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"],
                  source_information_cutoff=q["source_information_cutoff"], scope=q["scope"],
                  outcome="ESTABLISHED" if finding is None else "UNKNOWN", reason_codes=["COMPARISON_ESTABLISHED" if finding is None else finding["reason_code"]],
                  findings=[] if finding is None else [finding], state=state, native_references=references, daily_measure=measure,
                  required_targets=list(TARGETS), admission_bindings=bindings,
                  reconstruction_evidence=dict(request=q, request_sha256=_digest(q),
                      c8_context_sha256=None if ctx8 is None else _digest(ctx8), c10_context_sha256=None if ctx10 is None else _digest(ctx10),
                      trusted_context_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, limitations=list(LIMITATIONS), authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_as_of_equity_daily_reset_loss_floor_comparison(
    request: dict, *, trusted_c8_context=None, trusted_c10_context=None, trusted_context=None,
) -> dict:
    """Establish an admitted AS-OF comparison, without current eligibility.

    The host supplies independent admission and source trust. A point comparison
    cannot clear an earlier breach or the separate FROZEN_AWAITING_PAYOUT veto.
    """
    try:
        return deepcopy(_evaluate(request, trusted_c8_context, trusted_c10_context, trusted_context))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError,
            UnicodeError, binascii.Error, StopIteration) as exc:
        raise ValueError("INVALID_EQUITY_DAILY_FLOOR_INPUT") from exc


def validate_as_of_equity_daily_reset_loss_floor_comparison(
    result: dict, request: dict, *, trusted_c8_context=None, trusted_c10_context=None, trusted_context=None,
) -> dict:
    """Genuinely replay both owners and type-sensitively reconstruct every field."""
    expected = evaluate_as_of_equity_daily_reset_loss_floor_comparison(
        request, trusted_c8_context=trusted_c8_context, trusted_c10_context=trusted_c10_context, trusted_context=trusted_context)
    try:
        if type(result) is not dict or _canonical(result) != _canonical(expected):
            raise ValueError()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("EQUITY_DAILY_FLOOR_RESULT_MISMATCH") from exc
    return deepcopy(expected)
