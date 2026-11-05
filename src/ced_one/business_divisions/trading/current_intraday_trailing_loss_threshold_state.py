"""Independently admitted as-of threshold reconstruction; no trading authority.

The host supplies trusted_context independently of the request/result. Accepting
an issuer string is not authentication. Native replay establishes consistency;
the admitted, target-specific originals establish the bounded source semantics.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re
from typing import Any

from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regime_owner
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account_owner


CONTRACT = "trading.current_intraday_trailing_loss_threshold_state.v1"
RULE_VERSION = "current_intraday_trailing_loss_threshold_state_v1"
ADMISSION_CONTRACT = "trading.current_intraday_trailing_loss_threshold_state.admission.v1"
ADMISSION_RULE_VERSION = "current_intraday_trailing_loss_threshold_state_admission_v1"
TEMPORAL_SCOPE = "AS_OF_T_USING_EVIDENCE_BY_K"
IDENTITY_PREFIX = "current_intraday_trailing_loss_threshold_state_"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                           "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
NAMESPACE_FIELDS = ("source_id", "source_contract", "source_contract_version")
SOURCE_FIELDS = (*NAMESPACE_FIELDS, "source_snapshot_id")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")
TOPICS = ("BALANCE_ACTIVITY", "POSITION_CLOSURES", "ACCOUNT_LIFECYCLE", "RULE_LIFECYCLE", "SOURCE_REVISIONS")
EXCLUSIONS = ("rewards_or_withdrawals", "deposits_or_credits", "reset_or_migration", "capital_change",
              "historical_correction", "partial_close_or_deal_posting", "unknown_transaction",
              "separate_cost_posting", "unresolved_cost", "ambiguous_ordering", "rule_change")
EVENT_KINDS = ("ATOMIC_FULL_CLOSE", "REWARD_OR_WITHDRAWAL", "DEPOSIT_OR_CREDIT", "RESET_OR_MIGRATION",
               "CAPITAL_CHANGE", "HISTORICAL_CORRECTION", "PARTIAL_CLOSE_OR_DEAL_POSTING",
               "UNKNOWN_TRANSACTION", "SEPARATE_COST_POSTING", "UNRESOLVED_COST", "RULE_CHANGE")
EVENT_EXCLUSION = dict(zip(EVENT_KINDS[1:], (*EXCLUSIONS[:9], EXCLUSIONS[10])))
TARGET_KINDS = ("ACCOUNT_PROVIDER_IDENTITY", "ORIGINAL_RULE", "INITIAL_CAPITAL", "COMPLETE_HISTORY",
                "HISTORICAL_ORDERING", "BALANCE_RECONSTRUCTION", "SNAPSHOT_CONSISTENCY",
                "SOURCE_REVISIONS_AVAILABILITY", "EXCLUDED_ACTIVITY_ABSENCE", "EVENT_CLASSIFICATION")
REASON_CODES = (
    "THRESHOLD_ESTABLISHED", "ACCOUNT_SNAPSHOT_MISSING", "PROVIDER_REGIME_MISSING", "HISTORY_MISSING",
    "INCEPTION_MISSING", "INITIAL_CAPITAL_MISSING", "RULE_MISSING", "COVERAGE_MISSING",
    "NATIVE_REGIME_UNRESOLVED", "RULE_NOT_SUPPORTED", "NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED",
    "SNAPSHOT_BALANCE_MISSING", "SNAPSHOT_NOT_AT_ASSESSMENT_TIME", "SOURCE_COVERAGE_INCOMPLETE",
    "HISTORY_COVERAGE_INCOMPLETE", "REVISION_UNSUPPORTED", "EXCLUDED_ACTIVITY_UNRESOLVED",
    "EVENT_UNSUPPORTED", "ORDER_UNRESOLVED", "ORIGINAL_AVAILABILITY_UNKNOWN", "NATIVE_AVAILABILITY_UNKNOWN",
    "SUPPORT_INCOMPLETE", "ADMISSION_MISSING", "ADMISSION_NOT_CURRENT", "RECEIPT_MISSING",
    "RECEIPT_UNRESOLVED", "RECEIPT_MEMBERSHIP_INCOMPLETE", "BALANCE_CHAIN_UNRECONCILED",
    "SNAPSHOT_UNRECONCILED",
)
CLOSE_FIELDS = ("balance_before", "gross_realized_pnl", "commission_delta", "financing_delta",
                "other_cost_delta", "net_balance_delta", "balance_after")


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


def _native_time(value):
    # Called only after public native replay; preserve original native bytes.
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


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


def _native_money(value):
    # Public snapshot replay already canonicalizes monetary strings.
    return _money(value)


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


def _citations(rows, originals):
    def key(row):
        _keys(row, "evidence_id locator")
        identifier = _id(row["evidence_id"])
        if identifier not in originals:
            raise ValueError()
        return identifier, _text(row["locator"])
    _ordered(rows, key)


def _originals(rows, boundary):
    def key(row):
        _keys(row, "evidence_id source document media_type content content_sha256 source_available_at observed_at")
        return _id(row["evidence_id"])
    _ordered(rows, key)
    versions, captures = {}, set()
    for row in rows:
        source = _source(row["source"])
        document = row["document"]
        _keys(document, "namespace document_id document_revision")
        namespace = _namespace(document["namespace"])
        if namespace != source[:3]:
            raise ValueError()
        version = (namespace, _text(document["document_id"]), document["document_revision"])
        if version[2] is not None:
            _text(version[2])
        raw = _bytes(row["content"])
        if hashlib.sha256(raw).hexdigest() != _hash(row["content_sha256"]):
            raise ValueError()
        content = (raw, _text(row["media_type"]))
        if version in versions and versions[version] != content:
            raise ValueError()
        capture = (source, version)
        if capture in captures:
            raise ValueError()
        captures.add(capture)
        versions[version] = content
        observed = _time(row["observed_at"])
        available = row["source_available_at"]
        if observed > boundary or (available is not None and _time(available) > observed):
            raise ValueError()
    return {row["evidence_id"]: row for row in rows}


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


def _history(history, originals, scope, economic_time):
    if history is None:
        return
    _keys(history, "inception initial_capital rule sources coverage events revisions")
    inception = history["inception"]
    if inception is not None and _time(inception) > economic_time:
        raise ValueError()
    initial = history["initial_capital"]
    if initial is not None:
        _keys(initial, "amount currency citations")
        if _money(initial["amount"]) <= 0 or initial["currency"] != scope["account"]["currency"]:
            raise ValueError()
        _citations(initial["citations"], originals)
    rule = history["rule"]
    if rule is not None:
        _keys(rule, "assignment_id package_index rule_index native_rule_sha256 effective_from effective_until model deduction lower_bound update citations")
        _text(rule["assignment_id"])
        _nat(rule["package_index"])
        _nat(rule["rule_index"])
        _hash(rule["native_rule_sha256"])
        _time(rule["effective_from"])
        if rule["effective_until"] is not None and _time(rule["effective_until"]) <= rule["effective_from"]:
            raise ValueError()
        for field, supported in (("model", "CLOSED_POSITION_BALANCE_HIGH_WATERMARK"),
                                 ("deduction", "ONE_TENTH_INITIAL_CAPITAL"), ("lower_bound", "INITIAL_CAPITAL"),
                                 ("update", "EACH_ATOMIC_FULL_POSITION_CLOSE")):
            _enum(rule[field], (supported, "UNKNOWN"))
        _citations(rule["citations"], originals)
    def source_key(row):
        _keys(row, "namespace topics citations")
        namespace = _namespace(row["namespace"])
        _ordered(row["topics"], lambda t: TOPICS.index(_enum(t, TOPICS)))
        _citations(row["citations"], originals)
        return namespace
    _ordered(history["sources"], source_key)
    namespaces = {_ns(row["namespace"]) for row in history["sources"]}
    coverage = history["coverage"]
    if coverage is not None:
        _keys(coverage, "report from through source_information_cutoff account_wide inception source_inventory events revisions ordering expected_event_count exclusions citations")
        reference = coverage["report"]
        _keys(reference, "evidence_id original_sha256")
        original = originals[_id(reference["evidence_id"])]
        if _hash(reference["original_sha256"]) != _digest(original):
            raise ValueError()
        if namespaces and _ns(original["source"]) not in namespaces:
            raise ValueError()
        for field in ("from", "through", "source_information_cutoff"):
            if coverage[field] is not None:
                _time(coverage[field])
        if coverage["from"] is not None and coverage["through"] is not None and coverage["from"] > coverage["through"]:
            raise ValueError()
        for field in ("through", "source_information_cutoff"):
            value = coverage[field]
            if value is not None and (value > original["observed_at"] or
                                     (original["source_available_at"] is not None and value > original["source_available_at"])):
                raise ValueError()
        for field in ("account_wide", "inception", "source_inventory", "events", "revisions"):
            _enum(coverage[field], ("COMPLETE", "UNKNOWN"))
        _enum(coverage["ordering"], ("AUTHORITATIVE_TOTAL_ORDER", "UNKNOWN"))
        if coverage["expected_event_count"] is not None:
            _nat(coverage["expected_event_count"])
        _keys(coverage["exclusions"], EXCLUSIONS)
        for value in coverage["exclusions"].values():
            _enum(value, ("ABSENT", "PRESENT", "UNKNOWN"))
        _citations(coverage["citations"], originals)
    def event_key(row):
        _keys(row, "event_id origin original_record_id occurred_at sequence currency kind close citations")
        identifier = _id(row["event_id"])
        if row["sequence"] is not None:
            _nat(row["sequence"], 1)
        return (row["sequence"] is None, row["sequence"] or 0, identifier if row["sequence"] is None else "")
    _ordered(history["events"], event_key)
    identifiers, original_keys, positions = set(), set(), set()
    for row in history["events"]:
        source = _source(row["origin"])
        original_key = (source, _text(row["original_record_id"]))
        if row["event_id"] in identifiers or original_key in original_keys:
            raise ValueError()
        identifiers.add(row["event_id"])
        original_keys.add(original_key)
        if namespaces and source[:3] not in namespaces:
            raise ValueError()
        occurred = _time(row["occurred_at"])
        if occurred > economic_time or (inception is not None and occurred <= inception):
            raise ValueError()
        if row["currency"] != scope["account"]["currency"]:
            raise ValueError()
        kind = _enum(row["kind"], EVENT_KINDS)
        _citations(row["citations"], originals)
        if kind != "ATOMIC_FULL_CLOSE":
            if row["close"] is not None or (coverage is not None and coverage["exclusions"][EVENT_EXCLUSION[kind]] == "ABSENT"):
                raise ValueError()
            continue
        close = row["close"]
        _keys(close, ("position_id", "instrument", *CLOSE_FIELDS))
        position_key = (source[:3], _text(close["position_id"]))
        if position_key in positions:
            raise ValueError()
        positions.add(position_key)
        _keys(close["instrument"], "namespace instrument_id")
        _namespace(close["instrument"]["namespace"])
        _text(close["instrument"]["instrument_id"])
        amounts = {field: _money(close[field]) for field in CLOSE_FIELDS}
        if amounts["net_balance_delta"] != sum(amounts[f] for f in ("gross_realized_pnl", "commission_delta", "financing_delta", "other_cost_delta")):
            raise ValueError()
        if amounts["balance_after"] != amounts["balance_before"] + amounts["net_balance_delta"]:
            raise ValueError()
    def revision_key(row):
        _keys(row, "notice_id origin original_record_id effective_at kind citations")
        return _time(row["effective_at"]), _id(row["notice_id"])
    _ordered(history["revisions"], revision_key)
    identifiers, original_keys = set(), set()
    for row in history["revisions"]:
        source = _source(row["origin"])
        original_key = (source, _text(row["original_record_id"]))
        if row["notice_id"] in identifiers or original_key in original_keys or row["effective_at"] > economic_time:
            raise ValueError()
        identifiers.add(row["notice_id"])
        original_keys.add(original_key)
        if namespaces and source[:3] not in namespaces:
            raise ValueError()
        _enum(row["kind"], ("CORRECTION", "REPLACEMENT", "WITHDRAWAL", "UNKNOWN"))
        _citations(row["citations"], originals)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _native_bundle(bundle, validator):
    if bundle is None:
        return None
    _keys(bundle, "input_json result_json")
    def decode(value):
        value = json.loads(_bytes(value).decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_int=_parse_integer, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        _canonical(value)
        if type(value) is not dict:
            raise ValueError()
        return value
    payload, supplied = decode(bundle["input_json"]), decode(bundle["result_json"])
    # Each public validator performs genuine owner analysis and full comparison.
    return payload, validator(supplied, payload)


def _native_bindings(q, account, regime):
    scope, t, k = q["scope"], q["economic_time"], q["knowledge_boundary"]
    account_scope = scope["account"]
    if account is not None:
        result = account[1]
        observation = result["observation"]
        if result["requested_evaluation_timestamp"] != k or _ns(observation["source"]) != _ns(account_scope["namespace"]):
            raise ValueError()
        if any(observation["account"][f] != account_scope[f] for f in ("account_id", "environment", "currency")):
            raise ValueError()
    if regime is None:
        return None
    payload, result = regime
    if result["economic_timestamp"] != t or not t <= result["requested_knowledge_boundary"] <= k:
        raise ValueError()
    if _ns(result["account"]) != _ns(account_scope["namespace"]) or any(
            result["account"][f] != account_scope[f] for f in ("account_id", "environment")):
        raise ValueError()
    selected = result["selected_regime"]
    if selected is not None:
        for row in (selected["assignment"], selected["package"]):
            for field in SCOPE_FIELDS:
                if row[field] is not None and row[field] != scope[field]:
                    raise ValueError()
    history = q["history"]
    if history is None or history["rule"] is None:
        return None
    rule = history["rule"]
    package = payload["manifest"]["packages"][rule["package_index"]]
    native_rule = package["rules"][rule["rule_index"]]
    if _digest(native_rule) != rule["native_rule_sha256"]:
        raise ValueError()
    return package, native_rule


def _target_key(target):
    _keys(target, "kind event_id")
    kind = _enum(target["kind"], TARGET_KINDS)
    if kind == "EVENT_CLASSIFICATION":
        _id(target["event_id"])
    elif target["event_id"] is not None:
        raise ValueError()
    return TARGET_KINDS.index(kind), target["event_id"] or ""


def _targets(history):
    targets = [dict(kind=kind, event_id=None) for kind in TARGET_KINDS[:-1]]
    if history is not None:
        targets.extend(dict(kind="EVENT_CLASSIFICATION", event_id=identifier)
                       for identifier in sorted(row["event_id"] for row in history["events"]))
    return targets


def _support(q, targets, originals):
    allowed = {_target_key(target) for target in targets}
    def key(row):
        _keys(row, "target citations")
        target = _target_key(row["target"])
        if target not in allowed:
            raise ValueError()
        _citations(row["citations"], originals)
        return target
    _ordered(q["support_assertions"], key)
    return {_target_key(row["target"]): row for row in q["support_assertions"]}


def _observations(q, account, regime):
    observations = [row["observed_at"] for row in q["originals"]]
    if account is not None:
        observations.append(account[1]["observation"]["timing"]["observed_at"])
    if regime is not None:
        payload = regime[0]
        observations.append(_native_time(payload["manifest"]["timing"]["observed_at"]))
        observations.extend(_native_time(row["timing"]["observed_at"]) for row in payload["manifest"]["evidence"])
        observations.extend(_native_time(row["observed_at"]) for row in payload["approvals"])
    return observations


def _context(context, q, targets, assertions, originals, observations):
    if context is None:
        return {}
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 admitted_at available_at effective_from effective_until receipts")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _id(context["admission_id"])
    _namespace(context["authority_namespace"])
    _text(context["authority_id"])
    _text(context["mandate_id"])
    _nat(context["mandate_revision"], 1)
    if _hash(context["request_sha256"]) != _digest(q):
        raise ValueError()
    for field in ("admitted_at", "available_at", "effective_from"):
        _time(context[field])
    if context["effective_until"] is not None and _time(context["effective_until"]) <= context["effective_from"]:
        raise ValueError()
    if context["admitted_at"] > context["available_at"] or (observations and max(observations) > context["admitted_at"]):
        raise ValueError()
    allowed = {_target_key(target) for target in targets}
    def key(row):
        _keys(row, "target request_sha256 assertion_sha256 original_ids decision")
        target = _target_key(row["target"])
        if target not in allowed or _hash(row["request_sha256"]) != context["request_sha256"]:
            raise ValueError()
        assertion = assertions.get(target)
        expected = None if assertion is None else _digest(assertion)
        if row["assertion_sha256"] != expected:
            raise ValueError()
        _ordered(row["original_ids"], _id)
        if any(identifier not in originals for identifier in row["original_ids"]):
            raise ValueError()
        _enum(row["decision"], ("ADMITTED", "UNRESOLVED"))
        return target
    _ordered(context["receipts"], key)
    return {_target_key(row["target"]): (index, row) for index, row in enumerate(context["receipts"])}


def _period(period):
    return (None if period["effective_from"] is None else _native_time(period["effective_from"]),
            None if period["effective_until"] is None else _native_time(period["effective_until"]), period["end_status"])


def _covers(period, start, end):
    lower, upper, status = _period(period)
    return lower is not None and lower <= start and (status == "OPEN_ENDED" or (status == "KNOWN" and upper > end))


def _may_overlap(periods, start, end):
    bounds = [_period(p) for p in periods]
    lowers = [b[0] for b in bounds if b[0] is not None]
    uppers = [b[1] for b in bounds if b[2] == "KNOWN"]
    lower, upper = max(lowers) if lowers else None, min(uppers) if uppers else None
    return not ((upper is not None and upper <= start) or (lower is not None and lower > end) or
                (lower is not None and upper is not None and lower >= upper))


def _historical(regime, inception, t):
    payload, result = regime
    selected = result["selected_regime"]
    assignment, package = selected["assignment"], selected["package"]
    periods = [payload["manifest"]["coverage"]["economic_period"], assignment["enrollment_period"],
               assignment["phase_period"], package["effective_period"]]
    if not all(_covers(p, inception, t) for p in periods):
        return False
    package_key = (package["package_id"], package["package_revision"])
    original_assignment = next(row for row in payload["manifest"]["assignments"] if row["assignment_id"] == assignment["assignment_id"])
    intervals = []
    packages = {(row["package_id"], row["package_revision"]): row for row in payload["manifest"]["packages"]}
    for row in payload["manifest"]["assignments"]:
        if row["assignment_id"] != assignment["assignment_id"] and _may_overlap(
                [row["enrollment_period"], row["phase_period"]], inception, t):
            return False
    for binding in original_assignment["package_bindings"]:
        key = (binding["package"]["package_id"], binding["package"]["package_revision"])
        if key != package_key:
            if _may_overlap([binding["effective_period"], packages[key]["effective_period"]], inception, t):
                return False
            continue
        period = binding["effective_period"]
        if not _may_overlap([period], inception, t):
            continue
        lower, upper, status = _period(period)
        if lower is None or status == "UNKNOWN":
            return False
        intervals.append((lower, upper))
    intervals.sort(key=lambda p: (p[0], p[1] is None, p[1] or ""))
    if not intervals or intervals[0][0] > inception:
        return False
    frontier = intervals[0][1]
    for lower, upper in intervals[1:]:
        if frontier is None:
            break
        if lower > frontier:
            break
        frontier = None if upper is None else max(frontier, upper)
    return frontier is None or frontier > t


def _finding(code, pointer, root="REQUEST"):
    return dict(reason_code=code, subject=dict(root=root, pointer=pointer))


def _unknown(q, context, account, regime, selector, targets, assertions, receipts):
    """First failure only; structural checks have already run for all inputs."""
    for field, code in (("account_snapshot", "ACCOUNT_SNAPSHOT_MISSING"), ("provider_regime", "PROVIDER_REGIME_MISSING"),
                        ("history", "HISTORY_MISSING")):
        if q[field] is None:
            return _finding(code, "/" + field)
    h, t, k = q["history"], q["economic_time"], q["knowledge_boundary"]
    for field, code in (("inception", "INCEPTION_MISSING"), ("initial_capital", "INITIAL_CAPITAL_MISSING"),
                        ("rule", "RULE_MISSING"), ("coverage", "COVERAGE_MISSING")):
        if h[field] is None:
            return _finding(code, "/history/" + field)
    if regime[1]["outcome"] != "UNIQUE_APPLICABLE_APPROVED_REGIME":
        return _finding("NATIVE_REGIME_UNRESOLVED", "/provider_regime")
    rule, coverage, selected = h["rule"], h["coverage"], regime[1]["selected_regime"]
    package, native_rule = selector
    if (any(rule[field] == "UNKNOWN" for field in ("model", "deduction", "lower_bound", "update")) or
            native_rule["representation"] != "UNSUPPORTED" or native_rule["instrument_scope"] != {"kind": "ALL_ACCOUNT_INSTRUMENTS"} or
            selected["assignment"]["assignment_id"] != rule["assignment_id"] or
            any(package[field] != selected["package"][field] for field in ("package_id", "package_revision")) or
            rule["effective_from"] > h["inception"] or
            (rule["effective_until"] is not None and rule["effective_until"] <= t)):
        return _finding("RULE_NOT_SUPPORTED", "/history/rule")
    if not _historical(regime, h["inception"], t):
        return _finding("NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED", "/provider_regime")
    observation = account[1]["observation"]
    if observation["account_measures"]["balance"] is None:
        return _finding("SNAPSHOT_BALANCE_MISSING", "/account_snapshot")
    if observation["timing"]["effective_at"] != t:
        return _finding("SNAPSHOT_NOT_AT_ASSESSMENT_TIME", "/account_snapshot")
    if not h["sources"] or set(TOPICS) != {topic for row in h["sources"] for topic in row["topics"]}:
        return _finding("SOURCE_COVERAGE_INCOMPLETE", "/history/sources")
    cutoff = coverage["source_information_cutoff"]
    if (coverage["from"] != h["inception"] or coverage["through"] != t or cutoff is None or not t <= cutoff <= k or
            any(coverage[field] != "COMPLETE" for field in ("account_wide", "inception", "source_inventory", "events", "revisions")) or
            coverage["expected_event_count"] != len(h["events"])):
        return _finding("HISTORY_COVERAGE_INCOMPLETE", "/history/coverage")
    if h["revisions"]:
        return _finding("REVISION_UNSUPPORTED", "/history/revisions/0")
    families = {}
    for row in q["originals"]:
        document = row["document"]
        families.setdefault((_ns(document["namespace"]), document["document_id"]), set()).add(document["document_revision"])
    for i, row in enumerate(q["originals"]):
        document = row["document"]
        if len(families[(_ns(document["namespace"]), document["document_id"])]) > 1:
            return _finding("REVISION_UNSUPPORTED", f"/originals/{i}")
    for field in EXCLUSIONS:
        if coverage["exclusions"][field] != "ABSENT":
            return _finding("EXCLUDED_ACTIVITY_UNRESOLVED", "/history/coverage/exclusions/" + field)
    for i, row in enumerate(h["events"]):
        if row["kind"] != "ATOMIC_FULL_CLOSE":
            return _finding("EVENT_UNSUPPORTED", f"/history/events/{i}")
    events = h["events"]
    if (coverage["ordering"] != "AUTHORITATIVE_TOTAL_ORDER" or
            [row["sequence"] for row in events] != list(range(1, len(events) + 1)) or
            any(a["occurred_at"] > b["occurred_at"] for a, b in zip(events, events[1:]))):
        return _finding("ORDER_UNRESOLVED", "/history/events")
    for i, row in enumerate(q["originals"]):
        if row["source_available_at"] is None:
            return _finding("ORIGINAL_AVAILABILITY_UNKNOWN", f"/originals/{i}/source_available_at")
    if observation["timing"]["source_available_at"] is None:
        return _finding("NATIVE_AVAILABILITY_UNKNOWN", "/account_snapshot")
    manifest = regime[0]["manifest"]
    if manifest["timing"]["source_available_at"] is None or any(
            row["timing"]["source_available_at"] is None for row in sorted(manifest["evidence"], key=lambda r: r["evidence_id"])):
        return _finding("NATIVE_AVAILABILITY_UNKNOWN", "/provider_regime")
    citation_objects = [h["initial_capital"], rule, *h["sources"], coverage, *events]
    if (any(not row["citations"] for row in citation_objects) or
            not any(c["evidence_id"] == coverage["report"]["evidence_id"] for c in coverage["citations"]) or
            any(_target_key(target) not in assertions or not assertions[_target_key(target)]["citations"] for target in targets)):
        return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
    if context is None:
        return _finding("ADMISSION_MISSING", "", "TRUSTED_CONTEXT")
    for field, failed in (("available_at", context["available_at"] > k), ("effective_from", context["effective_from"] > k),
                          ("effective_until", context["effective_until"] is not None and context["effective_until"] <= k)):
        if failed:
            return _finding("ADMISSION_NOT_CURRENT", "/" + field, "TRUSTED_CONTEXT")
    if any(_target_key(target) not in receipts for target in targets):
        return _finding("RECEIPT_MISSING", "/receipts", "TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["decision"] == "UNRESOLVED":
            return _finding("RECEIPT_UNRESOLVED", f"/receipts/{i}", "TRUSTED_CONTEXT")
    original_ids = [row["evidence_id"] for row in q["originals"]]
    for i, receipt in receipts.values():
        if receipt["original_ids"] != original_ids:
            return _finding("RECEIPT_MEMBERSHIP_INCOMPLETE", f"/receipts/{i}/original_ids", "TRUSTED_CONTEXT")
    balance = _money(h["initial_capital"]["amount"])
    for i, row in enumerate(events):
        if _money(row["close"]["balance_before"]) != balance:
            return _finding("BALANCE_CHAIN_UNRECONCILED", f"/history/events/{i}/close/balance_before")
        balance = _money(row["close"]["balance_after"])
    if balance != _native_money(observation["account_measures"]["balance"]):
        return _finding("SNAPSHOT_UNRECONCILED", "/account_snapshot")
    return None


def _evaluate(request, trusted_context):
    _canonical(request)
    _canonical(trusted_context)
    q, context = deepcopy(request), deepcopy(trusted_context)
    _keys(q, "contract rule_version economic_time knowledge_boundary scope account_snapshot provider_regime originals history support_assertions")
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    if _time(q["economic_time"]) > _time(q["knowledge_boundary"]):
        raise ValueError()
    _scope(q["scope"])
    originals = _originals(q["originals"], q["knowledge_boundary"])
    _history(q["history"], originals, q["scope"], q["economic_time"])
    account = _native_bundle(q["account_snapshot"], account_owner.validate_causal_financial_account_state_snapshot)
    regime = _native_bundle(q["provider_regime"], regime_owner.validate_causal_account_rule_regime_assessment)
    selector = _native_bindings(q, account, regime)
    targets = _targets(q["history"])
    assertions = _support(q, targets, originals)
    receipts = _context(context, q, targets, assertions, originals, _observations(q, account, regime))
    finding = _unknown(q, context, account, regime, selector, targets, assertions, receipts)
    state = None
    if finding is None:
        h = q["history"]
        initial = _money(h["initial_capital"]["amount"])
        balance = high = initial
        steps = []
        for row in h["events"]:
            balance = _money(row["close"]["balance_after"])
            high = max(high, balance)
            steps.append(dict(event_id=row["event_id"], sequence=row["sequence"], balance=_decimal(balance),
                              high_watermark=_decimal(high), threshold=_decimal(high - initial / 10)))
        state = dict(inception=h["inception"], as_of=q["economic_time"], currency=q["scope"]["account"]["currency"],
                     initial_capital=_decimal(initial), final_balance=_decimal(balance), high_watermark=_decimal(high),
                     threshold=_decimal(high - initial / 10), steps=steps)
    bindings = []
    for target in targets:
        key = _target_key(target)
        assertion = assertions.get(key)
        receipt = receipts.get(key)
        bindings.append(dict(target=target, assertion_sha256=None if assertion is None else _digest(assertion),
                             receipt_sha256=None if receipt is None else _digest(receipt[1]), original_ids=list(originals)))
    native_references = dict(
        account_snapshot=None if account is None else dict(snapshot_id=account[1]["snapshot_id"], bundle_sha256=_digest(q["account_snapshot"])),
        provider_regime=None if regime is None else dict(assessment_id=regime[1]["assessment_id"], bundle_sha256=_digest(q["provider_regime"])))
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, temporal_scope=TEMPORAL_SCOPE,
                  economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"], scope=q["scope"],
                  outcome="ESTABLISHED" if finding is None else "UNKNOWN",
                  reason_codes=["THRESHOLD_ESTABLISHED" if finding is None else finding["reason_code"]],
                  findings=[] if finding is None else [finding], state=state, native_references=native_references,
                  required_targets=targets, admission_bindings=bindings,
                  reconstruction_evidence=dict(request=q, request_sha256=_digest(q),
                                               trusted_context_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_current_intraday_trailing_loss_threshold_state(request: dict, *, trusted_context=None) -> dict:
    """Reconstruct as of T. The host must independently trust the supplied issuer.

    This result supplies no equity, daily-loss, margin, payout or trading
    permission. The separate FROZEN_AWAITING_PAYOUT veto remains mandatory.
    """
    try:
        return deepcopy(_evaluate(request, trusted_context))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError,
            RecursionError, UnicodeError, binascii.Error) as exc:
        raise ValueError("INVALID_TRAILING_LOSS_INPUT") from exc


def validate_current_intraday_trailing_loss_threshold_state(value: dict, request: dict, *, trusted_context=None) -> dict:
    """Reconstruct every field with independent originals and host admission."""
    expected = evaluate_current_intraday_trailing_loss_threshold_state(request, trusted_context=trusted_context)
    try:
        if type(value) is not dict or _canonical(value) != _canonical(expected):
            raise ValueError()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("TRAILING_LOSS_RESULT_MISMATCH") from exc
    return deepcopy(expected)


@dataclass(frozen=True)
class CurrentIntradayTrailingLossThresholdStateResult:
    _payload: dict

    def to_dict(self) -> dict:
        return deepcopy(self._payload)


class CurrentIntradayTrailingLossThresholdStateAnalyzer:
    def analyze(self, request: dict, trusted_context=None) -> CurrentIntradayTrailingLossThresholdStateResult:
        return CurrentIntradayTrailingLossThresholdStateResult(
            evaluate_current_intraday_trailing_loss_threshold_state(request, trusted_context=trusted_context))


CURRENT_INTRADAY_TRAILING_LOSS_THRESHOLD_STATE = CurrentIntradayTrailingLossThresholdStateAnalyzer()
