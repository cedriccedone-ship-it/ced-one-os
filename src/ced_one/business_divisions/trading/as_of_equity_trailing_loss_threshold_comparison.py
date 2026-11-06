"""Admitted historical account equity versus a genuinely replayed C8 threshold.

Host admission supplies source semantics; this module does not authenticate an
issuer or grant trading authority. FROZEN_AWAITING_PAYOUT remains a separate veto.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import re

from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8_owner
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account_owner

CONTRACT = "trading.as_of_equity_trailing_loss_threshold_comparison.v1"
RULE_VERSION = "as_of_equity_trailing_loss_threshold_comparison_v1"
ADMISSION_CONTRACT = "trading.as_of_equity_trailing_loss_threshold_comparison.admission.v1"
ADMISSION_RULE_VERSION = "as_of_equity_trailing_loss_threshold_comparison_admission_v1"
IDENTITY_PREFIX = "as_of_equity_trailing_loss_threshold_comparison_"
TEMPORAL_SCOPE = "AS_OF_T_USING_EVIDENCE_BY_K"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
LIMITATIONS = ("AS_OF_ONLY", "SOURCE_REVISION_REVIEW_THROUGH_REPORTED_CUTOFF", "NO_CONTINUOUS_BREACH_PROOF",
              "NO_DAILY_LOSS_MARGIN_OR_AUTHORIZATION", "NO_SOURCE_AUTHENTICATION")
TARGETS = ("EQUITY_IDENTITY_BINDING", "EQUITY_AGGREGATE_MEANING", "EQUITY_ACCOUNT_WIDE_COMPLETENESS",
           "EQUITY_COST_COMPONENTS", "EQUITY_SOURCE_VERSION_VALIDITY")
TARGET_ROLES = (("aggregate", "definition"), ("aggregate", "definition"), ("aggregate", "coverage"),
                ("definition", "coverage"), ("aggregate", "definition", "coverage"))
ROLES = ("aggregate", "definition", "coverage")
COMPONENTS = ("balance", "floating_pnl", "commissions", "swaps", "other_costs")
NAMESPACE_FIELDS = ("source_id", "source_contract", "source_contract_version")
SOURCE_FIELDS = (*NAMESPACE_FIELDS, "source_snapshot_id")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")
REASON_CODES = (
    "COMPARISON_ESTABLISHED", "C8_MISSING", "C8_CONTEXT_MISSING", "C8_NOT_ESTABLISHED", "NATIVE_EQUITY_MISSING",
    "EQUITY_ASSERTION_MISSING", "EQUITY_AMOUNT_UNDECLARED", "AGGREGATE_ORIGINAL_MISSING", "DEFINITION_ORIGINAL_MISSING",
    "COVERAGE_ORIGINAL_MISSING", "ORIGINAL_ROLE_COVERAGE_INCOMPLETE", "DOCUMENT_REVISION_UNKNOWN",
    "DOCUMENT_VERSION_CONFLICT", "SOURCE_REVIEW_CUTOFF_UNKNOWN", "ORIGINAL_AVAILABILITY_UNKNOWN",
    "SOURCE_REVIEW_CUTOFF_INSUFFICIENT", "SOURCE_REVISIONS_UNRESOLVED", "DEFINITION_NOT_APPLICABLE",
    "ACCOUNT_WIDE_UNRESOLVED", "COMPONENT_TREATMENT_UNSUPPORTED", "COMPONENT_INTEGRITY_UNRESOLVED",
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


def _equity(q, originals):
    equity = q["equity"]
    if equity is None:
        return
    _keys(equity, "scope economic_time knowledge_boundary snapshot_source snapshot_id snapshot_bundle_sha256 amount currency "
                  "originals definition_period source_information_cutoff account_wide components component_integrity source_revisions")
    _scope(equity["scope"])
    _same(equity["scope"], q["scope"])
    for field in ("economic_time", "knowledge_boundary"):
        _time(equity[field])
        _same(equity[field], q[field])
    _source(equity["snapshot_source"])
    if _ns(equity["snapshot_source"]) != _ns(q["scope"]["account"]["namespace"]):
        raise ValueError()
    _text(equity["snapshot_id"])
    _hash(equity["snapshot_bundle_sha256"])
    if equity["amount"] is not None:
        _money(equity["amount"])
    _currency(equity["currency"])
    _same(equity["currency"], q["scope"]["account"]["currency"])
    _keys(equity["originals"], ROLES)
    for role, ref in equity["originals"].items():
        if ref is None:
            continue
        _keys(ref, "evidence_id original_sha256")
        identifier = _id(ref["evidence_id"])
        if identifier not in originals or _hash(ref["original_sha256"]) != _digest(originals[identifier]):
            raise ValueError()
        original = originals[identifier]
        namespace = _ns(original["source"])
        allowed = [_ns(q["scope"]["account"]["namespace"])]
        if role == "definition":
            allowed.append(_ns(q["scope"]["provider_namespace"]))
        if namespace not in allowed:
            raise ValueError()
        if role == "aggregate":
            _same(original["source"], equity["snapshot_source"])
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
    cutoff = equity["source_information_cutoff"]
    if cutoff is not None:
        if not q["economic_time"] <= _time(cutoff) <= q["knowledge_boundary"]:
            raise ValueError()
        ref = equity["originals"]["coverage"]
        if ref is not None:
            report = originals[ref["evidence_id"]]
            if report["observed_at"] < cutoff or (report["source_available_at"] is not None and report["source_available_at"] < cutoff):
                raise ValueError()
    _enum(equity["account_wide"], ("COMPLETE", "UNKNOWN"))
    _keys(equity["components"], COMPONENTS)
    for field in COMPONENTS:
        allowed = ("INCLUDED_ONCE", "OMITTED", "UNKNOWN")
        if field not in ("balance", "floating_pnl"):
            allowed = (*allowed, "NOT_APPLICABLE")
        _enum(equity["components"][field], allowed)
    _enum(equity["component_integrity"], ("COMPLETE_EXACTLY_ONCE", "OMISSION", "DUPLICATION", "UNKNOWN"))
    _enum(equity["source_revisions"], ("NONE", "PRESENT", "UNKNOWN"))


def _support(q, originals):
    expected = None if q["equity"] is None else _digest(q["equity"])
    def key(row):
        _keys(row, "target equity_sha256 citations")
        target = _enum(row["target"], TARGETS)
        _same(row["equity_sha256"], expected)
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


def _replay(q, trusted_c8_context):
    if q["c8"] is None:
        if trusted_c8_context is not None:
            raise ValueError()
        return None, None, None
    _keys(q["c8"], "request_json result_json")
    original = _decode(q["c8"]["request_json"])
    supplied = _decode(q["c8"]["result_json"])
    result = c8_owner.validate_current_intraday_trailing_loss_threshold_state(
        supplied, original, trusted_context=trusted_c8_context)
    for field in ("scope", "economic_time", "knowledge_boundary"):
        _same(original[field], q[field])
    bundle = original["account_snapshot"]
    account = None
    if bundle is not None:
        _keys(bundle, "input_json result_json")
        account = account_owner.validate_causal_financial_account_state_snapshot(
            _decode(bundle["result_json"]), _decode(bundle["input_json"]))
        equity = q["equity"]
        if equity is not None:
            observation = account["observation"]
            _same(equity["snapshot_source"], observation["source"])
            _same(equity["snapshot_id"], account["snapshot_id"])
            _same(equity["snapshot_bundle_sha256"], _digest(bundle))
            native_amount = observation["account_measures"]["equity"]
            if native_amount is not None and equity["amount"] is not None:
                _same(equity["amount"], native_amount)
            ref = equity["originals"]["aggregate"]
            if ref is not None:
                aggregate = next(row for row in q["originals"] if row["evidence_id"] == ref["evidence_id"])
                publication = aggregate["source_available_at"]
                native_publication = observation["timing"]["source_available_at"]
                if publication is not None and native_publication is not None:
                    _same(publication, native_publication)
    return original, result, account


def _families(q, c8_request):
    families, versions, captures = {}, {}, {}
    rows = ([] if c8_request is None else c8_request["originals"]) + q["originals"]
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
    return families


def _context(context, q, c8_context, account, assertions, originals):
    if context is None:
        return {}
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 "
                   "c8_context_sha256 admitted_at available_at effective_from effective_until receipts")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _id(context["admission_id"])
    _namespace(context["authority_namespace"])
    for field in ("authority_id", "mandate_id"):
        _text(context[field])
    _nat(context["mandate_revision"], 1)
    request_hash = _digest(q)
    c8_hash = None if c8_context is None else _digest(c8_context)
    _same(context["request_sha256"], request_hash)
    _same(context["c8_context_sha256"], c8_hash)
    for field in ("admitted_at", "available_at", "effective_from"):
        _time(context[field])
    if context["effective_until"] is not None and _time(context["effective_until"]) <= context["effective_from"]:
        raise ValueError()
    if context["admitted_at"] > context["available_at"]:
        raise ValueError()
    observations = [row["observed_at"] for row in originals.values()]
    if account is not None:
        observations.append(account["observation"]["timing"]["observed_at"])
    if c8_context is not None:
        observations.append(c8_context["available_at"])
    # A universal condition is true for the empty observation set.
    if any(observed > context["admitted_at"] for observed in observations):
        raise ValueError()
    def key(row):
        _keys(row, "target request_sha256 c8_context_sha256 assertion_sha256 original_ids decision")
        target = _enum(row["target"], TARGETS)
        _same(row["request_sha256"], request_hash)
        _same(row["c8_context_sha256"], c8_hash)
        assertion = assertions.get(target)
        _same(row["assertion_sha256"], None if assertion is None else _digest(assertion))
        _ordered(row["original_ids"], _id)
        if any(identifier not in originals for identifier in row["original_ids"]):
            raise ValueError()
        _enum(row["decision"], ("ADMITTED", "UNRESOLVED"))
        return TARGETS.index(target)
    _ordered(context["receipts"], key)
    return {row["target"]: (i, row) for i, row in enumerate(context["receipts"])}


def _finding(reason, pointer, root="REQUEST"):
    return dict(reason_code=reason, subject=dict(root=root, pointer=pointer))


def _unknown(q, c8_context, context, c8_result, account, originals, families, assertions, receipts):
    if q["c8"] is None:
        return _finding("C8_MISSING", "/c8")
    if c8_context is None:
        return _finding("C8_CONTEXT_MISSING", "", "C8_TRUSTED_CONTEXT")
    if c8_result["outcome"] != "ESTABLISHED":
        return _finding("C8_NOT_ESTABLISHED", "/c8")
    if account["observation"]["account_measures"]["equity"] is None:
        return _finding("NATIVE_EQUITY_MISSING", "/c8")
    equity = q["equity"]
    if equity is None:
        return _finding("EQUITY_ASSERTION_MISSING", "/equity")
    if equity["amount"] is None:
        return _finding("EQUITY_AMOUNT_UNDECLARED", "/equity/amount")
    for role in ROLES:
        if equity["originals"][role] is None:
            return _finding(role.upper() + "_ORIGINAL_MISSING", "/equity/originals/" + role)
    role_ids = {ref["evidence_id"] for ref in equity["originals"].values()}
    for i, row in enumerate(q["originals"]):
        if row["evidence_id"] not in role_ids:
            return _finding("ORIGINAL_ROLE_COVERAGE_INCOMPLETE", f"/originals/{i}")
    for i, row in enumerate(q["originals"]):
        if row["document"]["document_revision"] is None:
            return _finding("DOCUMENT_REVISION_UNKNOWN", f"/originals/{i}/document/document_revision")
    for i, row in enumerate(q["originals"]):
        if len(families[_document_keys(row)[0]]) > 1:
            return _finding("DOCUMENT_VERSION_CONFLICT", f"/originals/{i}/document")
    cutoff = equity["source_information_cutoff"]
    if cutoff is None:
        return _finding("SOURCE_REVIEW_CUTOFF_UNKNOWN", "/equity/source_information_cutoff")
    for i, row in enumerate(q["originals"]):
        if row["source_available_at"] is None:
            return _finding("ORIGINAL_AVAILABILITY_UNKNOWN", f"/originals/{i}/source_available_at")
    if any(originals[equity["originals"][role]["evidence_id"]]["source_available_at"] > cutoff for role in ("aggregate", "definition")):
        return _finding("SOURCE_REVIEW_CUTOFF_INSUFFICIENT", "/equity/source_information_cutoff")
    if equity["source_revisions"] != "NONE":
        return _finding("SOURCE_REVISIONS_UNRESOLVED", "/equity/source_revisions")
    period, t = equity["definition_period"], q["economic_time"]
    if (period["effective_from"] is None or period["effective_from"] > t or period["end_status"] == "UNKNOWN" or
            (period["end_status"] == "KNOWN" and period["effective_until"] <= t)):
        return _finding("DEFINITION_NOT_APPLICABLE", "/equity/definition_period")
    if equity["account_wide"] != "COMPLETE":
        return _finding("ACCOUNT_WIDE_UNRESOLVED", "/equity/account_wide")
    for field in COMPONENTS:
        allowed = ("INCLUDED_ONCE",) if field in ("balance", "floating_pnl") else ("INCLUDED_ONCE", "NOT_APPLICABLE")
        if equity["components"][field] not in allowed:
            return _finding("COMPONENT_TREATMENT_UNSUPPORTED", "/equity/components/" + field)
    if equity["component_integrity"] != "COMPLETE_EXACTLY_ONCE":
        return _finding("COMPONENT_INTEGRITY_UNRESOLVED", "/equity/component_integrity")
    for target, roles in zip(TARGETS, TARGET_ROLES):
        assertion = assertions.get(target)
        cited = set() if assertion is None else {row["evidence_id"] for row in assertion["citations"]}
        if not {equity["originals"][role]["evidence_id"] for role in roles} <= cited:
            return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
    if context is None:
        return _finding("EQUITY_ADMISSION_MISSING", "", "EQUITY_TRUSTED_CONTEXT")
    k = q["knowledge_boundary"]
    for field, failed in (("available_at", context["available_at"] > k),
                          ("effective_from", context["admitted_at"] < context["effective_from"] or k < context["effective_from"]),
                          ("effective_until", context["effective_until"] is not None and
                           (context["admitted_at"] >= context["effective_until"] or k >= context["effective_until"]))):
        if failed:
            return _finding("EQUITY_ADMISSION_NOT_CURRENT", "/" + field, "EQUITY_TRUSTED_CONTEXT")
    if any(target not in receipts for target in TARGETS):
        return _finding("RECEIPT_MISSING", "/receipts", "EQUITY_TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["decision"] == "UNRESOLVED":
            return _finding("RECEIPT_UNRESOLVED", f"/receipts/{i}", "EQUITY_TRUSTED_CONTEXT")
    for i, receipt in receipts.values():
        if receipt["original_ids"] != list(originals):
            return _finding("RECEIPT_MEMBERSHIP_INCOMPLETE", f"/receipts/{i}/original_ids", "EQUITY_TRUSTED_CONTEXT")
    return None


def _evaluate(request, trusted_c8_context, trusted_equity_context):
    for value in (request, trusted_c8_context, trusted_equity_context):
        _canonical(value)
    q, c8_context, context = deepcopy(request), deepcopy(trusted_c8_context), deepcopy(trusted_equity_context)
    _keys(q, "contract rule_version economic_time knowledge_boundary scope c8 equity originals support_assertions")
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    if _time(q["economic_time"]) > _time(q["knowledge_boundary"]):
        raise ValueError()
    _scope(q["scope"])
    originals = _originals(q["originals"], q["knowledge_boundary"])
    _equity(q, originals)
    assertions = _support(q, originals)
    c8_request, c8_result, account = _replay(q, c8_context)
    families = _families(q, c8_request)
    receipts = _context(context, q, c8_context, account, assertions, originals)
    finding = _unknown(q, c8_context, context, c8_result, account, originals, families, assertions, receipts)
    state = None
    if finding is None:
        equity = _money(account["observation"]["account_measures"]["equity"])
        threshold = _money(c8_result["state"]["threshold"])
        difference = equity - threshold
        state = dict(as_of=q["economic_time"], currency=q["scope"]["account"]["currency"], equity=_decimal(equity),
                     threshold=_decimal(threshold), difference=_decimal(difference),
                     relation="ABOVE" if difference > 0 else "BELOW" if difference < 0 else "EQUAL",
                     source_information_cutoff=q["equity"]["source_information_cutoff"])
    bindings = [dict(target=target, assertion_sha256=None if target not in assertions else _digest(assertions[target]),
                     receipt_sha256=None if target not in receipts else _digest(receipts[target][1]), original_ids=list(originals))
                for target in TARGETS]
    references = dict(
        c8=None if c8_result is None else dict(assessment_identity=c8_result["assessment_identity"],
                                             bundle_sha256=_digest(q["c8"]), outcome=c8_result["outcome"]),
        account_snapshot=None if account is None else dict(snapshot_id=account["snapshot_id"],
                                                           bundle_sha256=_digest(c8_request["account_snapshot"])))
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, temporal_scope=TEMPORAL_SCOPE,
                  economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"], scope=q["scope"],
                  outcome="ESTABLISHED" if finding is None else "UNKNOWN", reason_codes=["COMPARISON_ESTABLISHED" if finding is None else finding["reason_code"]],
                  findings=[] if finding is None else [finding], state=state, native_references=references,
                  required_targets=list(TARGETS), admission_bindings=bindings,
                  reconstruction_evidence=dict(request=q, request_sha256=_digest(q),
                      c8_trusted_context_sha256=None if c8_context is None else _digest(c8_context),
                      equity_trusted_context_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, limitations=list(LIMITATIONS), authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_as_of_equity_trailing_loss_threshold_comparison(
    request: dict, *, trusted_c8_context=None, trusted_equity_context=None,
) -> dict:
    """Establish an admitted historical difference; never current eligibility.

    Independent host admission supplies evidence semantics, not an authorization
    lease. FROZEN_AWAITING_PAYOUT remains a separate mandatory trading veto.
    """
    try:
        return deepcopy(_evaluate(request, trusted_c8_context, trusted_equity_context))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError,
            UnicodeError, binascii.Error, StopIteration) as exc:
        raise ValueError("INVALID_EQUITY_THRESHOLD_INPUT") from exc


def validate_as_of_equity_trailing_loss_threshold_comparison(
    result: dict, request: dict, *, trusted_c8_context=None, trusted_equity_context=None,
) -> dict:
    """Replay both public owners and compare every field with exact JSON types."""
    expected = evaluate_as_of_equity_trailing_loss_threshold_comparison(
        request, trusted_c8_context=trusted_c8_context, trusted_equity_context=trusted_equity_context)
    try:
        if type(result) is not dict or _canonical(result) != _canonical(expected):
            raise ValueError()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("EQUITY_THRESHOLD_RESULT_MISMATCH") from exc
    return deepcopy(expected)
