"""C12 contract witnesses; every positive C9/C11/native replay is real.

Provider documents, account identities and independent admissions are synthetic.
Rebinding a fixture supplies new synthetic admission, not an owner-result mock.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from ced_one.business_divisions.trading import as_of_historical_loss_limit_breach_condition_witness as c12
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f9 = load("c12_c9_witness", "test_as_of_equity_trailing_loss_threshold_comparison.py")
f11 = load("c12_c11_witness", "test_as_of_equity_daily_reset_loss_floor_comparison.py")
OWNERS = ("C8", "C9", "C10", "C11", "C12")
ROLES = ("mandatory_trigger", "account_applicability", "measure_equivalence", "source_validity")
TARGETS = ("ACCOUNT_AND_RULE_BINDING", "INSTANTANEOUS_TRIGGER", "MEASURE_EQUIVALENCE",
           "OBSERVATION_APPLICABILITY", "SOURCE_VALIDITY")
FLAGS = ("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval",
         "trade_decision", "financial_risk", "execution")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def encoded(value):
    return base64.b64encode(canonical(value).encode()).decode()


def decoded(value):
    return json.loads(base64.b64decode(value))


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def at(case, *, minutes=0, boundary="knowledge_boundary"):
    return stamp(datetime.fromisoformat(case[0][boundary].replace("Z", "+00:00")) + timedelta(minutes=minutes))


def dependencies(case):
    q = case[0]
    if q["comparison"] is None:
        return {}, None
    owner = q["comparison"]["owner"]
    result = decoded(q["comparison"]["result_json"])
    request = decoded(q["comparison"]["request_json"])
    requests = {owner: request}
    if owner == "C9":
        if request["c8"] is not None:
            requests["C8"] = decoded(request["c8"]["request_json"])
    elif request["c10"] is not None:
        requests["C10"] = decoded(request["c10"]["request_json"])
        if requests["C10"]["c8"] is not None:
            requests["C8"] = decoded(requests["C10"]["c8"]["request_json"])
    return requests, result


def inventory(case):
    requests, _ = dependencies(case)
    requests["C12"] = case[0]
    return [(owner, row) for owner in OWNERS for row in requests.get(owner, {}).get("originals", [])]


def members(case):
    return [dict(owner=owner, evidence_id=row["evidence_id"], original_sha256=digest(row))
            for owner, row in sorted(inventory(case), key=lambda x: (OWNERS.index(x[0]), x[1]["evidence_id"]))]


def rule_reference(case):
    """Independent fixture construction from original serialized dependencies."""
    q = case[0]
    requests, result = dependencies(case)
    if result is None or result["outcome"] != "ESTABLISHED":
        return None
    owner = q["comparison"]["owner"]
    ref = dict(comparison_owner=owner, comparison_assessment_identity=result["assessment_identity"],
               comparison_bundle_sha256=digest(q["comparison"]), equity_declaration_sha256=digest(requests[owner]["equity"]))
    if owner == "C9":
        q9, q8 = requests["C9"], requests["C8"]
        r8 = decoded(q9["c8"]["result_json"])
        s = q8["history"]["rule"]
        native = decoded(q8["provider_regime"]["input_json"])
        package = native["manifest"]["packages"][s["package_index"]]
        rule = package["rules"][s["rule_index"]]
        ref.update(threshold_owner="C8", threshold_assessment_identity=r8["assessment_identity"], threshold_bundle_sha256=digest(q9["c8"]),
            regime_bundle_sha256=digest(q8["provider_regime"]), assignment_id=s["assignment_id"], package_index=s["package_index"],
            package_id=package["package_id"], package_revision=package["package_revision"], rule_index=s["rule_index"], rule_id=rule["rule_id"],
            native_rule_sha256=digest(rule), model_binding_sha256=digest(s), native_measure_sha256=None, reset_session=None)
    else:
        m = result["daily_measure"]
        ref.update(threshold_owner="C10", threshold_assessment_identity=m["c10_assessment_identity"], threshold_bundle_sha256=m["c10_bundle_sha256"],
            regime_bundle_sha256=m["daily_regime_bundle_sha256"], model_binding_sha256=digest(m), native_measure_sha256=m["measure_sha256"],
            reset_session=dict(reset_boundary=result["state"]["reset_boundary"], next_reset_boundary=result["state"]["next_reset_boundary"]))
        ref.update({k: m[k] for k in ("assignment_id", "package_index", "package_id", "package_revision", "rule_index", "rule_id", "native_rule_sha256")})
    return ref


def required_support(case):
    q = case[0]
    requests, result = dependencies(case)
    role = {r: (ref["owner"], ref["evidence_id"]) for r, ref in q["roles"].items() if ref is not None}
    b, m, a, u = set(), set(), set(), set()
    if result is not None and result["outcome"] == "ESTABLISHED":
        owner, q8 = q["comparison"]["owner"], requests["C8"]
        u.add(("C8", q8["history"]["coverage"]["report"]["evidence_id"]))
        if owner == "C9":
            b = {("C8", c["evidence_id"]) for c in q8["history"]["rule"]["citations"]}
            refs = requests[owner]["equity"]["originals"]
        else:
            d = result["daily_measure"]
            b = {(d["rule_original"]["owner"], d["rule_original"]["evidence_id"])}
            m = {(x["original"]["owner"], x["original"]["evidence_id"]) for x in d["definition_bindings"]}
            u.add(("C10", requests["C10"]["roles"]["coverage"]["evidence_id"]))
            refs = requests[owner]["equity"]["roles"]
        a.add((owner, refs["aggregate"]["evidence_id"]))
        m.update((owner, refs[r]["evidence_id"]) for r in ("aggregate", "definition"))
        u.add((owner, refs["coverage"]["evidence_id"]))
    def r(*names):
        return {role[n] for n in names if n in role}
    return [r("mandatory_trigger", "account_applicability") | b, r("mandatory_trigger", "measure_equivalence") | b,
            r("measure_equivalence") | m, r("account_applicability", "measure_equivalence") | a, set(role.values()) | u]


def build_support(case):
    q = case[0]
    originals = {(owner, row["evidence_id"]): row for owner, row in inventory(case)}
    ref = rule_reference(case)
    q["support_assertions"] = [dict(target=target, trigger_sha256=None if q["trigger"] is None else digest(q["trigger"]),
        rule_reference_sha256=None if ref is None else digest(ref), citations=[dict(owner=owner, evidence_id=identifier, start=0,
            end=len(base64.b64decode(originals[(owner, identifier)]["content"]))) for owner, identifier in sorted(required, key=lambda x: (OWNERS.index(x[0]), x[1]))])
        for target, required in zip(TARGETS, required_support(case))]


def seal(case):
    """Issue synthetic host admission without silently repairing evidence bytes."""
    q, upstream_contexts, context = case
    index = {(m["owner"], m["evidence_id"]): m for m in members(case)}
    for ref in q["roles"].values():
        if ref is not None and (ref["owner"], ref["evidence_id"]) in index:
            ref["original_sha256"] = index[(ref["owner"], ref["evidence_id"])]["original_sha256"]
    rule = rule_reference(case)
    _, result = dependencies(case)
    if q["trigger"] is not None:
        q["trigger"]["rule_reference_sha256"] = None if rule is None else digest(rule)
        snapshot = None if result is None else result["native_references"]["account_snapshot"]
        q["trigger"]["event"]["snapshot_reference_sha256"] = None if snapshot is None else digest(snapshot)
    for assertion in q["support_assertions"]:
        assertion.update(trigger_sha256=None if q["trigger"] is None else digest(q["trigger"]),
                         rule_reference_sha256=None if rule is None else digest(rule))
    if context is not None:
        context.update(request_sha256=digest(q), upstream_contexts_sha256=None if upstream_contexts is None else digest(upstream_contexts))
        assertions = {a["target"]: a for a in q["support_assertions"]}
        context["receipts"] = [dict(target=t, request_sha256=digest(q), upstream_contexts_sha256=context["upstream_contexts_sha256"],
            assertion_sha256=None if t not in assertions else digest(assertions[t]), originals=members(case), decision="ADMITTED") for t in TARGETS]
    return case


def replace_upstream(case, upstream_case):
    owner = case[0]["comparison"]["owner"]
    f = f9 if owner == "C9" else f11
    result = f.run(upstream_case)
    case[0]["comparison"].update(request_json=encoded(upstream_case[0]), result_json=encoded(result))
    case[1] = dict(c8_context_json=None if upstream_case[1] is None else encoded(upstream_case[1]),
        c10_context_json=None if owner == "C9" or upstream_case[2] is None else encoded(upstream_case[2]),
        comparison_context_json=None if upstream_case[-1] is None else encoded(upstream_case[-1]))
    build_support(case)
    return seal(case)


def upstream_case(case):
    q = decoded(case[0]["comparison"]["request_json"])
    u = case[1]
    contexts = [None if u[k] is None else decoded(u[k]) for k in ("c8_context_json", "c10_context_json", "comparison_context_json")]
    return [q, contexts[0], contexts[2]] if case[0]["comparison"]["owner"] == "C9" else [q, *contexts]


def sample(owner="C9", equity=None, comparator="GREATER_THAN_OR_EQUAL"):
    f = f9 if owner == "C9" else f11
    upstream = f.sample(equity or ("899" if owner == "C9" else "969.99"))
    result = f.run(upstream)
    q = dict(contract=c12.CONTRACT, rule_version=c12.RULE_VERSION, economic_time=upstream[0]["economic_time"],
        knowledge_boundary=upstream[0]["knowledge_boundary"], source_information_cutoff="", scope=deepcopy(upstream[0]["scope"]),
        comparison=dict(owner=owner, request_json=encoded(upstream[0]), result_json=encoded(result)), trigger=None,
        originals=[], roles=dict.fromkeys(ROLES), support_assertions=[])
    u = dict(c8_context_json=encoded(upstream[1]), c10_context_json=None if owner == "C9" else encoded(upstream[2]), comparison_context_json=encoded(upstream[-1]))
    ctx = dict(contract=c12.ADMISSION_CONTRACT, rule_version=c12.ADMISSION_RULE_VERSION, admission_id="synthetic-c12",
        authority_namespace=deepcopy(q["scope"]["provider_namespace"]), authority_id="independent-synthetic-host", mandate_id="synthetic-c12-review", mandate_revision=1,
        request_sha256="", upstream_contexts_sha256="", admitted_at="", available_at="", effective_from="", effective_until=None, receipts=[])
    case = [q, u, ctx]
    q["source_information_cutoff"] = at(case, minutes=-25)
    requests, _ = dependencies(case)
    period = (dict(effective_from=requests["C8"]["history"]["inception"], effective_until=None, end_status="OPEN_ENDED") if owner == "C9" else
              dict(effective_from=result["state"]["reset_boundary"], effective_until=result["state"]["next_reset_boundary"], end_status="KNOWN"))
    ref = rule_reference(case)
    q["trigger"] = dict(scope=deepcopy(q["scope"]), economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"],
        rule_reference_sha256=digest(ref), effective_period=period, force="MANDATORY", permitted_when=comparator, measure_equivalence="EXACT",
        event=dict(mode="ACCOUNT_EQUITY_OBSERVATION_AT_T", snapshot_reference_sha256=digest(result["native_references"]["account_snapshot"])),
        conditions=dict.fromkeys(("duration", "grace", "confirmation", "provider_decision"), "NONE"),
        source_review=dict(complete_through_cutoff="COMPLETE", relevant_revisions="NONE", known_relevant_corrections="NONE"))
    for role in ROLES:
        raw = canonical(dict(synthetic=True, role=role, scope=q["scope"], rule_reference=ref, trigger=q["trigger"],
            statement="Exact selected mandatory rule; this account-wide equity valuation at T is sufficient. The comparator is exactly the declared one. No additional duration, grace, confirmation, provider decision or exception applies. Measure and source versions are complete and independently reviewed.")).encode()
        source = dict(**q["scope"]["provider_namespace"], source_snapshot_id="synthetic-c12-" + role)
        q["originals"].append(dict(evidence_id=role, source=source, document=dict(namespace=deepcopy(q["scope"]["provider_namespace"]),
            document_id="synthetic-c12-" + role, document_revision="1"), media_type="application/json", content=base64.b64encode(raw).decode(),
            content_sha256=hashlib.sha256(raw).hexdigest(), source_available_at=at(case, minutes=-24 if role == "source_validity" else -30),
            observed_at=at(case, minutes=-23 if role == "source_validity" else -29)))
    q["originals"].sort(key=lambda row: row["evidence_id"])
    q["roles"] = {r: dict(owner="C12", evidence_id=r, original_sha256=digest(next(o for o in q["originals"] if o["evidence_id"] == r))) for r in ROLES}
    ctx.update(admitted_at=at(case, minutes=-20), available_at=at(case, minutes=-19), effective_from=period["effective_from"])
    build_support(case)
    return seal(case)


def run(case):
    return c12.evaluate_as_of_historical_loss_limit_breach_condition_witness(case[0], trusted_upstream_contexts=case[1], trusted_context=case[2])


def validate(result, case):
    return c12.validate_as_of_historical_loss_limit_breach_condition_witness(result, case[0], trusted_upstream_contexts=case[1], trusted_context=case[2])


def invalid(case):
    with pytest.raises(ValueError, match="^INVALID_HISTORICAL_LOSS_LIMIT_WITNESS_INPUT$"):
        run(case)


def original(case, role):
    return next(o for o in case[0]["originals"] if o["evidence_id"] == role)


def rehash_result(result):
    result["assessment_identity"] = c12.IDENTITY_PREFIX + digest({k: v for k, v in result.items() if k != "assessment_identity"})


@pytest.mark.parametrize("owner,equity,comparator,met", [
    ("C9", "899", "GREATER_THAN_OR_EQUAL", True), ("C9", "899", "GREATER_THAN", True),
    ("C9", "900", "GREATER_THAN_OR_EQUAL", False), ("C9", "900", "GREATER_THAN", True),
    ("C9", "901", "GREATER_THAN_OR_EQUAL", False), ("C9", "901", "GREATER_THAN", False),
    ("C11", "969.99", "GREATER_THAN_OR_EQUAL", True), ("C11", "970", "GREATER_THAN_OR_EQUAL", False),
    ("C11", "970.01", "GREATER_THAN_OR_EQUAL", False),
])
def test_exact_decision_without_recomputing_financial_values(owner, equity, comparator, met):
    case = sample(owner, equity, comparator)
    before = deepcopy(case)
    r = run(case)
    _, upstream = dependencies(case)
    condition = "BREACH_CONDITION_MET" if met else "BREACH_CONDITION_NOT_MET"
    assert r["outcome"] == "ESTABLISHED" and r["reason_codes"] == [condition] and r["findings"] == []
    assert r["state"] == dict(as_of=case[0]["economic_time"], currency="USD", comparison_assessment_identity=upstream["assessment_identity"],
        rule_reference_sha256=digest(rule_reference(case)), relation=upstream["state"]["relation"], difference=upstream["state"]["difference"],
        permitted_when=comparator, breach_when="LESS_THAN" if comparator == "GREATER_THAN_OR_EQUAL" else "LESS_THAN_OR_EQUAL", condition=condition)
    assert r["rule_reference"] == rule_reference(case)
    assert r["native_references"]["comparison"] == dict(owner=owner, assessment_identity=upstream["assessment_identity"],
        outcome="ESTABLISHED", bundle_sha256=digest(case[0]["comparison"]))
    assert r["native_references"]["account_snapshot"] == upstream["native_references"]["account_snapshot"]
    assert r["temporal_scope"] == "AS_OF_T_USING_EVIDENCE_BY_K"
    assert len(r["limitations"]) == 13 and r["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert r["required_targets"] == list(TARGETS)
    assert r["reconstruction_evidence"] == dict(request=case[0], request_sha256=digest(case[0]), upstream_contexts_sha256=digest(case[1]), trusted_context_sha256=digest(case[2]))
    assert len(r["admission_bindings"]) == 5
    for i, binding in enumerate(r["admission_bindings"]):
        assert binding == dict(target=TARGETS[i], assertion_sha256=digest(case[0]["support_assertions"][i]), receipt_sha256=digest(case[2]["receipts"][i]), originals=members(case))
    assert validate(r, case) == r and case == before
    assert r["assessment_identity"] == c12.IDENTITY_PREFIX + digest({k: v for k, v in r.items() if k != "assessment_identity"})


UNKNOWN = (
    ("COMPARISON_MISSING", "/comparison", "REQUEST"),
    ("COMPARISON_NOT_ESTABLISHED", "/comparison", "REQUEST"),
    ("TRIGGER_MISSING", "/trigger", "REQUEST"),
    ("ORIGINAL_ROLE_MISSING", "/roles/mandatory_trigger", "REQUEST"),
    ("DOCUMENT_REVISION_UNKNOWN", "/originals/1/document/document_revision", "REQUEST"),
    ("DOCUMENT_REVISIONS_UNRESOLVED", "/originals/0/document", "REQUEST"),
    ("ORIGINAL_AVAILABILITY_UNKNOWN", "/originals/1/source_available_at", "REQUEST"),
    ("SOURCE_CUTOFF_INSUFFICIENT", "/source_information_cutoff", "REQUEST"),
    ("SOURCE_REVIEW_UNRESOLVED", "/trigger/source_review/known_relevant_corrections", "REQUEST"),
    ("RULE_NOT_APPLICABLE", "/trigger/effective_period", "REQUEST"),
    ("RULE_FORCE_UNRESOLVED", "/trigger/force", "REQUEST"),
    ("COMPARATOR_UNDECLARED", "/trigger/permitted_when", "REQUEST"),
    ("EVENT_SEMANTICS_UNSUPPORTED", "/trigger/conditions/duration", "REQUEST"),
    ("MEASURE_EQUIVALENCE_UNRESOLVED", "/trigger/measure_equivalence", "REQUEST"),
    ("SUPPORT_INCOMPLETE", "/support_assertions", "REQUEST"),
    ("ADMISSION_MISSING", "", "TRUSTED_CONTEXT"),
    ("ADMISSION_NOT_CURRENT", "/available_at", "TRUSTED_CONTEXT"),
    ("RECEIPT_MISSING", "/receipts", "TRUSTED_CONTEXT"),
    ("RECEIPT_UNRESOLVED", "/receipts/0", "TRUSTED_CONTEXT"),
    ("RECEIPT_MEMBERSHIP_INCOMPLETE", "/receipts/0/originals", "TRUSTED_CONTEXT"),
)


def unknown_case(code, owner="C9"):
    case = sample(owner)
    q, _, ctx = case
    if code == "COMPARISON_MISSING":
        q["comparison"], case[1] = None, None
    elif code == "COMPARISON_NOT_ESTABLISHED":
        upstream = upstream_case(case)
        upstream[-1]["receipts"] = []
        replace_upstream(case, upstream)
    elif code == "TRIGGER_MISSING": q["trigger"] = None
    elif code == "ORIGINAL_ROLE_MISSING":
        q["roles"]["mandatory_trigger"] = None
        q["originals"] = [o for o in q["originals"] if o["evidence_id"] != "mandatory_trigger"]
    elif code == "DOCUMENT_REVISION_UNKNOWN": original(case, "mandatory_trigger")["document"]["document_revision"] = None
    elif code == "DOCUMENT_REVISIONS_UNRESOLVED":
        row = original(case, "mandatory_trigger")
        row["document"]["document_id"] = original(case, "account_applicability")["document"]["document_id"]
        row["document"]["document_revision"] = "2"
    elif code == "ORIGINAL_AVAILABILITY_UNKNOWN": original(case, "mandatory_trigger")["source_available_at"] = None
    elif code == "SOURCE_CUTOFF_INSUFFICIENT":
        row = original(case, "mandatory_trigger")
        row.update(source_available_at=at(case, minutes=-24), observed_at=at(case, minutes=-23))
    elif code == "SOURCE_REVIEW_UNRESOLVED": q["trigger"]["source_review"]["known_relevant_corrections"] = "PRESENT"
    elif code == "RULE_NOT_APPLICABLE": q["trigger"]["effective_period"]["effective_from"] = at(case, boundary="economic_time", minutes=1)
    elif code == "RULE_FORCE_UNRESOLVED": q["trigger"]["force"] = "NON_MANDATORY"
    elif code == "COMPARATOR_UNDECLARED": q["trigger"]["permitted_when"] = "UNKNOWN"
    elif code == "EVENT_SEMANTICS_UNSUPPORTED": q["trigger"]["conditions"]["duration"] = "REQUIRED"
    elif code == "MEASURE_EQUIVALENCE_UNRESOLVED": q["trigger"]["measure_equivalence"] = "DIFFERENT"
    elif code == "ADMISSION_MISSING": case[2] = None
    elif code == "ADMISSION_NOT_CURRENT": ctx["available_at"] = at(case, minutes=1)
    build_support(case)
    if code == "SUPPORT_INCOMPLETE": q["support_assertions"][0]["citations"] = []
    seal(case)
    if code == "RECEIPT_MISSING": ctx["receipts"] = []
    elif code == "RECEIPT_UNRESOLVED": ctx["receipts"][0]["decision"] = "UNRESOLVED"
    elif code == "RECEIPT_MEMBERSHIP_INCOMPLETE": ctx["receipts"][0]["originals"].pop()
    return case


@pytest.mark.parametrize("owner", ["C9", "C11"])
@pytest.mark.parametrize("code,pointer,root", UNKNOWN)
def test_every_unknown_is_reachable_with_exact_existing_pointer(owner, code, pointer, root):
    case = unknown_case(code, owner)
    r = run(case)
    assert r["outcome"] == "UNKNOWN" and r["state"] is None
    assert r["reason_codes"] == [code] and r["findings"] == [dict(reason_code=code, subject=dict(root=root, pointer=pointer))]
    assert len(r["admission_bindings"]) == 5 and all(b["originals"] == members(case) for b in r["admission_bindings"])
    if code == "COMPARISON_MISSING":
        assert r["native_references"] == dict(comparison=None, account_snapshot=None) and r["rule_reference"] is None
    else:
        assert r["native_references"]["comparison"] is not None and r["native_references"]["account_snapshot"] is not None
        assert (r["rule_reference"] is None) == (code == "COMPARISON_NOT_ESTABLISHED")
    subject = case[0] if root == "REQUEST" else case[2]
    for part in pointer.split("/")[1:]:
        subject = subject[int(part)] if type(subject) is list else subject[part]
    assert validate(r, case) == r


@pytest.mark.parametrize("code,pointer,root", UNKNOWN[:-1])
def test_unknown_priority_over_later_partial_membership(code, pointer, root):
    case = unknown_case(code)
    if case[2] is not None and case[2]["receipts"]:
        case[2]["receipts"][-1]["originals"].clear()
    assert run(case)["reason_codes"] == [code]


@pytest.mark.parametrize("code,pointer,root", UNKNOWN)
def test_structural_contradiction_is_never_hidden_by_unknown(code, pointer, root):
    case = unknown_case(code)
    case[0]["roles"]["measure_equivalence"]["original_sha256"] = "0" * 64
    invalid(case)


def test_empty_observation_set_and_zero_receipts_are_total_and_bound():
    case = sample()
    q = case[0]
    q.update(comparison=None, trigger=None, originals=[], roles=dict.fromkeys(ROLES), support_assertions=[])
    case[1] = None
    seal(case)
    case[2]["receipts"] = []
    r = run(case)
    assert r["reason_codes"] == ["COMPARISON_MISSING"] and r["state"] is None
    assert r["native_references"] == dict(comparison=None, account_snapshot=None)
    assert all(b == dict(target=t, assertion_sha256=None, receipt_sha256=None, originals=[]) for b, t in zip(r["admission_bindings"], TARGETS))
    assert validate(r, case) == r
    case[2]["request_sha256"] = "0" * 64
    invalid(case)


@pytest.mark.parametrize("owner", ["C9", "C11"])
def test_genuine_selected_public_and_nested_native_replay_on_detached_validation(owner, monkeypatch):
    case = sample(owner)
    calls, native_calls = [], []
    module = f9.c9 if owner == "C9" else f11.c11
    name = ("validate_as_of_equity_trailing_loss_threshold_comparison" if owner == "C9" else "validate_as_of_equity_daily_reset_loss_floor_comparison")
    real = getattr(module, name)
    real_native = account.validate_causal_financial_account_state_snapshot
    def record(*args, **kwargs):
        calls.append((deepcopy(args), deepcopy(kwargs)))
        return real(*args, **kwargs)
    def record_native(*args, **kwargs):
        native_calls.append(1)
        return real_native(*args, **kwargs)
    monkeypatch.setattr(module, name, record)
    monkeypatch.setattr(account, "validate_causal_financial_account_state_snapshot", record_native)
    r = run(case)
    assert validate(r, case) == r and len(calls) == 2 and len(native_calls) >= 4
    expected = dict(trusted_c8_context=decoded(case[1]["c8_context_json"]))
    if owner == "C9": expected["trusted_equity_context"] = decoded(case[1]["comparison_context_json"])
    else: expected.update(trusted_c10_context=decoded(case[1]["c10_context_json"]), trusted_context=decoded(case[1]["comparison_context_json"]))
    assert all(args == (decoded(case[0]["comparison"]["result_json"]), decoded(case[0]["comparison"]["request_json"])) and kwargs == expected for args, kwargs in calls)


@pytest.mark.parametrize("field", FLAGS)
@pytest.mark.parametrize("value", [0, True])
@pytest.mark.parametrize("owner", ["C9", "C11"])
def test_rehashed_false_authority_mutations_are_rejected(owner, field, value):
    case = sample(owner)
    r = run(case)
    assert all(r["authority"][f] is False for f in FLAGS) and r["execution"] is False
    r["authority"][field] = value
    rehash_result(r)
    with pytest.raises(ValueError, match="^HISTORICAL_LOSS_LIMIT_WITNESS_RESULT_MISMATCH$"):
        validate(r, case)


@pytest.mark.parametrize("field,value", [
    ("execution", 0), ("execution", True), ("temporal_scope", "CURRENT"), ("state", None),
    ("rule_reference", None), ("native_references", dict(comparison=None, account_snapshot=None)),
    ("findings", []), ("reason_codes", ["OTHER"]), ("required_targets", []), ("admission_bindings", []),
    ("reconstruction_evidence", {}), ("source_authentication", "VERIFIED"), ("limitations", []),
])
def test_all_result_fields_are_reconstructed_after_rehash(field, value):
    case = unknown_case("RECEIPT_MISSING") if field == "findings" else sample()
    r = run(case)
    r[field] = value
    rehash_result(r)
    with pytest.raises(ValueError, match="^HISTORICAL_LOSS_LIMIT_WITNESS_RESULT_MISMATCH$"):
        validate(r, case)


@pytest.mark.parametrize("field,value", [("condition", "BREACH_CONDITION_NOT_MET"), ("difference", "1"), ("relation", "ABOVE"), ("rule_reference_sha256", "0" * 64)])
def test_state_values_cannot_be_relabelled_with_a_new_identity(field, value):
    case = sample()
    r = run(case)
    r["state"][field] = value
    rehash_result(r)
    with pytest.raises(ValueError, match="^HISTORICAL_LOSS_LIMIT_WITNESS_RESULT_MISMATCH$"):
        validate(r, case)


@pytest.mark.parametrize("owner", ["C9", "C11"])
@pytest.mark.parametrize("kind", ["comparison_result", "native_result", "omitted_context", "wrong_context", "selector"])
def test_dependency_tampering_is_structural(owner, kind):
    case = sample(owner)
    dependency = case[0]["comparison"]
    if kind == "comparison_result":
        r = decoded(dependency["result_json"])
        r["state"]["difference"] = "999"
        module = f9.c9 if owner == "C9" else f11.c11
        r["assessment_identity"] = module.IDENTITY_PREFIX + digest({k: v for k, v in r.items() if k != "assessment_identity"})
        dependency["result_json"] = encoded(r)
    elif kind == "omitted_context": case[1]["comparison_context_json"] = None
    elif kind == "wrong_context": case[1]["comparison_context_json"] = case[1]["c8_context_json"]
    else:
        source = decoded(dependency["request_json"])
        if owner == "C9":
            q8 = decoded(source["c8"]["request_json"])
            if kind == "selector": q8["history"]["rule"]["rule_index"] = 99
            else:
                r = decoded(q8["account_snapshot"]["result_json"])
                r["observation"]["account_measures"]["equity"] = "999"
                q8["account_snapshot"]["result_json"] = encoded(r)
            source["c8"]["request_json"] = encoded(q8)
        else:
            if kind == "selector":
                q10 = decoded(source["c10"]["request_json"])
                q10["daily_regime"]["selector"]["rule_index"] = 99
                source["c10"]["request_json"] = encoded(q10)
            else:
                r = decoded(source["account_snapshot"]["result_json"])
                r["observation"]["account_measures"]["equity"] = "999"
                source["account_snapshot"]["result_json"] = encoded(r)
        dependency["request_json"] = encoded(source)
    invalid(case)


@pytest.mark.parametrize("owner", ["C9", "C11"])
@pytest.mark.parametrize("field", ["account_id", "currency", "environment", "namespace", "lifecycle_id", "provider_id", "program_id", "account_type_id", "phase_id", "economic_time", "knowledge_boundary"])
def test_exact_scope_and_time_joins(owner, field):
    case = sample(owner)
    q = case[0]
    if field in ("economic_time", "knowledge_boundary"):
        q[field] = at(case, boundary=field, minutes=-1)
    elif field in ("account_id", "currency", "environment"):
        q["scope"]["account"][field] = {"account_id": "wrong", "currency": "EUR", "environment": "LIVE"}[field]
    elif field == "namespace": q["scope"]["account"]["namespace"]["source_id"] = "wrong"
    else: q["scope"][field] = "wrong"
    invalid(case)


@pytest.mark.parametrize("owner", ["C9", "C11"])
def test_original_selector_reordering_is_supported(owner):
    case = sample(owner)
    upstream = upstream_case(case)
    if owner == "C9":
        q8 = decoded(upstream[0]["c8"]["request_json"])
        n = decoded(q8["provider_regime"]["input_json"])
        dummy = deepcopy(n["manifest"]["packages"][0]["rules"][0]); dummy["rule_id"] = "a-other"
        n["manifest"]["packages"][0]["rules"].insert(0, dummy)
        q8["history"]["rule"]["rule_index"] = 1
        q8["provider_regime"] = f9.upstream.replay_regime(n)
        f9.replace_c8(upstream, q8, upstream[1])
        expected = 1
    else:
        floor = f11.floor_case(upstream)
        n = decoded(floor[0]["daily_regime"]["input_json"])
        n["manifest"]["packages"][0]["rules"].reverse()
        floor[0]["daily_regime"]["selector"]["rule_index"] = 0
        f11.upstream.set_daily(floor, n); f11.replace_floor(upstream, floor)
        expected = 0
    replace_upstream(case, upstream)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and r["rule_reference"]["rule_index"] == expected
    assert r["rule_reference"]["package_revision"] == "1"
    assert validate(r, case) == r


@pytest.mark.parametrize("field", ["mode", "duration", "grace", "confirmation", "provider_decision"])
@pytest.mark.parametrize("status", ["unsupported", "unknown"])
def test_unsupported_trigger_prerequisites_are_not_inferred(field, status):
    case = sample()
    if field == "mode": case[0]["trigger"]["event"][field] = "OTHER" if status == "unsupported" else "UNKNOWN"
    else: case[0]["trigger"]["conditions"][field] = "REQUIRED" if status == "unsupported" else "UNKNOWN"
    seal(case)
    r = run(case)
    pointer = "/trigger/event/mode" if field == "mode" else "/trigger/conditions/" + field
    assert r["reason_codes"] == ["EVENT_SEMANTICS_UNSUPPORTED"] and r["findings"][0]["subject"]["pointer"] == pointer


def test_daily_strict_comparator_is_invalid_even_with_missing_admission():
    case = sample("C11", comparator="GREATER_THAN")
    case[2] = None
    invalid(case)


@pytest.mark.parametrize("kind", ["raw_hash", "same_version", "cross_owner_version", "cross_owner_capture", "imported_duplicate", "unused", "namespace", "provenance", "empty"])
def test_original_contradictions_and_provenance_are_structural(kind):
    case = sample("C11")
    row = original(case, "mandatory_trigger")
    if kind == "raw_hash": row["content_sha256"] = "0" * 64
    elif kind == "same_version": row["document"] = deepcopy(original(case, "account_applicability")["document"])
    elif kind in ("cross_owner_version", "cross_owner_capture", "imported_duplicate"):
        source = next(r for o, r in inventory(case) if o == "C10" and r["evidence_id"] == "daily_rule")
        copied = deepcopy(source); copied["evidence_id"] = "mandatory_trigger"
        case[0]["originals"][1] = copied
        if kind == "cross_owner_version":
            copied["source"]["source_snapshot_id"] = "other-capture"
            copied["content"] = base64.b64encode(b'changed').decode(); copied["content_sha256"] = hashlib.sha256(b'changed').hexdigest()
        elif kind == "cross_owner_capture": copied["observed_at"] = at(case, minutes=-29)
    elif kind == "unused": case[0]["roles"]["mandatory_trigger"] = deepcopy(case[0]["roles"]["account_applicability"])
    elif kind == "namespace": row["document"]["namespace"]["source_id"] = "other"
    elif kind == "provenance":
        row["document"]["namespace"]["source_id"] = row["source"]["source_id"] = "other"
    else: row.update(content="", content_sha256=hashlib.sha256(b'').hexdigest())
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["request", "upstream", "assertion", "member_hash", "invented", "duplicate", "unordered", "decision", "extra"])
def test_receipt_binding_attacks_are_structural(kind):
    case = sample()
    receipt = case[2]["receipts"][0]
    if kind in ("request", "upstream", "assertion"):
        receipt[{"request": "request_sha256", "upstream": "upstream_contexts_sha256", "assertion": "assertion_sha256"}[kind]] = "0" * 64
    elif kind == "member_hash": receipt["originals"][0]["original_sha256"] = "0" * 64
    elif kind == "invented": receipt["originals"][0]["evidence_id"] = "invented"
    elif kind == "duplicate": receipt["originals"].append(deepcopy(receipt["originals"][-1]))
    elif kind == "unordered": receipt["originals"].reverse()
    elif kind == "decision": receipt["decision"] = "APPROVED"
    else: receipt["caller_approval"] = True
    invalid(case)


@pytest.mark.parametrize("kind", ["negative", "boolean", "empty", "past_bytes", "unknown_owner", "unknown_id", "duplicate", "unordered"])
def test_citation_range_and_identity_attacks_are_structural(kind):
    case = sample()
    rows = case[0]["support_assertions"][0]["citations"]
    if kind == "negative": rows[0]["start"] = -1
    elif kind == "boolean": rows[0]["start"] = False
    elif kind == "empty": rows[0]["end"] = rows[0]["start"]
    elif kind == "past_bytes": rows[0]["end"] = 10 ** 8
    elif kind == "unknown_owner": rows[0]["owner"] = "C13"
    elif kind == "unknown_id": rows[0]["evidence_id"] = "missing"
    elif kind == "duplicate": rows.append(deepcopy(rows[-1]))
    else: rows.reverse()
    invalid(case)


@pytest.mark.parametrize("kind", ["admission_before_original", "admission_before_upstream", "admission_after_availability", "report_before_cutoff", "publication_after_observation", "future_observation", "empty_mandate"])
def test_contradictory_chronology_is_structural(kind):
    case = sample("C11")
    if kind == "admission_before_original": case[2]["admitted_at"] = at(case, minutes=-24)
    elif kind == "admission_before_upstream":
        for row in case[0]["originals"]:
            row.update(source_available_at=at(case, minutes=-40), observed_at=at(case, minutes=-40))
        case[0]["source_information_cutoff"] = at(case, minutes=-40)
        case[2]["admitted_at"] = at(case, minutes=-30)
    elif kind == "admission_after_availability": case[2]["available_at"] = at(case, minutes=-21)
    elif kind == "report_before_cutoff": original(case, "source_validity")["source_available_at"] = at(case, minutes=-26)
    elif kind == "publication_after_observation": original(case, "mandatory_trigger")["source_available_at"] = at(case, minutes=-28)
    elif kind == "future_observation": original(case, "mandatory_trigger")["observed_at"] = at(case, minutes=1)
    else: case[2]["effective_until"] = case[2]["effective_from"]
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field,value", [("complete_through_cutoff", "UNKNOWN"), ("relevant_revisions", "PRESENT"), ("relevant_revisions", "UNKNOWN"), ("known_relevant_corrections", "PRESENT"), ("known_relevant_corrections", "UNKNOWN")])
def test_review_corrections_and_revision_flags_remain_unknown(field, value):
    case = sample()
    case[0]["trigger"]["source_review"][field] = value
    seal(case)
    r = run(case)
    assert r["reason_codes"] == ["SOURCE_REVIEW_UNRESOLVED"] and r["state"] is None
    assert r["findings"][0]["subject"]["pointer"] == "/trigger/source_review/" + field


@pytest.mark.parametrize("path", [(), ("scope",), ("scope", "account"), ("roles",), ("trigger",), ("trigger", "event"), ("trigger", "conditions"), ("trigger", "source_review"), ("trigger", "effective_period"), ("comparison",)])
@pytest.mark.parametrize("mode", ["extra", "missing"])
def test_request_objects_are_sealed_with_required_nullable_keys(path, mode):
    case = sample()
    obj = case[0]
    for key in path: obj = obj[key]
    if mode == "extra": obj["extra"] = None
    else: del obj[next(iter(obj))]
    invalid(case)


@pytest.mark.parametrize("kind", ["whitespace", "noncanonical_padding", "invalid_utf8", "duplicate_keys", "float", "nonobject"])
def test_dependency_byte_and_json_validation(kind):
    case = sample()
    dep = case[0]["comparison"]
    if kind == "whitespace": dep["request_json"] += "\n"
    elif kind == "noncanonical_padding": dep["request_json"] += "="
    else:
        raw = {"invalid_utf8": b'\xff', "duplicate_keys": b'{"x":1,"x":2}', "float": b'{"x":1.0}', "nonobject": b'[]'}[kind]
        dep["request_json"] = base64.b64encode(raw).decode()
    invalid(case)


@pytest.mark.parametrize("value", [False, 1.0, "1", 0, -1])
def test_mandate_revision_is_an_exact_positive_integer(value):
    case = sample()
    case[2]["mandate_revision"] = value
    invalid(case)


def test_original_dependency_bytes_are_preserved_and_hashed_not_reencoded():
    case = sample()
    original_bytes = json.dumps(decoded(case[0]["comparison"]["request_json"]), indent=2).encode()
    case[0]["comparison"]["request_json"] = base64.b64encode(original_bytes).decode()
    seal(case)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    assert r["reconstruction_evidence"]["request"]["comparison"]["request_json"] == case[0]["comparison"]["request_json"]
    assert r["native_references"]["comparison"]["bundle_sha256"] == digest(case[0]["comparison"])
    assert validate(r, case) == r


def test_future_calendar_boundary_is_not_a_future_account_observation():
    case = sample("C11")
    r = run(case)
    assert case[0]["economic_time"] < case[0]["knowledge_boundary"] < r["rule_reference"]["reset_session"]["next_reset_boundary"]
    assert r["outcome"] == "ESTABLISHED"
    r["rule_reference"]["reset_session"]["reset_boundary"] = r["rule_reference"]["reset_session"]["next_reset_boundary"]
    rehash_result(r)
    with pytest.raises(ValueError, match="^HISTORICAL_LOSS_LIMIT_WITNESS_RESULT_MISMATCH$"):
        validate(r, case)


def test_results_are_detached_and_do_not_claim_provider_status_or_freeze_clearance():
    case = sample()
    before = deepcopy(case)
    r = run(case)
    assert case == before
    assert set(r["state"]) == {"as_of", "currency", "comparison_assessment_identity", "rule_reference_sha256", "relation", "difference", "permitted_when", "breach_when", "condition"}
    assert "NO_PROVIDER_RECORDED_BREACH_STATUS" in r["limitations"]
    assert "NO_DISQUALIFICATION_OR_REINSTATEMENT" in r["limitations"]
    assert "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL" in r["limitations"]
    r["reconstruction_evidence"]["request"]["scope"]["lifecycle_id"] = "mutated"
    assert case == before and run(case)["reconstruction_evidence"]["request"] == case[0]


def test_wrong_branch_context_and_in_request_approval_are_rejected():
    case = sample()
    case[1]["c10_context_json"] = case[1]["c8_context_json"]
    invalid(case)
    case = sample()
    case[0]["trusted_context"] = case[2]
    invalid(case)


def test_arbitrary_precision_difference_and_numeric_settings_are_preserved():
    precision = sys.get_int_max_str_digits() if hasattr(sys, "get_int_max_str_digits") else None
    value = "9" * 4500 + ".000000000000000000000000000001"
    # C9's old fixture itself calls Fraction(string), which has Python's digit
    # limit. C11's genuine fixture uses Decimal and does not require changing it.
    case = sample("C11", value)
    r = run(case)
    _, upstream = dependencies(case)
    assert r["state"]["difference"] == upstream["state"]["difference"] and len(r["state"]["difference"]) > 4500
    assert validate(r, case) == r
    if precision is not None: assert sys.get_int_max_str_digits() == precision


@pytest.mark.parametrize("offset,expected", [(-1, "INVALID"), (0, "ESTABLISHED"), (1, "SOURCE_CUTOFF_INSUFFICIENT")])
def test_one_shared_original_obeys_both_operational_and_report_chronology(offset, expected):
    case = sample()
    q = case[0]
    shared = deepcopy(original(case, "mandatory_trigger"))
    shared.update(source_available_at=at(case, minutes=-25 + offset), observed_at=at(case, minutes=-23))
    q["originals"] = [shared]
    q["roles"] = {role: dict(owner="C12", evidence_id=shared["evidence_id"], original_sha256=digest(shared)) for role in ROLES}
    build_support(case); seal(case)
    if expected == "INVALID": invalid(case)
    else:
        r = run(case)
        assert (r["outcome"] if expected == "ESTABLISHED" else r["reason_codes"][0]) == expected
        assert all(len(b["originals"]) == 6 for b in r["admission_bindings"])
        assert validate(r, case) == r


@pytest.mark.parametrize("kind", ["rule", "snapshot", "assertion_rule", "assertion_trigger", "reset_session"])
def test_exact_derived_reference_bindings_cannot_be_substituted(kind):
    case = sample("C11")
    if kind == "rule": case[0]["trigger"]["rule_reference_sha256"] = "0" * 64
    elif kind == "snapshot": case[0]["trigger"]["event"]["snapshot_reference_sha256"] = "0" * 64
    elif kind == "assertion_rule": case[0]["support_assertions"][0]["rule_reference_sha256"] = "0" * 64
    elif kind == "assertion_trigger": case[0]["support_assertions"][0]["trigger_sha256"] = "0" * 64
    else:
        ref = rule_reference(case)
        ref["reset_session"]["reset_boundary"] = ref["reset_session"]["next_reset_boundary"]
        case[0]["trigger"]["rule_reference_sha256"] = digest(ref)
    invalid(case)


@pytest.mark.parametrize("mode", ["future_start", "end_at_T", "unknown_start", "unknown_end", "start_at_T", "end_after_T"])
def test_rule_effective_period_is_half_open_and_historical(mode):
    case = sample()
    period = case[0]["trigger"]["effective_period"]
    if mode == "future_start": period["effective_from"] = at(case, boundary="economic_time", minutes=1)
    elif mode == "end_at_T": period.update(end_status="KNOWN", effective_until=case[0]["economic_time"])
    elif mode == "unknown_start": period["effective_from"] = None
    elif mode == "unknown_end": period["end_status"] = "UNKNOWN"
    elif mode == "start_at_T": period["effective_from"] = case[0]["economic_time"]
    else: period.update(end_status="KNOWN", effective_until=at(case, boundary="economic_time", minutes=1))
    seal(case)
    r = run(case)
    assert r["reason_codes"] == (["BREACH_CONDITION_MET"] if mode in ("start_at_T", "end_after_T") else ["RULE_NOT_APPLICABLE"])


@pytest.mark.parametrize("field", ["effective_from", "effective_until"])
def test_mandate_must_cover_admission_and_K(field):
    case = sample()
    case[2][field] = at(case, minutes=-19) if field == "effective_from" else case[0]["knowledge_boundary"]
    r = run(case)
    assert r["reason_codes"] == ["ADMISSION_NOT_CURRENT"]
    assert r["findings"][0]["subject"] == dict(root="TRUSTED_CONTEXT", pointer="/" + field)


@pytest.mark.parametrize("where", ["context", "receipt", "original", "source", "document", "role", "assertion", "citation"])
@pytest.mark.parametrize("mode", ["extra", "missing"])
def test_every_remaining_serialized_object_is_sealed(where, mode):
    case = sample()
    q = case[0]
    obj = {"context": case[2], "receipt": case[2]["receipts"][0], "original": q["originals"][0],
           "source": q["originals"][0]["source"], "document": q["originals"][0]["document"],
           "role": q["roles"]["mandatory_trigger"], "assertion": q["support_assertions"][0],
           "citation": q["support_assertions"][0]["citations"][0]}[where]
    if mode == "extra": obj["extra"] = None
    else: del obj[next(iter(obj))]
    invalid(case)


@pytest.mark.parametrize("value", ["2026-01-10T00:00:00Z", "2026-01-10T00:00:00.000000+00:00", "2026-01-10T00:00:60.000000Z", "2026-02-30T00:00:00.000000Z", 0, False, None])
def test_time_is_exact_valid_UTC_with_six_fractional_digits(value):
    case = sample()
    case[0]["economic_time"] = value
    invalid(case)


@pytest.mark.parametrize("value", ["\ud800", " padded", "padded ", "\u0085padded", "padded\u3000", ""])
def test_text_and_unicode_are_not_silently_normalized(value):
    case = sample()
    case[2]["authority_id"] = value
    invalid(case)


def test_upstream_review_cutoffs_are_preserved_and_cannot_be_waived():
    case = sample()
    before = deepcopy(case[0]["comparison"])
    case[0]["source_information_cutoff"] = case[0]["economic_time"]
    for row in case[0]["originals"]:
        if row["evidence_id"] != "source_validity":
            row.update(source_available_at=at(case, boundary="economic_time", minutes=-1), observed_at=case[0]["economic_time"])
    seal(case)
    r = run(case)
    assert r["reason_codes"] == ["SOURCE_CUTOFF_INSUFFICIENT"] and r["state"] is None
    assert case[0]["comparison"] == before


def test_context_bytes_and_zero_receipt_root_binding_remain_exact():
    case = sample()
    case[2]["receipts"] = []
    case[2]["upstream_contexts_sha256"] = "0" * 64
    invalid(case)
    case = sample()
    original_result = run(case)
    obj = decoded(case[1]["comparison_context_json"])
    case[1]["comparison_context_json"] = base64.b64encode(json.dumps(obj, indent=2).encode()).decode()
    invalid(case)
    seal(case)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and r["native_references"] == original_result["native_references"]
    assert r["assessment_identity"] != original_result["assessment_identity"]
    assert validate(r, case) == r


def test_empty_upstream_envelope_is_distinct_from_absent_envelope():
    case = sample()
    case[0].update(comparison=None, trigger=None, originals=[], roles=dict.fromkeys(ROLES), support_assertions=[])
    case[1] = None
    seal(case); case[2]["receipts"] = []
    absent = run(case)
    case[1] = dict.fromkeys(("c8_context_json", "c10_context_json", "comparison_context_json"))
    invalid(case)
    seal(case); case[2]["receipts"] = []
    present = run(case)
    assert absent["reconstruction_evidence"]["upstream_contexts_sha256"] is None
    assert present["reconstruction_evidence"]["upstream_contexts_sha256"] == digest(case[1])
    assert absent["assessment_identity"] != present["assessment_identity"]


def test_later_recovery_retains_the_earlier_historical_witness():
    earlier = sample("C11", "969.99")
    early_result = run(earlier)
    later = sample("C11", "980")
    upstream = upstream_case(later)
    uq = upstream[0]
    new_t = f11.at(upstream, minutes=15)
    uq["economic_time"] = uq["equity"]["economic_time"] = uq["equity"]["coverage"]["economic_time"] = new_t
    floor = f11.floor_case(upstream)
    fq = floor[0]
    fq["economic_time"] = fq["coverage"]["economic_through"] = new_t
    floor[2]["admission_id"] += "-recovery"
    row = next(o for o in fq["originals"] if o["evidence_id"] == "coverage")
    body = decoded(row["content"]); body["through"] = new_t
    f11.upstream.set_content(row, canonical(body).encode())
    row["document"]["document_id"] += "-recovery"; row["source"]["source_snapshot_id"] += "-recovery"
    for a in fq["support_assertions"]:
        for c in a["citations"]:
            if c["evidence_id"] == "coverage": c["end"] = len(base64.b64decode(row["content"]))
    n = decoded(fq["daily_regime"]["input_json"]); n["economic_timestamp"] = new_t
    f11.upstream.set_daily(floor, n); f11.replace_floor(upstream, floor)
    inp = decoded(uq["account_snapshot"]["input_json"])
    inp["observation"]["timing"]["effective_at"] = new_t
    inp["observation"]["source"]["source_snapshot_id"] += "-recovery"
    f11.replace_snapshot(upstream, inp)
    for row in uq["originals"]:
        body = decoded(row["content"])
        if row["evidence_id"] == "aggregate":
            body["effective_at"] = new_t; row["source"] = deepcopy(inp["observation"]["source"])
        elif row["evidence_id"] == "coverage": body["economic_time"] = new_t
        else: body["selected_daily_measure"] = f11.measure_reference(upstream)
        row["document"]["document_id"] += "-recovery"
        if row["evidence_id"] != "aggregate": row["source"]["source_snapshot_id"] += "-recovery"
        f11.upstream.set_content(row, canonical(body).encode())
    upstream[-1]["admission_id"] += "-recovery"
    f11.build_support(upstream); f11.seal(upstream)
    later[0]["economic_time"] = later[0]["trigger"]["economic_time"] = new_t
    later[2]["admission_id"] += "-recovery"
    replace_upstream(later, upstream)
    for row in later[0]["originals"]:
        body = decoded(row["content"])
        body.update(trigger=later[0]["trigger"], rule_reference=rule_reference(later))
        row["document"]["document_id"] += "-recovery"
        row["source"]["source_snapshot_id"] += "-recovery"
        f11.upstream.set_content(row, canonical(body).encode())
    build_support(later); seal(later)
    late_result = run(later)
    assert early_result["state"]["condition"] == "BREACH_CONDITION_MET"
    assert late_result["state"]["condition"] == "BREACH_CONDITION_NOT_MET"
    assert early_result["rule_reference"]["reset_session"] == late_result["rule_reference"]["reset_session"]
    assert earlier[0]["scope"] == later[0]["scope"] and earlier[0]["knowledge_boundary"] == later[0]["knowledge_boundary"]
    assert run(earlier) == early_result and validate(late_result, later) == late_result


@pytest.mark.parametrize("where", ["trigger", "original", "receipt"])
def test_sealed_C12_grammar_is_checked_before_expensive_foreign_replay(where, monkeypatch):
    case = sample()
    calls = []
    real = f9.c9.validate_as_of_equity_trailing_loss_threshold_comparison
    def record(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(f9.c9, "validate_as_of_equity_trailing_loss_threshold_comparison", record)
    obj = {"trigger": case[0]["trigger"], "original": case[0]["originals"][0], "receipt": case[2]["receipts"][0]}[where]
    obj["extra"] = None
    invalid(case)
    assert calls == []


def test_arbitrary_precision_mandate_revision_needs_no_global_configuration_change():
    case = sample()
    before = sys.get_int_max_str_digits() if hasattr(sys, "get_int_max_str_digits") else None
    case[2]["mandate_revision"] = 10 ** 4500 + 1
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and validate(r, case) == r
    if before is not None: assert sys.get_int_max_str_digits() == before
