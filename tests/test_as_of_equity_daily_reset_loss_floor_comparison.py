"""Frozen C11 witnesses with genuine C10/native replay and synthetic admissions.

All sources and account/provider identities are explicitly synthetic. Fixture
resealing supplies new test admission, never a mocked positive owner result.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import localcontext, Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from ced_one.business_divisions.trading import as_of_equity_daily_reset_loss_floor_comparison as c11
from ced_one.business_divisions.trading import as_of_daily_reset_loss_floor_state as c10
from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account
from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regime

spec = importlib.util.spec_from_file_location("c11_upstream_witness", Path(__file__).with_name("test_as_of_daily_reset_loss_floor_state.py"))
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)

TARGETS = ("EQUITY_IDENTITY_BINDING", "EQUITY_AGGREGATE_MEANING", "EQUITY_ACCOUNT_WIDE_COMPLETENESS",
           "EQUITY_COST_COMPONENTS", "EQUITY_SOURCE_VERSION_VALIDITY")
FLAGS = ("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval",
         "trade_decision", "financial_risk", "execution")
OWNERS = ("C8", "C10", "C11")
COMPONENTS = ("balance", "floating_pnl", "commissions", "financing", "other_costs")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def encoded(value):
    return base64.b64encode(canonical(value).encode()).decode()


def decoded(value):
    return json.loads(base64.b64decode(value))


def at(case, hours=0, minutes=0):
    t = datetime.fromisoformat(case[0]["economic_time"].replace("Z", "+00:00"))
    return (t + timedelta(hours=hours, minutes=minutes)).isoformat(timespec="microseconds").replace("+00:00", "Z")


def inventory(case):
    q = case[0]
    originals = []
    if q["c10"] is not None:
        q10 = decoded(q["c10"]["request_json"])
        if q10["c8"] is not None:
            originals.extend(("C8", o) for o in decoded(q10["c8"]["request_json"])["originals"])
        originals.extend(("C10", o) for o in q10["originals"])
    originals.extend(("C11", o) for o in q["originals"])
    return originals


def members(case):
    return [dict(owner=owner, evidence_id=o["evidence_id"], original_sha256=digest(o)) for owner, o in inventory(case)]


def measure_reference(case):
    """Independent fixture construction from the frozen original-index grammar."""
    q = case[0]
    if q["c10"] is None:
        return None
    q10, r10 = decoded(q["c10"]["request_json"]), decoded(q["c10"]["result_json"])
    if r10["outcome"] != "ESTABLISHED":
        return None
    native = decoded(q10["daily_regime"]["input_json"])
    s = q10["daily_regime"]["selector"]
    p = native["manifest"]["packages"][s["package_index"]]
    r = p["rules"][s["rule_index"]]
    m = r["body"]["measure"]
    by_id = {(x["owner"], x["evidence_id"]): x for x in members(case)}
    mappings = {x["native_evidence_id"]: x["original"] for x in q10["native_mappings"]}
    return dict(c10_assessment_identity=r10["assessment_identity"], c10_bundle_sha256=digest(q["c10"]),
        daily_regime_bundle_sha256=digest(q10["daily_regime"]), assignment_id=s["assignment_id"], package_index=s["package_index"],
        package_id=p["package_id"], package_revision=p["package_revision"], rule_index=s["rule_index"], rule_id=r["rule_id"],
        native_rule_sha256=digest(r), measure_sha256=digest(m), kind="EQUITY", currency=m["currency"],
        instrument_scope="ALL_ACCOUNT_INSTRUMENTS", cost_treatment=deepcopy(m["cost_treatment"]),
        rule_original=deepcopy(by_id[("C10", q10["roles"]["daily_rule"]["evidence_id"])]),
        definition_bindings=[dict(index=i, native_evidence_id=clause["evidence_id"], clause_locator=clause["clause_locator"],
            original=deepcopy(by_id[("C10", mappings[clause["evidence_id"]]["evidence_id"])])) for i, clause in enumerate(m["definition_refs"])])


def build_support(case):
    q = case[0]
    local = set() if q["equity"] is None else {("C11", r["evidence_id"]) for r in q["equity"]["roles"].values() if r is not None}
    required = [set(local) for _ in TARGETS]
    m = measure_reference(case)
    if m is not None and q["equity"] is not None and all(q["equity"]["roles"].values()):
        a, d, c = [("C11", q["equity"]["roles"][role]["evidence_id"]) for role in ("aggregate", "definition", "coverage")]
        q10 = decoded(q["c10"]["request_json"])
        en = ("C10", q10["roles"]["enrollment"]["evidence_id"])
        dr = ("C10", m["rule_original"]["evidence_id"])
        df = {(x["original"]["owner"], x["original"]["evidence_id"]) for x in m["definition_bindings"]}
        cr = ("C10", q10["roles"]["coverage"]["evidence_id"])
        required = [{a, d, en}, {a, d, dr} | df, {a, c}, {d, c, dr} | df, {a, d, c, dr, cr} | df]
    env = {(owner, o["evidence_id"]): o for owner, o in inventory(case)}
    q["support_assertions"] = [dict(target=target, equity_sha256=None if q["equity"] is None else digest(q["equity"]),
        citations=[dict(owner=owner, evidence_id=identifier, start=0, end=len(base64.b64decode(env[(owner, identifier)]["content"])))
            for owner, identifier in sorted(required[i], key=lambda k: (OWNERS.index(k[0]), k[1]))]) for i, target in enumerate(TARGETS)]


def seal(case, *, original_refs=True):
    """Rebind unchanged shapes; deliberately does not repair dependency metadata."""
    q, ctx8, ctx10, ctx = case
    if q["equity"] is not None and original_refs:
        originals = {o["evidence_id"]: o for o in q["originals"]}
        for ref in q["equity"]["roles"].values():
            if type(ref) is dict and ref["evidence_id"] in originals:
                ref["original_sha256"] = digest(originals[ref["evidence_id"]])
    for a in q["support_assertions"]:
        a["equity_sha256"] = None if q["equity"] is None else digest(q["equity"])
    if ctx is not None:
        ctx.update(request_sha256=digest(q), c8_context_sha256=None if ctx8 is None else digest(ctx8),
                   c10_context_sha256=None if ctx10 is None else digest(ctx10))
        assertions = {a["target"]: a for a in q["support_assertions"]}
        ctx["receipts"] = [dict(target=t, request_sha256=digest(q), c8_context_sha256=ctx["c8_context_sha256"],
            c10_context_sha256=ctx["c10_context_sha256"], assertion_sha256=None if t not in assertions else digest(assertions[t]),
            originals=members(case), decision="ADMITTED") for t in TARGETS]
    return case


def replace_floor(case, upstream_case):
    r = upstream.run(upstream_case)
    case[0]["c10"] = dict(request_json=encoded(upstream_case[0]), result_json=encoded(r))
    case[1:3] = deepcopy(upstream_case[1:3])
    if case[0]["equity"] is not None:
        m = measure_reference(case)
        case[0]["equity"]["daily_measure_sha256"] = None if m is None else digest(m)
    build_support(case)
    return seal(case)


def replace_snapshot(case, inp):
    result = account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(inp).to_dict()
    bundle = dict(input_json=encoded(inp), result_json=encoded(result))
    case[0]["account_snapshot"] = bundle
    if case[0]["equity"] is not None:
        case[0]["equity"]["snapshot_reference"] = dict(snapshot_id=result["snapshot_id"], bundle_sha256=digest(bundle))
        case[0]["equity"]["amount"] = result["observation"]["account_measures"]["equity"]
    return seal(case)


def sample(equity="970", balances=(), initial="1000", date="2026-01-10"):
    q10, ctx8, ctx10 = upstream.sample(balances, initial, date)
    r10 = c10.evaluate_as_of_daily_reset_loss_floor_state(q10, trusted_c8_context=ctx8, trusted_context=ctx10)
    q8 = decoded(q10["c8"]["request_json"])
    inp = decoded(q8["account_snapshot"]["input_json"])
    inp["observation"]["source"]["source_snapshot_id"] = "synthetic-c11-equity"
    inp["observation"]["timing"]["effective_at"] = q10["economic_time"]
    inp["observation"]["account_measures"] = dict(completeness="PARTIAL", balance="1005", equity=equity, used_margin=None, free_margin=None)
    inp["observation"]["positions"] = dict(completeness="COMPLETE", items=[
        dict(position_id="xau", instrument_id="XAUUSD", direction="LONG", quantity="1", quantity_unit="LOT"),
        dict(position_id="eur", instrument_id="EURUSD", direction="SHORT", quantity="1", quantity_unit="LOT")])
    native = account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(inp).to_dict()
    q = dict(contract=c11.CONTRACT, rule_version=c11.RULE_VERSION, economic_time=q10["economic_time"], knowledge_boundary=q10["knowledge_boundary"],
        source_information_cutoff=upstream.at([q10], 5, 30), scope=deepcopy(q10["scope"]),
        c10=dict(request_json=encoded(q10), result_json=encoded(r10)), account_snapshot=dict(input_json=encoded(inp), result_json=encoded(native)),
        equity=None, originals=[], support_assertions=[])
    ctx = dict(contract=c11.ADMISSION_CONTRACT, rule_version=c11.ADMISSION_RULE_VERSION, admission_id="synthetic-c11-admission",
        authority_namespace=deepcopy(q["scope"]["provider_namespace"]), authority_id="independent-synthetic-host", mandate_id="synthetic-c11-review", mandate_revision=1,
        request_sha256="", c8_context_sha256="", c10_context_sha256="", admitted_at="", available_at="", effective_from="", effective_until=None, receipts=[])
    case = [q, ctx8, ctx10, ctx]
    ctx.update(admitted_at=at(case, 5, 30), available_at=at(case, 5, 31), effective_from=at(case, -24))
    m = measure_reference(case)
    source = native["observation"]["source"]
    with localcontext() as arithmetic:
        arithmetic.prec = 30 + (0 if equity is None else len(equity))
        pnl = None if equity is None else format(Decimal(equity) - Decimal("1005"), "f")
    bodies = [dict(synthetic=True, scope=q["scope"], effective_at=q["economic_time"], equity=equity, balance="1005", floating_pnl=pnl,
                   commissions="0", swaps_and_financing="0", other_charges="NOT_APPLICABLE", all_instruments=["XAUUSD", "EURUSD"], exactly_once=True),
        dict(synthetic=True, scope=q["scope"], economic_time=q["economic_time"], cutoff=q["source_information_cutoff"],
             all_account_instruments=True, floating_pnl_and_costs_complete=True, source_revisions=[], known_later_corrections=[]),
        dict(synthetic=True, scope=q["scope"], selected_daily_measure=m,
             definition="Account-wide balance plus all unrealized P/L. Commissions and all swaps/financing are included exactly once, including costs already in balance; other charges are not applicable.",
             effective_from=q10["reset_boundary"], effective_until=r10["state"]["next_reset_boundary"])]
    sources = [source, dict(**q["scope"]["account"]["namespace"], source_snapshot_id="synthetic-c11-coverage"),
               dict(**q["scope"]["provider_namespace"], source_snapshot_id="synthetic-c11-definition")]
    times = [(native["observation"]["timing"]["source_available_at"], native["observation"]["timing"]["observed_at"]),
             (at(case, 3, 45), at(case, 3, 46)), (at(case, -1), at(case, -1))]
    q["originals"] = [upstream.original(identifier, canonical(body).encode(), source, published, observed)
        for identifier, body, source, (published, observed) in zip(("aggregate", "coverage", "definition"), bodies, sources, times)]
    q["equity"] = dict(scope=deepcopy(q["scope"]), economic_time=q["economic_time"], knowledge_boundary=q["knowledge_boundary"],
        snapshot_reference=dict(snapshot_id=native["snapshot_id"], bundle_sha256=digest(q["account_snapshot"])), daily_measure_sha256=digest(m), amount=equity, currency="USD",
        roles={role:dict(evidence_id=role, original_sha256=digest(next(o for o in q["originals"] if o["evidence_id"]==role))) for role in ("aggregate", "definition", "coverage")},
        definition_period=dict(effective_from=q10["reset_boundary"], effective_until=r10["state"]["next_reset_boundary"], end_status="KNOWN"),
        coverage=dict(economic_time=q["economic_time"], source_information_cutoff=q["source_information_cutoff"], account_wide="COMPLETE", source_revisions="NONE", known_later_corrections="NONE"),
        measure_equivalence="EXACT", components=dict(balance="INCLUDED_ONCE", floating_pnl="INCLUDED_ONCE", commissions="INCLUDED_ONCE", financing="INCLUDED_ONCE", other_costs="NOT_APPLICABLE"),
        component_integrity="COMPLETE_EXACTLY_ONCE")
    build_support(case)
    return seal(case)


def run(case):
    return c11.evaluate_as_of_equity_daily_reset_loss_floor_comparison(case[0], trusted_c8_context=case[1], trusted_c10_context=case[2], trusted_context=case[3])


def validate(result, case):
    return c11.validate_as_of_equity_daily_reset_loss_floor_comparison(result, case[0], trusted_c8_context=case[1], trusted_c10_context=case[2], trusted_context=case[3])


def invalid(case):
    with pytest.raises(ValueError, match="^INVALID_EQUITY_DAILY_FLOOR_INPUT$"):
        run(case)


def reseal_result(result):
    result["assessment_identity"] = c11.IDENTITY_PREFIX + digest({k:v for k,v in result.items() if k != "assessment_identity"})


def floor_case(case):
    return [decoded(case[0]["c10"]["request_json"]), deepcopy(case[1]), deepcopy(case[2])]


@pytest.mark.parametrize("equity,difference,relation", [("969.99", "-0.01", "BELOW"), ("970", "0", "EQUAL"), ("970.01", "0.01", "ABOVE")])
def test_exact_positive_comparisons_with_genuine_c10_and_explicit_partial_snapshot(equity, difference, relation):
    case = sample(equity)
    original = deepcopy(case)
    r = run(case)
    q10 = decoded(case[0]["c10"]["request_json"])
    assert r["outcome"] == "ESTABLISHED"
    assert r["state"] == dict(as_of=case[0]["economic_time"], reset_boundary=q10["reset_boundary"], next_reset_boundary=q10["calendar"]["utc_end"],
        currency="USD", equity=equity, daily_loss_floor="970", difference=difference, relation=relation)
    assert r["temporal_scope"] == "AS_OF_T_USING_EVIDENCE_BY_K"
    assert r["reason_codes"] == ["COMPARISON_ESTABLISHED"] and r["findings"] == []
    assert validate(r, case) == r
    assert case == original
    assert r["reconstruction_evidence"]["request"] == case[0]
    assert r["reconstruction_evidence"] == dict(request=case[0], request_sha256=digest(case[0]),
        c8_context_sha256=digest(case[1]), c10_context_sha256=digest(case[2]), trusted_context_sha256=digest(case[3]))
    assert r["assessment_identity"] == c11.IDENTITY_PREFIX + digest({k:v for k,v in r.items() if k != "assessment_identity"})
    assert len(members(case)) == 12
    assert r["daily_measure"] == measure_reference(case)
    for binding in r["admission_bindings"]:
        assert binding["originals"] == members(case)
    r["state"]["equity"] = "999"
    assert run(case)["state"]["equity"] == equity


UNKNOWN = (
    ("C10_MISSING", "/c10", "REQUEST"),
    ("C8_CONTEXT_MISSING", "", "TRUSTED_C8_CONTEXT"),
    ("C10_CONTEXT_MISSING", "", "TRUSTED_C10_CONTEXT"),
    ("C10_NOT_ESTABLISHED", "/c10", "REQUEST"),
    ("EQUITY_SNAPSHOT_MISSING", "/account_snapshot", "REQUEST"),
    ("NATIVE_EQUITY_MISSING", "/account_snapshot", "REQUEST"),
    ("EQUITY_ASSERTION_MISSING", "/equity", "REQUEST"),
    ("EQUITY_AMOUNT_UNDECLARED", "/equity/amount", "REQUEST"),
    ("AGGREGATE_ORIGINAL_MISSING", "/equity/roles/aggregate", "REQUEST"),
    ("DEFINITION_ORIGINAL_MISSING", "/equity/roles/definition", "REQUEST"),
    ("COVERAGE_ORIGINAL_MISSING", "/equity/roles/coverage", "REQUEST"),
    ("ORIGINAL_ROLE_COVERAGE_INCOMPLETE", "/originals/2", "REQUEST"),
    ("DOCUMENT_REVISION_UNKNOWN", "/originals/2/document/document_revision", "REQUEST"),
    ("DOCUMENT_VERSION_CONFLICT", "/originals/0/document", "REQUEST"),
    ("NATIVE_AVAILABILITY_UNKNOWN", "/account_snapshot", "REQUEST"),
    ("ORIGINAL_AVAILABILITY_UNKNOWN", "/originals/2/source_available_at", "REQUEST"),
    ("EQUITY_SOURCE_CUTOFF_INSUFFICIENT", "/source_information_cutoff", "REQUEST"),
    ("SOURCE_REVISIONS_UNRESOLVED", "/equity/coverage/source_revisions", "REQUEST"),
    ("DEFINITION_NOT_APPLICABLE", "/equity/definition_period", "REQUEST"),
    ("ACCOUNT_WIDE_UNRESOLVED", "/equity/coverage/account_wide", "REQUEST"),
    ("RULE_MEASURE_EQUIVALENCE_UNRESOLVED", "/equity/measure_equivalence", "REQUEST"),
    ("COMPONENT_TREATMENT_UNSUPPORTED", "/equity/components/balance", "REQUEST"),
    ("COMPONENT_INTEGRITY_UNRESOLVED", "/equity/component_integrity", "REQUEST"),
    ("SUPPORT_INCOMPLETE", "/support_assertions", "REQUEST"),
    ("EQUITY_ADMISSION_MISSING", "", "TRUSTED_CONTEXT"),
    ("EQUITY_ADMISSION_NOT_CURRENT", "/available_at", "TRUSTED_CONTEXT"),
    ("RECEIPT_MISSING", "/receipts", "TRUSTED_CONTEXT"),
    ("RECEIPT_UNRESOLVED", "/receipts/0", "TRUSTED_CONTEXT"),
    ("RECEIPT_MEMBERSHIP_INCOMPLETE", "/receipts/0/originals", "TRUSTED_CONTEXT"),
)


def unknown_case(reason):
    case = sample()
    q, _, _, ctx = case
    e = q["equity"]
    if reason == "C10_MISSING":
        q["c10"] = None
        case[1:3] = [None, None]
        e["daily_measure_sha256"] = None
        build_support(case)
    elif reason in ("C8_CONTEXT_MISSING", "C10_CONTEXT_MISSING", "C10_NOT_ESTABLISHED"):
        cf = floor_case(case)
        if reason == "C8_CONTEXT_MISSING": upstream.replace8(cf, decoded(cf[0]["c8"]["request_json"]), None)
        elif reason == "C10_CONTEXT_MISSING": cf[2] = None
        else: cf[2]["receipts"] = []
        replace_floor(case, cf)
    elif reason == "EQUITY_SNAPSHOT_MISSING":
        q["account_snapshot"] = None
        e["snapshot_reference"] = None
    elif reason == "NATIVE_EQUITY_MISSING": return sample(None)
    elif reason == "EQUITY_ASSERTION_MISSING": q["equity"] = None
    elif reason == "EQUITY_AMOUNT_UNDECLARED": e["amount"] = None
    elif reason in ("AGGREGATE_ORIGINAL_MISSING", "DEFINITION_ORIGINAL_MISSING", "COVERAGE_ORIGINAL_MISSING"):
        e["roles"][reason.split("_")[0].lower()] = None
    elif reason == "ORIGINAL_ROLE_COVERAGE_INCOMPLETE": e["roles"]["definition"] = deepcopy(e["roles"]["aggregate"])
    elif reason == "DOCUMENT_REVISION_UNKNOWN": q["originals"][2]["document"]["document_revision"] = None
    elif reason == "DOCUMENT_VERSION_CONFLICT":
        d = q["originals"][2]
        d["source"].update(q["scope"]["account"]["namespace"])
        d["document"] = deepcopy(q["originals"][0]["document"])
        d["document"]["document_revision"] = "2"
    elif reason == "NATIVE_AVAILABILITY_UNKNOWN":
        inp = decoded(q["account_snapshot"]["input_json"])
        inp["observation"]["timing"]["source_available_at"] = None
        replace_snapshot(case, inp)
    elif reason == "ORIGINAL_AVAILABILITY_UNKNOWN": q["originals"][2]["source_available_at"] = None
    elif reason == "EQUITY_SOURCE_CUTOFF_INSUFFICIENT":
        q["originals"][2].update(source_available_at=at(case, 4), observed_at=at(case, 4))
    elif reason == "SOURCE_REVISIONS_UNRESOLVED": e["coverage"]["source_revisions"] = "PRESENT"
    elif reason == "DEFINITION_NOT_APPLICABLE": e["definition_period"]["effective_from"] = at(case, 1)
    elif reason == "ACCOUNT_WIDE_UNRESOLVED": e["coverage"]["account_wide"] = "UNKNOWN"
    elif reason == "RULE_MEASURE_EQUIVALENCE_UNRESOLVED": e["measure_equivalence"] = "DIFFERENT"
    elif reason == "COMPONENT_TREATMENT_UNSUPPORTED": e["components"]["balance"] = "OMITTED"
    elif reason == "COMPONENT_INTEGRITY_UNRESOLVED": e["component_integrity"] = "DUPLICATION"
    elif reason == "SUPPORT_INCOMPLETE": q["support_assertions"].pop(0)
    elif reason == "EQUITY_ADMISSION_MISSING": case[3] = None
    elif reason == "EQUITY_ADMISSION_NOT_CURRENT": ctx["available_at"] = at(case, 7)
    seal(case)
    if reason == "RECEIPT_MISSING": ctx["receipts"].pop(0)
    elif reason == "RECEIPT_UNRESOLVED": ctx["receipts"][0]["decision"] = "UNRESOLVED"
    elif reason == "RECEIPT_MEMBERSHIP_INCOMPLETE": ctx["receipts"][0]["originals"].pop()
    return case


@pytest.mark.parametrize("reason,pointer,root", UNKNOWN)
def test_all_29_unknown_reasons_priority_pointers_membership_and_detached_replay(reason, pointer, root):
    case = unknown_case(reason)
    r = run(case)
    assert r["outcome"] == "UNKNOWN" and r["state"] is None
    assert r["authority"] == dict.fromkeys(FLAGS, False) and r["execution"] is False
    assert r["reason_codes"] == [reason]
    assert r["findings"] == [dict(reason_code=reason, subject=dict(root=root, pointer=pointer))]
    assert r["required_targets"] == list(TARGETS)
    assert all(b["originals"] == members(case) for b in r["admission_bindings"])
    assert validate(r, case) == r
    roots = dict(REQUEST=case[0], TRUSTED_C8_CONTEXT=case[1], TRUSTED_C10_CONTEXT=case[2], TRUSTED_CONTEXT=case[3])
    subject = roots[root]
    for part in pointer.split("/")[1:]:
        subject = subject[int(part)] if isinstance(subject, list) else subject[part]


def test_reason_inventory_is_exact_and_all_structural_checks_precede_unknown():
    assert c11.REASON_CODES == ("COMPARISON_ESTABLISHED", *(r[0] for r in UNKNOWN))
    case = unknown_case("C10_MISSING")
    case[0]["originals"][0]["content_sha256"] = "0"*64
    seal(case)
    invalid(case)
    case = unknown_case("EQUITY_AMOUNT_UNDECLARED")
    case[0]["equity"]["coverage"]["account_wide"] = "UNKNOWN"
    seal(case)
    assert run(case)["reason_codes"] == ["EQUITY_AMOUNT_UNDECLARED"]


@pytest.mark.parametrize("present", [False, True])
def test_empty_parents_and_empty_observation_set_with_zero_receipts(present):
    case = sample()
    case[0].update(c10=None, account_snapshot=None, equity=None, originals=[], support_assertions=[])
    case[1:3] = [None, None]
    if not present: case[3] = None
    seal(case)
    if present: case[3]["receipts"] = []
    r = run(case)
    assert r["reason_codes"] == ["C10_MISSING"] and r["state"] is None
    assert r["native_references"] == dict(c10=None, account_snapshot=None) and r["daily_measure"] is None
    assert r["admission_bindings"] == [dict(target=t, assertion_sha256=None, receipt_sha256=None, originals=[]) for t in TARGETS]
    assert validate(r, case) == r


@pytest.mark.parametrize("equity", ["-1.25", "0", "1" + "0"*5000, "970." + "0"*4999 + "1", "-0." + "0"*4999 + "1"],
                         ids=("negative", "zero", "5001-digit-integer", "positive-5000-decimals", "negative-5000-decimals"))
def test_extreme_and_negative_money_is_exact_without_global_precision_changes(equity):
    integer_limit = sys.get_int_max_str_digits()
    with localcontext() as context:
        context.prec = 2
        case = sample(equity)
        r = run(case)
        assert r["outcome"] == "ESTABLISHED" and r["state"]["equity"] == equity
        if equity == "-1.25": assert r["state"]["difference"] == "-971.25"
        elif equity == "0": assert r["state"]["difference"] == "-970"
        elif equity.startswith("970."):
            assert r["state"]["difference"] == "0." + "0"*4999 + "1"
        elif equity.startswith("-0."):
            assert r["state"]["difference"] == "-970." + "0"*4999 + "1"
        else: assert r["state"]["difference"] == "9"*4997 + "030"
        assert validate(r, case) == r
    assert sys.get_int_max_str_digits() == integer_limit


@pytest.mark.parametrize("equity", ["+970", "0970", "970.0", "-0", "1e3", 970, 970.0, False])
def test_noncanonical_equity_declaration_amounts_reject(equity):
    case = sample()
    case[0]["equity"]["amount"] = equity
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field", FLAGS)
@pytest.mark.parametrize("value", [True, 0])
def test_all_rehashed_authority_mutations_reject(field, value):
    case = sample()
    r = run(case)
    r["authority"][field] = value
    reseal_result(r)
    with pytest.raises(ValueError, match="^EQUITY_DAILY_FLOOR_RESULT_MISMATCH$"):
        validate(r, case)


@pytest.mark.parametrize("field,value", [("execution", 0), ("execution", True), ("temporal_scope", "CURRENT"),
    ("state", None), ("native_references", dict(c10=None, account_snapshot=None)), ("daily_measure", None),
    ("required_targets", []), ("admission_bindings", []), ("source_authentication", "VERIFIED"), ("limitations", []),
    ("assessment_identity", "caller-identity"), ("outcome", "UNKNOWN"), ("findings", []), ("reason_codes", [])])
def test_detached_validator_reconstructs_all_result_fields(field, value):
    case = sample()
    r = run(case)
    if field == "findings": value = [dict(reason_code="C10_MISSING", subject=dict(root="REQUEST", pointer="/c10"))]
    r[field] = value
    if field != "assessment_identity": reseal_result(r)
    with pytest.raises(ValueError, match="^EQUITY_DAILY_FLOOR_RESULT_MISMATCH$"):
        validate(r, case)


def test_genuine_public_replay_calls_original_contexts_and_exact_explicit_snapshot(monkeypatch):
    case = sample()
    calls = []
    real_floor = c10.validate_as_of_daily_reset_loss_floor_state
    real_c8 = c8.validate_current_intraday_trailing_loss_threshold_state
    real_snapshot = account.validate_causal_financial_account_state_snapshot
    real_regime = regime.validate_causal_account_rule_regime_assessment
    def floor(*args, **kwargs):
        calls.append(("C10", deepcopy(args), deepcopy(kwargs)))
        return real_floor(*args, **kwargs)
    def trailing(*args, **kwargs):
        calls.append(("C8", deepcopy(args), deepcopy(kwargs)))
        return real_c8(*args, **kwargs)
    def snapshot(*args, **kwargs):
        calls.append(("SNAPSHOT", deepcopy(args), deepcopy(kwargs)))
        return real_snapshot(*args, **kwargs)
    def rules(*args, **kwargs):
        calls.append(("REGIME", deepcopy(args), deepcopy(kwargs)))
        return real_regime(*args, **kwargs)
    monkeypatch.setattr(c10, "validate_as_of_daily_reset_loss_floor_state", floor)
    monkeypatch.setattr(c8, "validate_current_intraday_trailing_loss_threshold_state", trailing)
    monkeypatch.setattr(account, "validate_causal_financial_account_state_snapshot", snapshot)
    monkeypatch.setattr(regime, "validate_causal_account_rule_regime_assessment", rules)
    r = run(case)
    assert validate(r, case) == r
    one_run = ["C10", "C8", "SNAPSHOT", "REGIME", "SNAPSHOT", "REGIME", "SNAPSHOT"]
    assert [c[0] for c in calls] == one_run * 2
    q10 = decoded(case[0]["c10"]["request_json"])
    for kind, args, kwargs in calls:
        if kind == "C10":
            assert args == (decoded(case[0]["c10"]["result_json"]), q10)
            assert kwargs == dict(trusted_c8_context=case[1], trusted_context=case[2])
    for offset in (6, 13):
        assert calls[offset][1] == (decoded(case[0]["account_snapshot"]["result_json"]), decoded(case[0]["account_snapshot"]["input_json"]))


@pytest.mark.parametrize("reverse", [False, True])
def test_rule_indices_use_original_arrays_not_normalized_order(reverse):
    case = sample()
    cf = floor_case(case)
    native = decoded(cf[0]["daily_regime"]["input_json"])
    assert [r["rule_id"] for r in native["manifest"]["packages"][0]["rules"]] == ["trailing", "daily"]
    if reverse:
        native["manifest"]["packages"][0]["rules"].reverse()
        cf[0]["daily_regime"]["selector"]["rule_index"] = 0
        upstream.set_daily(cf, native)
        replace_floor(case, cf)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    m = r["daily_measure"]
    assert m["rule_id"] == "daily" and m["rule_index"] == (0 if reverse else 1)
    assert m["package_index"] == 0 and m["package_revision"] == "1"
    assert m["definition_bindings"][0]["native_evidence_id"] == "terms"
    assert m["definition_bindings"][0]["original"]["owner"] == "C10"
    nr = decoded(cf[0]["daily_regime"]["result_json"])
    assert [x["rule_id"] for x in nr["selected_regime"]["package"]["rules"]] == ["daily", "trailing"]
    assert validate(r, case) == r


def test_multiple_definition_clauses_keep_original_order_and_indices():
    case = sample()
    cf = floor_case(case)
    q8 = decoded(cf[0]["c8"]["request_json"])
    original_c8_native = decoded(q8["provider_regime"]["input_json"])
    daily_native = decoded(cf[0]["daily_regime"]["input_json"])
    clauses = [dict(evidence_id="terms", clause_locator="z-equity"), dict(evidence_id="terms", clause_locator="a-equity")]
    for n in (original_c8_native, daily_native):
        next(r for r in n["manifest"]["packages"][0]["rules"] if r["rule_id"] == "daily")["body"]["measure"]["definition_refs"] = deepcopy(clauses)
    q8["provider_regime"] = upstream.fixture_owner().replay_regime(original_c8_native)
    upstream.replace8(cf, q8, cf[1])
    upstream.set_daily(cf, daily_native)
    replace_floor(case, cf)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    assert [(d["index"], d["clause_locator"]) for d in r["daily_measure"]["definition_bindings"]] == [(0, "z-equity"), (1, "a-equity")]
    assert validate(r, case) == r


@pytest.mark.parametrize("balances,equity,floor,difference", [
    ((), "970", "970", "0"), (("1100", "1050", "1120"), "1090", "1090", "0"),
    (("1100", "1050", "1120"), "970", "1090", "-120")])
def test_c10_floor_is_preserved_with_account_wide_history_and_changed_current_balance(balances, equity, floor, difference):
    case = sample(equity, balances)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    assert r["state"]["daily_loss_floor"] == floor and r["state"]["difference"] == difference
    native = decoded(case[0]["account_snapshot"]["result_json"])
    assert native["observation"]["account_measures"]["balance"] == "1005"
    assert {p["instrument_id"] for p in native["observation"]["positions"]["items"]} == {"EURUSD", "XAUUSD"}


def test_explicit_exact_reset_bundle_reuse_only_when_M_equals_T():
    case = sample()
    cf = floor_case(case)
    m = cf[0]["reset_boundary"]
    cf[0]["economic_time"] = m
    cf[0]["coverage"]["economic_through"] = m
    original = next(o for o in cf[0]["originals"] if o["evidence_id"] == "coverage")
    body = decoded(original["content"]); body["through"] = m
    upstream.set_content(original, canonical(body).encode())
    native = decoded(cf[0]["daily_regime"]["input_json"]); native["economic_timestamp"] = m
    upstream.set_daily(cf, native)
    case[0]["economic_time"] = case[0]["equity"]["economic_time"] = case[0]["equity"]["coverage"]["economic_time"] = m
    replace_floor(case, cf)
    q8 = decoded(cf[0]["c8"]["request_json"])
    case[0]["account_snapshot"] = deepcopy(q8["account_snapshot"])
    result = decoded(q8["account_snapshot"]["result_json"])
    case[0]["equity"]["snapshot_reference"] = dict(snapshot_id=result["snapshot_id"], bundle_sha256=digest(q8["account_snapshot"]))
    case[0]["equity"]["amount"] = result["observation"]["account_measures"]["equity"]
    case[0]["originals"][0]["source"] = deepcopy(result["observation"]["source"])
    seal(case)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and r["state"]["as_of"] == r["state"]["reset_boundary"]
    assert r["state"]["equity"] == "1000" and r["state"]["difference"] == "30"
    case = sample()
    cf = floor_case(case)
    reset_bundle = decoded(cf[0]["c8"]["request_json"])["account_snapshot"]
    case[0]["account_snapshot"] = deepcopy(reset_bundle)
    case[0]["equity"]["snapshot_reference"] = dict(snapshot_id=decoded(reset_bundle["result_json"])["snapshot_id"], bundle_sha256=digest(reset_bundle))
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field", ["scope/account/account_id", "scope/account/environment", "scope/account/currency", "scope/account/namespace/source_id",
    "scope/provider_namespace/source_id", "scope/provider_id", "scope/program_id", "scope/account_type_id", "scope/phase_id", "scope/lifecycle_id", "economic_time", "knowledge_boundary"])
def test_c10_request_scope_and_time_joins_are_exact_after_readmission(field):
    case = sample()
    value = "EUR" if field.endswith("currency") else "LIVE" if field.endswith("environment") else at(case, -1) if field == "economic_time" else at(case, 7) if field == "knowledge_boundary" else "different"
    for root in (case[0], case[0]["equity"]):
        parts = field.split("/"); row = root
        for part in parts[:-1]: row = row[part]
        row[parts[-1]] = value
    # Keep the other local joins consistent so the C10 boundary/scope join is
    # required; a stale C11 request hash must not be the reason this test passes.
    inp = decoded(case[0]["account_snapshot"]["input_json"])
    scope = case[0]["scope"]
    if field.startswith("scope/account/"):
        for key in ("account_id", "environment", "currency"):
            inp["observation"]["account"][key] = scope["account"][key]
        inp["observation"]["source"].update(scope["account"]["namespace"])
        case[0]["equity"]["currency"] = scope["account"]["currency"]
        for o in case[0]["originals"][:2]:
            o["source"].update(scope["account"]["namespace"])
            o["document"]["namespace"] = deepcopy(scope["account"]["namespace"])
    elif field.startswith("scope/provider_namespace/"):
        case[0]["originals"][2]["source"].update(scope["provider_namespace"])
        case[0]["originals"][2]["document"]["namespace"] = deepcopy(scope["provider_namespace"])
    elif field == "economic_time":
        inp["observation"]["timing"]["effective_at"] = value
        case[0]["equity"]["coverage"]["economic_time"] = value
    elif field == "knowledge_boundary":
        inp["requested_evaluation_timestamp"] = value
    replace_snapshot(case, inp)
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field,value", [("account_id", "wrong"), ("environment", "LIVE"), ("currency", "EUR"), ("source_id", "wrong-namespace"),
    ("effective_at", "2026-01-09T23:00:00.000000Z"), ("requested_evaluation_timestamp", "2026-01-10T08:00:00.000000Z")])
def test_genuinely_valid_but_misbound_explicit_snapshot_rejects(field, value):
    case = sample()
    inp = decoded(case[0]["account_snapshot"]["input_json"])
    if field in ("account_id", "environment", "currency"): inp["observation"]["account"][field] = value
    elif field == "source_id": inp["observation"]["source"][field] = value
    elif field == "effective_at": inp["observation"]["timing"][field] = value
    else: inp[field] = value
    replace_snapshot(case, inp)
    invalid(case)


@pytest.mark.parametrize("path,value", [("snapshot_reference/snapshot_id", "caller"), ("snapshot_reference/bundle_sha256", "0"*64),
    ("daily_measure_sha256", "0"*64), ("currency", "EUR"), ("amount", "971"), ("scope/lifecycle_id", "wrong"), ("scope/phase_id", None)])
def test_declared_equity_cannot_rebind_known_native_or_daily_measure_identity(path, value):
    case = sample()
    row = case[0]["equity"]; parts = path.split("/")
    for part in parts[:-1]: row = row[part]
    row[parts[-1]] = value
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["floor", "authority", "snapshot", "selector", "context8", "context10", "missing_context8", "missing_context10"])
def test_forged_dependencies_cannot_pass_even_with_new_c11_admission(kind):
    case = sample()
    if kind in ("floor", "authority"):
        r = decoded(case[0]["c10"]["result_json"])
        if kind == "floor": r["state"]["daily_loss_floor"] = "971"
        else: r["authority"]["execution"] = 0
        r["assessment_identity"] = c10.IDENTITY_PREFIX + digest({k:v for k,v in r.items() if k != "assessment_identity"})
        case[0]["c10"]["result_json"] = encoded(r)
    elif kind == "snapshot":
        r = decoded(case[0]["account_snapshot"]["result_json"])
        r["observation"]["account_measures"]["equity"] = "999"
        r.pop("snapshot_id"); r["snapshot_id"] = "financial_account_state_snapshot_" + digest(r)[:24]
        case[0]["account_snapshot"]["result_json"] = encoded(r)
    elif kind == "selector":
        q10 = decoded(case[0]["c10"]["request_json"])
        q10["daily_regime"]["selector"]["rule_index"] = 99
        case[0]["c10"]["request_json"] = encoded(q10)
        case[2]["request_sha256"] = digest(q10)
    elif kind == "context8": case[1]["request_sha256"] = "0"*64
    elif kind == "context10": case[2]["request_sha256"] = "0"*64
    elif kind == "missing_context8": case[1] = None
    else: case[2] = None
    seal(case)
    invalid(case)


@pytest.mark.parametrize("target", TARGETS)
def test_each_admission_target_requires_its_own_assertion_and_support(target):
    case = sample()
    a = next(a for a in case[0]["support_assertions"] if a["target"] == target)
    a["citations"].pop()
    seal(case)
    r = run(case)
    assert r["reason_codes"] == ["SUPPORT_INCOMPLETE"] and r["state"] is None
    binding = next(b for b in r["admission_bindings"] if b["target"] == target)
    assert binding["assertion_sha256"] == digest(a) and binding["originals"] == members(case)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("kind,reason", [("missing", "RECEIPT_MISSING"), ("unresolved", "RECEIPT_UNRESOLVED"), ("subset", "RECEIPT_MEMBERSHIP_INCOMPLETE")])
def test_each_target_receipt_is_independent_and_never_selects_required_membership(target, kind, reason):
    case = sample()
    receipt = next(r for r in case[3]["receipts"] if r["target"] == target)
    if kind == "missing": case[3]["receipts"].remove(receipt)
    elif kind == "unresolved": receipt["decision"] = "UNRESOLVED"
    else: receipt["originals"] = []
    r = run(case)
    assert r["reason_codes"] == [reason] and r["state"] is None
    assert r["required_targets"] == list(TARGETS)
    b = next(b for b in r["admission_bindings"] if b["target"] == target)
    assert b["originals"] == members(case)
    assert b["receipt_sha256"] == (None if kind == "missing" else digest(receipt))


@pytest.mark.parametrize("field", ["request_sha256", "c8_context_sha256", "c10_context_sha256"])
def test_context_root_binding_is_required_with_zero_receipts(field):
    case = sample()
    case[3]["receipts"] = []
    assert run(case)["reason_codes"] == ["RECEIPT_MISSING"]
    case[3][field] = "0"*64
    invalid(case)


@pytest.mark.parametrize("field", ["request_sha256", "c8_context_sha256", "c10_context_sha256", "assertion_sha256", "target", "decision", "originals"])
def test_receipt_binding_corruption_is_structural(field):
    case = sample()
    receipt = case[3]["receipts"][0]
    receipt[field] = "different-target" if field == "target" else "APPROVED" if field == "decision" else [dict(owner="C11", evidence_id="missing", original_sha256="0"*64)] if field == "originals" else "0"*64
    invalid(case)


@pytest.mark.parametrize("kind", ["wrong_hash", "wrong_owner", "duplicate", "unordered", "extra_field"])
def test_owner_qualified_receipt_member_validation(kind):
    case = sample()
    rows = case[3]["receipts"][0]["originals"]
    if kind == "wrong_hash": rows[0]["original_sha256"] = "0"*64
    elif kind == "wrong_owner": rows[0]["owner"] = "C11"
    elif kind == "duplicate": rows.insert(0, deepcopy(rows[0]))
    elif kind == "unordered": rows.reverse()
    else: rows[0]["source_authentic"] = True
    invalid(case)


@pytest.mark.parametrize("field,value,pointer", [("available_at", "late", "/available_at"), ("effective_from", "after_admission", "/effective_from"), ("effective_from", "after_K", "/effective_from"),
    ("effective_until", "at_K", "/effective_until"), ("effective_until", "at_admission", "/effective_until")])
def test_context_knowledge_and_mandate_boundaries(field, value, pointer):
    case = sample()
    values = dict(late=at(case, 7), after_admission=at(case, 5, 31), after_K=at(case, 7), at_K=case[0]["knowledge_boundary"], at_admission=case[3]["admitted_at"])
    case[3][field] = values[value]
    r = run(case)
    assert r["reason_codes"] == ["EQUITY_ADMISSION_NOT_CURRENT"] and r["state"] is None
    assert r["findings"][0]["subject"] == dict(root="TRUSTED_CONTEXT", pointer=pointer)


@pytest.mark.parametrize("kind", ["observation_after_K", "publication_after_observation", "coverage_publication_before_SE", "coverage_observation_before_SE",
    "SE_before_T", "SE_after_K", "admitted_after_available", "admitted_before_upstream_available", "native_observation_after_admission", "aggregate_publication_mismatch"])
def test_structural_causality_rejections_survive_readmission_and_later_unknown(kind):
    case = sample()
    q = case[0]
    if kind == "observation_after_K": q["originals"][2]["observed_at"] = at(case, 7)
    elif kind == "publication_after_observation": q["originals"][2]["source_available_at"] = at(case, 1)
    elif kind == "coverage_publication_before_SE": q["originals"][1]["source_available_at"] = at(case, 3, 29)
    elif kind == "coverage_observation_before_SE": q["originals"][1].update(source_available_at=None, observed_at=at(case, 3, 29))
    elif kind == "SE_before_T":
        q["source_information_cutoff"] = q["equity"]["coverage"]["source_information_cutoff"] = at(case, -1)
    elif kind == "SE_after_K":
        q["source_information_cutoff"] = q["equity"]["coverage"]["source_information_cutoff"] = at(case, 7)
    elif kind == "admitted_after_available": case[3]["admitted_at"] = at(case, 5, 32)
    elif kind == "admitted_before_upstream_available": case[3]["admitted_at"] = at(case, 5, 4)
    elif kind == "native_observation_after_admission":
        inp = decoded(q["account_snapshot"]["input_json"]); inp["observation"]["timing"]["observed_at"] = at(case, 5, 35)
        replace_snapshot(case, inp)
    else: q["originals"][0]["source_available_at"] = at(case, 2)
    q["equity"]["coverage"]["account_wide"] = "UNKNOWN"
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field", ["source_revisions", "known_later_corrections"])
@pytest.mark.parametrize("status", ["PRESENT", "UNKNOWN"])
def test_equity_and_later_known_corrections_never_silently_reuse_approval(field, status):
    case = sample()
    case[0]["equity"]["coverage"][field] = status
    seal(case)
    r = run(case)
    assert r["reason_codes"] == ["SOURCE_REVISIONS_UNRESOLVED"] and r["state"] is None
    assert r["findings"][0]["subject"]["pointer"] == "/equity/coverage/" + field


@pytest.mark.parametrize("field", COMPONENTS)
@pytest.mark.parametrize("status", ["OMITTED", "UNKNOWN"])
def test_commissions_floating_pnl_financing_and_all_costs_are_required(field, status):
    case = sample()
    case[0]["equity"]["components"][field] = status
    seal(case)
    r = run(case)
    assert r["reason_codes"] == ["COMPONENT_TREATMENT_UNSUPPORTED"]
    assert r["findings"][0]["subject"]["pointer"] == "/equity/components/" + field


@pytest.mark.parametrize("field", ["commissions", "financing", "other_costs"])
def test_not_applicable_is_not_a_substitute_for_native_cost_inclusion(field):
    case = sample()
    case[0]["equity"]["components"][field] = "INCLUDED_ONCE" if field == "other_costs" else "NOT_APPLICABLE"
    seal(case)
    assert run(case)["reason_codes"] == ["COMPONENT_TREATMENT_UNSUPPORTED"]


@pytest.mark.parametrize("equivalence", ["DIFFERENT", "UNKNOWN"])
def test_equity_label_and_numeric_equality_cannot_establish_measure_equivalence(equivalence):
    case = sample()
    case[0]["equity"]["measure_equivalence"] = equivalence
    seal(case)
    assert run(case)["reason_codes"] == ["RULE_MEASURE_EQUIVALENCE_UNRESOLVED"]


@pytest.mark.parametrize("kind", ["start_unknown", "start_after_T", "end_at_T", "end_unknown", "open_ended"])
def test_definition_period_applicability_is_historical_and_half_open(kind):
    case = sample()
    p = case[0]["equity"]["definition_period"]
    if kind == "start_unknown": p["effective_from"] = None
    elif kind == "start_after_T": p["effective_from"] = at(case, 1)
    elif kind == "end_at_T": p["effective_until"] = case[0]["economic_time"]
    elif kind == "end_unknown": p.update(effective_until=None, end_status="UNKNOWN")
    else: p.update(effective_until=None, end_status="OPEN_ENDED")
    seal(case)
    assert run(case)["reason_codes"] == ["COMPARISON_ESTABLISHED" if kind == "open_ended" else "DEFINITION_NOT_APPLICABLE"]


@pytest.mark.parametrize("kind", ["raw_hash", "same_version", "same_local_capture", "cross_owner_capture", "cross_owner_version", "wrong_namespace", "aggregate_source", "empty_content"])
def test_original_identity_conflicts_and_provenance_are_structural(kind):
    case = sample()
    q = case[0]
    if kind == "raw_hash": q["originals"][0]["content_sha256"] = "0"*64
    elif kind == "same_version":
        d = q["originals"][2]; d["source"].update(q["scope"]["account"]["namespace"]); d["document"] = deepcopy(q["originals"][0]["document"])
    elif kind == "same_local_capture":
        q["originals"][2] = deepcopy(q["originals"][0]); q["originals"][2]["evidence_id"] = "definition"
    elif kind in ("cross_owner_capture", "cross_owner_version"):
        orig = next(o for o in decoded(q["c10"]["request_json"])["originals"] if o["evidence_id"] == "daily_rule")
        q["originals"][2] = deepcopy(orig); q["originals"][2]["evidence_id"] = "definition"
        if kind == "cross_owner_capture": q["originals"][2]["observed_at"] = at(case, 4)
        else:
            upstream.set_content(q["originals"][2], b'changed source bytes')
            build_support(case)
    elif kind == "wrong_namespace": q["originals"][0]["document"]["namespace"]["source_id"] = "other"
    elif kind == "aggregate_source": q["originals"][0]["source"]["source_snapshot_id"] = "other"
    else:
        upstream.set_content(q["originals"][2], b'')
        for a in q["support_assertions"]:
            a["citations"] = [c for c in a["citations"] if (c["owner"], c["evidence_id"]) != ("C11", "definition")]
    seal(case)
    invalid(case)


@pytest.mark.parametrize("identifier,root", [("daily_rule", "C8_REQUEST"), ("enrollment", "C10_REQUEST")])
def test_revision_conflict_subject_is_the_first_original_in_complete_owner_order(identifier, root):
    case = sample()
    q10 = decoded(case[0]["c10"]["request_json"])
    original = deepcopy(next(o for o in q10["originals"] if o["evidence_id"] == identifier))
    original["evidence_id"] = "definition"; original["document"]["document_revision"] = "2"
    case[0]["originals"][2] = original
    build_support(case); seal(case)
    r = run(case)
    assert r["reason_codes"] == ["DOCUMENT_VERSION_CONFLICT"]
    expected_rows = decoded(q10["c8"]["request_json"])["originals"] if root == "C8_REQUEST" else q10["originals"]
    target_doc = original["document"]["document_id"]
    i = next(i for i,o in enumerate(expected_rows) if o["document"]["document_id"] == target_doc)
    assert r["findings"][0]["subject"] == dict(root=root, pointer=f"/originals/{i}/document")
    assert validate(r, case) == r


@pytest.mark.parametrize("publication_offset,reason", [(30, "COMPARISON_ESTABLISHED"), (35, "EQUITY_SOURCE_CUTOFF_INSUFFICIENT")])
def test_cross_owner_report_role_sharing_preserves_distinct_cutoffs(publication_offset, reason):
    case = sample()
    cf = floor_case(case)
    original = next(o for o in cf[0]["originals"] if o["evidence_id"] == "coverage")
    original["source"] = dict(**cf[0]["scope"]["account"]["namespace"], source_snapshot_id="shared-report")
    original["document"]["namespace"] = deepcopy(cf[0]["scope"]["account"]["namespace"])
    original.update(source_available_at=at(case, 3, publication_offset), observed_at=at(case, 3, publication_offset))
    upstream.seal(cf)
    replace_floor(case, cf)
    shared = deepcopy(original); shared["evidence_id"] = "coverage"
    case[0]["originals"] = [case[0]["originals"][0], shared]
    case[0]["equity"]["roles"]["definition"] = deepcopy(case[0]["equity"]["roles"]["coverage"])
    build_support(case); seal(case)
    r = run(case)
    assert r["reason_codes"] == [reason]
    assert decoded(case[0]["c10"]["result_json"])["outcome"] == "ESTABLISHED"
    assert case[0]["source_information_cutoff"] != cf[0]["source_information_cutoff"]
    assert validate(r, case) == r


def test_original_document_identity_is_not_snapshot_id_or_metadata_hash():
    case = sample()
    original = case[0]["originals"][0]
    assert original["document"]["document_id"] != original["source"]["source_snapshot_id"]
    assert original["content_sha256"] != digest(original)
    original["document"]["document_id"] = "independent-document-name"
    seal(case)
    assert run(case)["outcome"] == "ESTABLISHED"


@pytest.mark.parametrize("kind", ["c10_bytes", "snapshot_bytes", "native_offset_timestamp"])
def test_original_byte_bundle_hashes_are_not_normalized_identity_hashes(kind):
    case = sample()
    before = run(case)
    if kind == "c10_bytes":
        q10 = decoded(case[0]["c10"]["request_json"])
        case[0]["c10"]["request_json"] = base64.b64encode(json.dumps(q10, indent=2).encode()).decode()
        case[0]["equity"]["daily_measure_sha256"] = digest(measure_reference(case))
    else:
        inp = decoded(case[0]["account_snapshot"]["input_json"])
        if kind == "native_offset_timestamp":
            inp["observation"]["timing"]["effective_at"] = "2026-01-10T02:00:00+01:00"
        case[0]["account_snapshot"]["input_json"] = base64.b64encode(json.dumps(inp, indent=2).encode()).decode()
        case[0]["equity"]["snapshot_reference"]["bundle_sha256"] = digest(case[0]["account_snapshot"])
    seal(case)
    after = run(case)
    assert after["state"] == before["state"]
    owner = "c10" if kind == "c10_bytes" else "account_snapshot"
    assert after["native_references"][owner]["bundle_sha256"] != before["native_references"][owner]["bundle_sha256"]
    assert after["assessment_identity"] != before["assessment_identity"]
    identity_field = "assessment_identity" if owner == "c10" else "snapshot_id"
    assert after["native_references"][owner][identity_field] == before["native_references"][owner][identity_field]
    assert validate(after, case) == after


@pytest.mark.parametrize("reason", ["C10_MISSING", "C8_CONTEXT_MISSING", "C10_CONTEXT_MISSING", "C10_NOT_ESTABLISHED", "EQUITY_SNAPSHOT_MISSING", "NATIVE_EQUITY_MISSING", "EQUITY_ADMISSION_MISSING", "RECEIPT_MISSING"])
def test_valid_references_are_retained_by_presence_even_for_unknown(reason):
    case = unknown_case(reason)
    r = run(case)
    dep = case[0]["c10"]
    if dep is None: assert r["native_references"]["c10"] is None
    else:
        floor = decoded(dep["result_json"])
        assert r["native_references"]["c10"] == dict(assessment_identity=floor["assessment_identity"], outcome=floor["outcome"], bundle_sha256=digest(dep))
    snapshot = case[0]["account_snapshot"]
    if snapshot is None: assert r["native_references"]["account_snapshot"] is None
    else:
        assert r["native_references"]["account_snapshot"] == dict(snapshot_id=decoded(snapshot["result_json"])["snapshot_id"], bundle_sha256=digest(snapshot))
    assert r["daily_measure"] == measure_reference(case)


@pytest.mark.parametrize("kind", ["negative_start", "boolean_start", "empty_range", "past_bytes", "wrong_owner", "unknown_evidence", "duplicate", "unordered"])
def test_citations_are_owner_qualified_original_byte_ranges(kind):
    case = sample()
    rows = case[0]["support_assertions"][0]["citations"]
    if kind == "negative_start": rows[0]["start"] = -1
    elif kind == "boolean_start": rows[0]["start"] = False
    elif kind == "empty_range": rows[0]["end"] = 0
    elif kind == "past_bytes": rows[0]["end"] = 10**9
    elif kind == "wrong_owner": rows[0]["owner"] = "C12"
    elif kind == "unknown_evidence": rows[0]["evidence_id"] = "absent"
    elif kind == "duplicate": rows.insert(0, deepcopy(rows[0]))
    else: rows.reverse()
    seal(case)
    invalid(case)


@pytest.mark.parametrize("collection", ["originals", "support_assertions", "receipts"])
@pytest.mark.parametrize("kind", ["duplicate", "unordered"])
def test_local_collection_duplicates_and_order_are_rejected(collection, kind):
    case = sample()
    if collection == "originals":
        if kind == "duplicate": case[0]["originals"][1]["evidence_id"] = "aggregate"
        else: case[0]["originals"].reverse()
        seal(case)
    elif collection == "support_assertions":
        rows = case[0][collection]
        if kind == "duplicate": rows.insert(0, deepcopy(rows[0]))
        else: rows.reverse()
        seal(case)
    else:
        rows = case[3][collection]
        if kind == "duplicate": rows.insert(0, deepcopy(rows[0]))
        else: rows.reverse()
    invalid(case)


def pointer(root, path):
    row = root
    for token in path.split("/") if path else []:
        row = row[int(token)] if isinstance(row, list) else row[token]
    return row


@pytest.mark.parametrize("path", ["", "equity", "equity/scope", "equity/scope/account", "equity/roles", "equity/roles/aggregate", "equity/coverage", "equity/components", "equity/definition_period",
    "c10", "account_snapshot", "originals/0", "originals/0/source", "originals/0/document", "support_assertions/0", "support_assertions/0/citations/0"])
def test_request_and_all_nested_local_objects_are_sealed(path):
    case = sample()
    pointer(case[0], path)["unspecified"] = "not-permitted"
    seal(case)
    invalid(case)


@pytest.mark.parametrize("path", ["", "receipts/0", "receipts/0/originals/0", "authority_namespace"])
def test_independent_context_and_receipt_objects_are_sealed(path):
    case = sample()
    pointer(case[3], path)["unspecified"] = True
    invalid(case)


@pytest.mark.parametrize("path,key", [("", "contract"), ("equity", "measure_equivalence"), ("equity/coverage", "known_later_corrections"),
    ("equity/components", "financing"), ("originals/0", "media_type"), ("originals/0/document", "document_revision")])
def test_required_fields_do_not_acquire_defaults(path, key):
    case = sample()
    del pointer(case[0], path)[key]
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["duplicate_json_key", "float_json", "json_not_object", "invalid_utf8", "base64_whitespace", "missing_padding", "unicode_surrogate"])
def test_dependency_byte_grammar_is_strict_before_unknown(kind):
    case = unknown_case("EQUITY_AMOUNT_UNDECLARED")
    if kind == "duplicate_json_key": raw = b'{"contract":1,"contract":2}'
    elif kind == "float_json": raw = b'{"x":1.5}'
    elif kind == "json_not_object": raw = b'[]'
    elif kind == "invalid_utf8": raw = b'\xff'
    elif kind == "unicode_surrogate": raw = b'{"x":"\\ud800"}'
    else: raw = None
    if raw is not None: case[0]["account_snapshot"]["input_json"] = base64.b64encode(raw).decode()
    elif kind == "base64_whitespace": case[0]["account_snapshot"]["input_json"] += "\n"
    else: case[0]["account_snapshot"]["input_json"] = "e30"
    seal(case)
    invalid(case)


@pytest.mark.parametrize("value", [" leading", "trailing ", "\u00a0edge", "\x1cedge", "\ud800"])
def test_local_text_fields_obey_frozen_unicode_rules(value):
    case = sample()
    case[0]["originals"][2]["document"]["document_id"] = value
    seal(case)
    invalid(case)


@pytest.mark.parametrize("path,value", [
    ("state/difference", "1"), ("state/equity", "999"), ("state/daily_loss_floor", "999"), ("state/relation", "ABOVE"),
    ("daily_measure/package_revision", 1), ("daily_measure/measure_sha256", "0"*64), ("daily_measure/native_rule_sha256", "0"*64),
    ("daily_measure/definition_bindings/0/index", False), ("daily_measure/definition_bindings/0/clause_locator", "different"),
    ("daily_measure/definition_bindings/0/original/original_sha256", "0"*64), ("daily_measure/cost_treatment/financing", "NOT_APPLICABLE"),
    ("native_references/c10/bundle_sha256", "0"*64), ("native_references/account_snapshot/snapshot_id", "forged"),
    ("admission_bindings/0/assertion_sha256", None), ("admission_bindings/0/receipt_sha256", None), ("admission_bindings/0/originals/0/original_sha256", "0"*64),
    ("reconstruction_evidence/request_sha256", "0"*64), ("reconstruction_evidence/c8_context_sha256", None),
    ("reconstruction_evidence/c10_context_sha256", None), ("reconstruction_evidence/trusted_context_sha256", None),
    ("reconstruction_evidence/request/equity/amount", "999")])
def test_rehashed_nested_result_tampering_never_replaces_full_reconstruction(path, value):
    case = sample()
    r = run(case)
    parts = path.split("/"); parent = pointer(r, "/".join(parts[:-1])); parent[parts[-1]] = value
    reseal_result(r)
    with pytest.raises(ValueError, match="^EQUITY_DAILY_FLOOR_RESULT_MISMATCH$"):
        validate(r, case)


@pytest.mark.parametrize("equity", ["969.99", "970", "970.01"])
def test_authority_and_profit_lock_veto_are_preserved_for_every_relation(equity):
    case = sample(equity)
    body = decoded(case[0]["originals"][1]["content"])
    body.update(earlier_daily_equity_breach=True, external_profit_lock="FROZEN_AWAITING_PAYOUT")
    upstream.set_content(case[0]["originals"][1], canonical(body).encode())
    build_support(case); seal(case)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    assert r["authority"] == dict.fromkeys(FLAGS, False)
    assert all(type(v) is bool and v is False for v in r["authority"].values())
    assert r["execution"] is False
    assert "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL" in r["limitations"]
    assert "NO_EARLIER_BREACH_ABSENCE" in r["limitations"] and "NO_CONTINUOUS_COMPLIANCE" in r["limitations"]
    assert not {"trading_allowed", "compliant", "payout_allowed", "earlier_breach_cleared"} & set(r)
    assert r["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"


@pytest.mark.parametrize("date,hours", [("2026-01-10", 24), ("2026-03-29", 23), ("2026-10-25", 25)])
def test_floor_session_boundaries_remain_owned_by_c10_including_DST(date, hours):
    case = sample(date=date)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    m = datetime.fromisoformat(r["state"]["reset_boundary"].replace("Z", "+00:00"))
    n = datetime.fromisoformat(r["state"]["next_reset_boundary"].replace("Z", "+00:00"))
    assert (n-m).total_seconds() == hours*3600
    assert r["state"]["next_reset_boundary"] > case[0]["knowledge_boundary"]
    assert validate(r, case) == r


def test_detached_invalid_input_retains_input_error_not_result_mismatch():
    case = sample()
    r = run(case)
    case[0]["equity"]["amount"] = "999"
    seal(case)
    with pytest.raises(ValueError, match="^INVALID_EQUITY_DAILY_FLOOR_INPUT$"):
        validate(r, case)


@pytest.mark.parametrize("role", ["aggregate", "definition", "coverage"])
@pytest.mark.parametrize("kind", ["hash", "dangling"])
def test_original_references_bind_complete_existing_envelopes(role, kind):
    case = sample()
    ref = case[0]["equity"]["roles"][role]
    ref["original_sha256" if kind == "hash" else "evidence_id"] = "0"*64 if kind == "hash" else "missing"
    seal(case, original_refs=False)
    invalid(case)


@pytest.mark.parametrize("status", ["OMISSION", "DUPLICATION", "UNKNOWN"])
def test_integrity_is_a_separate_requirement_even_with_all_components_present(status):
    case = sample()
    case[0]["equity"]["component_integrity"] = status
    seal(case)
    assert run(case)["reason_codes"] == ["COMPONENT_INTEGRITY_UNRESOLVED"]


@pytest.mark.parametrize("kind", ["null_phase", "extra_authority", "orphan_c8", "orphan_c10"])
def test_missing_identity_or_caller_authority_never_invents_valid_scope(kind):
    case = sample()
    if kind == "null_phase": case[0]["scope"]["phase_id"] = case[0]["equity"]["scope"]["phase_id"] = None
    elif kind == "extra_authority": case[0]["authority"] = dict.fromkeys(FLAGS, True)
    else:
        case[0].update(c10=None, account_snapshot=None, equity=None, originals=[], support_assertions=[])
        if kind == "orphan_c8": case[2] = None
        else: case[1] = None
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["negative_interval", "unknown_end_with_value", "known_end_null"])
def test_invalid_definition_schema_cannot_degrade_to_unknown(kind):
    case = sample()
    p = case[0]["equity"]["definition_period"]
    if kind == "negative_interval": p["effective_until"] = p["effective_from"]
    elif kind == "unknown_end_with_value": p["end_status"] = "UNKNOWN"
    else: p["effective_until"] = None
    seal(case)
    invalid(case)


def test_arbitrary_precision_context_integer_without_changing_global_limit():
    case = sample()
    limit = sys.get_int_max_str_digits()
    expected_bytes = canonical(case[3]).replace('"mandate_revision":1', '"mandate_revision":1' + '0'*5000).encode()
    case[3]["mandate_revision"] = 10**5000
    r = run(case)
    assert r["outcome"] == "ESTABLISHED"
    assert r["reconstruction_evidence"]["trusted_context_sha256"] == hashlib.sha256(expected_bytes).hexdigest()
    assert validate(r, case) == r
    assert sys.get_int_max_str_digits() == limit


def test_T_equal_previous_session_end_cannot_use_old_floor_session():
    case = sample()
    cf = floor_case(case)
    n = cf[0]["calendar"]["utc_end"]
    # A retained old positive result at a different T cannot pass the C10/C11 join.
    case[0]["economic_time"] = case[0]["equity"]["economic_time"] = case[0]["equity"]["coverage"]["economic_time"] = n
    case[0]["source_information_cutoff"] = case[0]["equity"]["coverage"]["source_information_cutoff"] = n
    case[0]["knowledge_boundary"] = case[0]["equity"]["knowledge_boundary"] = n
    seal(case)
    invalid(case)


def test_unsupported_upstream_measure_is_retained_unknown_without_local_equity_adjustment():
    case = sample()
    cf = floor_case(case)
    native = decoded(cf[0]["daily_regime"]["input_json"])
    daily = next(r for r in native["manifest"]["packages"][0]["rules"] if r["rule_id"] == "daily")
    daily["body"]["measure"]["cost_treatment"]["financing"] = "SUBTRACT_SEPARATELY"
    upstream.set_daily(cf, native)
    replace_floor(case, cf)
    r = run(case)
    assert r["reason_codes"] == ["C10_NOT_ESTABLISHED"] and r["state"] is None and r["daily_measure"] is None
    assert r["native_references"]["c10"]["outcome"] == "UNKNOWN"


def test_receipt_failure_priority_is_global_before_membership():
    case = sample()
    case[3]["receipts"][0]["originals"] = []
    case[3]["receipts"][-1]["decision"] = "UNRESOLVED"
    r = run(case)
    assert r["reason_codes"] == ["RECEIPT_UNRESOLVED"]
    assert r["findings"][0]["subject"]["pointer"] == "/receipts/4"
    case[3]["receipts"].pop(1)
    assert run(case)["reason_codes"] == ["RECEIPT_MISSING"]


def test_other_charges_in_measure_requires_inclusion_without_second_subtraction():
    case = sample()
    cf = floor_case(case)
    q8 = decoded(cf[0]["c8"]["request_json"])
    n8 = decoded(q8["provider_regime"]["input_json"])
    n10 = decoded(cf[0]["daily_regime"]["input_json"])
    for native in (n8, n10):
        daily = next(r for r in native["manifest"]["packages"][0]["rules"] if r["rule_id"] == "daily")
        daily["body"]["measure"]["cost_treatment"]["other_charges"] = "IN_MEASURE"
    terms = next(o for o in q8["originals"] if o["evidence_id"] == "terms")
    body = decoded(terms["content"])
    body["daily_rule"] = deepcopy(next(r for r in n8["manifest"]["packages"][0]["rules"] if r["rule_id"] == "daily")["body"])
    body["synthetic_equity_definition"] = "All account P/L and applicable commissions, swaps, financing and other charges are already included in equity exactly once."
    upstream.set_content(terms, canonical(body).encode())
    for native in (n8, n10):
        next(e for e in native["manifest"]["evidence"] if e["evidence_id"] == "terms")["document_sha256"] = terms["content_sha256"]
    q8["provider_regime"] = upstream.fixture_owner().replay_regime(n8)
    copied = deepcopy(terms); copied["evidence_id"] = "daily_rule"
    cf[0]["originals"][next(i for i,o in enumerate(cf[0]["originals"]) if o["evidence_id"] == "daily_rule")] = copied
    upstream.replace8(cf, q8, cf[1])
    upstream.set_daily(cf, n10)
    replace_floor(case, cf)
    case[0]["equity"]["components"]["other_costs"] = "INCLUDED_ONCE"
    definition = decoded(case[0]["originals"][2]["content"])
    definition.update(selected_daily_measure=measure_reference(case), definition=body["synthetic_equity_definition"])
    upstream.set_content(case[0]["originals"][2], canonical(definition).encode())
    aggregate = decoded(case[0]["originals"][0]["content"]); aggregate["other_charges"] = "0"
    upstream.set_content(case[0]["originals"][0], canonical(aggregate).encode())
    build_support(case); seal(case)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and r["state"]["difference"] == "0"
    assert r["daily_measure"]["cost_treatment"]["other_charges"] == "IN_MEASURE"
    assert validate(r, case) == r
    case[0]["equity"]["components"]["other_costs"] = "NOT_APPLICABLE"
    seal(case)
    assert run(case)["reason_codes"] == ["COMPONENT_TREATMENT_UNSUPPORTED"]


def test_native_position_inventory_is_not_an_equity_reconstruction_engine():
    case = sample()
    inp = decoded(case[0]["account_snapshot"]["input_json"])
    inp["observation"]["positions"] = dict(completeness="UNAVAILABLE", items=[])
    replace_snapshot(case, inp)
    r = run(case)
    assert r["outcome"] == "ESTABLISHED" and r["state"]["equity"] == "970"
    assert case[0]["equity"]["coverage"]["account_wide"] == "COMPLETE"
    assert validate(r, case) == r
