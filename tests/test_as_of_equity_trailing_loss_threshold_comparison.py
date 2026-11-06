"""Frozen C9 contract witnesses using real C8 and native public replay.

All provider/source documents and host admissions here are explicitly synthetic.
Rebinding a fixture issues test admission; it never mocks an owner verdict.
"""
import ast
import base64
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from ced_one.business_divisions.trading import as_of_equity_trailing_loss_threshold_comparison as c9
from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account

upstream = SimpleNamespace(**runpy.run_path(str(Path(__file__).with_name("test_current_intraday_trailing_loss_threshold_state.py"))))


TARGET_ROLES = {
    "EQUITY_IDENTITY_BINDING": ("aggregate", "definition"),
    "EQUITY_AGGREGATE_MEANING": ("aggregate", "definition"),
    "EQUITY_ACCOUNT_WIDE_COMPLETENESS": ("aggregate", "coverage"),
    "EQUITY_COST_COMPONENTS": ("definition", "coverage"),
    "EQUITY_SOURCE_VERSION_VALIDITY": ("aggregate", "definition", "coverage"),
}
FLAGS = ("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval",
         "trade_decision", "financial_risk", "execution")
T, K = upstream.T, upstream.K
time = upstream.time


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def encoded(value):
    return base64.b64encode(canonical(value).encode()).decode()


def decoded(value):
    return json.loads(base64.b64decode(value))


def original(identifier, body, source, published, observed):
    raw = canonical(body).encode()
    return dict(evidence_id=identifier, source=deepcopy(source),
                document=dict(namespace={k: source[k] for k in ("source_id", "source_contract", "source_contract_version")},
                              document_id="synthetic-equity-" + identifier, document_revision="1"),
                media_type="application/json", content=base64.b64encode(raw).decode(),
                content_sha256=hashlib.sha256(raw).hexdigest(), source_available_at=published, observed_at=observed)


def set_content(row, body):
    raw = canonical(body).encode()
    row["content"] = base64.b64encode(raw).decode()
    row["content_sha256"] = hashlib.sha256(raw).hexdigest()


def seal(case):
    """Bind all existing declarations and issue independent synthetic receipts."""
    q, c8_context, context = case
    originals = {row["evidence_id"]: row for row in q["originals"]}
    if q["equity"] is not None:
        for ref in q["equity"]["originals"].values():
            if ref is not None and ref["evidence_id"] in originals:
                ref["original_sha256"] = digest(originals[ref["evidence_id"]])
    for assertion in q["support_assertions"]:
        assertion["equity_sha256"] = None if q["equity"] is None else digest(q["equity"])
    if context is not None:
        context["request_sha256"] = digest(q)
        context["c8_context_sha256"] = None if c8_context is None else digest(c8_context)
        assertions = {row["target"]: row for row in q["support_assertions"]}
        context["receipts"] = [dict(target=target, request_sha256=digest(q),
            c8_context_sha256=context["c8_context_sha256"],
            assertion_sha256=None if target not in assertions else digest(assertions[target]),
            original_ids=list(originals), decision="ADMITTED") for target in TARGET_ROLES]
    return case


def replace_c8(case, q8, context8):
    if context8 is not None:
        upstream.admit(q8, context8)
    r8 = c8.evaluate_current_intraday_trailing_loss_threshold_state(q8, trusted_context=context8)
    case[0]["c8"] = dict(request_json=encoded(q8), result_json=encoded(r8))
    case[1] = context8
    if q8["account_snapshot"] is not None and case[0]["equity"] is not None:
        bundle = q8["account_snapshot"]
        native = decoded(bundle["result_json"])
        equity = case[0]["equity"]
        equity.update(snapshot_source=deepcopy(native["observation"]["source"]), snapshot_id=native["snapshot_id"],
                      snapshot_bundle_sha256=digest(bundle), amount=native["observation"]["account_measures"]["equity"])
    return seal(case)


def sample(equity="950", balances=(), initial="1000"):
    q8, context8 = upstream.sample(balances, initial=initial)
    native_input = decoded(q8["account_snapshot"]["input_json"])
    final_balance = balances[-1] if balances else initial
    native_input["observation"]["account_measures"] = dict(completeness="PARTIAL", balance=final_balance,
        equity=equity, used_margin=None, free_margin=None)
    native_input["observation"]["positions"]["items"] = [
        dict(position_id="open-xau", instrument_id="XAUUSD", direction="LONG", quantity="1", quantity_unit="LOT"),
        dict(position_id="open-eur", instrument_id="EURUSD", direction="SHORT", quantity="1", quantity_unit="LOT")]
    snapshot = account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(native_input).to_dict()
    q8["account_snapshot"] = dict(input_json=encoded(native_input), result_json=encoded(snapshot))
    upstream.admit(q8, context8)
    r8 = c8.evaluate_current_intraday_trailing_loss_threshold_state(q8, trusted_context=context8)
    source = native_input["observation"]["source"]
    q = dict(contract=c9.CONTRACT, rule_version=c9.RULE_VERSION, economic_time=T, knowledge_boundary=K,
             scope=deepcopy(q8["scope"]), c8=dict(request_json=encoded(q8), result_json=encoded(r8)),
             equity=None, originals=[], support_assertions=[])
    q["originals"] = [
        original("aggregate", dict(synthetic=True, scope=q["scope"], effective_at=T, balance=final_balance, equity=equity,
            instruments=["XAUUSD", "EURUSD"], floating_pnl=None if equity is None else upstream.number(Fraction(equity)-Fraction(final_balance)),
            costs="included exactly once", source=source), source, time(11), time(11)),
        original("coverage", dict(synthetic=True, scope=q["scope"], effective_at=T, information_cutoff=time(11, 8),
            all_account_instruments=True, components_complete_exactly_once=True, revisions=[]),
            dict(**upstream.ACCOUNT_NS, source_snapshot_id="coverage"), time(11, 9), time(11, 10)),
        original("definition", dict(synthetic=True, scope=q["scope"], definition="account-wide balance plus net floating P/L",
            costs="commissions, swaps and all other applicable costs are already included exactly once",
            applicable_from=time(1), applicable_until=None, provider_rule="synthetic C8 trailing equity comparison"),
            dict(**upstream.ACCOUNT_NS, source_snapshot_id="definition"), time(9), time(9)),
    ]
    q["equity"] = dict(scope=deepcopy(q["scope"]), economic_time=T, knowledge_boundary=K,
        snapshot_source=deepcopy(source), snapshot_id=snapshot["snapshot_id"], snapshot_bundle_sha256=digest(q8["account_snapshot"]),
        amount=equity, currency="USD", originals={role: dict(evidence_id=role, original_sha256=digest(next(r for r in q["originals"] if r["evidence_id"]==role))) for role in ("aggregate", "definition", "coverage")},
        definition_period=dict(effective_from=time(1), effective_until=None, end_status="OPEN_ENDED"),
        source_information_cutoff=time(11, 8), account_wide="COMPLETE",
        components=dict.fromkeys(("balance", "floating_pnl", "commissions", "swaps", "other_costs"), "INCLUDED_ONCE"),
        component_integrity="COMPLETE_EXACTLY_ONCE", source_revisions="NONE")
    for target, roles in TARGET_ROLES.items():
        citations = [dict(evidence_id=role, start=0, end=len(base64.b64decode(next(r for r in q["originals"] if r["evidence_id"]==role)["content"]))) for role in sorted(roles)]
        q["support_assertions"].append(dict(target=target, equity_sha256=digest(q["equity"]), citations=citations))
    context = dict(contract=c9.ADMISSION_CONTRACT, rule_version=c9.ADMISSION_RULE_VERSION,
        admission_id="synthetic-equity-admission", authority_namespace=deepcopy(upstream.NS), authority_id="independent-test-host",
        mandate_id="synthetic-equity-review", mandate_revision=1, request_sha256=digest(q), c8_context_sha256=digest(context8),
        admitted_at=time(11, 14), available_at=time(11, 15), effective_from=time(1), effective_until=None, receipts=[])
    return seal([q, context8, context])


def run(case):
    return c9.evaluate_as_of_equity_trailing_loss_threshold_comparison(case[0], trusted_c8_context=case[1], trusted_equity_context=case[2])


def validate(result, case):
    return c9.validate_as_of_equity_trailing_loss_threshold_comparison(result, case[0], trusted_c8_context=case[1], trusted_equity_context=case[2])


def invalid(case):
    with pytest.raises(ValueError, match="^INVALID_EQUITY_THRESHOLD_INPUT$"):
        run(case)


@pytest.mark.parametrize("equity,difference,relation", [("1019.99", "-0.01", "BELOW"), ("1020", "0", "EQUAL"), ("1020.01", "0.01", "ABOVE")])
def test_exact_comparison_with_real_multi_instrument_c8_history(equity, difference, relation):
    case = sample(equity, ("1100", "1050", "1120"))
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["state"] == dict(as_of=T, currency="USD", equity=equity, threshold="1020", difference=difference,
                                   relation=relation, source_information_cutoff=time(11, 8))
    assert validate(result, case) == result
    assert case == before
    result["state"]["difference"] = "999"
    assert run(case)["state"]["difference"] == difference


@pytest.mark.parametrize("equity,balances,threshold,difference", [
    ("950", (), "900", "50"), ("899", (), "900", "-1"), ("-1", (), "900", "-901"),
    ("899", ("1200", "900"), "1100", "-201")])
def test_zero_events_floating_loss_negative_equity_and_preserved_watermark(equity, balances, threshold, difference):
    result = run(sample(equity, balances))
    assert result["outcome"] == "ESTABLISHED"
    assert result["state"]["threshold"] == threshold
    assert result["state"]["difference"] == difference


UNKNOWN_CASES = [
    ("C8_MISSING", "/c8", "REQUEST"),
    ("C8_CONTEXT_MISSING", "", "C8_TRUSTED_CONTEXT"),
    ("C8_NOT_ESTABLISHED", "/c8", "REQUEST"),
    ("NATIVE_EQUITY_MISSING", "/c8", "REQUEST"),
    ("EQUITY_ASSERTION_MISSING", "/equity", "REQUEST"),
    ("EQUITY_AMOUNT_UNDECLARED", "/equity/amount", "REQUEST"),
    ("AGGREGATE_ORIGINAL_MISSING", "/equity/originals/aggregate", "REQUEST"),
    ("DEFINITION_ORIGINAL_MISSING", "/equity/originals/definition", "REQUEST"),
    ("COVERAGE_ORIGINAL_MISSING", "/equity/originals/coverage", "REQUEST"),
    ("ORIGINAL_ROLE_COVERAGE_INCOMPLETE", "/originals/2", "REQUEST"),
    ("DOCUMENT_REVISION_UNKNOWN", "/originals/0/document/document_revision", "REQUEST"),
    ("DOCUMENT_VERSION_CONFLICT", "/originals/0/document", "REQUEST"),
    ("SOURCE_REVIEW_CUTOFF_UNKNOWN", "/equity/source_information_cutoff", "REQUEST"),
    ("ORIGINAL_AVAILABILITY_UNKNOWN", "/originals/2/source_available_at", "REQUEST"),
    ("SOURCE_REVIEW_CUTOFF_INSUFFICIENT", "/equity/source_information_cutoff", "REQUEST"),
    ("SOURCE_REVISIONS_UNRESOLVED", "/equity/source_revisions", "REQUEST"),
    ("DEFINITION_NOT_APPLICABLE", "/equity/definition_period", "REQUEST"),
    ("ACCOUNT_WIDE_UNRESOLVED", "/equity/account_wide", "REQUEST"),
    ("COMPONENT_TREATMENT_UNSUPPORTED", "/equity/components/floating_pnl", "REQUEST"),
    ("COMPONENT_INTEGRITY_UNRESOLVED", "/equity/component_integrity", "REQUEST"),
    ("SUPPORT_INCOMPLETE", "/support_assertions", "REQUEST"),
    ("EQUITY_ADMISSION_MISSING", "", "EQUITY_TRUSTED_CONTEXT"),
    ("EQUITY_ADMISSION_NOT_CURRENT", "/available_at", "EQUITY_TRUSTED_CONTEXT"),
    ("RECEIPT_MISSING", "/receipts", "EQUITY_TRUSTED_CONTEXT"),
    ("RECEIPT_UNRESOLVED", "/receipts/0", "EQUITY_TRUSTED_CONTEXT"),
    ("RECEIPT_MEMBERSHIP_INCOMPLETE", "/receipts/0/original_ids", "EQUITY_TRUSTED_CONTEXT"),
]


def unknown_case(reason):
    case = sample()
    q, context8, context = case
    equity = q["equity"]
    if reason == "C8_MISSING":
        q["c8"], case[1] = None, None
    elif reason == "C8_CONTEXT_MISSING":
        replace_c8(case, decoded(q["c8"]["request_json"]), None)
    elif reason == "C8_NOT_ESTABLISHED":
        q8 = decoded(q["c8"]["request_json"])
        q8["history"] = None
        replace_c8(case, q8, context8)
    elif reason == "NATIVE_EQUITY_MISSING":
        case = sample(None)
    elif reason == "EQUITY_ASSERTION_MISSING":
        q["equity"] = None
    elif reason == "EQUITY_AMOUNT_UNDECLARED":
        equity["amount"] = None
    elif reason in ("AGGREGATE_ORIGINAL_MISSING", "DEFINITION_ORIGINAL_MISSING", "COVERAGE_ORIGINAL_MISSING"):
        equity["originals"][reason.split("_")[0].lower()] = None
    elif reason == "ORIGINAL_ROLE_COVERAGE_INCOMPLETE":
        equity["originals"]["definition"] = deepcopy(equity["originals"]["aggregate"])
    elif reason == "DOCUMENT_REVISION_UNKNOWN":
        q["originals"][0]["document"]["document_revision"] = None
    elif reason == "DOCUMENT_VERSION_CONFLICT":
        q["originals"][2]["document"]["document_id"] = q["originals"][0]["document"]["document_id"]
        q["originals"][2]["document"]["document_revision"] = "2"
    elif reason == "SOURCE_REVIEW_CUTOFF_UNKNOWN":
        equity["source_information_cutoff"] = None
    elif reason == "ORIGINAL_AVAILABILITY_UNKNOWN":
        q["originals"][2]["source_available_at"] = None
    elif reason == "SOURCE_REVIEW_CUTOFF_INSUFFICIENT":
        equity["source_information_cutoff"] = T
    elif reason == "SOURCE_REVISIONS_UNRESOLVED":
        equity["source_revisions"] = "PRESENT"
    elif reason == "DEFINITION_NOT_APPLICABLE":
        equity["definition_period"]["effective_from"] = time(11)
    elif reason == "ACCOUNT_WIDE_UNRESOLVED":
        equity["account_wide"] = "UNKNOWN"
    elif reason == "COMPONENT_TREATMENT_UNSUPPORTED":
        equity["components"]["floating_pnl"] = "OMITTED"
    elif reason == "COMPONENT_INTEGRITY_UNRESOLVED":
        equity["component_integrity"] = "UNKNOWN"
    elif reason == "SUPPORT_INCOMPLETE":
        q["support_assertions"].pop(0)
    elif reason == "EQUITY_ADMISSION_MISSING":
        case[2] = None
    elif reason == "EQUITY_ADMISSION_NOT_CURRENT":
        context["available_at"] = time(13)
    seal(case)
    if reason == "RECEIPT_MISSING":
        case[2]["receipts"].pop(0)
    elif reason == "RECEIPT_UNRESOLVED":
        case[2]["receipts"][0]["decision"] = "UNRESOLVED"
    elif reason == "RECEIPT_MEMBERSHIP_INCOMPLETE":
        case[2]["receipts"][0]["original_ids"].pop()
    return case


@pytest.mark.parametrize("reason,pointer,root", UNKNOWN_CASES)
def test_all_26_unknown_reasons_are_reachable_and_reconstructible(reason, pointer, root):
    case = unknown_case(reason)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["state"] is None
    assert result["reason_codes"] == [reason]
    assert result["findings"] == [dict(reason_code=reason, subject=dict(root=root, pointer=pointer))]
    assert result["required_targets"] == list(TARGET_ROLES)
    assert len(result["admission_bindings"]) == 5
    assert validate(result, case) == result
    subject = {"REQUEST": case[0], "C8_TRUSTED_CONTEXT": case[1], "EQUITY_TRUSTED_CONTEXT": case[2]}[root]
    for token in pointer.split("/")[1:]:
        subject = subject[int(token)] if isinstance(subject, list) else subject[token]


def test_frozen_reason_inventory_and_priority():
    assert c9.REASON_CODES == ("COMPARISON_ESTABLISHED", *(row[0] for row in UNKNOWN_CASES))
    case = unknown_case("SOURCE_REVIEW_CUTOFF_UNKNOWN")
    case[0]["equity"]["account_wide"] = "UNKNOWN"
    case[2] = None
    seal(case)
    assert run(case)["reason_codes"] == ["SOURCE_REVIEW_CUTOFF_UNKNOWN"]
    case[0]["originals"][0]["content_sha256"] = "0" * 64
    seal(case)
    invalid(case)


@pytest.mark.parametrize("context_present", [False, True])
def test_repaired_empty_observation_witness(context_present):
    case = sample()
    case[0].update(c8=None, equity=None, originals=[], support_assertions=[])
    case[1] = None
    if not context_present:
        case[2] = None
    seal(case)
    if case[2] is not None:
        case[2]["receipts"] = []
    result = run(case)
    assert result["reason_codes"] == ["C8_MISSING"]
    assert result["state"] is None
    assert result["native_references"] == dict(c8=None, account_snapshot=None)
    assert result["findings"] == [dict(reason_code="C8_MISSING", subject=dict(root="REQUEST", pointer="/c8"))]
    assert result["admission_bindings"] == [dict(target=t, assertion_sha256=None, receipt_sha256=None, original_ids=[]) for t in TARGET_ROLES]
    assert result["reconstruction_evidence"]["equity_trusted_context_sha256"] == (digest(case[2]) if context_present else None)
    assert validate(result, case) == result


def test_empty_observations_do_not_excuse_invalid_context_or_orphan_c8_context():
    case = sample()
    case[0].update(c8=None, equity=None, originals=[], support_assertions=[])
    case[1] = None
    seal(case)
    case[2]["request_sha256"] = "0" * 64
    invalid(case)
    seal(case)
    case[2]["admitted_at"] = time(20)
    invalid(case)
    case = sample()
    case[0]["c8"] = None
    seal(case)
    invalid(case)


def test_unknown_references_preserve_valid_native_owners_and_exact_bundle_hashes():
    for reason in ("C8_CONTEXT_MISSING", "C8_NOT_ESTABLISHED", "NATIVE_EQUITY_MISSING", "EQUITY_ADMISSION_MISSING", "RECEIPT_MISSING"):
        case = unknown_case(reason)
        result = run(case)
        q8, r8 = decoded(case[0]["c8"]["request_json"]), decoded(case[0]["c8"]["result_json"])
        native = decoded(q8["account_snapshot"]["result_json"])
        assert result["native_references"] == dict(
            c8=dict(assessment_identity=r8["assessment_identity"], outcome=r8["outcome"], bundle_sha256=digest(case[0]["c8"])),
            account_snapshot=dict(snapshot_id=native["snapshot_id"], bundle_sha256=digest(q8["account_snapshot"])))
        assert native["snapshot_id"] != native["observation"]["source"]["source_snapshot_id"]
    case = sample()
    q8 = decoded(case[0]["c8"]["request_json"])
    q8["account_snapshot"] = None
    replace_c8(case, q8, case[1])
    result = run(case)
    assert result["reason_codes"] == ["C8_NOT_ESTABLISHED"]
    assert result["native_references"]["c8"] is not None
    assert result["native_references"]["account_snapshot"] is None


def test_dependency_hash_binds_original_base64_strings():
    case = sample()
    before = run(case)
    q8 = decoded(case[0]["c8"]["request_json"])
    case[0]["c8"]["request_json"] = base64.b64encode(json.dumps(q8, indent=2).encode()).decode()
    seal(case)
    after = run(case)
    assert after["state"] == before["state"]
    assert after["native_references"]["c8"]["assessment_identity"] == before["native_references"]["c8"]["assessment_identity"]
    assert after["native_references"]["c8"]["bundle_sha256"] != before["native_references"]["c8"]["bundle_sha256"]
    assert after["native_references"]["account_snapshot"] == before["native_references"]["account_snapshot"]
    native_input = decoded(q8["account_snapshot"]["input_json"])
    q8["account_snapshot"]["input_json"] = base64.b64encode(json.dumps(native_input, indent=2).encode()).decode()
    replace_c8(case, q8, case[1])
    inner = run(case)
    assert inner["native_references"]["account_snapshot"]["snapshot_id"] == before["native_references"]["account_snapshot"]["snapshot_id"]
    assert inner["native_references"]["account_snapshot"]["bundle_sha256"] != before["native_references"]["account_snapshot"]["bundle_sha256"]
    assert validate(inner, case) == inner


def test_both_public_validators_actually_replay_without_mocked_success(monkeypatch):
    case = sample()
    real_c8 = c8.validate_current_intraday_trailing_loss_threshold_state
    real_account = account.validate_causal_financial_account_state_snapshot
    calls = []
    def observe_c8(*args, **kwargs):
        calls.append(("c8", deepcopy(args), deepcopy(kwargs)))
        return real_c8(*args, **kwargs)
    def observe_account(*args, **kwargs):
        calls.append(("account", deepcopy(args), deepcopy(kwargs)))
        return real_account(*args, **kwargs)
    monkeypatch.setattr(c8, "validate_current_intraday_trailing_loss_threshold_state", observe_c8)
    monkeypatch.setattr(account, "validate_causal_financial_account_state_snapshot", observe_account)
    result = run(case)
    assert validate(result, case) == result
    assert [kind for kind, _, _ in calls] == ["c8", "account", "account"] * 2
    q8 = decoded(case[0]["c8"]["request_json"])
    for kind, args, kwargs in calls:
        if kind == "c8":
            assert args[1] == q8
            assert kwargs == dict(trusted_context=case[1])
        else:
            assert args == (decoded(q8["account_snapshot"]["result_json"]), decoded(q8["account_snapshot"]["input_json"]))


@pytest.mark.parametrize("field", ["scope/account/account_id", "scope/account/environment", "scope/account/currency", "scope/lifecycle_id",
    "scope/provider_id", "scope/program_id", "scope/account_type_id", "scope/phase_id", "scope/provider_namespace/source_id",
    "scope/account/namespace/source_id", "economic_time", "knowledge_boundary"])
def test_exact_c8_request_scope_and_boundary_joins(field):
    case = sample()
    for root in (case[0], case[0]["equity"]):
        parts = field.split("/")
        row = root
        for part in parts[:-1]: row = row[part]
        row[parts[-1]] = "EUR" if parts[-1] == "currency" else "LIVE" if parts[-1] == "environment" else time(13) if parts[-1] == "knowledge_boundary" else time(9) if parts[-1] == "economic_time" else "other"
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field,value", [("amount", "951"), ("currency", "EUR"), ("snapshot_id", "snapshot"),
    ("snapshot_bundle_sha256", "0"*64), ("economic_time", time(9)), ("knowledge_boundary", time(13))])
def test_assertion_cannot_rebind_native_equity(field, value):
    case = sample()
    case[0]["equity"][field] = value
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["missing_context", "context_hash", "result", "authority", "native_result", "selector"])
def test_c8_dependency_cannot_be_forged_even_after_c9_readmission(kind):
    case = sample()
    q8 = decoded(case[0]["c8"]["request_json"])
    r8 = decoded(case[0]["c8"]["result_json"])
    if kind == "missing_context": case[1] = None
    elif kind == "context_hash": case[1]["request_sha256"] = "0" * 64
    elif kind in ("result", "authority"):
        if kind == "result": r8["state"]["threshold"] = "901"
        else: r8["authority"]["execution"] = 0
        r8["assessment_identity"] = c8.IDENTITY_PREFIX + digest({k:v for k,v in r8.items() if k != "assessment_identity"})
        case[0]["c8"]["result_json"] = encoded(r8)
    elif kind == "native_result":
        native = decoded(q8["account_snapshot"]["result_json"])
        native["observation"]["account_measures"]["equity"] = "999"
        q8["account_snapshot"]["result_json"] = encoded(native)
        case[0]["c8"]["request_json"] = encoded(q8)
        upstream.admit(q8, case[1])
    else:
        q8["history"]["rule"]["rule_index"] = 50
        case[0]["c8"]["request_json"] = encoded(q8)
        upstream.admit(q8, case[1])
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field", FLAGS)
@pytest.mark.parametrize("value", [True, 0])
def test_rehashed_authority_mutation_is_rejected(field, value):
    case = sample()
    result = run(case)
    result["authority"][field] = value
    result["assessment_identity"] = c9.IDENTITY_PREFIX + digest({k:v for k,v in result.items() if k != "assessment_identity"})
    with pytest.raises(ValueError, match="^EQUITY_THRESHOLD_RESULT_MISMATCH$"):
        validate(result, case)


@pytest.mark.parametrize("field,value", [("execution", 0), ("execution", True), ("temporal_scope", "CURRENT"),
    ("state", None), ("native_references", dict(c8=None, account_snapshot=None)), ("required_targets", []),
    ("admission_bindings", []), ("limitations", []), ("source_authentication", "VERIFIED")])
def test_all_result_content_is_detached_reconstructed(field, value):
    case = sample()
    result = run(case)
    result[field] = value
    result["assessment_identity"] = c9.IDENTITY_PREFIX + digest({k:v for k,v in result.items() if k != "assessment_identity"})
    with pytest.raises(ValueError, match="^EQUITY_THRESHOLD_RESULT_MISMATCH$"):
        validate(result, case)


@pytest.mark.parametrize("where", ["original", "native", "c8_availability"])
def test_admission_follows_every_observation_and_c8_availability(where):
    case = sample()
    if where == "original":
        case[0]["originals"][2]["observed_at"] = time(11, 16)
    elif where == "native":
        q8 = decoded(case[0]["c8"]["request_json"])
        native = decoded(q8["account_snapshot"]["input_json"])
        native["observation"]["timing"]["observed_at"] = time(11, 16)
        q8["account_snapshot"] = upstream.bundle(native, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
        case[1].update(admitted_at=time(11, 17), available_at=time(11, 18))
        replace_c8(case, q8, case[1])
    else:
        q8 = decoded(case[0]["c8"]["request_json"])
        case[1]["available_at"] = time(11, 16)
        replace_c8(case, q8, case[1])
    seal(case)
    invalid(case)


@pytest.mark.parametrize("kind", ["observation_after_K", "publication_after_observation", "coverage_before_cutoff",
    "cutoff_before_T", "cutoff_after_K", "aggregate_publication_mismatch", "admission_after_available", "reversed_context_period"])
def test_structural_chronology_cannot_be_hidden_by_unknown(kind):
    case = sample()
    q, _, context = case
    if kind == "observation_after_K": q["originals"][2]["observed_at"] = time(13)
    elif kind == "publication_after_observation": q["originals"][2]["source_available_at"] = time(10)
    elif kind == "coverage_before_cutoff": q["originals"][1]["source_available_at"] = time(11, 7)
    elif kind == "cutoff_before_T": q["equity"]["source_information_cutoff"] = time(9)
    elif kind == "cutoff_after_K": q["equity"]["source_information_cutoff"] = time(13)
    elif kind == "aggregate_publication_mismatch": q["originals"][0]["source_available_at"] = time(10)
    elif kind == "admission_after_available": context["admitted_at"] = time(11, 16)
    else: context["effective_until"] = time(1)
    q["equity"]["account_wide"] = "UNKNOWN"
    seal(case)
    invalid(case)


@pytest.mark.parametrize("field,value,pointer", [("available_at", time(13), "/available_at"),
    ("effective_from", time(11, 15), "/effective_from"), ("effective_until", K, "/effective_until")])
def test_context_validity_boundaries(field, value, pointer):
    case = sample()
    case[2][field] = value
    result = run(case)
    assert result["reason_codes"] == ["EQUITY_ADMISSION_NOT_CURRENT"]
    assert result["findings"][0]["subject"] == dict(root="EQUITY_TRUSTED_CONTEXT", pointer=pointer)


@pytest.mark.parametrize("field", ["balance", "floating_pnl", "commissions", "swaps", "other_costs"])
@pytest.mark.parametrize("treatment", ["OMITTED", "UNKNOWN"])
def test_missing_components_never_produce_established_equity(field, treatment):
    case = sample()
    case[0]["equity"]["components"][field] = treatment
    seal(case)
    result = run(case)
    assert result["reason_codes"] == ["COMPONENT_TREATMENT_UNSUPPORTED"]
    assert result["state"] is None
    assert result["findings"][0]["subject"]["pointer"] == "/equity/components/"+field


@pytest.mark.parametrize("integrity", ["OMISSION", "DUPLICATION", "UNKNOWN"])
def test_component_integrity_is_independently_required(integrity):
    case = sample()
    case[0]["equity"]["component_integrity"] = integrity
    seal(case)
    assert run(case)["reason_codes"] == ["COMPONENT_INTEGRITY_UNRESOLVED"]


@pytest.mark.parametrize("field", ["request_sha256", "c8_context_sha256", "assertion_sha256", "target", "original_ids", "decision"])
def test_misbound_receipts_are_structurally_rejected(field):
    case = sample()
    row = case[2]["receipts"][0]
    row[field] = ["nonexistent"] if field == "original_ids" else "FALSE_TARGET" if field == "target" else "APPROVED" if field == "decision" else "0"*64
    invalid(case)


@pytest.mark.parametrize("kind", ["raw_hash", "envelope_hash", "same_version_different_content", "same_capture", "wrong_namespace", "wrong_aggregate_source", "rehashed_original"])
def test_original_provenance_and_content_binding(kind):
    case = sample()
    q = case[0]
    if kind == "raw_hash":
        q["originals"][0]["content_sha256"] = "0"*64
        seal(case)
    elif kind == "envelope_hash":
        q["equity"]["originals"]["aggregate"]["original_sha256"] = "0"*64
        # Bind the altered assertion/request without repairing the bad envelope reference.
        for row in q["support_assertions"]: row["equity_sha256"] = digest(q["equity"])
        case[2]["request_sha256"] = digest(q)
    elif kind == "same_version_different_content":
        q["originals"][2]["document"] = deepcopy(q["originals"][0]["document"])
        seal(case)
    elif kind == "same_capture":
        q["originals"][2] = deepcopy(q["originals"][0])
        q["originals"][2]["evidence_id"] = "definition"
        seal(case)
    elif kind == "wrong_namespace":
        q["originals"][0]["document"]["namespace"]["source_id"] = "other"
        seal(case)
    elif kind == "wrong_aggregate_source":
        q["originals"][0]["source"]["source_snapshot_id"] = "other"
        seal(case)
    else:
        set_content(q["originals"][0], dict(synthetic=True, equity="1000000"))
        for ref in q["equity"]["originals"].values():
            if ref["evidence_id"] == "aggregate": ref["original_sha256"] = digest(q["originals"][0])
        for row in q["support_assertions"]:
            row["equity_sha256"] = digest(q["equity"])
            for citation in row["citations"]:
                if citation["evidence_id"] == "aggregate": citation["end"] = len(base64.b64decode(q["originals"][0]["content"]))
        # The independent existing host context is intentionally not reissued.
    invalid(case)


@pytest.mark.parametrize("kind", ["context", "receipt", "assertion", "citation", "original", "role", "equity", "request", "components", "period"])
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_sealed_local_objects(kind, mutation):
    case = sample()
    q = case[0]
    objects = dict(context=case[2], receipt=case[2]["receipts"][0], assertion=q["support_assertions"][0],
        citation=q["support_assertions"][0]["citations"][0], original=q["originals"][0],
        role=q["equity"]["originals"]["aggregate"], equity=q["equity"], request=q,
        components=q["equity"]["components"], period=q["equity"]["definition_period"])
    obj = objects[kind]
    if mutation == "missing": obj.pop(next(iter(obj)))
    else: obj["unexpected"] = "value"
    invalid(case)


@pytest.mark.parametrize("kind", ["originals", "support", "citations", "receipts", "membership"])
@pytest.mark.parametrize("mutation", ["reverse", "duplicate"])
def test_collection_identity_and_canonical_order(kind, mutation):
    case = sample()
    q = case[0]
    rows = dict(originals=q["originals"], support=q["support_assertions"], citations=q["support_assertions"][0]["citations"],
                receipts=case[2]["receipts"], membership=case[2]["receipts"][0]["original_ids"])[kind]
    if mutation == "reverse": rows.reverse()
    else: rows.append(deepcopy(rows[-1]))
    invalid(case)


@pytest.mark.parametrize("value", ["NaN", "1e3", "01", "+1", "1.0", "-0", " 1", 1, True, 1.0])
def test_canonical_money_and_exact_types(value):
    case = sample()
    case[0]["equity"]["amount"] = value
    seal(case)
    invalid(case)


@pytest.mark.parametrize("payload", [b'{"contract":1,"contract":2}', b'[]', b'{"x":NaN}', b'{"x":1.0}', b'\xff'])
def test_nested_json_is_strict(payload):
    case = sample()
    case[0]["c8"]["request_json"] = base64.b64encode(payload).decode()
    seal(case)
    invalid(case)


def test_missing_evidence_never_masks_invalid_references():
    case = sample()
    case[0]["c8"], case[1] = None, None
    case[0]["equity"]["originals"]["aggregate"]["evidence_id"] = "missing"
    seal(case)
    invalid(case)


def test_exact_precision_is_independent_of_decimal_context():
    amount = "0." + "0" * 120 + "1"
    case = sample(amount, initial=amount)
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["state"]["difference"] == "0." + "0" * 121 + "1"
    assert result["state"]["relation"] == "ABOVE"
    assert validate(result, case) == result


@pytest.mark.parametrize("target", list(TARGET_ROLES))
def test_receipt_membership_cannot_replace_target_specific_support(target):
    case = sample()
    assertion = next(row for row in case[0]["support_assertions"] if row["target"] == target)
    assertion["citations"].pop(0)
    seal(case)
    assert all(row["decision"] == "ADMITTED" and row["original_ids"] == ["aggregate", "coverage", "definition"] for row in case[2]["receipts"])
    result = run(case)
    assert result["reason_codes"] == ["SUPPORT_INCOMPLETE"]
    assert result["state"] is None


def recite(case):
    lengths = {row["evidence_id"]: len(base64.b64decode(row["content"])) for row in case[0]["originals"]}
    for assertion in case[0]["support_assertions"]:
        for citation in assertion["citations"]:
            citation["start"], citation["end"] = 0, lengths[citation["evidence_id"]]
    return seal(case)


@pytest.mark.parametrize("kind", ["exact_reuse", "capture_metadata", "same_version_other_content", "other_revision"])
def test_document_and_capture_identity_across_c8_and_c9(kind):
    case = sample()
    q8 = decoded(case[0]["c8"]["request_json"])
    terms = next(row for row in q8["originals"] if row["evidence_id"] == "terms")
    body = decoded(terms["content"])
    body["equity_definition"] = "Account-wide balance plus floating P/L with commissions, swaps and other costs included exactly once."
    set_content(terms, body)
    case[0]["originals"][2] = deepcopy(terms)
    definition = case[0]["originals"][2]
    definition["evidence_id"] = "definition"
    if kind == "capture_metadata": definition["observed_at"] = time(3)
    elif kind == "same_version_other_content":
        body["equity_definition"] = "Contradictory document content."
        set_content(definition, body)
    elif kind == "other_revision": definition["document"]["document_revision"] = "2"
    replace_c8(case, q8, case[1])
    recite(case)
    if kind in ("capture_metadata", "same_version_other_content"):
        invalid(case)
    elif kind == "other_revision":
        result = run(case)
        assert result["reason_codes"] == ["DOCUMENT_VERSION_CONFLICT"]
        assert result["findings"][0]["subject"]["pointer"] == "/originals/2/document"
    else:
        result = run(case)
        assert result["outcome"] == "ESTABLISHED"
        assert validate(result, case) == result


def test_local_evidence_ids_are_not_confused_with_c8_local_ids():
    case = sample()
    case[0]["originals"][0]["evidence_id"] = "report"
    case[0]["originals"].sort(key=lambda row: row["evidence_id"])
    case[0]["equity"]["originals"]["aggregate"]["evidence_id"] = "report"
    for assertion in case[0]["support_assertions"]:
        for citation in assertion["citations"]:
            if citation["evidence_id"] == "aggregate": citation["evidence_id"] = "report"
        assertion["citations"].sort(key=lambda row: (row["evidence_id"], row["start"], row["end"]))
    seal(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert all(binding["original_ids"] == ["coverage", "definition", "report"] for binding in result["admission_bindings"])


def test_known_correction_after_source_cutoff_prevents_establishment():
    case = sample()
    coverage = case[0]["originals"][1]
    body = decoded(coverage["content"])
    body["revisions"] = [dict(observed_at=time(11, 11), kind="CORRECTION", affects="aggregate")]
    set_content(coverage, body)
    coverage.update(source_available_at=time(11, 12), observed_at=time(11, 12))
    case[0]["equity"]["source_revisions"] = "PRESENT"
    recite(case)
    case[2]["receipts"][-1]["decision"] = "UNRESOLVED"
    result = run(case)
    assert result["reason_codes"] == ["SOURCE_REVISIONS_UNRESOLVED"]
    assert result["state"] is None


@pytest.mark.parametrize("boundary", ["T", "K"])
def test_inclusive_source_cutoff_boundaries(boundary):
    case = sample()
    cutoff = T if boundary == "T" else K
    case[0]["equity"]["source_information_cutoff"] = cutoff
    coverage = case[0]["originals"][1]
    body = decoded(coverage["content"])
    body["information_cutoff"] = cutoff
    set_content(coverage, body)
    if boundary == "T":
        q8 = decoded(case[0]["c8"]["request_json"])
        native = decoded(q8["account_snapshot"]["input_json"])
        native["observation"]["timing"]["source_available_at"] = T
        q8["account_snapshot"] = upstream.bundle(native, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
        case[0]["originals"][0]["source_available_at"] = T
        replace_c8(case, q8, case[1])
    else:
        coverage.update(source_available_at=K, observed_at=K)
        case[2].update(admitted_at=K, available_at=K)
    recite(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["state"]["source_information_cutoff"] == cutoff


def test_observation_equality_and_duplicate_times_are_valid():
    case = sample()
    case[0]["originals"][1]["observed_at"] = case[1]["available_at"]
    case[2]["admitted_at"] = case[1]["available_at"]
    seal(case)
    assert run(case)["outcome"] == "ESTABLISHED"


def test_arbitrary_precision_above_default_integer_conversion_limit():
    case = sample()
    huge = "1" + "0" * 5000
    q8 = decoded(case[0]["c8"]["request_json"])
    native = decoded(q8["account_snapshot"]["input_json"])
    native["observation"]["account_measures"]["equity"] = huge
    q8["account_snapshot"] = upstream.bundle(native, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    aggregate = case[0]["originals"][0]
    body = decoded(aggregate["content"])
    body.update(equity=huge, floating_pnl="9" * 4997 + "000")
    set_content(aggregate, body)
    replace_c8(case, q8, case[1])
    recite(case)
    case[2]["mandate_revision"] = 10 ** 5000
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["state"]["difference"] == "9" * 4997 + "100"
    assert result["state"]["relation"] == "ABOVE"
    independent_context = deepcopy(case[2])
    independent_context["mandate_revision"] = "HUGE_INTEGER_PLACEHOLDER"
    raw = canonical(independent_context).replace('"HUGE_INTEGER_PLACEHOLDER"', huge).encode()
    assert result["reconstruction_evidence"]["equity_trusted_context_sha256"] == hashlib.sha256(raw).hexdigest()
    assert validate(result, case) == result


def test_result_is_narrow_historical_fact_with_no_profit_lock_bypass():
    case = sample()
    body = decoded(case[0]["originals"][0]["content"])
    body.update(earlier_equity="890", earlier_threshold="900", funded_state="FROZEN_AWAITING_PAYOUT")
    set_content(case[0]["originals"][0], body)
    seal(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED" and result["state"]["relation"] == "ABOVE"
    assert result["temporal_scope"] == "AS_OF_T_USING_EVIDENCE_BY_K"
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["limitations"] == ["AS_OF_ONLY", "SOURCE_REVISION_REVIEW_THROUGH_REPORTED_CUTOFF", "NO_CONTINUOUS_BREACH_PROOF",
                                      "NO_DAILY_LOSS_MARGIN_OR_AUTHORIZATION", "NO_SOURCE_AUTHENTICATION"]
    assert result["authority"] == dict.fromkeys(FLAGS, False)
    assert all(type(v) is bool and v is False for v in result["authority"].values())
    assert type(result["execution"]) is bool and result["execution"] is False
    assert set(result) == set("contract rule_version temporal_scope economic_time knowledge_boundary scope outcome reason_codes findings state native_references required_targets admission_bindings reconstruction_evidence source_authentication limitations authority execution assessment_identity".split())
    assert result["assessment_identity"] == c9.IDENTITY_PREFIX + digest({k:v for k,v in result.items() if k != "assessment_identity"})
    assert validate(result, case) == result
    source = Path(c9.__file__).read_text()
    assert "FROZEN_AWAITING_PAYOUT" in source
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and
                   node.value.id in ("c8_owner", "account_owner") and node.attr.startswith("_") for node in ast.walk(tree))
