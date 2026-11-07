"""Independently admitted as-of daily reset floor; no trading authority.

Public owners reconstruct native facts. The host independently admits original
source semantics and authenticity. FROZEN_AWAITING_PAYOUT remains a separate veto.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import re
import struct
from zoneinfo import ZoneInfo

from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8_owner
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account_owner
from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regime_owner

CONTRACT = "trading.as_of_daily_reset_loss_floor_state.v1"
RULE_VERSION = "as_of_daily_reset_loss_floor_state_v1"
ADMISSION_CONTRACT = "trading.as_of_daily_reset_loss_floor_state.admission.v1"
ADMISSION_RULE_VERSION = "as_of_daily_reset_loss_floor_state_admission_v1"
IDENTITY_PREFIX = "as_of_daily_reset_loss_floor_state_"
TEMPORAL_SCOPE = "AS_OF_T_USING_EVIDENCE_BY_K"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
LIMITATIONS = ("AS_OF_ONLY", "SOURCE_REVISION_COVERAGE_THROUGH_S", "NO_EQUITY_COMPARISON",
               "NO_CONTINUOUS_COMPLIANCE", "NO_CURRENT_ELIGIBILITY", "NO_MARGIN_OR_EXECUTION_APPROVAL",
               "NO_PAYOUT_AUTHORIZATION", "SOURCE_AUTHENTICATION_EXTERNAL", "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL")
TARGETS = ("ACCOUNT_LIFECYCLE", "DAILY_RULE", "RESET_CALENDAR", "RESET_BALANCE", "INITIAL_CAPITAL",
           "SOURCE_COMPLETENESS", "SOURCE_REVISIONS")
ROLES = ("enrollment", "daily_rule", "calendar_definition", "tzif", "reset_balance", "initial_capital", "coverage")
TARGET_ROLES = (("enrollment",), ("daily_rule", "enrollment"), ("calendar_definition", "tzif", "daily_rule"),
                ("reset_balance", "daily_rule"), ("initial_capital", "daily_rule"), ("coverage",), ("coverage",))
EXCLUSIONS = ("deposits_or_credits", "rewards_or_withdrawals", "capital_change", "phase_change",
              "reset_or_migration", "anchor_correction", "rule_or_calendar_change", "unresolved_activity")
NAMESPACE_FIELDS = ("source_id", "source_contract", "source_contract_version")
SOURCE_FIELDS = (*NAMESPACE_FIELDS, "source_snapshot_id")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")
REASON_CODES = ("DAILY_FLOOR_ESTABLISHED", "C8_MISSING", "C8_NOT_ESTABLISHED", "FIRST_PARTIAL_DAY_UNSUPPORTED",
    "DAILY_REGIME_MISSING", "NATIVE_REGIME_UNRESOLVED", "RULE_SELECTOR_MISSING", "RULE_NOT_SELECTED",
    "RULE_MODEL_UNSUPPORTED", "RULE_COVERAGE_INCOMPLETE", "CALENDAR_MISSING", "ORIGINAL_ROLE_MISSING",
    "CALENDAR_BOUNDARY_UNRESOLVED", "RULE_CALENDAR_UNSUPPORTED", "RULE_SESSION_UNRESOLVED",
    "RESET_SEMANTICS_UNRESOLVED", "COVERAGE_MISSING", "SOURCE_COVERAGE_INCOMPLETE", "COVERAGE_INCOMPLETE",
    "REVISION_UNSUPPORTED", "EXCLUDED_ACTIVITY_UNRESOLVED", "ORIGINAL_AVAILABILITY_UNKNOWN",
    "SOURCE_CUTOFF_UNRESOLVED", "NATIVE_AVAILABILITY_UNKNOWN", "NATIVE_MAPPING_INCOMPLETE", "ORIGINAL_UNUSED",
    "SUPPORT_INCOMPLETE", "ADMISSION_MISSING", "ADMISSION_NOT_CURRENT", "RECEIPT_MISSING",
    "RECEIPT_UNRESOLVED", "RECEIPT_MEMBERSHIP_INCOMPLETE")


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
    captures, versions = set(), {}
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
        if hashlib.sha256(raw).hexdigest() != _hash(row["content_sha256"]):
            raise ValueError()
        content = raw, _text(row["media_type"])
        _, version, capture = _document_keys(row)
        if capture in captures or (version in versions and versions[version] != content):
            raise ValueError()
        captures.add(capture)
        versions[version] = content
        observed = _time(row["observed_at"])
        publication = row["source_available_at"]
        if observed > boundary or (publication is not None and _time(publication) > observed):
            raise ValueError()
    return {row["evidence_id"]: row for row in rows}


def _reference(ref, originals):
    _keys(ref, "evidence_id original_sha256")
    identifier = _id(ref["evidence_id"])
    if identifier not in originals or _hash(ref["original_sha256"]) != _digest(originals[identifier]):
        raise ValueError()
    return originals[identifier]


def _declarations(q, originals):
    _keys(q["roles"], ROLES)
    account_ns = _ns(q["scope"]["account"]["namespace"])
    provider_ns = _ns(q["scope"]["provider_namespace"])
    for role in ROLES:
        ref = q["roles"][role]
        if ref is None:
            continue
        original = _reference(ref, originals)
        ns = _ns(original["source"])
        allowed = {account_ns, provider_ns}
        if role in ("daily_rule", "calendar_definition"):
            allowed = {provider_ns}
        elif role == "reset_balance":
            allowed = {account_ns}
        if role not in ("tzif", "coverage") and ns not in allowed:
            raise ValueError()
    meaning = q["reset_meaning"]
    if meaning is not None:
        _keys(meaning, "mode")
        _enum(meaning["mode"], ("AFTER_ALL_C8_EVENTS_AT_M", "NO_C8_EVENTS_AT_M", "BEFORE_SOME_EVENTS_AT_M", "UNKNOWN"))
    coverage = q["coverage"]
    if coverage is not None:
        _keys(coverage, "economic_from economic_through sources source_inventory reset_activity lifecycle rule_calendar source_revisions excluded_activity")
        _time(coverage["economic_from"])
        _time(coverage["economic_through"])
        _ordered(coverage["sources"], _namespace)
        for field in ("source_inventory", "reset_activity", "lifecycle", "rule_calendar"):
            _enum(coverage[field], ("COMPLETE", "UNKNOWN"))
        _enum(coverage["source_revisions"], ("NONE", "PRESENT", "UNKNOWN"))
        _keys(coverage["excluded_activity"], EXCLUSIONS)
        for value in coverage["excluded_activity"].values():
            _enum(value, ("ABSENT", "PRESENT", "UNKNOWN"))
        report = q["roles"]["coverage"]
        if report is not None and coverage["sources"] and _ns(originals[report["evidence_id"]]["source"]) not in {
                _ns(ns) for ns in coverage["sources"]}:
            raise ValueError()


def _calendar(q, originals):
    calendar = q["calendar"]
    if calendar is not None:
        _keys(calendar, "timezone_id tzdb_release tzif_sha256 local_date local_reset_time utc_start utc_end")
        _text(calendar["timezone_id"])
        _text(calendar["tzdb_release"])
        _hash(calendar["tzif_sha256"])
        date = calendar["local_date"]
        if type(date) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date) is None:
            raise ValueError()
        local = datetime.fromisoformat(date)
        following = local + timedelta(days=1)
        _enum(calendar["local_reset_time"], ("00:00:00",))
        start, end = _time(calendar["utc_start"]), _time(calendar["utc_end"])
        if start != q["reset_boundary"] or not start <= q["economic_time"] < end:
            raise ValueError()
    ref = q["roles"]["tzif"]
    if ref is None:
        return None
    raw = _bytes(originals[ref["evidence_id"]]["content"])
    zone = ZoneInfo.from_file(BytesIO(raw), key=None if calendar is None else calendar["timezone_id"])
    if calendar is None:
        return None
    if hashlib.sha256(raw).hexdigest() != calendar["tzif_sha256"]:
        raise ValueError()
    boundaries = []
    for naive in (local, following):
        candidates = set()
        for fold in (0, 1):
            utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == naive:
                candidates.add(utc.isoformat(timespec="microseconds").replace("+00:00", "Z"))
        if len(candidates) != 1:
            return False
        boundaries.append(next(iter(candidates)))
    _same(boundaries, [calendar["utc_start"], calendar["utc_end"]])
    return True


def _native_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _replay(q, c8_context, originals):
    c8_request = c8_result = account = None
    if q["c8"] is None:
        if c8_context is not None:
            raise ValueError()
    else:
        _keys(q["c8"], "request_json result_json")
        c8_request = _decode(q["c8"]["request_json"])
        c8_result = c8_owner.validate_current_intraday_trailing_loss_threshold_state(
            _decode(q["c8"]["result_json"]), c8_request, trusted_context=c8_context)
        _same(c8_request["scope"], q["scope"])
        _same(c8_request["economic_time"], q["reset_boundary"])
        _same(c8_request["knowledge_boundary"], q["knowledge_boundary"])
        bundle = c8_request["account_snapshot"]
        if bundle is not None:
            account = account_owner.validate_causal_financial_account_state_snapshot(
                _decode(bundle["result_json"]), _decode(bundle["input_json"]))
            ref = q["roles"]["reset_balance"]
            if ref is not None:
                original = originals[ref["evidence_id"]]
                _same(original["source"], account["observation"]["source"])
                publication = account["observation"]["timing"]["source_available_at"]
                if publication is not None and original["source_available_at"] is not None:
                    _same(original["source_available_at"], publication)
        history = c8_request["history"]
        if (q["reset_meaning"] is not None and q["reset_meaning"]["mode"] == "NO_C8_EVENTS_AT_M" and history is not None
                and any(row["occurred_at"] == q["reset_boundary"] for row in history["events"])):
            raise ValueError()
    native = result = selected_rule = None
    dependency = q["daily_regime"]
    if dependency is not None:
        _keys(dependency, "input_json result_json selector")
        native = _decode(dependency["input_json"])
        result = regime_owner.validate_causal_account_rule_regime_assessment(_decode(dependency["result_json"]), native)
        if result["economic_timestamp"] != q["economic_time"] or not q["economic_time"] <= result["requested_knowledge_boundary"] <= q["source_information_cutoff"]:
            raise ValueError()
        account_scope = q["scope"]["account"]
        if _ns(result["account"]) != _ns(account_scope["namespace"]) or any(result["account"][f] != account_scope[f] for f in ("account_id", "environment")):
            raise ValueError()
        selected = result["selected_regime"]
        if selected is not None:
            for row in (selected["assignment"], selected["package"]):
                for field in SCOPE_FIELDS:
                    if row[field] is not None and row[field] != q["scope"][field]:
                        raise ValueError()
        selector = dependency["selector"]
        if selector is not None:
            _keys(selector, "assignment_id package_index rule_index native_rule_sha256")
            _text(selector["assignment_id"])
            if not any(a["assignment_id"] == selector["assignment_id"] for a in native["manifest"]["assignments"]):
                raise ValueError()
            package = native["manifest"]["packages"][_nat(selector["package_index"])]
            rule = package["rules"][_nat(selector["rule_index"])]
            if _hash(selector["native_rule_sha256"]) != _digest(rule):
                raise ValueError()
            if selected is not None and selector["assignment_id"] == selected["assignment"]["assignment_id"] and all(
                    package[f] == selected["package"][f] for f in ("package_id", "package_revision")):
                selected_rule = next(r for r in selected["package"]["rules"] if r["rule_id"] == rule["rule_id"])
                body = selected_rule["body"]
                if body.get("measure") is not None and body["measure"]["currency"] != q["scope"]["account"]["currency"]:
                    raise ValueError()
                if body["type"] == "DAILY_RESET_FLOOR" and q["calendar"] is not None:
                    _same(body["reset_schedule"]["source_timezone"], q["calendar"]["timezone_id"])
                    _same(body["reset_schedule"]["source_local_reset_time"], q["calendar"]["local_reset_time"])
    return c8_request, c8_result, account, native, result, selected_rule


def _evidence(q, c8_request, originals, native):
    families, versions, captures, members = {}, {}, {}, []
    for owner, rows in (("C8", [] if c8_request is None else c8_request["originals"]), ("C10", q["originals"])):
        for row in rows:
            family, version, capture = _document_keys(row)
            content = _bytes(row["content"]), row["media_type"]
            if version in versions and versions[version] != content:
                raise ValueError()
            envelope = {k: v for k, v in row.items() if k != "evidence_id"}
            if capture in captures:
                _same(envelope, captures[capture])
            captures[capture] = envelope
            versions[version] = content
            families.setdefault(family, set()).add(row["document"]["document_revision"])
            members.append(dict(owner=owner, evidence_id=row["evidence_id"], original_sha256=_digest(row)))
    def mapping_key(row):
        _keys(row, "native_evidence_id original")
        identifier = _text(row["native_evidence_id"])
        original = _reference(row["original"], originals)
        if native is None:
            raise ValueError()
        evidence = next(e for e in native["manifest"]["evidence"] if e["evidence_id"] == identifier)
        _same(evidence["source"], original["source"])
        _same(evidence["document_reference"], original["document"]["document_id"])
        _same(evidence["document_revision"], original["document"]["document_revision"])
        if evidence["document_sha256"] is not None:
            _same(evidence["document_sha256"], original["content_sha256"])
        publication = evidence["timing"]["source_available_at"]
        if publication is not None and original["source_available_at"] is not None:
            _same(_native_time(publication), original["source_available_at"])
        return identifier
    _ordered(q["native_mappings"], mapping_key)
    return families, members


def _support(q, originals):
    def key(row):
        _keys(row, "target citations")
        target = _enum(row["target"], TARGETS)
        def citation_key(citation):
            _keys(citation, "evidence_id start end")
            identifier = _id(citation["evidence_id"])
            start, end = _nat(citation["start"]), _nat(citation["end"], 1)
            if identifier not in originals or not start < end <= len(_bytes(originals[identifier]["content"])):
                raise ValueError()
            return identifier, start, end
        _ordered(row["citations"], citation_key)
        return TARGETS.index(target)
    _ordered(q["support_assertions"], key)
    return {row["target"]: row for row in q["support_assertions"]}


def _observations(q, c8_request, account, native, c8_context):
    rows = q["originals"] + ([] if c8_request is None else c8_request["originals"])
    values = [row["observed_at"] for row in rows]
    if account is not None:
        values.append(account["observation"]["timing"]["observed_at"])
    regimes = [] if native is None else [native]
    if c8_request is not None and c8_request["provider_regime"] is not None:
        regimes.append(_decode(c8_request["provider_regime"]["input_json"]))
    for regime in regimes:
        values.append(_native_time(regime["manifest"]["timing"]["observed_at"]))
        values.extend(_native_time(row["timing"]["observed_at"]) for row in regime["manifest"]["evidence"])
        values.extend(_native_time(row["observed_at"]) for row in regime["approvals"])
    if c8_context is not None:
        values.append(c8_context["available_at"])
    return values


def _context(context, q, c8_context, observations, assertions, members):
    if context is None:
        return {}
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 c8_context_sha256 admitted_at available_at effective_from effective_until receipts")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _id(context["admission_id"])
    _namespace(context["authority_namespace"])
    for field in ("authority_id", "mandate_id"):
        _text(context[field])
    _nat(context["mandate_revision"], 1)
    request_hash, c8_hash = _digest(q), None if c8_context is None else _digest(c8_context)
    _same(context["request_sha256"], request_hash)
    _same(context["c8_context_sha256"], c8_hash)
    for field in ("admitted_at", "available_at", "effective_from"):
        _time(context[field])
    if context["effective_until"] is not None and _time(context["effective_until"]) <= context["effective_from"]:
        raise ValueError()
    if context["admitted_at"] > context["available_at"] or any(o > context["admitted_at"] for o in observations):
        raise ValueError()
    expected = {(r["owner"], r["evidence_id"]): r for r in members}
    def key(receipt):
        _keys(receipt, "target request_sha256 c8_context_sha256 assertion_sha256 originals decision")
        target = _enum(receipt["target"], TARGETS)
        _same(receipt["request_sha256"], request_hash)
        _same(receipt["c8_context_sha256"], c8_hash)
        _same(receipt["assertion_sha256"], None if target not in assertions else _digest(assertions[target]))
        def member_key(row):
            _keys(row, "owner evidence_id original_sha256")
            owner = _enum(row["owner"], ("C8", "C10"))
            identifier = _id(row["evidence_id"])
            _hash(row["original_sha256"])
            if (owner, identifier) not in expected:
                raise ValueError()
            _same(row, expected[(owner, identifier)])
            return (0 if owner == "C8" else 1), identifier
        _ordered(receipt["originals"], member_key)
        _enum(receipt["decision"], ("ADMITTED", "UNRESOLVED"))
        return TARGETS.index(target)
    _ordered(context["receipts"], key)
    return {row["target"]: (i, row) for i, row in enumerate(context["receipts"])}


def _period(period):
    return (None if period["effective_from"] is None else _native_time(period["effective_from"]),
            None if period["effective_until"] is None else _native_time(period["effective_until"]), period["end_status"])


def _covers(period, start, end):
    lo, hi, status = _period(period)
    return lo is not None and lo <= start and (status == "OPEN_ENDED" or (status == "KNOWN" and hi >= end))


def _may_overlap(periods, start, end):
    bounds = [_period(p) for p in periods]
    lowers = [p[0] for p in bounds if p[0] is not None]
    uppers = [p[1] for p in bounds if p[2] == "KNOWN"]
    lo, hi = max(lowers) if lowers else None, min(uppers) if uppers else None
    return not ((hi is not None and hi <= start) or (lo is not None and lo >= end) or
                (lo is not None and hi is not None and lo >= hi))


def _union_covers(periods, start, end):
    intervals = []
    for period in periods:
        if not _may_overlap([period], start, end):
            continue
        lo, hi, status = _period(period)
        if lo is None or status == "UNKNOWN":
            return False
        intervals.append((max(lo, start), min(hi, end) if hi is not None else end))
    frontier = start
    for lo, hi in sorted(intervals):
        if lo > frontier:
            break
        frontier = max(frontier, hi)
    return frontier >= end


def _session(q, c8_request, native, result):
    selected = result["selected_regime"]
    old = _decode(c8_request["provider_regime"]["result_json"])["selected_regime"]
    if _canonical(old["package"]) != _canonical(selected["package"]):
        return False
    start, end = q["reset_boundary"], q["calendar"]["utc_end"]
    assignment, package = selected["assignment"], selected["package"]
    if not all(_covers(p, start, end) for p in (native["manifest"]["coverage"]["economic_period"],
            assignment["enrollment_period"], assignment["phase_period"], package["effective_period"])):
        return False
    package_key = package["package_id"], package["package_revision"]
    packages = {(p["package_id"], p["package_revision"]): p for p in native["manifest"]["packages"]}
    bindings = []
    for original in native["manifest"]["assignments"]:
        if original["assignment_id"] != assignment["assignment_id"]:
            if _may_overlap([original["enrollment_period"], original["phase_period"]], start, end):
                return False
            continue
        for binding in original["package_bindings"]:
            key = binding["package"]["package_id"], binding["package"]["package_revision"]
            if key == package_key:
                bindings.append(binding["effective_period"])
            elif _may_overlap([binding["effective_period"], packages[key]["effective_period"]], start, end):
                return False
    approvals = []
    for row in native["approvals"]:
        if row["assignment_id"] != assignment["assignment_id"] or (row["package"]["package_id"], row["package"]["package_revision"]) != package_key:
            continue
        if _may_overlap([row["effective_period"]], start, end):
            if row["decision"] == "REJECTED":
                return False
            approvals.append(row["effective_period"])
    return _union_covers(bindings, start, end) and _union_covers(approvals, start, end)


def _model(rule):
    body = rule["body"]
    if rule["representation"] != "SUPPORTED" or rule["instrument_scope"] != {"kind": "ALL_ACCOUNT_INSTRUMENTS"} or body["type"] != "DAILY_RESET_FLOOR":
        return False
    deduction, measure = body["deduction"], body["measure"]
    return (body["reset_anchor"] == "BALANCE" and deduction["kind"] == "INITIAL_REFERENCE_FRACTION" and
            deduction["reference"] == "INITIAL_BALANCE" and _money(deduction["fraction"]) == Fraction(3, 100) and
            measure["kind"] == "EQUITY" and measure["cost_treatment"]["commissions"] == "IN_MEASURE" and
            measure["cost_treatment"]["financing"] == "IN_MEASURE" and
            measure["cost_treatment"]["other_charges"] in ("IN_MEASURE", "NOT_APPLICABLE") and
            body["compliant_when"] == "GREATER_THAN_OR_EQUAL" and
            body["adjustment_policy"] == "NO_UNREPRESENTED_CAPITAL_OR_PHASE_ADJUSTMENTS")


def _source_namespaces(q, c8_request, native):
    expected = {_ns(q["scope"]["account"]["namespace"]), _ns(q["scope"]["provider_namespace"])}
    rows = list(q["originals"])
    if c8_request is not None:
        rows.extend(c8_request["originals"])
        if c8_request["history"] is not None:
            expected.update(_ns(s["namespace"]) for s in c8_request["history"]["sources"])
    expected.update(_ns(r["source"]) for r in rows)
    if native is not None:
        expected.add(_ns(native["manifest"]["source"]))
        expected.update(_ns(e["source"]) for e in native["manifest"]["evidence"])
    return expected


def _cutoff(q, c8_request, account, originals):
    """Apply the repaired capture-wide report/operational precedence."""
    reports, operations = set(), set()
    def use(index, identifier, collection):
        collection.add(_document_keys(index[identifier])[2])
    def citations(index, rows, collection):
        for citation in rows:
            use(index, citation["evidence_id"], collection)
    for role in ROLES:
        ref = q["roles"][role]
        if ref is not None:
            use(originals, ref["evidence_id"], reports if role == "coverage" else operations)
    for row in q["native_mappings"]:
        use(originals, row["original"]["evidence_id"], operations)
    for row in q["support_assertions"]:
        if row["target"] in TARGETS[:5]:
            citations(originals, row["citations"], operations)
    imported = {} if c8_request is None else {r["evidence_id"]: r for r in c8_request["originals"]}
    if c8_request is not None and c8_request["history"] is not None:
        history = c8_request["history"]
        coverage = history["coverage"]
        if coverage is not None:
            use(imported, coverage["report"]["evidence_id"], reports)
            if coverage["source_information_cutoff"] is not None and coverage["source_information_cutoff"] > q["source_information_cutoff"]:
                return False
        for field in ("initial_capital", "rule"):
            if history[field] is not None:
                citations(imported, history[field]["citations"], operations)
        for row in (*history["events"], *history["revisions"]):
            citations(imported, row["citations"], operations)
        report_targets = ("COMPLETE_HISTORY", "SOURCE_REVISIONS_AVAILABILITY", "EXCLUDED_ACTIVITY_ABSENCE")
        for row in c8_request["support_assertions"]:
            if row["target"]["kind"] not in report_targets:
                citations(imported, row["citations"], operations)
    cutoff = q["source_information_cutoff"]
    for row in (*imported.values(), *originals.values()):
        publication = row["source_available_at"]
        if publication is None:
            continue
        capture = _document_keys(row)[2]
        if capture in reports and publication < cutoff:
            return False
        if (capture in operations or capture not in reports) and publication > cutoff:
            return False
    publication = None if account is None else account["observation"]["timing"]["source_available_at"]
    return publication is None or publication <= cutoff


def _finding(reason, pointer, root="REQUEST"):
    return dict(reason_code=reason, subject=dict(root=root, pointer=pointer))


def _unknown(q, context, replay, originals, families, calendar, assertions, receipts, members):
    c8_request, c8_result, account, native, result, rule = replay
    if q["c8"] is None:
        return _finding("C8_MISSING", "/c8")
    if c8_result["outcome"] != "ESTABLISHED":
        return _finding("C8_NOT_ESTABLISHED", "/c8")
    if c8_result["state"]["inception"] == q["reset_boundary"]:
        return _finding("FIRST_PARTIAL_DAY_UNSUPPORTED", "/reset_boundary")
    if native is None:
        return _finding("DAILY_REGIME_MISSING", "/daily_regime")
    if result["outcome"] != "UNIQUE_APPLICABLE_APPROVED_REGIME":
        return _finding("NATIVE_REGIME_UNRESOLVED", "/daily_regime")
    if q["daily_regime"]["selector"] is None:
        return _finding("RULE_SELECTOR_MISSING", "/daily_regime/selector")
    if rule is None:
        return _finding("RULE_NOT_SELECTED", "/daily_regime/selector")
    if not _model(rule):
        return _finding("RULE_MODEL_UNSUPPORTED", "/daily_regime/selector")
    selected = result["selected_regime"]
    if (selected["package"]["coverage"]["completeness"] != "COMPLETE" or
            selected["package"]["interpretation"]["limitations"] or any(e["limitations"] for e in selected["evidence"])):
        return _finding("RULE_COVERAGE_INCOMPLETE", "/daily_regime")
    if q["calendar"] is None:
        return _finding("CALENDAR_MISSING", "/calendar")
    for role in ROLES:
        if q["roles"][role] is None:
            return _finding("ORIGINAL_ROLE_MISSING", "/roles/" + role)
    if calendar is False:
        return _finding("CALENDAR_BOUNDARY_UNRESOLVED", "/calendar")
    start, end = q["reset_boundary"], q["calendar"]["utc_end"]
    schedule = rule["body"]["reset_schedule"]
    if (schedule["schedule_period"] != dict(effective_from=start, effective_until=end, end_status="KNOWN") or
            schedule["boundaries"] != [start, end]):
        return _finding("RULE_CALENDAR_UNSUPPORTED", "/daily_regime/selector")
    if not _session(q, c8_request, native, result):
        return _finding("RULE_SESSION_UNRESOLVED", "/daily_regime")
    if q["reset_meaning"] is None or q["reset_meaning"]["mode"] not in ("AFTER_ALL_C8_EVENTS_AT_M", "NO_C8_EVENTS_AT_M"):
        return _finding("RESET_SEMANTICS_UNRESOLVED", "/reset_meaning")
    coverage = q["coverage"]
    if coverage is None:
        return _finding("COVERAGE_MISSING", "/coverage")
    if (not coverage["sources"] or coverage["source_inventory"] != "COMPLETE" or
            not _source_namespaces(q, c8_request, native) <= {_ns(ns) for ns in coverage["sources"]}):
        return _finding("SOURCE_COVERAGE_INCOMPLETE", "/coverage/sources")
    if (coverage["economic_from"] != c8_result["state"]["inception"] or coverage["economic_through"] != q["economic_time"] or
            any(coverage[f] != "COMPLETE" for f in ("reset_activity", "lifecycle", "rule_calendar"))):
        return _finding("COVERAGE_INCOMPLETE", "/coverage")
    if any(len(revisions) > 1 for revisions in families.values()):
        return _finding("REVISION_UNSUPPORTED", "/originals")
    if coverage["source_revisions"] != "NONE":
        return _finding("REVISION_UNSUPPORTED", "/coverage/source_revisions")
    for field in EXCLUSIONS:
        if coverage["excluded_activity"][field] != "ABSENT":
            return _finding("EXCLUDED_ACTIVITY_UNRESOLVED", "/coverage/excluded_activity/" + field)
    for i, row in enumerate(q["originals"]):
        if row["source_available_at"] is None:
            return _finding("ORIGINAL_AVAILABILITY_UNKNOWN", f"/originals/{i}/source_available_at")
    if not _cutoff(q, c8_request, account, originals):
        return _finding("SOURCE_CUTOFF_UNRESOLVED", "/source_information_cutoff")
    manifest = native["manifest"]
    if manifest["timing"]["source_available_at"] is None or any(e["timing"]["source_available_at"] is None for e in manifest["evidence"]):
        return _finding("NATIVE_AVAILABILITY_UNKNOWN", "/daily_regime")
    if {e["evidence_id"] for e in manifest["evidence"]} != {m["native_evidence_id"] for m in q["native_mappings"]}:
        return _finding("NATIVE_MAPPING_INCOMPLETE", "/native_mappings")
    used = {ref["evidence_id"] for ref in q["roles"].values() if ref is not None}
    used.update(row["original"]["evidence_id"] for row in q["native_mappings"])
    for i, row in enumerate(q["originals"]):
        if row["evidence_id"] not in used:
            return _finding("ORIGINAL_UNUSED", f"/originals/{i}")
    for target, roles in zip(TARGETS, TARGET_ROLES):
        assertion = assertions.get(target)
        cited = set() if assertion is None else {c["evidence_id"] for c in assertion["citations"]}
        required = {q["roles"][role]["evidence_id"] for role in roles}
        if target == "DAILY_RULE":
            required.update(m["original"]["evidence_id"] for m in q["native_mappings"])
        if not required <= cited:
            return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
        if target == "RESET_CALENDAR":
            identifier = q["roles"]["tzif"]["evidence_id"]
            length = len(_bytes(originals[identifier]["content"]))
            if not any(c == dict(evidence_id=identifier, start=0, end=length) for c in assertion["citations"]):
                return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
    if context is None:
        return _finding("ADMISSION_MISSING", "", "TRUSTED_CONTEXT")
    k = q["knowledge_boundary"]
    for field, failed in (("available_at", context["available_at"] > k), ("effective_from", context["effective_from"] > k),
                          ("effective_until", context["effective_until"] is not None and context["effective_until"] <= k)):
        if failed:
            return _finding("ADMISSION_NOT_CURRENT", "/" + field, "TRUSTED_CONTEXT")
    if any(target not in receipts for target in TARGETS):
        return _finding("RECEIPT_MISSING", "/receipts", "TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["decision"] == "UNRESOLVED":
            return _finding("RECEIPT_UNRESOLVED", f"/receipts/{i}", "TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["originals"] != members:
            return _finding("RECEIPT_MEMBERSHIP_INCOMPLETE", f"/receipts/{i}/originals", "TRUSTED_CONTEXT")
    return None


def _evaluate(request, trusted_c8_context, trusted_context):
    for value in (request, trusted_c8_context, trusted_context):
        _canonical(value)
    q, c8_context, context = deepcopy(request), deepcopy(trusted_c8_context), deepcopy(trusted_context)
    _keys(q, "contract rule_version economic_time knowledge_boundary reset_boundary source_information_cutoff scope c8 daily_regime calendar reset_meaning coverage originals roles native_mappings support_assertions")
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    if not _time(q["reset_boundary"]) <= _time(q["economic_time"]) <= _time(q["source_information_cutoff"]) <= _time(q["knowledge_boundary"]):
        raise ValueError()
    _scope(q["scope"])
    originals = _originals(q["originals"], q["knowledge_boundary"])
    _declarations(q, originals)
    replay = _replay(q, c8_context, originals)
    c8_request, c8_result, account, native, native_result, rule = replay
    families, members = _evidence(q, c8_request, originals, native)
    calendar = _calendar(q, originals)
    assertions = _support(q, originals)
    receipts = _context(context, q, c8_context, _observations(q, c8_request, account, native, c8_context), assertions, members)
    finding = _unknown(q, context, replay, originals, families, calendar, assertions, receipts, members)
    state = None
    if finding is None:
        initial, balance = _money(c8_result["state"]["initial_capital"]), _money(c8_result["state"]["final_balance"])
        allowance = initial * Fraction(3, 100)
        state = dict(inception=c8_result["state"]["inception"], as_of=q["economic_time"], reset_boundary=q["reset_boundary"],
                     next_reset_boundary=q["calendar"]["utc_end"], local_date=q["calendar"]["local_date"], timezone_id=q["calendar"]["timezone_id"],
                     currency=q["scope"]["account"]["currency"], initial_capital=_decimal(initial), reset_balance=_decimal(balance),
                     daily_loss_allowance=_decimal(allowance), daily_loss_floor=_decimal(balance - allowance))
    references = dict(c8=None if c8_result is None else dict(assessment_identity=c8_result["assessment_identity"], outcome=c8_result["outcome"], bundle_sha256=_digest(q["c8"])),
                      reset_snapshot=None if account is None else dict(snapshot_id=account["snapshot_id"], bundle_sha256=_digest(c8_request["account_snapshot"])),
                      daily_regime=None if native_result is None else dict(assessment_id=native_result["assessment_id"], outcome=native_result["outcome"], bundle_sha256=_digest(q["daily_regime"])))
    bindings = [dict(target=t, assertion_sha256=None if t not in assertions else _digest(assertions[t]),
                     receipt_sha256=None if t not in receipts else _digest(receipts[t][1]), originals=deepcopy(members)) for t in TARGETS]
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, temporal_scope=TEMPORAL_SCOPE, economic_time=q["economic_time"],
                  knowledge_boundary=q["knowledge_boundary"], reset_boundary=q["reset_boundary"], source_information_cutoff=q["source_information_cutoff"],
                  scope=q["scope"], outcome="ESTABLISHED" if finding is None else "UNKNOWN", reason_codes=["DAILY_FLOOR_ESTABLISHED" if finding is None else finding["reason_code"]],
                  findings=[] if finding is None else [finding], state=state, native_references=references, required_targets=list(TARGETS), admission_bindings=bindings,
                  reconstruction_evidence=dict(request=q, request_sha256=_digest(q), c8_context_sha256=None if c8_context is None else _digest(c8_context),
                                               trusted_context_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, limitations=list(LIMITATIONS), authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_as_of_daily_reset_loss_floor_state(request: dict, *, trusted_c8_context=None, trusted_context=None) -> dict:
    """Establish an admitted historical floor, with no equity/compliance permission.

    Independent host admission supplies semantic truth and source authenticity.
    FROZEN_AWAITING_PAYOUT remains a separate mandatory trading veto.
    """
    try:
        return deepcopy(_evaluate(request, trusted_c8_context, trusted_context))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError,
            UnicodeError, binascii.Error, StopIteration, EOFError, struct.error, AssertionError) as exc:
        raise ValueError("INVALID_DAILY_RESET_FLOOR_INPUT") from exc


def validate_as_of_daily_reset_loss_floor_state(result: dict, request: dict, *, trusted_c8_context=None, trusted_context=None) -> dict:
    """Replay every owner and reconstruct all fields, preserving exact JSON types."""
    expected = evaluate_as_of_daily_reset_loss_floor_state(request, trusted_c8_context=trusted_c8_context, trusted_context=trusted_context)
    try:
        if type(result) is not dict or _canonical(result) != _canonical(expected):
            raise ValueError()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("DAILY_RESET_FLOOR_RESULT_MISMATCH") from exc
    return deepcopy(expected)
