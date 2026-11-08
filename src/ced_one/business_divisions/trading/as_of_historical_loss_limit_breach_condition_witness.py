"""An independently admitted instantaneous historical loss-limit condition.

Public C9/C11 replay owns the financial comparison. The independently trusted
host owns source authenticity and semantic admission. This point witness grants
no eligibility, trading, payout or execution authority; the separate
FROZEN_AWAITING_PAYOUT veto remains mandatory.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re

from ced_one.business_divisions.trading import as_of_equity_trailing_loss_threshold_comparison as c9_owner
from ced_one.business_divisions.trading import as_of_equity_daily_reset_loss_floor_comparison as c11_owner

CONTRACT = "trading.as_of_historical_loss_limit_breach_condition_witness.v1"
RULE_VERSION = "as_of_historical_loss_limit_breach_condition_witness_v1"
ADMISSION_CONTRACT = "trading.as_of_historical_loss_limit_breach_condition_witness.admission.v1"
ADMISSION_RULE_VERSION = "as_of_historical_loss_limit_breach_condition_witness_admission_v1"
IDENTITY_PREFIX = "as_of_historical_loss_limit_breach_condition_witness_"
TEMPORAL_SCOPE = "AS_OF_T_USING_EVIDENCE_BY_K"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
LIMITATIONS = ("AS_OF_ONLY", "POINT_OBSERVATION_ONLY", "SOURCE_REVIEW_CUTOFFS_NOT_LATEST_AT_K",
               "NO_CONTINUOUS_BREACH_ABSENCE", "NO_PROVIDER_RECORDED_BREACH_STATUS",
               "NO_DISQUALIFICATION_OR_REINSTATEMENT", "NO_CURRENT_ACCOUNT_ELIGIBILITY",
               "NO_MARGIN_OR_RISK_BUDGET_APPROVAL", "NO_PRETRADE_STOP_LOSS_APPROVAL",
               "NO_TRADING_OR_EXECUTION_AUTHORIZATION", "NO_PAYOUT_AUTHORIZATION",
               "SOURCE_AUTHENTICATION_EXTERNAL", "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL")
TARGETS = ("ACCOUNT_AND_RULE_BINDING", "INSTANTANEOUS_TRIGGER", "MEASURE_EQUIVALENCE",
           "OBSERVATION_APPLICABILITY", "SOURCE_VALIDITY")
ROLES = ("mandatory_trigger", "account_applicability", "measure_equivalence", "source_validity")
OWNERS = ("C8", "C9", "C10", "C11", "C12")
CONDITIONS = ("duration", "grace", "confirmation", "provider_decision")
NAMESPACE_FIELDS = ("source_id", "source_contract", "source_contract_version")
SOURCE_FIELDS = (*NAMESPACE_FIELDS, "source_snapshot_id")
SCOPE_FIELDS = ("provider_id", "program_id", "account_type_id", "phase_id")
UNKNOWN_REASONS = (
    "COMPARISON_MISSING", "COMPARISON_NOT_ESTABLISHED", "TRIGGER_MISSING", "ORIGINAL_ROLE_MISSING",
    "DOCUMENT_REVISION_UNKNOWN", "DOCUMENT_REVISIONS_UNRESOLVED", "ORIGINAL_AVAILABILITY_UNKNOWN",
    "SOURCE_CUTOFF_INSUFFICIENT", "SOURCE_REVIEW_UNRESOLVED", "RULE_NOT_APPLICABLE",
    "RULE_FORCE_UNRESOLVED", "COMPARATOR_UNDECLARED", "EVENT_SEMANTICS_UNSUPPORTED",
    "MEASURE_EQUIVALENCE_UNRESOLVED", "SUPPORT_INCOMPLETE", "ADMISSION_MISSING",
    "ADMISSION_NOT_CURRENT", "RECEIPT_MISSING", "RECEIPT_UNRESOLVED", "RECEIPT_MEMBERSHIP_INCOMPLETE",
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
    if value < 0:
        return "-" + _integer_text(-value)
    parts = []
    while value >= 10 ** 1000:
        value, part = divmod(value, 10 ** 1000)
        parts.append(str(part).zfill(1000))
    return str(value) + "".join(reversed(parts))


def _canonical(value):
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


def _ns(value):
    return tuple(value[f] for f in NAMESPACE_FIELDS)


def _scope(value):
    _keys(value, ("account", "provider_namespace", *SCOPE_FIELDS, "lifecycle_id"))
    _namespace(value["provider_namespace"])
    for field in SCOPE_FIELDS:
        _text(value[field])
    _id(value["lifecycle_id"])
    account = value["account"]
    _keys(account, "namespace account_id environment currency")
    _namespace(account["namespace"])
    _text(account["account_id"])
    _enum(account["environment"], ("DEMO", "LIVE"))
    if type(account["currency"]) is not str or re.fullmatch(r"[A-Z]{3}", account["currency"]) is None:
        raise ValueError()


def _preflight(q, upstream_contexts, context):
    """Phase-one sealed grammar, before decoding/replaying any foreign owner.

    Reference resolution, content binding and causal relations follow genuine
    replay. Keeping these distinct also prevents malformed C12 grammar from
    unnecessarily invoking expensive upstream validators.
    """
    def nullable_hash(value):
        if value is not None:
            _hash(value)

    def member(row):
        _keys(row, "owner evidence_id original_sha256")
        _enum(row["owner"], OWNERS)
        _id(row["evidence_id"])
        _hash(row["original_sha256"])
        return OWNERS.index(row["owner"]), row["evidence_id"]

    def original(row):
        _keys(row, "evidence_id source document media_type content content_sha256 source_available_at observed_at")
        _id(row["evidence_id"])
        _keys(row["source"], SOURCE_FIELDS)
        for value in row["source"].values():
            _text(value)
        _keys(row["document"], "namespace document_id document_revision")
        _namespace(row["document"]["namespace"])
        _text(row["document"]["document_id"])
        if row["document"]["document_revision"] is not None:
            _text(row["document"]["document_revision"])
        _text(row["media_type"])
        _bytes(row["content"])
        _hash(row["content_sha256"])
        if row["source_available_at"] is not None:
            _time(row["source_available_at"])
        _time(row["observed_at"])
        return row["evidence_id"]

    _ordered(q["originals"], original)
    if len(q["originals"]) > 4:
        raise ValueError()
    _keys(q["roles"], ROLES)
    for ref in q["roles"].values():
        if ref is not None:
            member(ref)
    dependency = q["comparison"]
    if dependency is not None:
        _keys(dependency, "owner request_json result_json")
        _enum(dependency["owner"], ("C9", "C11"))
        _bytes(dependency["request_json"])
        _bytes(dependency["result_json"])
    trigger = q["trigger"]
    if trigger is not None:
        _keys(trigger, "scope economic_time knowledge_boundary rule_reference_sha256 effective_period force permitted_when "
                       "measure_equivalence event conditions source_review")
        _scope(trigger["scope"])
        _time(trigger["economic_time"])
        _time(trigger["knowledge_boundary"])
        nullable_hash(trigger["rule_reference_sha256"])
        period = trigger["effective_period"]
        _keys(period, "effective_from effective_until end_status")
        _enum(period["end_status"], ("KNOWN", "OPEN_ENDED", "UNKNOWN"))
        for field in ("effective_from", "effective_until"):
            if period[field] is not None:
                _time(period[field])
        _enum(trigger["force"], ("MANDATORY", "NON_MANDATORY", "UNKNOWN"))
        _enum(trigger["permitted_when"], ("GREATER_THAN_OR_EQUAL", "GREATER_THAN", "UNKNOWN"))
        _enum(trigger["measure_equivalence"], ("EXACT", "DIFFERENT", "UNKNOWN"))
        _keys(trigger["event"], "mode snapshot_reference_sha256")
        _enum(trigger["event"]["mode"], ("ACCOUNT_EQUITY_OBSERVATION_AT_T", "OTHER", "UNKNOWN"))
        nullable_hash(trigger["event"]["snapshot_reference_sha256"])
        _keys(trigger["conditions"], CONDITIONS)
        for value in trigger["conditions"].values():
            _enum(value, ("NONE", "REQUIRED", "UNKNOWN"))
        review = trigger["source_review"]
        _keys(review, "complete_through_cutoff relevant_revisions known_relevant_corrections")
        _enum(review["complete_through_cutoff"], ("COMPLETE", "UNKNOWN"))
        for field in ("relevant_revisions", "known_relevant_corrections"):
            _enum(review[field], ("NONE", "PRESENT", "UNKNOWN"))

    def assertion(row):
        _keys(row, "target trigger_sha256 rule_reference_sha256 citations")
        _enum(row["target"], TARGETS)
        nullable_hash(row["trigger_sha256"])
        nullable_hash(row["rule_reference_sha256"])
        def citation(c):
            _keys(c, "owner evidence_id start end")
            _enum(c["owner"], OWNERS)
            _id(c["evidence_id"])
            _nat(c["start"])
            _nat(c["end"], 1)
            return OWNERS.index(c["owner"]), c["evidence_id"], c["start"], c["end"]
        _ordered(row["citations"], citation)
        return TARGETS.index(row["target"])
    _ordered(q["support_assertions"], assertion)
    if upstream_contexts is not None:
        _keys(upstream_contexts, "c8_context_json c10_context_json comparison_context_json")
        for value in upstream_contexts.values():
            if value is not None:
                _bytes(value)
    if context is not None:
        _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 "
                       "upstream_contexts_sha256 admitted_at available_at effective_from effective_until receipts")
        _enum(context["contract"], (ADMISSION_CONTRACT,))
        _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
        _id(context["admission_id"])
        _namespace(context["authority_namespace"])
        _text(context["authority_id"])
        _text(context["mandate_id"])
        _nat(context["mandate_revision"], 1)
        _hash(context["request_sha256"])
        nullable_hash(context["upstream_contexts_sha256"])
        for field in ("admitted_at", "available_at", "effective_from"):
            _time(context[field])
        if context["effective_until"] is not None:
            _time(context["effective_until"])
        def receipt(row):
            _keys(row, "target request_sha256 upstream_contexts_sha256 assertion_sha256 originals decision")
            _enum(row["target"], TARGETS)
            _hash(row["request_sha256"])
            nullable_hash(row["upstream_contexts_sha256"])
            nullable_hash(row["assertion_sha256"])
            _ordered(row["originals"], member)
            _enum(row["decision"], ("ADMITTED", "UNRESOLVED"))
            return TARGETS.index(row["target"])
        _ordered(context["receipts"], receipt)


def _contexts(value):
    fields = ("c8_context_json", "c10_context_json", "comparison_context_json")
    if value is None:
        return (None, None, None)
    _keys(value, fields)
    return tuple(None if value[f] is None else _decode(value[f]) for f in fields)


def _replay(q, contexts):
    ctx8, ctx10, comparison_context = contexts
    dependency = q["comparison"]
    if dependency is None:
        if any(c is not None for c in contexts):
            raise ValueError()
        return {}, None
    _keys(dependency, "owner request_json result_json")
    owner = _enum(dependency["owner"], ("C9", "C11"))
    original, supplied = _decode(dependency["request_json"]), _decode(dependency["result_json"])
    if owner == "C9":
        if ctx10 is not None:
            raise ValueError()
        result = c9_owner.validate_as_of_equity_trailing_loss_threshold_comparison(
            supplied, original, trusted_c8_context=ctx8, trusted_equity_context=comparison_context)
        requests = {"C9": original}
        if original["c8"] is not None:
            requests["C8"] = _decode(original["c8"]["request_json"])
    else:
        result = c11_owner.validate_as_of_equity_daily_reset_loss_floor_comparison(
            supplied, original, trusted_c8_context=ctx8, trusted_c10_context=ctx10,
            trusted_context=comparison_context)
        requests = {"C11": original}
        if original["c10"] is not None:
            q10 = requests["C10"] = _decode(original["c10"]["request_json"])
            if q10["c8"] is not None:
                requests["C8"] = _decode(q10["c8"]["request_json"])
    for field in ("scope", "economic_time", "knowledge_boundary"):
        _same(original[field], q[field])
    return requests, result


def _references(q, requests, comparison):
    if comparison is None:
        return dict(comparison=None, account_snapshot=None), None
    owner = q["comparison"]["owner"]
    reference = dict(owner=owner, assessment_identity=comparison["assessment_identity"],
                     outcome=comparison["outcome"], bundle_sha256=_digest(q["comparison"]))
    native = dict(comparison=reference, account_snapshot=deepcopy(comparison["native_references"]["account_snapshot"]))
    if comparison["outcome"] != "ESTABLISHED":
        return native, None
    rule = dict(comparison_owner=owner, comparison_assessment_identity=comparison["assessment_identity"],
                comparison_bundle_sha256=reference["bundle_sha256"],
                equity_declaration_sha256=_digest(requests[owner]["equity"]))
    if owner == "C9":
        q9, q8 = requests["C9"], requests["C8"]
        r8 = _decode(q9["c8"]["result_json"])
        selector = q8["history"]["rule"]
        original = _decode(q8["provider_regime"]["input_json"])
        package = original["manifest"]["packages"][selector["package_index"]]
        native_rule = package["rules"][selector["rule_index"]]
        rule.update(threshold_owner="C8", threshold_assessment_identity=r8["assessment_identity"],
                    threshold_bundle_sha256=_digest(q9["c8"]), regime_bundle_sha256=_digest(q8["provider_regime"]),
                    assignment_id=selector["assignment_id"], package_index=selector["package_index"],
                    package_id=package["package_id"], package_revision=package["package_revision"],
                    rule_index=selector["rule_index"], rule_id=native_rule["rule_id"],
                    native_rule_sha256=selector["native_rule_sha256"], model_binding_sha256=_digest(selector),
                    native_measure_sha256=None, reset_session=None)
    else:
        measure = comparison["daily_measure"]
        rule.update(threshold_owner="C10", threshold_assessment_identity=measure["c10_assessment_identity"],
                    threshold_bundle_sha256=measure["c10_bundle_sha256"],
                    regime_bundle_sha256=measure["daily_regime_bundle_sha256"],
                    model_binding_sha256=_digest(measure), native_measure_sha256=measure["measure_sha256"],
                    reset_session=dict(reset_boundary=comparison["state"]["reset_boundary"],
                                       next_reset_boundary=comparison["state"]["next_reset_boundary"]))
        for field in ("assignment_id", "package_index", "package_id", "package_revision", "rule_index", "rule_id", "native_rule_sha256"):
            rule[field] = measure[field]
    return native, rule


def _document_keys(row):
    document = row["document"]
    family = _ns(document["namespace"]), document["document_id"]
    version = family, document["document_revision"]
    return family, version, (tuple(row["source"][f] for f in SOURCE_FIELDS), version)


def _inventory(q, requests):
    def local_key(row):
        _keys(row, "evidence_id source document media_type content content_sha256 source_available_at observed_at")
        return _id(row["evidence_id"])
    _ordered(q["originals"], local_key)
    if len(q["originals"]) > 4:
        raise ValueError()
    originals, locations, families, captures, versions, imported_captures = {}, {}, {}, {}, {}, set()
    members = []
    for owner in OWNERS:
        rows = q["originals"] if owner == "C12" else requests.get(owner, {}).get("originals", [])
        for i, row in enumerate(rows):
            local_key(row)
            _keys(row["source"], SOURCE_FIELDS)
            for value in row["source"].values():
                _text(value)
            document = row["document"]
            _keys(document, "namespace document_id document_revision")
            if _namespace(document["namespace"]) != _ns(row["source"]):
                raise ValueError()
            _text(document["document_id"])
            if document["document_revision"] is not None:
                _text(document["document_revision"])
            raw = _bytes(row["content"])
            if (owner == "C12" and not raw) or hashlib.sha256(raw).hexdigest() != _hash(row["content_sha256"]):
                raise ValueError()
            content = raw, _text(row["media_type"])
            family, version, capture = _document_keys(row)
            if document["document_revision"] is not None:
                if version in versions and versions[version] != content:
                    raise ValueError()
                versions[version] = content
            envelope = {k: v for k, v in row.items() if k != "evidence_id"}
            if capture in captures:
                _same(envelope, captures[capture])
            if owner == "C12" and capture in imported_captures:
                raise ValueError()
            if owner != "C12":
                imported_captures.add(capture)
            captures[capture] = envelope
            families.setdefault(family, set()).add(document["document_revision"])
            observed, publication = _time(row["observed_at"]), row["source_available_at"]
            if observed > q["knowledge_boundary"] or (publication is not None and _time(publication) > observed):
                raise ValueError()
            key = owner, row["evidence_id"]
            if key in originals:
                raise ValueError()
            originals[key] = row
            locations[key] = ("REQUEST" if owner == "C12" else owner + "_REQUEST", f"/originals/{i}")
            members.append(dict(owner=owner, evidence_id=row["evidence_id"], original_sha256=_digest(row)))
    members.sort(key=lambda row: (OWNERS.index(row["owner"]), row["evidence_id"]))
    return members, originals, locations, families


def _member(row, originals):
    _keys(row, "owner evidence_id original_sha256")
    owner = _enum(row["owner"], OWNERS)
    key = owner, _id(row["evidence_id"])
    if key not in originals or _hash(row["original_sha256"]) != _digest(originals[key]):
        raise ValueError()
    return key


def _roles(q, originals):
    _keys(q["roles"], ROLES)
    keys = {}
    for role in ROLES:
        ref = q["roles"][role]
        if ref is None:
            continue
        key = keys[role] = _member(ref, originals)
        allowed = {_ns(q["scope"]["provider_namespace"])}
        if role in ("account_applicability", "measure_equivalence"):
            allowed.add(_ns(q["scope"]["account"]["namespace"]))
        if role != "source_validity" and _ns(originals[key]["source"]) not in allowed:
            raise ValueError()
    if any(("C12", row["evidence_id"]) not in keys.values() for row in q["originals"]):
        raise ValueError()
    return keys


def _trigger(q, native, rule):
    trigger = q["trigger"]
    if trigger is None:
        return
    _keys(trigger, "scope economic_time knowledge_boundary rule_reference_sha256 effective_period force permitted_when "
                   "measure_equivalence event conditions source_review")
    _scope(trigger["scope"])
    for field in ("scope", "economic_time", "knowledge_boundary"):
        _same(trigger[field], q[field])
    _same(trigger["rule_reference_sha256"], None if rule is None else _digest(rule))
    period = trigger["effective_period"]
    _keys(period, "effective_from effective_until end_status")
    status = _enum(period["end_status"], ("KNOWN", "OPEN_ENDED", "UNKNOWN"))
    if period["effective_from"] is not None:
        _time(period["effective_from"])
    if status == "KNOWN":
        _time(period["effective_until"])
        if period["effective_from"] is not None and period["effective_from"] >= period["effective_until"]:
            raise ValueError()
    elif period["effective_until"] is not None:
        raise ValueError()
    _enum(trigger["force"], ("MANDATORY", "NON_MANDATORY", "UNKNOWN"))
    _enum(trigger["permitted_when"], ("GREATER_THAN_OR_EQUAL", "GREATER_THAN", "UNKNOWN"))
    if q["comparison"] is not None and q["comparison"]["owner"] == "C11" and trigger["permitted_when"] == "GREATER_THAN":
        raise ValueError()
    _enum(trigger["measure_equivalence"], ("EXACT", "DIFFERENT", "UNKNOWN"))
    event = trigger["event"]
    _keys(event, "mode snapshot_reference_sha256")
    _enum(event["mode"], ("ACCOUNT_EQUITY_OBSERVATION_AT_T", "OTHER", "UNKNOWN"))
    snapshot = native["account_snapshot"]
    _same(event["snapshot_reference_sha256"], None if snapshot is None else _digest(snapshot))
    _keys(trigger["conditions"], CONDITIONS)
    for field in CONDITIONS:
        _enum(trigger["conditions"][field], ("NONE", "REQUIRED", "UNKNOWN"))
    review = trigger["source_review"]
    _keys(review, "complete_through_cutoff relevant_revisions known_relevant_corrections")
    _enum(review["complete_through_cutoff"], ("COMPLETE", "UNKNOWN"))
    for field in ("relevant_revisions", "known_relevant_corrections"):
        _enum(review[field], ("NONE", "PRESENT", "UNKNOWN"))


def _support(q, originals, rule):
    def key(row):
        _keys(row, "target trigger_sha256 rule_reference_sha256 citations")
        target = _enum(row["target"], TARGETS)
        _same(row["trigger_sha256"], None if q["trigger"] is None else _digest(q["trigger"]))
        _same(row["rule_reference_sha256"], None if rule is None else _digest(rule))
        def citation_key(c):
            _keys(c, "owner evidence_id start end")
            owner, identifier = _enum(c["owner"], OWNERS), _id(c["evidence_id"])
            start, end = _nat(c["start"]), _nat(c["end"], 1)
            if (owner, identifier) not in originals or not start < end <= len(_bytes(originals[(owner, identifier)]["content"])):
                raise ValueError()
            return OWNERS.index(owner), identifier, start, end
        _ordered(row["citations"], citation_key)
        return TARGETS.index(target)
    _ordered(q["support_assertions"], key)
    return {row["target"]: row for row in q["support_assertions"]}


def _required_support(q, requests, comparison, roles):
    bound, measure, aggregate, coverage = set(), set(), set(), set()
    if comparison is not None and comparison["outcome"] == "ESTABLISHED":
        owner = q["comparison"]["owner"]
        source, q8 = requests[owner], requests["C8"]
        coverage.add(("C8", q8["history"]["coverage"]["report"]["evidence_id"]))
        if owner == "C9":
            bound = {("C8", c["evidence_id"]) for c in q8["history"]["rule"]["citations"]}
            refs = source["equity"]["originals"]
        else:
            daily = comparison["daily_measure"]
            bound = {(daily["rule_original"]["owner"], daily["rule_original"]["evidence_id"])}
            measure = {(d["original"]["owner"], d["original"]["evidence_id"]) for d in daily["definition_bindings"]}
            coverage.add(("C10", requests["C10"]["roles"]["coverage"]["evidence_id"]))
            refs = source["equity"]["roles"]
        aggregate.add((owner, refs["aggregate"]["evidence_id"]))
        measure.update((owner, refs[role]["evidence_id"]) for role in ("aggregate", "definition"))
        coverage.add((owner, refs["coverage"]["evidence_id"]))
    def selected(*names):
        return {roles[name] for name in names if name in roles}
    return (selected("mandatory_trigger", "account_applicability") | bound,
            selected("mandatory_trigger", "measure_equivalence") | bound,
            selected("measure_equivalence") | measure,
            selected("account_applicability", "measure_equivalence") | aggregate,
            set(roles.values()) | coverage)


def _native_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _chronology(q, requests, contexts, originals, roles):
    observations = [row["observed_at"] for row in originals.values()]
    cutoffs = []
    for owner in OWNERS[:-1]:
        if owner not in requests:
            continue
        source = requests[owner]
        if source.get("source_information_cutoff") is not None:
            cutoffs.append(source["source_information_cutoff"])
        if owner == "C8" and source["history"] is not None and source["history"]["coverage"] is not None:
            cutoff = source["history"]["coverage"]["source_information_cutoff"]
            if cutoff is not None:
                cutoffs.append(cutoff)
        if owner == "C9" and source["equity"] is not None and source["equity"]["source_information_cutoff"] is not None:
            cutoffs.append(source["equity"]["source_information_cutoff"])
        if source.get("account_snapshot") is not None:
            account = _decode(source["account_snapshot"]["result_json"])
            observations.append(_native_time(account["observation"]["timing"]["observed_at"]))
        for field in ("provider_regime", "daily_regime"):
            if source.get(field) is None:
                continue
            regime = _decode(source[field]["input_json"])
            observations.append(_native_time(regime["manifest"]["timing"]["observed_at"]))
            observations.extend(_native_time(row["timing"]["observed_at"]) for row in regime["manifest"]["evidence"])
            observations.extend(_native_time(row["observed_at"]) for row in regime["approvals"])
            cutoff = regime["manifest"]["coverage"]["source_information_cutoff"]
            if cutoff is not None:
                cutoffs.append(_native_time(cutoff))
    observations.extend(context["available_at"] for context in contexts if context is not None)
    if "source_validity" in roles:
        capture = _document_keys(originals[roles["source_validity"]])[2]
        for row in originals.values():
            if _document_keys(row)[2] == capture:
                cutoff = q["source_information_cutoff"]
                if row["observed_at"] < cutoff or (row["source_available_at"] is not None and row["source_available_at"] < cutoff):
                    raise ValueError()
    return observations, cutoffs


def _context(context, q, upstream_contexts, observations, assertions, originals):
    if context is None:
        return {}
    _keys(context, "contract rule_version admission_id authority_namespace authority_id mandate_id mandate_revision request_sha256 "
                   "upstream_contexts_sha256 admitted_at available_at effective_from effective_until receipts")
    _enum(context["contract"], (ADMISSION_CONTRACT,))
    _enum(context["rule_version"], (ADMISSION_RULE_VERSION,))
    _id(context["admission_id"])
    _namespace(context["authority_namespace"])
    _text(context["authority_id"])
    _text(context["mandate_id"])
    _nat(context["mandate_revision"], 1)
    _same(context["request_sha256"], _digest(q))
    _same(context["upstream_contexts_sha256"], None if upstream_contexts is None else _digest(upstream_contexts))
    for field in ("admitted_at", "available_at", "effective_from"):
        _time(context[field])
    end = context["effective_until"]
    if end is not None and _time(end) <= context["effective_from"]:
        raise ValueError()
    if context["admitted_at"] > context["available_at"] or any(o > context["admitted_at"] for o in observations):
        raise ValueError()
    def key(receipt):
        _keys(receipt, "target request_sha256 upstream_contexts_sha256 assertion_sha256 originals decision")
        target = _enum(receipt["target"], TARGETS)
        for field in ("request_sha256", "upstream_contexts_sha256"):
            _same(receipt[field], context[field])
        _same(receipt["assertion_sha256"], None if target not in assertions else _digest(assertions[target]))
        def member_key(member):
            owner, identifier = _member(member, originals)
            return OWNERS.index(owner), identifier
        _ordered(receipt["originals"], member_key)
        _enum(receipt["decision"], ("ADMITTED", "UNRESOLVED"))
        return TARGETS.index(target)
    _ordered(context["receipts"], key)
    return {r["target"]: (i, r) for i, r in enumerate(context["receipts"])}


def _finding(code, pointer, root="REQUEST"):
    return dict(reason_code=code, subject=dict(root=root, pointer=pointer))


def _unknown(q, comparison, inventory, roles, cutoffs, required, assertions, context, receipts):
    members, originals, locations, families = inventory
    if q["comparison"] is None:
        return _finding("COMPARISON_MISSING", "/comparison")
    if comparison["outcome"] != "ESTABLISHED":
        return _finding("COMPARISON_NOT_ESTABLISHED", "/comparison")
    trigger = q["trigger"]
    if trigger is None:
        return _finding("TRIGGER_MISSING", "/trigger")
    for role in ROLES:
        if role not in roles:
            return _finding("ORIGINAL_ROLE_MISSING", "/roles/" + role)
    for member in members:
        key = member["owner"], member["evidence_id"]
        if originals[key]["document"]["document_revision"] is None:
            root, pointer = locations[key]
            return _finding("DOCUMENT_REVISION_UNKNOWN", pointer + "/document/document_revision", root)
    for member in members:
        key = member["owner"], member["evidence_id"]
        if len(families[_document_keys(originals[key])[0]] - {None}) > 1:
            root, pointer = locations[key]
            return _finding("DOCUMENT_REVISIONS_UNRESOLVED", pointer + "/document", root)
    for member in members:
        key = member["owner"], member["evidence_id"]
        if originals[key]["source_available_at"] is None:
            root, pointer = locations[key]
            return _finding("ORIGINAL_AVAILABILITY_UNKNOWN", pointer + "/source_available_at", root)
    operational = {_document_keys(originals[roles[role]])[2] for role in ROLES[:-1]}
    cutoff = q["source_information_cutoff"]
    if (any(c > cutoff for c in cutoffs) or
            any(row["source_available_at"] > cutoff for row in originals.values() if _document_keys(row)[2] in operational)):
        return _finding("SOURCE_CUTOFF_INSUFFICIENT", "/source_information_cutoff")
    for field, expected in (("complete_through_cutoff", "COMPLETE"), ("relevant_revisions", "NONE"), ("known_relevant_corrections", "NONE")):
        if trigger["source_review"][field] != expected:
            return _finding("SOURCE_REVIEW_UNRESOLVED", "/trigger/source_review/" + field)
    period, t = trigger["effective_period"], q["economic_time"]
    if (period["effective_from"] is None or period["effective_from"] > t or period["end_status"] == "UNKNOWN" or
            (period["end_status"] == "KNOWN" and period["effective_until"] <= t)):
        return _finding("RULE_NOT_APPLICABLE", "/trigger/effective_period")
    if trigger["force"] != "MANDATORY":
        return _finding("RULE_FORCE_UNRESOLVED", "/trigger/force")
    if trigger["permitted_when"] == "UNKNOWN":
        return _finding("COMPARATOR_UNDECLARED", "/trigger/permitted_when")
    if trigger["event"]["mode"] != "ACCOUNT_EQUITY_OBSERVATION_AT_T":
        return _finding("EVENT_SEMANTICS_UNSUPPORTED", "/trigger/event/mode")
    for field in CONDITIONS:
        if trigger["conditions"][field] != "NONE":
            return _finding("EVENT_SEMANTICS_UNSUPPORTED", "/trigger/conditions/" + field)
    if trigger["measure_equivalence"] != "EXACT":
        return _finding("MEASURE_EQUIVALENCE_UNRESOLVED", "/trigger/measure_equivalence")
    for target, support in zip(TARGETS, required):
        cited = set() if target not in assertions else {(c["owner"], c["evidence_id"]) for c in assertions[target]["citations"]}
        if target not in assertions or not support <= cited:
            return _finding("SUPPORT_INCOMPLETE", "/support_assertions")
    if context is None:
        return _finding("ADMISSION_MISSING", "", "TRUSTED_CONTEXT")
    k = q["knowledge_boundary"]
    for field, failed in (("available_at", context["available_at"] > k),
                          ("effective_from", context["effective_from"] > min(context["admitted_at"], k)),
                          ("effective_until", context["effective_until"] is not None and context["effective_until"] <= max(context["admitted_at"], k))):
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


def _evaluate(request, trusted_upstream_contexts, trusted_context):
    for value in (request, trusted_upstream_contexts, trusted_context):
        _canonical(value)
    q, upstream_contexts, context = deepcopy((request, trusted_upstream_contexts, trusted_context))
    _keys(q, "contract rule_version economic_time knowledge_boundary source_information_cutoff scope comparison trigger originals roles support_assertions")
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    if not _time(q["economic_time"]) <= _time(q["source_information_cutoff"]) <= _time(q["knowledge_boundary"]):
        raise ValueError()
    _scope(q["scope"])
    _preflight(q, upstream_contexts, context)
    contexts = _contexts(upstream_contexts)
    requests, comparison = _replay(q, contexts)
    native, rule = _references(q, requests, comparison)
    inventory = _inventory(q, requests)
    members, originals, _, _ = inventory
    roles = _roles(q, originals)
    _trigger(q, native, rule)
    assertions = _support(q, originals, rule)
    required = _required_support(q, requests, comparison, roles)
    observations, cutoffs = _chronology(q, requests, contexts, originals, roles)
    receipts = _context(context, q, upstream_contexts, observations, assertions, originals)
    finding = _unknown(q, comparison, inventory, roles, cutoffs, required, assertions, context, receipts)
    state = None
    if finding is None:
        upstream_state = comparison["state"]
        permitted = q["trigger"]["permitted_when"]
        met = upstream_state["relation"] == "BELOW" or (upstream_state["relation"] == "EQUAL" and permitted == "GREATER_THAN")
        state = dict(as_of=q["economic_time"], currency=q["scope"]["account"]["currency"],
                     comparison_assessment_identity=comparison["assessment_identity"], rule_reference_sha256=_digest(rule),
                     relation=upstream_state["relation"], difference=upstream_state["difference"], permitted_when=permitted,
                     breach_when="LESS_THAN" if permitted == "GREATER_THAN_OR_EQUAL" else "LESS_THAN_OR_EQUAL",
                     condition="BREACH_CONDITION_MET" if met else "BREACH_CONDITION_NOT_MET")
    bindings = [dict(target=t, assertion_sha256=None if t not in assertions else _digest(assertions[t]),
                     receipt_sha256=None if t not in receipts else _digest(receipts[t][1]), originals=deepcopy(members)) for t in TARGETS]
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, temporal_scope=TEMPORAL_SCOPE,
                  economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"],
                  source_information_cutoff=q["source_information_cutoff"], scope=q["scope"],
                  outcome="ESTABLISHED" if finding is None else "UNKNOWN",
                  reason_codes=[state["condition"] if finding is None else finding["reason_code"]],
                  findings=[] if finding is None else [finding], state=state, native_references=native, rule_reference=rule,
                  required_targets=list(TARGETS), admission_bindings=bindings,
                  reconstruction_evidence=dict(request=q, request_sha256=_digest(q),
                      upstream_contexts_sha256=None if upstream_contexts is None else _digest(upstream_contexts),
                      trusted_context_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, limitations=list(LIMITATIONS), authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_as_of_historical_loss_limit_breach_condition_witness(
    request, *, trusted_upstream_contexts=None, trusted_context=None,
) -> dict:
    """Replay one comparison and independently admitted instantaneous semantics."""
    try:
        return deepcopy(_evaluate(request, trusted_upstream_contexts, trusted_context))
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError,
            UnicodeError, binascii.Error, StopIteration) as exc:
        raise ValueError("INVALID_HISTORICAL_LOSS_LIMIT_WITNESS_INPUT") from exc


def validate_as_of_historical_loss_limit_breach_condition_witness(
    result, request, *, trusted_upstream_contexts=None, trusted_context=None,
) -> dict:
    """Genuinely replay the dependency and reconstruct every type-sensitive field."""
    expected = evaluate_as_of_historical_loss_limit_breach_condition_witness(
        request, trusted_upstream_contexts=trusted_upstream_contexts, trusted_context=trusted_context)
    try:
        if type(result) is not dict or _canonical(result) != _canonical(expected):
            raise ValueError()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("HISTORICAL_LOSS_LIMIT_WITNESS_RESULT_MISMATCH") from exc
    return deepcopy(expected)
