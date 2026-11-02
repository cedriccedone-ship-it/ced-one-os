"""Genuine shared-original native replay and synthetic independently supplied admission."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
from fractions import Fraction
from functools import lru_cache
import hashlib
import inspect
import json
import sys
from unittest.mock import patch

import pytest

from ced_one.business_divisions.trading import xauusd_current_entry_provider_measure_projection_basis as owner
from tests import test_xauusd_current_entry_quantity_constraint_composition as cf
from tests import test_trading_vertical_slice_v29 as rf


T, EARLY, END = cf.T, cf.EARLY, cf.END
H = "2026-01-02T01:00:00.000000Z"
FUTURE = "2026-01-02T00:45:00.000000Z"
CONTEXTS = (*cf.CONTEXTS, "trusted_financial_projection_context")
TIMES = {"assessment_economic_time", "knowledge_boundary", "settlement_before", "source_available_at",
         "observed_at", "economic_from", "economic_until", "source_information_cutoff", "effective_from",
         "effective_until", "state_at", "known_effective_at", "admitted_at", "available_at"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalized(value, key=None):
    if key == "quantity_composition":
        return deepcopy(value)
    if type(value) is dict:
        return {k: normalized(v, k) for k, v in value.items()}
    if type(value) is list:
        rows = [normalized(v) for v in value]
        field = {"originals": "evidence_id", "records": "record_id", "actors": "actor_id",
                 "source_roster": "inventory_id", "reports": "inventory_id", "effects": "effect_id",
                 "charge_recognition": "charge_id", "root_records": "record_id"}.get(key)
        if field:
            return sorted(rows, key=lambda row: row[field])
        if key == "admissions":
            return sorted(rows, key=lambda row: canonical(row["target"]))
        if key in ("evidence_refs", "native_mappings"):
            return sorted(rows, key=canonical)
        if key in ("missing_record_ids", "actor_ids"):
            return sorted(rows)
        return rows
    if value is not None and key in TIMES:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    return value


def eref(original):
    return dict(evidence_id=original["evidence_id"], envelope_sha256=digest(normalized(original)))


def record_ref(record):
    return dict(record_id=record["record_id"], content_sha256=digest(normalized(record)))


def nref(kind, bundle, node, selector=None):
    return dict(kind=kind, owner_bundle_sha256=digest(bundle), selector=deepcopy(selector), content_sha256=digest(node))


def pairs(upstream):
    f = upstream[0]["risk_budget_feasibility"]["request"]
    p = f["risk_policy"]
    return p, f["risk_basis"], p["request"]["account_state"], p["request"]["account_rule_regime"]


def catalogue(bundle):
    """Independent fixture catalogue, built from actual original paths, not evaluator internals."""
    p, r, a, g = pairs((bundle["request"],))
    refs = [nref(kind, pair, pair) for kind, pair in (("COMPOSITION_BUNDLE", bundle), ("POLICY_BUNDLE", p),
        ("RISK_BASIS_BUNDLE", r), ("ACCOUNT_BUNDLE", a), ("REGIME_BUNDLE", g))]
    function = r["assessment"]["risk_function"]
    if function is not None:
        refs += [nref("RISK_FUNCTION", r, function)]
        refs += [nref("RISK_CHARGE", r, charge, dict(charge_id=charge["charge_id"])) for charge in function["charges"]]

    def add(kind, node, selector):
        ref = nref(kind, g, node, selector)
        refs.append(ref)
        return ref

    def clauses(container, field, rows):
        for i, row in enumerate(rows):
            add("REGIME_CLAUSE", row, dict(container=container, field=field, clause_index=i))

    manifest = g["assessment_input"]["manifest"]
    for node in manifest["evidence"]:
        add("REGIME_DOCUMENT", node, dict(evidence_id=node["evidence_id"]))
    for node in manifest["assignments"]:
        ref = add("REGIME_ASSIGNMENT", node, dict(assignment_id=node["assignment_id"]))
        clauses(ref, "EVIDENCE_REFS", node["evidence_refs"])
        for i, binding in enumerate(node["package_bindings"]):
            ref = add("REGIME_BINDING", binding, dict(assignment_id=node["assignment_id"], binding_index=i))
            clauses(ref, "EVIDENCE_REFS", binding["evidence_refs"])
    for node in manifest["packages"]:
        selector = {key: node[key] for key in ("package_id", "package_revision")}
        ref = add("REGIME_PACKAGE", node, selector)
        clauses(ref, "EVIDENCE_REFS", node["evidence_refs"])
        clauses(ref, "COVERAGE_EVIDENCE_REFS", node["coverage"]["evidence_refs"])
        for rule in node["rules"]:
            rs = dict(selector, rule_id=rule["rule_id"])
            ref = add("REGIME_RULE", rule, rs)
            clauses(ref, "EVIDENCE_REFS", rule["evidence_refs"])
            if "measure" in rule["body"]:
                ref = add("REGIME_MEASURE", rule["body"]["measure"], rs)
                clauses(ref, "DEFINITION_REFS", rule["body"]["measure"]["definition_refs"])
    for i, approval in enumerate(g["assessment_input"]["approvals"]):
        add("REGIME_APPROVAL", approval, dict(approval_index=i))
    return refs


@lru_cache(maxsize=16)
def upstream(direction="LONG", mode="NETTING", balance=None, measure="BALANCE", envelope=False):
    case = deepcopy(cf.joined(direction, mode))
    p = cf.financial(case)[0]["risk_policy"]["request"]
    g = p["account_rule_regime"]
    rule = rf.rule("STATIC_FLOOR")
    rule["rule_id"] = "settlement-balance"
    # Select a named native measure without asking the pre-entry floor owner to
    # judge its future payout-only floor or grant post-entry authorization.
    rule["effects"] = ["PAYOUT"]
    rule["body"]["measure"].update(kind=measure, cost_treatment=dict(
        commissions="IN_MEASURE", financing="NOT_APPLICABLE", other_charges="NOT_APPLICABLE"))
    if measure == "SEPARATE":
        rule["body"]["measure"].update(kind="BALANCE", cost_treatment=dict(
            commissions="SUBTRACT_SEPARATELY", financing="NOT_APPLICABLE", other_charges="NOT_APPLICABLE"))
    g["assessment_input"]["manifest"]["packages"][0]["rules"].append(rule)
    g["assessment"] = rf.run(rf.refresh(g["assessment_input"]))
    if balance is not None:
        p["account_state"]["snapshot_input"]["observation"]["account_measures"]["balance"] = balance
        cf.ff.refresh_joined_account(cf.financial(case))
    if envelope:
        risk = cf.financial(case)[0]["risk_basis"]["request"]
        risk["scenario_evidence"][0]["terms"]["charges"][0]["basis"] = "SUPPORTED_SCENARIO_ENVELOPE"
        cf.ff.rfixtures.align_policy(risk, case[1])
    tq = cf.limits(case)[0]
    tq["account_rule_regime"] = deepcopy(g)
    pe = tq["position_effect"]["request"]
    pe["account_state"] = deepcopy(p["account_state"])
    cf.pf.body((pe, case[4]))["account_bundle_sha256"] = digest(pe["account_state"])
    for original in pe["effect_inventory"]["evidence"]:
        if original["evidence_id"] == "account":
            original["content_base64"] = base64.b64encode(canonical(pe["account_state"]["snapshot_input"]).encode()).decode()
    cf.pf.seal((pe, case[4]))
    cf.rebuild_financial(case)
    case = cf.rebuild_terminal(case)
    result = cf.run(case)
    assert result["outcome"] == "ESTABLISHED", result
    return case


def original(identifier, source, content, at=EARLY):
    raw = canonical(content).encode()
    return dict(evidence_id=identifier, source=deepcopy(source), media_type="application/json",
                content_base64=base64.b64encode(raw).decode(), content_sha256=hashlib.sha256(raw).hexdigest(),
                source_available_at=at, observed_at=at)


def body(case):
    return case[0]["projection_evidence"]["records"][0]["body"]


def seal(case):
    q, *contexts = case
    evidence = q["projection_evidence"]
    catalog = {} if evidence is None else {row["evidence_id"]: row for row in evidence["originals"]}

    def refresh(value):
        if type(value) is dict:
            if set(value) == {"evidence_id", "envelope_sha256"} and value["evidence_id"] in catalog:
                value.update(eref(catalog[value["evidence_id"]]))
            else:
                for key, item in value.items():
                    if key != "quantity_composition":
                        refresh(item)
        elif type(value) is list:
            for item in value:
                refresh(item)
    refresh(q)
    context = contexts[5]
    if context is not None:
        refresh(context)
    if evidence is not None:
        # Reissue content links in predecessor order, independent of list order.
        pending = list(evidence["records"])
        done = {}
        while pending:
            ready = [r for r in pending if r["predecessor"]["kind"] != "RECORD" or
                     r["predecessor"]["record"]["record_id"] in done or
                     r["predecessor"]["record"]["record_id"] not in {x["record_id"] for x in pending}]
            if not ready:
                break
            for record in ready:
                if record["predecessor"]["kind"] == "RECORD":
                    parent = done.get(record["predecessor"]["record"]["record_id"])
                    if parent is not None:
                        record["predecessor"]["record"].update(record_ref(parent))
                done[record["record_id"]] = record
                pending.remove(record)
        for ref in evidence["coverage"]["root_records"]:
            if ref["record_id"] in done:
                ref.update(record_ref(done[ref["record_id"]]))
    if context is not None:
        context["request_content_sha256"] = digest(normalized(q))
        fingerprints = q["quantity_composition"]["assessment"]["reconstruction_evidence"]
        pins = {"trusted_" + name + "_context_sha256": fingerprints["trusted_" + name + "_context_sha256"]
                for name in ("planning", "quantity", "feasibility", "position_effect", "position_limit")}
        for receipt in context["admissions"]:
            receipt["subject_content_sha256"] = digest(dict(request_content_sha256=context["request_content_sha256"],
                native_context_fingerprints=pins, target=receipt["target"]))
    return case


def _sample(direction="LONG", mode="NETTING", balance=None, measure="BALANCE", envelope=False, native=None):
    up = deepcopy(upstream(direction, mode, balance, measure, envelope) if native is None else native)
    composition = dict(assessment=cf.run(up), request=up[0])
    p, r, a, g = pairs(up)
    refs = catalogue(composition)
    target = {field: next(ref for ref in refs if ref["kind"] == kind and
                         (field not in ("rule", "measure") or ref["selector"]["rule_id"] == "settlement-balance"))
              for field, kind in (("assignment", "REGIME_ASSIGNMENT"), ("package", "REGIME_PACKAGE"),
                                  ("rule", "REGIME_RULE"), ("measure", "REGIME_MEASURE"))}
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T,
             knowledge_boundary=T, scope=deepcopy(up[0]["scope"]), quantity_composition=composition,
             measure_target=target, scenario=dict(endpoint=owner.ENDPOINT, settlement_before=H), projection_evidence=None)
    source = dict(source_id="synthetic-review", source_contract="projection-originals", source_contract_version="1", source_snapshot_id="review-1")
    originals = [original("assertions", source, dict(synthetic=True, scope=q["scope"],
        meaning="Original package, assignment, approval, native risk and source-schedule interpretation support")),
        original("account", a["snapshot"]["observation"]["source"], a["snapshot_input"], T),
        original("accounting", source, dict(synthetic=True, scope=q["scope"], state_at=T, deadline=H,
            balance="direct native balance", price="exact once after baseline", charge_aggregation="native aggregate",
            rounding="native expression on entire C", settled="no residual position or amount",
            financial_coverage="complete all actors and sources; seven categories absent; full revision history"), T)]
    for document in g["assessment_input"]["manifest"]["evidence"]:
        originals.append(original("document:" + document["evidence_id"], document["source"],
                                  dict(synthetic=True, meaning="Complete original provider balance and cost definition clauses")))
    by_id = {row["evidence_id"]: row for row in originals}
    mappings = []
    for ref in refs:
        kind = ref["kind"]
        if kind in ("REGIME_DOCUMENT", "REGIME_CLAUSE"):
            original_id = "document:" + (ref["selector"]["evidence_id"] if kind == "REGIME_DOCUMENT" else "terms")
        else:
            original_id = "account" if kind == "ACCOUNT_BUNDLE" else "assertions"
        mappings.append(dict(native_reference=deepcopy(ref), original_reference=eref(by_id[original_id]),
            original_locator="synthetic original clause", relationship={"REGIME_DOCUMENT": "EXACT_DOCUMENT",
            "REGIME_CLAUSE": "CLAUSE_SUPPORT"}.get(kind, "ASSERTION_SUPPORT")))
    supports = [eref(by_id["accounting"])]
    ns = {key: source[key] for key in ("source_id", "source_contract", "source_contract_version")}
    finance = dict(state_at=T, source_information_cutoff=T, economic_from=T, economic_until=H,
        source_universe_completeness="COMPLETE", actor_completeness="COMPLETE",
        actors=[dict(actor_id="provider", namespace=ns, role="PROVIDER", evidence_refs=deepcopy(supports)),
                dict(actor_id="automation", namespace=ns, role="AUTOMATION", evidence_refs=deepcopy(supports))],
        source_roster=[dict(inventory_id="ledger", source_namespace=ns, role="PROVIDER",
                           actor_ids=["provider", "automation"], evidence_refs=deepcopy(supports))],
        reports=[dict(inventory_id="ledger", source=source, state_at=T, source_information_cutoff=T,
            economic_from=T, economic_until=H, source_available_at=T, observed_at=T,
            inventory_completeness="COMPLETE", revision_completeness="COMPLETE",
            categories={key: dict(status="ABSENT", effects=[], evidence_refs=deepcopy(supports)) for key in owner.FINANCIAL_CATEGORIES},
            evidence_refs=deepcopy(supports))], evidence_refs=deepcopy(supports))
    charges = r["assessment"]["risk_function"]["charges"]
    declaration = dict(record_id="interpretation-1", kind="DECLARE", predecessor=dict(kind="ROOT"),
        effective_from=T, effective_until=None, source_available_at=T, observed_at=T, evidence_refs=deepcopy(supports),
        body=dict(subjects=dict(quantity_composition_bundle_sha256=digest(composition), account_bundle_sha256=digest(a),
            regime_bundle_sha256=digest(g), risk_basis_bundle_sha256=digest(r), measure_target_sha256=digest(target)),
            baseline_binding=dict(state_at=T, source_information_cutoff=T, relationship="DIRECT_NATIVE_BALANCE", evidence_refs=deepcopy(supports)),
            price_loss_recognition=dict(recognition="EXACT_ONCE_AFTER_BASELINE", evidence_refs=deepcopy(supports)),
            charge_recognition=[dict(charge_id=c["charge_id"], charge_content_sha256=digest(c),
                recognition="EXACT_ONCE_AFTER_BASELINE", aggregation="EXACT_NATIVE_AGGREGATE", evidence_refs=deepcopy(supports)) for c in charges],
            cost_coverage_and_rounding=dict(completeness="COMPLETE", rounding="EXACT_NATIVE_EXPRESSION_ON_C",
                financing="NOT_APPLICABLE", evidence_refs=deepcopy(supports)), financial_coverage=finance,
            scenario_compatibility=dict(endpoint=owner.ENDPOINT, settlement_before=H, economic_from=T, economic_until=H,
                source_information_cutoff=T, accounting_continuity="SUPPORTED", settlement_meaning="SUPPORTED", evidence_refs=deepcopy(supports))))
    q["projection_evidence"] = dict(source=source, scope=deepcopy(q["scope"]), source_available_at=T, observed_at=T,
        originals=originals, native_mappings=mappings,
        coverage=dict(economic_from=T, economic_until=H, source_information_cutoff=T, declaration_completeness="COMPLETE",
            revision_completeness="COMPLETE", starting_basis="FROM_INCEPTION", root_records=[record_ref(declaration)],
            missing_record_ids=[], records_omitted=False, history_truncated=False, source_available_at=T, observed_at=T,
            evidence_refs=deepcopy(supports)), records=[declaration])
    targets = [dict(kind=name) for name in owner.ADMISSION_TARGETS] + [dict(kind="CHARGE_RECOGNITION",
        charge_id=c["charge_id"], charge_content_sha256=digest(c)) for c in charges]
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE_VERSION, admission_id="fixture-admission",
        authority_namespace=ns, authority_id="independent-fixture-review", mandate_id="projection-facts-only", mandate_revision=1,
        purpose=owner.ADMISSION_PURPOSE, request_content_sha256="0" * 64, knowledge_boundary=T,
        effective_from=EARLY, effective_until=END, admitted_at=T, available_at=T,
        admissions=[dict(target=target, subject_content_sha256="0" * 64, status="ADMITTED",
                         evidence_refs=[eref(row) for row in originals]) for target in targets])
    return seal((q, *up[1:], context))


@lru_cache(maxsize=16)
def _cached_sample(direction, mode, balance, measure, envelope):
    return _sample(direction, mode, balance, measure, envelope)


def sample(direction="LONG", mode="NETTING", balance=None, measure="BALANCE", envelope=False, native=None):
    return deepcopy(_cached_sample(direction, mode, balance, measure, envelope)) if native is None else _sample(native=native)


def run(case):
    return owner.evaluate_current_entry_provider_measure_projection_basis(case[0], **dict(zip(CONTEXTS, case[1:])))


def validate(result, case):
    return owner.validate_current_entry_provider_measure_projection_basis(result, case[0], **dict(zip(CONTEXTS, case[1:])))


@pytest.fixture
def case():
    return sample()


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("mode", ["NETTING", "HEDGING"])
def test_genuine_shared_original_positive(direction, mode):
    case = sample(direction, mode)
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["reason_codes"] == ["CONDITIONAL_BALANCE_PROJECTION_ESTABLISHED"]
    assert result["projection_basis"]["risk_function"] == pairs((case[0]["quantity_composition"]["request"],))[1]["assessment"]["risk_function"]
    assert result["supported_domain"] == case[0]["quantity_composition"]["assessment"]["composed_domain"]
    assert validate(result, case) == result
    assert case == before


def require_unknown(case, reason):
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN", result
    assert reason in result["reason_codes"], result["reason_codes"]
    assert result["projection_basis"] is None
    return result


def modeled(descriptor, quantity):
    # Independent test-only point arithmetic. The production API returns a
    # symbolic descriptor and never enumerates or selects a quantity.
    f = descriptor["risk_function"]
    q = Fraction(quantity)
    loss = Fraction(f["price_loss_per_quantity_unit"]) * q
    loss += sum(max(Fraction(c["minimum"]), Fraction(c["fixed"]) + Fraction(c["per_unit"]) * q) for c in f["charges"])
    return Fraction(descriptor["baseline_amount"]) - loss


@pytest.mark.parametrize("balance,expected", [("4", 1), ("3", 0), ("2", -1)])
def test_signed_projected_balances_and_unequal_equity(balance, expected):
    case = sample(balance=balance)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert modeled(result["projection_basis"], "0.1") == expected
    assert pairs((case[0]["quantity_composition"]["request"],))[2]["snapshot"]["observation"]["account_measures"]["equity"] != balance


def test_minimum_fixed_breakpoint_retained():
    up = cf.change_cap(deepcopy(upstream()), "0.9")
    result = run(sample(native=up))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    d = result["projection_basis"]
    c = d["risk_function"]["charges"][0]
    assert c["minimum"] == "2" and c["fixed"] == "1" and c["per_unit"] == "2"
    assert d["support"]["domain"]["last_index"] >= "5"
    baseline = Fraction(d["baseline_amount"])
    assert modeled(d, "0.4") == baseline - 6
    assert modeled(d, "0.5") == baseline - 7
    assert modeled(d, "0.6") == baseline - Fraction("8.2")


@pytest.mark.parametrize("field,value,reason", [
    ("recognition", "UNKNOWN", "CHARGE_RECOGNITION_UNRESOLVED"),
    ("recognition", "ALREADY_REFLECTED", "CHARGE_ALREADY_REFLECTED"),
    ("aggregation", "OTHER", "CHARGE_AGGREGATION_UNRESOLVED"),
])
def test_charge_recognition(case, field, value, reason):
    body(case)["charge_recognition"][0][field] = value
    require_unknown(case, reason)


def test_charge_missing(case):
    body(case)["charge_recognition"] = []
    require_unknown(case, "CHARGE_RECOGNITION_MISSING")


def test_envelope_cannot_become_exact():
    require_unknown(sample(envelope=True), "EXACT_DEBIT_UNESTABLISHED")


def test_equity_valid_but_unsupported():
    require_unknown(sample(measure="EQUITY"), "MEASURE_MODEL_UNSUPPORTED")


def test_separately_adjusted_native_measure_is_unsupported():
    require_unknown(sample(measure="SEPARATE"), "MEASURE_MODEL_UNSUPPORTED")


@pytest.mark.parametrize("field,value,reason", [
    ("completeness", "LIMITED", "COST_COVERAGE_UNRESOLVED"),
    ("rounding", "OTHER", "ROUNDING_SEMANTICS_UNRESOLVED"),
    ("financing", "UNKNOWN", "FINANCING_HORIZON_UNRESOLVED"),
])
def test_cost_horizon_and_rounding(case, field, value, reason):
    body(case)["cost_coverage_and_rounding"][field] = value
    require_unknown(case, reason)


@pytest.mark.parametrize("field", ["source_universe_completeness", "actor_completeness"])
def test_incomplete_universe(case, field):
    body(case)["financial_coverage"][field] = "LIMITED"
    require_unknown(case, "FINANCIAL_COVERAGE_UNRESOLVED")


@pytest.mark.parametrize("mutation,reason", [
    ("missing-report", "FINANCIAL_REPORT_MISSING"), ("empty-universe", "FINANCIAL_COVERAGE_UNRESOLVED"),
    ("uncovered-actor", "FINANCIAL_COVERAGE_UNRESOLVED"), ("no-provider-actor", "FINANCIAL_COVERAGE_UNRESOLVED"),
    ("no-provider-source", "FINANCIAL_COVERAGE_UNRESOLVED"), ("partial-revisions", "FINANCIAL_COVERAGE_UNRESOLVED"),
    ("unknown-category", "FINANCIAL_COVERAGE_UNRESOLVED"),
])
def test_financial_coverage_closure(case, mutation, reason):
    f = body(case)["financial_coverage"]
    if mutation == "missing-report":
        f["reports"] = []
    elif mutation == "empty-universe":
        f["reports"], f["source_roster"], f["actors"] = [], [], []
    elif mutation == "uncovered-actor":
        f["source_roster"][0]["actor_ids"] = ["provider"]
    elif mutation == "no-provider-actor":
        f["actors"][0]["role"] = "OTHER"
    elif mutation == "no-provider-source":
        f["source_roster"][0]["role"] = "OTHER"
    elif mutation == "partial-revisions":
        f["reports"][0]["revision_completeness"] = "LIMITED"
    else:
        f["reports"][0]["categories"]["UNPOSTED_CHARGES"]["status"] = "UNKNOWN"
    require_unknown(case, reason)


@pytest.mark.parametrize("category", owner.FINANCIAL_CATEGORIES)
def test_additional_effects_are_not_adjustments_or_floor_breaches(case, category):
    c = body(case)["financial_coverage"]["reports"][0]["categories"][category]
    c.update(status="PRESENT", effects=[dict(effect_id="known-effect", actor_id="provider", known_effective_at=FUTURE,
                                            evidence_refs=deepcopy(c["evidence_refs"]))])
    result = require_unknown(case, "ADDITIONAL_FINANCIAL_EFFECT_PRESENT")
    assert "NOT_SUITABLE" not in result["outcome"]


@pytest.mark.parametrize("mutation", ["extra-report", "duplicate-report", "unknown-actor", "wrong-source", "absent-with-effect", "unknown-with-effect", "duplicate-effect"])
def test_financial_structural_contradictions(case, mutation):
    f = body(case)["financial_coverage"]
    report = f["reports"][0]
    if mutation == "extra-report":
        report["inventory_id"] = "unlisted"
    elif mutation == "duplicate-report":
        f["reports"].append(deepcopy(report))
    elif mutation == "unknown-actor":
        f["source_roster"][0]["actor_ids"].append("not-listed")
    elif mutation == "wrong-source":
        report["source"]["source_id"] = "other"
    else:
        effect = dict(effect_id="effect", actor_id="provider", known_effective_at=None, evidence_refs=deepcopy(report["evidence_refs"]))
        cat = report["categories"]["UNPOSTED_CHARGES"]
        cat.update(status="ABSENT" if mutation == "absent-with-effect" else "UNKNOWN" if mutation == "unknown-with-effect" else "PRESENT", effects=[effect])
        if mutation == "duplicate-effect":
            report["categories"]["MONETARY_RESERVATIONS"].update(status="PRESENT", effects=[deepcopy(effect)])
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("field", ["measure_target", "projection_evidence"])
def test_nullable_prerequisites(case, field):
    case[0][field] = None
    if field == "projection_evidence":
        case = (*case[:6], None)
    require_unknown(case, "MEASURE_TARGET_MISSING" if field == "measure_target" else "PROJECTION_EVIDENCE_MISSING")


@pytest.mark.parametrize("field", ["state_at", "source_information_cutoff", "relationship"])
def test_baseline_unestablished(case, field):
    body(case)["baseline_binding"][field] = "UNKNOWN" if field == "relationship" else EARLY
    require_unknown(case, "MEASURE_BINDING_UNRESOLVED" if field == "relationship" else "CURRENT_BASELINE_UNESTABLISHED")


def test_missing_original_support_cannot_be_admitted(case):
    body(case)["baseline_binding"]["evidence_refs"] = []
    require_unknown(case, "ORIGINAL_SUPPORT_MISSING")


def test_price_recognition_must_be_exact(case):
    body(case)["price_loss_recognition"]["recognition"] = "OTHER"
    require_unknown(case, "PRICE_RECOGNITION_UNRESOLVED")


@pytest.mark.parametrize("field,value", [("settlement_meaning", "UNKNOWN"), ("accounting_continuity", "OTHER"),
    ("settlement_before", END), ("economic_until", FUTURE), ("source_information_cutoff", EARLY)])
def test_settlement_meaning_and_whole_horizon(case, field, value):
    body(case)["scenario_compatibility"][field] = value
    require_unknown(case, "SCENARIO_CONTINUITY_UNRESOLVED")


@pytest.mark.parametrize("end,expected", [(FUTURE, "UNKNOWN"), (H, "ESTABLISHED")])
def test_declaration_expiry_covers_entire_horizon(case, end, expected):
    case[0]["projection_evidence"]["records"][0]["effective_until"] = end
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]


def test_missing_subject_pin_is_unknown(case):
    body(case)["subjects"]["account_bundle_sha256"] = None
    require_unknown(case, "MEASURE_BINDING_UNRESOLVED")


def test_literal_currency_mismatch_rejects(case):
    case[0]["scope"]["account"]["currency"] = "EUR"
    with pytest.raises(ValueError):
        run(case)


def test_semantic_denomination_admission_gap_is_unknown(case):
    next(r for r in case[6]["admissions"] if r["target"]["kind"] == "MEASURE_DEFINITION_AND_BASELINE")["status"] = "UNRESOLVED"
    require_unknown(case, "DENOMINATION_UNRESOLVED")


@pytest.mark.parametrize("kind", ["REGIME_ASSIGNMENT", "REGIME_BINDING", "REGIME_PACKAGE", "REGIME_RULE", "REGIME_MEASURE", "REGIME_DOCUMENT", "REGIME_APPROVAL", "REGIME_CLAUSE", "ACCOUNT_BUNDLE", "RISK_BASIS_BUNDLE", "RISK_FUNCTION", "RISK_CHARGE"])
def test_every_required_native_mapping(case, kind):
    evidence = case[0]["projection_evidence"]
    evidence["native_mappings"] = [m for m in evidence["native_mappings"] if m["native_reference"]["kind"] != kind]
    require_unknown(case, "ORIGINAL_SUPPORT_MISSING")


@pytest.mark.parametrize("target", (*owner.ADMISSION_TARGETS, "CHARGE_RECOGNITION"))
def test_every_required_receipt(case, target):
    case[6]["admissions"] = [r for r in case[6]["admissions"] if r["target"]["kind"] != target]
    require_unknown(case, "RECEIPT_MISSING")


@pytest.mark.parametrize("target", owner.ADMISSION_TARGETS)
def test_unresolved_receipt(case, target):
    next(r for r in case[6]["admissions"] if r["target"]["kind"] == target)["status"] = "UNRESOLVED"
    require_unknown(case, "RECEIPT_UNRESOLVED")


def test_absent_context_does_not_authenticate_documents(case):
    result = require_unknown((*case[:6], None), "ADMISSION_MISSING")
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"


def test_missing_admission_retains_independent_reported_effect(case):
    category = body(case)["financial_coverage"]["reports"][0]["categories"]["UNPOSTED_CHARGES"]
    category.update(status="PRESENT", effects=[dict(effect_id="reported", actor_id="provider", known_effective_at=None,
                                                     evidence_refs=deepcopy(category["evidence_refs"]))])
    result = require_unknown((*case[:6], None), "ADMISSION_MISSING")
    assert "ADDITIONAL_FINANCIAL_EFFECT_PRESENT" in result["reason_codes"]
    assert result["resolved_record"] is None


@pytest.mark.parametrize("field,value", [("effective_from", END), ("effective_until", T)])
def test_noncurrent_admission(case, field, value):
    case[6][field] = value
    if field == "effective_from":
        case[6]["effective_until"] = None
    require_unknown(case, "ADMISSION_NOT_CURRENT")


def test_receipt_with_valid_but_insufficient_original_support(case):
    r = next(r for r in case[6]["admissions"] if r["target"]["kind"] == "PRICE_LOSS_RECOGNITION")
    r["evidence_refs"] = [eref(case[0]["projection_evidence"]["originals"][1])]
    require_unknown(case, "ORIGINAL_SUPPORT_MISSING")


@pytest.mark.parametrize("mutation", ["request-pin", "subject-pin", "empty", "dangling", "hash", "duplicate", "nonexistent-charge", "mandate-bool", "late-admission", "early-admission"])
def test_admission_attacks(case, mutation):
    context = case[6]
    receipt = context["admissions"][0]
    if mutation == "request-pin":
        context["request_content_sha256"] = "0" * 64
    elif mutation == "subject-pin":
        receipt["subject_content_sha256"] = "0" * 64
    elif mutation == "empty":
        receipt["evidence_refs"] = []
    elif mutation == "dangling":
        receipt["evidence_refs"][0]["evidence_id"] = "absent"
    elif mutation == "hash":
        receipt["evidence_refs"][0]["envelope_sha256"] = "0" * 64
    elif mutation == "duplicate":
        context["admissions"].append(deepcopy(receipt))
    elif mutation == "nonexistent-charge":
        receipt["target"] = dict(kind="CHARGE_RECOGNITION", charge_id="invented", charge_content_sha256="0" * 64)
    elif mutation == "mandate-bool":
        context["mandate_revision"] = True
    elif mutation == "late-admission":
        context["admitted_at"] = FUTURE
    else:
        context["admitted_at"] = EARLY
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("mutation", ["bytes", "base64", "source", "selector", "owner", "content", "recursive-clause", "bool-index", "duplicate-original", "duplicate-mapping"])
def test_original_and_native_reference_attacks(case, mutation):
    evidence = case[0]["projection_evidence"]
    mapping = next(m for m in evidence["native_mappings"] if m["native_reference"]["kind"] == "REGIME_DOCUMENT")
    if mutation == "bytes":
        evidence["originals"][0]["content_base64"] = base64.b64encode(b"changed").decode()
    elif mutation == "base64":
        evidence["originals"][0]["content_base64"] += "\n"
    elif mutation == "source":
        next(o for o in evidence["originals"] if o["evidence_id"] == mapping["original_reference"]["evidence_id"])["source"]["source_snapshot_id"] = "wrong"
    elif mutation in ("selector", "owner", "content"):
        if mutation == "selector":
            mapping["native_reference"]["selector"]["evidence_id"] = "nonexistent"
        else:
            mapping["native_reference"]["owner_bundle_sha256" if mutation == "owner" else "content_sha256"] = "0" * 64
    elif mutation in ("recursive-clause", "bool-index"):
        ref = next(m["native_reference"] for m in evidence["native_mappings"] if m["native_reference"]["kind"] == "REGIME_CLAUSE")
        if mutation == "recursive-clause":
            ref["selector"]["container"] = deepcopy(ref)
        else:
            ref["selector"]["clause_index"] = True
    elif mutation == "duplicate-original":
        evidence["originals"].append(deepcopy(evidence["originals"][0]))
    else:
        evidence["native_mappings"].append(deepcopy(mapping))
    with pytest.raises(ValueError):
        run(seal(case))


def successor(case, kind="DECLARE", effective=T):
    evidence = case[0]["projection_evidence"]
    old = evidence["records"][-1]
    row = dict(record_id="interpretation-2", kind=kind, predecessor=dict(kind="RECORD", record=record_ref(old)),
               effective_from=effective, observed_at=T, source_available_at=T, evidence_refs=deepcopy(old["evidence_refs"]))
    if kind == "DECLARE":
        row.update(effective_until=None, body=deepcopy(next(r["body"] for r in reversed(evidence["records"]) if r["kind"] == "DECLARE")))
    evidence["records"].append(row)
    return row


@pytest.mark.parametrize("kind,reason", [("WITHDRAW", "INTERPRETATION_WITHDRAWN"), ("expired", "INTERPRETATION_EXPIRED")])
def test_no_predecessor_resurrection(case, kind, reason):
    if kind == "WITHDRAW":
        successor(case, kind)
    else:
        row = case[0]["projection_evidence"]["records"][0]
        row["effective_from"], row["effective_until"] = EARLY, T
    result = require_unknown(case, reason)
    assert result["resolved_record"] is not None


@pytest.mark.parametrize("effective,expected", [(FUTURE, "UNKNOWN"), (H, "ESTABLISHED"), (END, "ESTABLISHED")])
def test_known_future_change(case, effective, expected):
    successor(case, effective=effective)
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]
    assert result["resolved_record"]["record_id"] == "interpretation-1"
    if expected == "UNKNOWN":
        assert "HORIZON_INTERPRETATION_CHANGE" in result["reason_codes"]


def test_explicit_declare_after_withdrawal(case):
    successor(case, "WITHDRAW")
    old = case[0]["projection_evidence"]["records"][0]
    record = successor(case)
    record["body"] = deepcopy(old["body"])
    record["record_id"] = "interpretation-3"
    assert run(seal(case))["outcome"] == "ESTABLISHED"


def test_historical_pins_and_charge_ids_are_not_current(case):
    old = case[0]["projection_evidence"]["records"][0]
    successor(case)
    old["effective_from"] = EARLY
    old["body"]["subjects"] = {k: "f" * 64 for k in old["body"]["subjects"]}
    old["body"]["charge_recognition"][0]["charge_id"] = "historical-charge"
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["reconstruction_evidence"]["request"]["projection_evidence"]["records"][0]["body"]["subjects"] == old["body"]["subjects"]


def test_expired_latest_body_retains_its_historical_pins(case):
    row = case[0]["projection_evidence"]["records"][0]
    row["effective_from"], row["effective_until"] = EARLY, T
    row["body"]["subjects"] = {key: "f" * 64 for key in row["body"]["subjects"]}
    row["body"]["charge_recognition"][0]["charge_id"] = "old-charge"
    require_unknown(case, "INTERPRETATION_EXPIRED")


@pytest.mark.parametrize("mutation,reason", [("gap", "REVISION_HISTORY_INCOMPLETE"), ("unknown-parent", "REVISION_HISTORY_INCOMPLETE"),
    ("competing", "COMPETING_INTERPRETATIONS"), ("backwards", "REVISION_ORDER_UNSUPPORTED"),
    ("no-current", "NO_CURRENT_INTERPRETATION"), ("coverage", "INTERPRETATION_COVERAGE_UNRESOLVED")])
def test_honest_revision_uncertainty(case, mutation, reason):
    e = case[0]["projection_evidence"]
    if mutation == "gap":
        e["coverage"]["revision_completeness"] = "LIMITED"
        e["coverage"]["missing_record_ids"] = ["missing-root"]
        e["coverage"]["root_records"] = [dict(record_id="missing-root", content_sha256="0" * 64)]
        e["records"][0]["predecessor"] = dict(kind="RECORD", record=dict(record_id="missing-root", content_sha256="0" * 64))
    elif mutation == "unknown-parent":
        e["coverage"].update(revision_completeness="LIMITED", root_records=[], starting_basis="INCOMPLETE_OR_UNKNOWN")
        e["records"][0]["predecessor"] = dict(kind="UNKNOWN")
    elif mutation == "competing":
        row = deepcopy(e["records"][0]); row["record_id"] = "another-root"
        e["records"].append(row); e["coverage"]["root_records"].append(record_ref(row))
    elif mutation == "backwards":
        successor(case, effective=EARLY)
    elif mutation == "no-current":
        e["records"][0]["effective_from"] = FUTURE
    else:
        e["coverage"]["declaration_completeness"] = "LIMITED"
    require_unknown(case, reason)


@pytest.mark.parametrize("mutation", ["hash", "undeclared-gap", "complete-gap", "duplicate", "missing-root", "self-cycle", "governing-pin", "extra-charge", "charge-hash"])
def test_revision_and_governing_forgery(case, mutation):
    e = case[0]["projection_evidence"]
    if mutation == "hash":
        e["coverage"]["root_records"][0]["content_sha256"] = "0" * 64
    elif mutation == "undeclared-gap":
        e["records"][0]["predecessor"] = dict(kind="RECORD", record=dict(record_id="missing", content_sha256="0" * 64))
        e["coverage"]["root_records"] = []
    elif mutation == "complete-gap":
        e["coverage"]["history_truncated"] = True
    elif mutation == "duplicate":
        e["records"].append(deepcopy(e["records"][0]))
    elif mutation == "missing-root":
        e["coverage"]["root_records"] = []
    elif mutation == "self-cycle":
        e["coverage"]["root_records"] = []
        e["records"][0]["predecessor"] = dict(kind="RECORD", record=record_ref(e["records"][0]))
    elif mutation == "governing-pin":
        body(case)["subjects"]["account_bundle_sha256"] = "0" * 64
    elif mutation == "extra-charge":
        body(case)["charge_recognition"][0]["charge_id"] = "invented"
    else:
        body(case)["charge_recognition"][0]["charge_content_sha256"] = "0" * 64
    if mutation not in ("hash", "self-cycle"):
        seal(case)
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("where", ["unused-original", "record", "report", "coverage", "inventory", "context"])
def test_post_k_supplied_material_rejects(case, where):
    e = case[0]["projection_evidence"]
    if where == "unused-original":
        extra = deepcopy(e["originals"][0]); extra.update(evidence_id="unused", observed_at=FUTURE)
        e["originals"].append(extra)
    elif where == "record":
        e["records"][0]["observed_at"] = FUTURE
    elif where == "report":
        body(case)["financial_coverage"]["reports"][0]["observed_at"] = FUTURE
    elif where == "coverage":
        e["coverage"]["observed_at"] = FUTURE
    elif where == "inventory":
        e["observed_at"] = FUTURE
    else:
        case[6]["available_at"] = FUTURE
    with pytest.raises(ValueError):
        run(seal(case))


def test_required_unknown_publication_and_unused_unknown(case):
    evidence = case[0]["projection_evidence"]
    extra = deepcopy(evidence["originals"][0]); extra.update(evidence_id="unused", source_available_at=None)
    evidence["originals"].append(extra)
    assert run(seal(case))["outcome"] == "ESTABLISHED"
    evidence["originals"][0]["source_available_at"] = None
    require_unknown(case, "SOURCE_AVAILABILITY_UNKNOWN")


@pytest.mark.parametrize("state", ["UNKNOWN", "NOT_SUITABLE"])
def test_native_unknown_and_negative_preserve_exact_diagnostics(state):
    up = deepcopy(upstream())
    up = cf.terminal_unknown(up) if state == "UNKNOWN" else cf.change_cap(up, "0.01")
    case = sample(native=up)
    native = case[0]["quantity_composition"]["assessment"]
    assert native["outcome"] == state
    result = require_unknown(case, "OWNER_UNKNOWN" if state == "UNKNOWN" else "OWNER_NOT_SUITABLE")
    assert result["native_diagnostics"] == {key: native[key] for key in
        ("negative_proofs", "native_negative_proof_references", "unresolved_findings")}
    assert result["supported_domain"] is None


def absent_owner(case):
    case[0]["quantity_composition"] = None
    case[0]["measure_target"] = None
    case[0]["projection_evidence"]["native_mappings"] = []
    return (case[0], None, None, None, None, None, None)


def test_missing_owner_with_well_formed_independent_material(case):
    result = require_unknown(absent_owner(case), "OWNER_MISSING")
    assert result["owner_reference"] is result["native_diagnostics"] is None


def test_missing_owner_does_not_hide_malformed_material(case):
    case = absent_owner(case)
    case[0]["projection_evidence"]["originals"][0]["content_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("index", range(6))
def test_native_positive_without_original_context_rejects(case, index):
    changed = list(case); changed[index + 1] = None
    if index == 5:
        require_unknown(tuple(changed), "ADMISSION_MISSING")
    else:
        with pytest.raises(ValueError):
            run(tuple(changed))


def test_orphaned_contexts_and_projection_context(case):
    case[0]["projection_evidence"] = None
    with pytest.raises(ValueError):
        run(seal(case))
    case[0]["quantity_composition"] = None
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("mutation", ["native-rehash", "local-rehash", "false-as-zero"])
def test_rehashed_assessment_attacks(case, mutation):
    if mutation == "native-rehash":
        native = case[0]["quantity_composition"]["assessment"]
        native["conditions"].append("caller-approved")
        native["assessment_identity"] = cf.owner.IDENTITY_PREFIX + digest({k: v for k, v in native.items() if k != "assessment_identity"})
        with pytest.raises(ValueError):
            run(seal(case))
    else:
        result = run(case)
        if mutation == "local-rehash":
            result["projection_basis"]["baseline_amount"] = "999999"
        else:
            result["authority"]["execution"] = 0
        result["assessment_identity"] = owner.IDENTITY_PREFIX + digest({k: v for k, v in result.items() if k != "assessment_identity"})
        with pytest.raises(ValueError):
            validate(result, case)


def test_every_owned_result_field_is_reconstructed(case):
    result = run(case)
    for key in result:
        changed = deepcopy(result)
        if type(changed[key]) is bool:
            changed[key] = not changed[key]
        elif type(changed[key]) is dict:
            changed[key]["caller-added"] = True
        elif type(changed[key]) is list:
            changed[key].append("caller-added")
        elif changed[key] is None:
            changed[key] = "caller-added"
        else:
            changed[key] += "caller-added"
        if key != "assessment_identity":
            changed["assessment_identity"] = owner.IDENTITY_PREFIX + digest({k: v for k, v in changed.items() if k != "assessment_identity"})
        with pytest.raises(ValueError):
            validate(changed, case)


def test_presentation_equivalence_and_native_preservation(case):
    before = run(case)
    q = case[0]
    q["assessment_economic_time"] = "2026-01-02T01:32:00+01:00"
    e = q["projection_evidence"]
    e["originals"].reverse(); e["native_mappings"].reverse()
    e["records"][0]["body"]["financial_coverage"]["actors"].reverse()
    case[6]["admissions"].reverse()
    after = run(seal(case))
    assert after == before
    assert after["reconstruction_evidence"]["request"]["quantity_composition"] == q["quantity_composition"]


def test_extreme_grid_without_global_numeric_changes():
    step = "0." + "0" * 5000 + "1"
    up = cf.change_grid(deepcopy(upstream()), step=step)
    case = sample(native=up)
    previous = sys.get_int_max_str_digits()
    with localcontext() as ctx:
        ctx.prec = 2
        result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    grid = result["supported_domain"]["domain"]
    assert grid["increment"] == step
    assert grid["first_index"] == "1" + "0" * 5000
    assert grid["last_index"] == "2" + "0" * 5000
    assert sys.get_int_max_str_digits() == previous


@pytest.mark.parametrize("origin,step,minimum,maximum,first,last", [
    ("0.1", "0.1", "0.1", "0.1", "0", "0"),
    ("-0.1", "0.1", "0.1", "0.2", "2", "3"),
])
def test_native_grid_index_semantics(origin, step, minimum, maximum, first, last):
    up = cf.change_grid(deepcopy(upstream()), origin=origin, step=step, minimum=minimum, maximum=maximum)
    result = run(sample(native=up))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    domain = result["supported_domain"]["domain"]
    # Compare the native canonical origin/index choices without translating them.
    assert domain == cf.run(up)["composed_domain"]["domain"]
    assert Fraction(domain["origin"]) + int(domain["first_index"]) * Fraction(domain["increment"]) == Fraction(minimum)


def test_detached_complete_output_and_authority(case):
    before = deepcopy(case)
    result = run(case)
    expected_keys = "contract rule_version assessment_economic_time knowledge_boundary scope measure_target scenario outcome reason_codes owner_reference resolved_record supported_domain projection_basis native_diagnostics unresolved_findings conditions limitations reconstruction_evidence downstream_obligations source_authentication authority execution assessment_identity"
    assert set(result) == set(expected_keys.split())
    assert result["assessment_identity"] == owner.IDENTITY_PREFIX + digest({k: v for k, v in result.items() if k != "assessment_identity"})
    assert len(result["conditions"]) == 8 and len(result["limitations"]) == 11
    assert len(result["downstream_obligations"]) == 17
    assert "ACCOUNT_PROFIT_LOCK_AND_PAYOUT_ELIGIBILITY" in result["downstream_obligations"]
    assert result["authority"] == owner.AUTHORITY
    assert all(type(v) is bool and v is False for v in result["authority"].values())
    assert result["execution"] is False
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert not {"selected_quantity", "quantity", "order", "decision", "floor", "headroom", "authorization"} & result.keys()
    for field in ("scope", "projection_basis", "native_diagnostics", "reconstruction_evidence", "authority"):
        result[field]["mutation"] = True
    assert case == before
    assert run(case)["authority"] == owner.AUTHORITY


def test_no_mutable_aliases_inside_result(case):
    result = run(case)
    seen = set()

    def visit(value):
        if type(value) in (dict, list):
            assert id(value) not in seen
            seen.add(id(value))
            for item in value.values() if type(value) is dict else value:
                visit(item)
    visit(result)
    visit(validate(result, case))


@pytest.mark.parametrize("bad", [True, 1, 1.0, None, "2026-01-02", "2026-01-02T00:32Z", "2026-01-02T00:32:00", "2026-01-02T00:32:00.0000001Z"])
def test_invalid_local_timestamps(case, bad):
    case[0]["assessment_economic_time"] = bad
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("field,value", [("knowledge_boundary", EARLY), ("settlement_before", T)])
def test_current_boundary_and_deadline(case, field, value):
    if field == "knowledge_boundary":
        case[0][field] = value
    else:
        case[0]["scenario"][field] = value
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("path", [(), ("scope",), ("scenario",), ("projection_evidence",),
    ("projection_evidence", "coverage"), ("projection_evidence", "records", 0),
    ("projection_evidence", "records", 0, "body"), ("measure_target",)])
def test_closed_local_objects(case, path):
    value = case[0]
    for key in path:
        value = value[key]
    value["extra"] = True
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "\ud800", {1: "bad"}, (1, 2)])
def test_non_json_and_invalid_unicode(case, bad):
    case[0]["extra"] = bad
    with pytest.raises(ValueError):
        run(case)


def test_no_public_point_selection_api_and_no_numeric_global_settings():
    source = inspect.getsource(owner)
    assert "set_int_max_str_digits" not in source
    assert "getcontext" not in source
    assert "float(" not in source
    assert not any(name.startswith("evaluate_") and name != "evaluate_current_entry_provider_measure_projection_basis" for name in vars(owner))


def rebuild_regime(up, document_bytes=None):
    p = cf.financial(up)[0]["risk_policy"]["request"]
    g = p["account_rule_regime"]
    g["assessment"] = rf.run(rf.refresh(g["assessment_input"]))
    cf.limits(up)[0]["account_rule_regime"] = deepcopy(g)
    cf.rebuild_financial(up)
    if document_bytes is not None:
        with patch.object(cf.tf, "T", T):
            terminal = cf.tf.issue(cf.limits(up))
        for original in terminal[0]["rule_support"]["evidence"]:
            if original["evidence_id"] == "original:terms":
                original["content_base64"] = base64.b64encode(document_bytes).decode()
                original["content_sha256"] = hashlib.sha256(document_bytes).hexdigest()
        cf.tf.seal(terminal)
        up = (up[0], *up[1:4], terminal[1], terminal[2])
        return cf.rebuild_terminal(up, issue=False)
    return cf.rebuild_terminal(up)


@pytest.mark.parametrize("kind", ["REGIME_BINDING", "REGIME_APPROVAL"])
def test_every_contributing_binding_and_connected_approval(kind):
    up = deepcopy(upstream())
    g = pairs(up)[3]["assessment_input"]
    if kind == "REGIME_BINDING":
        bindings = g["manifest"]["assignments"][0]["package_bindings"]
        extra = deepcopy(bindings[0])
        extra["effective_period"]["effective_from"] = "2026-01-01T12:00:00.000000Z"
        bindings.append(extra)
    else:
        extra = deepcopy(g["approvals"][0])
        extra["approval_reference"]["source_snapshot_id"] = "connected-future-approval"
        extra["effective_period"]["effective_from"] = FUTURE
        g["approvals"].append(extra)
    case = sample(native=rebuild_regime(up))
    assert run(case)["outcome"] == "ESTABLISHED"
    e = case[0]["projection_evidence"]
    selector = "binding_index" if kind == "REGIME_BINDING" else "approval_index"
    e["native_mappings"] = [m for m in e["native_mappings"] if not (
        m["native_reference"]["kind"] == kind and m["native_reference"]["selector"][selector] == 1)]
    require_unknown(case, "ORIGINAL_SUPPORT_MISSING")


def test_known_native_document_hash_cannot_be_reissued_away():
    up = deepcopy(upstream())
    raw = canonical(dict(synthetic=True, meaning="Complete original provider balance and cost definition clauses")).encode()
    pairs(up)[3]["assessment_input"]["manifest"]["evidence"][0]["document_sha256"] = hashlib.sha256(raw).hexdigest()
    case = sample(native=rebuild_regime(up, document_bytes=raw))
    assert run(case)["outcome"] == "ESTABLISHED"
    doc = next(o for o in case[0]["projection_evidence"]["originals"] if o["evidence_id"] == "document:terms")
    doc["content_base64"] = base64.b64encode(b"different original").decode()
    doc["content_sha256"] = hashlib.sha256(b"different original").hexdigest()
    with pytest.raises(ValueError):
        run(seal(case))
