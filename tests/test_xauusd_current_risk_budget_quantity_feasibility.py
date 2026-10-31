"""Real owner composition under synthetic host admission, never provider rules."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
from fractions import Fraction
import hashlib
import json

import pytest

from ced_one.business_divisions.trading import xauusd_current_risk_budget_quantity_feasibility as owner
from ced_one.business_divisions.trading import xauusd_current_entry_to_stop_risk_basis as risks
from ced_one.business_divisions.trading import xauusd_current_entry_quantity_domain as quantities
from ced_one.business_divisions.trading import xauusd_account_specific_risk_policy_evaluation as policies
from ced_one.business_divisions.trading import causal_instrument_specification_applicability_resolver as applicability
from tests import test_xauusd_current_entry_to_stop_risk_basis as rfixtures
from tests import test_xauusd_account_specific_risk_policy_evaluation as pfixtures
from tests import test_xauusd_current_entry_quantity_domain as dfixtures
from tests import test_xauusd_candidate_gross_reference_financial_measurement as measurements
from tests import test_trading_vertical_slice_v29 as regimes


T = rfixtures.moment(32)
EARLY = "2026-01-01T00:00:00.000000Z"
END = "2027-01-01T00:00:00.000000Z"
AFTER = rfixtures.moment(32, microseconds=1)
SOURCE = dict(source_id="synthetic-review", source_contract="test-proof", source_contract_version="1", source_snapshot_id="review-1")
CLAIMS = ("account_provider_venue", "instrument_namespace", "quantity_denomination", "monetary_denomination")
ASSURANCES = ("source_authority", "fact_and_policy_semantics", "coverage_for_proposition", "causal_availability")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def original(identifier="original", content=b"synthetic independently reviewed evidence"):
    return dict(evidence_id=identifier, source=deepcopy(SOURCE), media_type="application/octet-stream",
                content_base64=base64.b64encode(content).decode(), source_available_at=T, observed_at=T)


def eref(row):
    return dict(evidence_id=row["evidence_id"], content_sha256=digest(row))


def gates(policy):
    return [(dict(kind="POLICY_GATE", gate=gate), value) for gate, value in (
        ("EQUITY", policy["own_policy"]["equity_gate"]),
        ("DAILY_LOSS", policy["own_policy"]["daily_loss_gate"]),
        ("FINANCIAL_COMPATIBILITY", policy["financial_compatibility"]),
        ("REGIME", policy["provider_policy"]["regime_gate"]))] + [
        (dict(kind="PROVIDER_RULE", rule_reference=deepcopy(row["rule_reference"])), row)
        for row in policy["provider_policy"]["rule_results"]]


def projection(target, q, planning):
    if target["kind"] in ("POLICY_GATE", "PROVIDER_RULE"):
        return dict(target=target, owner_bundle=q["risk_policy"])
    if target["kind"] in ("RISK_FUNCTION_INPUTS", "RISK_NEGATIVE"):
        return dict(target=target, owner_bundle=q["risk_basis"],
                    trusted_planning_context_sha256=None if planning is None else digest(planning))
    return dict(target=target, binding_evidence=q["binding_evidence"])


def receipt(target, q, planning, support):
    return dict(target=deepcopy(target), subject_content_sha256=digest(projection(target, q, planning)),
                assurances={key: dict(status="ADMITTED", evidence_refs=deepcopy(support)) for key in ASSURANCES})


def issue(case, *, reset=True):
    """Synthetic external host issuance; no production admission helpers are bypassed."""
    q, planning, quantity_context, context = case
    for name in ("risk_policy", "risk_basis", "quantity_domain"):
        pair = q[name]
        if pair is None:
            continue
        if name == "risk_policy":
            pair["assessment"] = policies.evaluate_account_specific_risk_policy(pair["request"])
        elif name == "risk_basis":
            pair["assessment"] = risks.evaluate_current_entry_to_stop_risk_basis(pair["request"], trusted_planning_context=planning)
        else:
            pair["assessment"] = quantities.evaluate_current_entry_quantity_domain(pair["request"], trusted_quantity_context=quantity_context)
    binding = q["binding_evidence"]
    if binding is not None:
        binding["subjects"] = {name + "_bundle_sha256": None if q[name] is None else digest(q[name])
                               for name in ("risk_policy", "risk_basis", "quantity_domain")}
    if context is None:
        return case
    support = [eref(row) for row in context["evidence"]]
    if reset:
        targets = []
        if q["risk_policy"] is not None:
            targets.extend(target for target, _ in gates(q["risk_policy"]["assessment"]))
        if q["risk_basis"] is not None:
            result = q["risk_basis"]["assessment"]
            targets.append(dict(kind="RISK_FUNCTION_INPUTS"))
            if result["outcome"] == "NOT_SUITABLE":
                targets.extend(dict(kind="RISK_NEGATIVE", reason_code=reason) for reason in
                               sorted(set(result["reasons"]) - set(result["uncertainties"])))
        if binding is not None:
            targets.extend(dict(kind="BINDING", claim=name) for name in CLAIMS)
    else:
        targets = [row["target"] for row in context["admissions"]]
    context["admissions"] = [receipt(target, q, planning, support) for target in targets]
    return case


def sample(direction="LONG", budget="11.8", *, at=32, history=None, age=500_000):
    request, planning = rfixtures.sample(direction, at=at, history=history, age_microseconds=age,
                                         payoff_change=lambda p: p.update(payoff_units_per_quantity_unit="1"))
    now = request["knowledge_boundary"]
    # Build the policy from its original inputs, replacing all subjects and time
    # assertions through their real owners rather than editing output artifacts.
    p = deepcopy(pfixtures.baseline.__wrapped__())
    p["assessment_economic_time"] = p["knowledge_boundary"] = now
    p["candidate"] = deepcopy(request["candidate"])
    a = p["account_state"]["snapshot_input"]
    a["requested_evaluation_timestamp"] = now
    a["observation"]["timing"] = dict(effective_at=now, observed_at=now, source_available_at=now)
    equity = Fraction(budget) * 100
    assert equity.denominator == 1  # Fixture budgets have at most two decimal places.
    a["observation"]["account_measures"]["equity"] = str(equity.numerator)
    p["account_state"]["snapshot"] = pfixtures.accounts.run(a)
    regime_input = p["account_rule_regime"]["assessment_input"]
    regime_input["economic_timestamp"] = regime_input["requested_knowledge_boundary"] = now
    regime_input["manifest"]["timing"]["observed_at"] = now
    regime_input["manifest"]["coverage"]["source_information_cutoff"] = now
    for row in regime_input["manifest"]["evidence"]:
        row["timing"]["observed_at"] = EARLY
    for row in regime_input["manifest"]["packages"]:
        row["interpretation"]["interpreted_at"] = EARLY
    for row in regime_input["approvals"]:
        row["decided_at"] = row["observed_at"] = EARLY
    p["account_rule_regime"]["assessment"] = regimes.run(regimes.refresh(regime_input))
    m = measurements.sample({direction: rfixtures.formulation_input(direction)}, direction)
    app = deepcopy(request["applicability"]["resolver_input"])
    app["economic_timestamp"] = request["candidate"]["formulation"]["candidate"]["valid_from"]
    m["knowledge_boundary"] = now
    m["applicability_input"] = app
    m["applicability"] = applicability.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2.analyze(app).to_dict()
    spec = next(row["snapshot"] for row in app["specification_revisions"]
                if row["snapshot"]["specification"]["source"] == m["applicability"]["selected_revision"])
    m["bridge_assertions"] = [dict(contract=measurements.owner.ASSERTION_CONTRACT, assertion_revision_id="current-test-bridge",
        source=dict(source_id="test-domain", source_contract="price-domain", source_contract_version="1"),
        available_at=now, candidate_formulation=deepcopy(m["candidate_formulation"]), selected_specification=deepcopy(spec),
        relationship=measurements.owner.RELATIONSHIP, verdict="COMPATIBLE")]
    p["financial_measurement"] = dict(assessment=measurements.run(m), measurement_input=m)
    pfixtures.compatibility(p)
    pfixtures.coverage(p)
    for row in p["provider_operands"]:
        row["available_at"] = now
        for evidence in row["supporting_evidence"]:
            evidence["available_at"] = now
    request["account_state"] = deepcopy(p["account_state"])
    account = p["account_state"]["snapshot"]
    scope = {key: account["observation"]["account"][key] for key in ("environment", "account_id", "currency")}
    declaration = request["scenario_evidence"][0]
    declaration["subjects"]["account"] = risks._ref(account)
    declaration["terms"].update(account_scope=scope, maximum_supported_quantity="1", adverse_entry_allowance="0", adverse_stop_allowance="0")
    declaration["terms"]["charges"] = [dict(charge_id="opening", category="opening_commission", basis="SOURCE_SCHEDULE",
        currency="USD", quantity_unit=" lot ", fixed="1", per_unit="2", minimum="2")]
    declaration["terms"]["cost_coverage"]["closing_commission"] = "NOT_APPLICABLE"
    policy = request["planning_evidence"]["records"][0]["policy_definition"]
    policy["account_scope"] = deepcopy(scope)
    planning["scope"]["account_scope"] = deepcopy(scope)
    rfixtures.revise_price(request, "BID", value="116.9" if direction == "LONG" else "183")
    rfixtures.revise_price(request, "ASK", value="117" if direction == "LONG" else "183.1")
    rfixtures.align_policy(request, planning)
    d, dc = dfixtures.sample()
    for key in ("assessment_economic_time", "knowledge_boundary"):
        d[key] = now
    d["scope"].update(account_id=scope["account_id"], venue_id="venue-1", quantity_unit=" lot ", entry_direction=direction)
    inv = d["quantity_inventory"]
    inv["scope"] = deepcopy(d["scope"])
    inv["observed_at"] = inv["source_available_at"] = now
    inv["coverage"].update(observed_at=now, source_available_at=now, source_information_cutoff=now)
    inv["records"][0]["domain"] = dfixtures.grid(maximum=None)
    dc.update(scope=deepcopy(d["scope"]), knowledge_boundary=now, admitted_at=now, available_at=now)
    dfixtures.seal(d, dc)
    evidence = original()
    evidence["observed_at"] = evidence["source_available_at"] = now
    support = [eref(evidence)]
    binding = dict(contract=owner.BINDING_CONTRACT, rule_version=owner.BINDING_RULE, binding_id="binding", source=deepcopy(SOURCE),
        assessment_economic_time=now, knowledge_boundary=now, effective_from=EARLY, effective_until=END,
        source_available_at=now, observed_at=now, subjects={},
        claims={name: dict(status="COMPATIBLE", evidence_refs=deepcopy(support)) for name in CLAIMS}, evidence=[deepcopy(evidence)])
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=now, knowledge_boundary=now,
        risk_policy=dict(request=p, assessment=None), risk_basis=dict(request=request, assessment=None),
        quantity_domain=dict(request=d, assessment=None), binding_evidence=binding)
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE, admission_id="test-admission",
        authority_id="external-test-host", mandate_id="test-mandate", mandate_revision=1, purpose=owner.PURPOSE,
        knowledge_boundary=now, effective_from=EARLY, effective_until=END, admitted_at=now, available_at=now,
        evidence=[deepcopy(evidence)], admissions=[])
    return issue((q, planning, dc, context))


@pytest.fixture(scope="module")
def established():
    return sample()


@pytest.fixture
def case(established):
    return deepcopy(established)


def run(case):
    q, planning, dc, context = case
    return owner.evaluate_current_risk_budget_quantity_feasibility(q, trusted_planning_context=planning,
        trusted_quantity_context=dc, trusted_feasibility_context=context)


def validate(result, case):
    q, planning, dc, context = case
    return owner.validate_current_risk_budget_quantity_feasibility(result, q, trusted_planning_context=planning,
        trusted_quantity_context=dc, trusted_feasibility_context=context)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_positive_real_composition(direction):
    case = sample(direction)
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["budget"] == dict(amount="11.8", currency="USD")
    assert result["risk_support"] == dict(maximum_quantity="1", quantity_unit=" lot ")
    assert result["supported_entry_domain"]["domain"]["last_index"] == "10"
    assert result["feasible_domain"]["domain"]["last_index"] == "9"
    assert result["outside_risk_support"]["domain"]["first_index"] == "11"
    assert result["outside_risk_support"]["domain"]["last_index"] is None
    assert validate(result, case) == result
    assert case == before
    assert not any(result["authority"].values()) and result["execution"] is False
    assert not {"quantity", "selected_quantity", "proposed_quantity", "decision", "authorization"} & result.keys()


@pytest.mark.parametrize("budget,last", [("7", "5"), ("3", "1"), ("2.99", None)])
def test_exact_budget_boundaries(budget, last):
    result = run(sample(budget=budget))
    if last is None:
        assert result["outcome"] == "NOT_SUITABLE"
        assert result["feasible_domain"]["domain"] == dict(kind="EMPTY")
        assert "BUDGET_BELOW_FIRST_SUPPORTED_QUANTITY_RISK" in result["reason_codes"]
    else:
        assert result["outcome"] == "ESTABLISHED"
        assert result["feasible_domain"]["domain"]["last_index"] == last


def modify_grid(case, origin="0", step="0.1", minimum="0.1", maximum=None):
    q, _, dc, _ = case
    d = q["quantity_domain"]["request"]
    d["quantity_inventory"]["records"][0]["domain"] = dfixtures.grid(origin, step, minimum, maximum)
    dfixtures.seal(d, dc)
    return issue(case)


def remove(case, kind, **fields):
    case[3]["admissions"] = [row for row in case[3]["admissions"] if not
        (row["target"]["kind"] == kind and all(row["target"].get(key) == value for key, value in fields.items()))]


def at(value, path):
    for part in path:
        value = value[part]
    return value


def paths(value, prefix=()):
    if type(value) is dict:
        for key, item in value.items():
            yield from paths(item, prefix + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from paths(item, prefix + (index,))
    else:
        yield prefix


@pytest.mark.parametrize("origin,step,minimum,maximum,first,last", [
    ("0.07", "0.1", "0", None, "0", "9"),
    ("-0.23", "0.1", "-2", "0.87", "0", "8"),
    ("0.2", "0.1", "0", "0.3", "1", "3"),
    ("-0.1", "0.1", "0.3", "0.3", "3", "3"),
])
def test_signed_origins_index_zero_and_endpoints(case, origin, step, minimum, maximum, first, last):
    result = run(modify_grid(case, origin, step, minimum, maximum))
    domain = result["supported_entry_domain"]["domain"]
    assert domain["first_index"] == first and domain["last_index"] == last
    assert result["outcome"] == "ESTABLISHED"
    if maximum is not None:
        assert result["outside_risk_support"]["domain"] == dict(kind="EMPTY")


def test_empty_entry_without_any_unrelated_owner_or_context(case):
    modify_grid(case, "0.07", "0.1", "0", "0.06")
    q, _, dc, _ = case
    q["risk_policy"] = q["risk_basis"] = q["binding_evidence"] = None
    result = run((q, None, dc, None))
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["entry_domain"]["domain"] == dict(kind="EMPTY")
    assert all(result[field] is None for field in ("budget", "risk_support", "supported_entry_domain", "feasible_domain", "outside_risk_support"))
    assert result["negative_proofs"] == [dict(reason_code="ENTRY_DOMAIN_EMPTY", target=dict(kind="ENTRY_DOMAIN"), scope="ENTRY_DOMAIN")]
    assert "OWNER_MISSING" in result["reason_codes"]
    assert validate(result, (q, None, dc, None)) == result


def test_empty_supported_domain_needs_no_budget(case):
    modify_grid(case, minimum="1.1")
    remove(case, "POLICY_GATE", gate="EQUITY")
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["supported_entry_domain"]["domain"] == dict(kind="EMPTY")
    assert result["feasible_domain"] is result["budget"] is None
    assert result["outside_risk_support"]["domain"]["first_index"] == "11"
    assert "NO_SUPPORTED_POSITIVE_QUANTITY" in result["reason_codes"]
    assert "ADMISSION_MISSING" in result["reason_codes"]


def test_empty_domains_with_complete_operands(case):
    result = run(modify_grid(case, "0.07", "0.1", "0", "0.06"))
    assert result["outcome"] == "NOT_SUITABLE"
    for field in ("entry_domain", "supported_entry_domain", "feasible_domain", "outside_risk_support"):
        assert result[field]["domain"] == dict(kind="EMPTY")


def test_native_unknown_quantity_cannot_be_relabelled_by_receipts(case):
    q, planning, _, context = case
    q["quantity_domain"]["assessment"] = quantities.evaluate_current_entry_quantity_domain(q["quantity_domain"]["request"])
    revised = (q, planning, None, context)
    issue(revised)
    result = run(revised)
    assert result["outcome"] == "UNKNOWN" and result["entry_domain"] is None
    assert "OWNER_UNKNOWN" in result["reason_codes"]
    assert not result["negative_proofs"]


@pytest.mark.parametrize("owner_name,context_index", [("risk_basis", 1), ("quantity_domain", 2)])
def test_positive_owner_requires_original_independent_context(case, owner_name, context_index):
    revised = list(case)
    revised[context_index] = None
    with pytest.raises(ValueError): run(revised)


def test_policy_block_retains_unknown_and_never_empties_feasibility(case):
    p = case[0]["risk_policy"]["request"]
    p["actual_trade_evidence"] = [pfixtures.trade(p, "a", close=rfixtures.moment(31)), pfixtures.trade(p, "b", close=rfixtures.moment(31, 1))]
    pfixtures.coverage(p, complete=False)
    p["financial_compatibility"] = []
    issue(case)
    # Admission only for the actual failing proposition is sufficient.
    case[3]["admissions"] = [row for row in case[3]["admissions"] if row["target"] == dict(kind="POLICY_GATE", gate="DAILY_LOSS")]
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert "PRE_QUANTITY_POLICY_BLOCKED" in result["reason_codes"]
    assert "OWNER_UNKNOWN" in result["reason_codes"]
    assert result["budget"] is result["feasible_domain"] is None
    assert result["negative_proofs"][0]["scope"] == "POLICY_GATE_AT_K"
    remove(case, "POLICY_GATE", gate="DAILY_LOSS")
    assert run(case)["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("kind", ["INVALIDATED", "EXPIRED"])
def test_candidate_negatives_need_only_own_receipt(kind):
    case = sample(history=(lambda h, d: rfixtures.set_breach(h, d, minute=31)) if kind == "INVALIDATED" else None,
                  at=32 if kind == "INVALIDATED" else 34)
    target = dict(kind="RISK_NEGATIVE", reason_code="CANDIDATE_" + kind)
    case[3]["admissions"] = [row for row in case[3]["admissions"] if row["target"] == target]
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["negative_proofs"] == [dict(reason_code="CANDIDATE_NOT_CURRENTLY_VALID", target=target, scope="CANDIDATE_AT_K")]
    assert result["feasible_domain"] is None and result["unresolved_findings"]
    remove(case, "RISK_NEGATIVE")
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and not result["negative_proofs"]
    assert "NEGATIVE_NOT_ADMITTED" in result["reason_codes"]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_missing_history_is_unknown_even_with_input_receipt(direction):
    def gap(history, _):
        history["M1"][:] = [row for row in history["M1"] if row["timestamp"] != rfixtures.ts(31)]
    case = sample(direction, history=gap)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["risk_support"] is result["feasible_domain"] is None
    assert not result["negative_proofs"]


@pytest.mark.parametrize("target", [
    dict(kind="POLICY_GATE", gate="EQUITY"), dict(kind="POLICY_GATE", gate="DAILY_LOSS"),
    dict(kind="POLICY_GATE", gate="FINANCIAL_COMPATIBILITY"), dict(kind="POLICY_GATE", gate="REGIME"),
    dict(kind="RISK_FUNCTION_INPUTS"),
    *[dict(kind="BINDING", claim=name) for name in CLAIMS],
])
def test_each_receipt_is_separately_necessary(case, target):
    case[3]["admissions"] = [row for row in case[3]["admissions"] if row["target"] != target]
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert dict(reason_code="ADMISSION_MISSING", target=target) in result["unresolved_findings"]


@pytest.mark.parametrize("assurance", ASSURANCES)
def test_insufficient_risk_admission(case, assurance):
    row = next(row for row in case[3]["admissions"] if row["target"]["kind"] == "RISK_FUNCTION_INPUTS")
    row["assurances"][assurance]["status"] = "UNRESOLVED"
    assert run(case)["outcome"] == "UNKNOWN"
    assert run(case)["risk_support"] is None


@pytest.mark.parametrize("field", ["effective_from", "effective_until"])
def test_feasibility_admission_outside_interval(case, field):
    case[3][field] = AFTER if field == "effective_from" else T
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and "ADMISSION_NOT_CURRENT" in result["reason_codes"]
    assert result["entry_domain"] is not None


@pytest.mark.parametrize("claim", CLAIMS)
def test_incompatible_binding_is_scoped_and_needs_own_admission(case, claim):
    case[0]["binding_evidence"]["claims"][claim]["status"] = "INCOMPATIBLE"
    issue(case)
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert any(row["reason_code"] == "BINDING_INCOMPATIBLE" and row["target"]["claim"] == claim for row in result["negative_proofs"])
    assert result["feasible_domain"] is None
    remove(case, "BINDING", claim=claim)
    assert run(case)["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("field,value,claim", [
    ("account_id", "different-account", "account_provider_venue"),
    ("environment", "LIVE", "account_provider_venue"),
    ("venue_id", "other-venue", "account_provider_venue"),
    ("instrument_id", "other-instrument", "instrument_namespace"),
    ("quantity_unit", "lot", "quantity_denomination"),
])
def test_literal_binding_contradictions_and_honest_incompatibility(case, field, value, claim):
    d, dc = case[0]["quantity_domain"]["request"], case[2]
    d["scope"][field] = value
    d["quantity_inventory"]["scope"] = deepcopy(d["scope"])
    dc["scope"] = deepcopy(d["scope"])
    dfixtures.seal(d, dc)
    issue(case)
    with pytest.raises(ValueError): run(case)
    if field == "environment":
        # Environment is a comparand of both claims. An honest partial binding
        # must preserve the independent instrument uncertainty as well.
        case[0]["binding_evidence"]["claims"]["instrument_namespace"]["status"] = "UNKNOWN"
    case[0]["binding_evidence"]["claims"][claim]["status"] = "UNKNOWN"
    issue(case)
    assert run(case)["outcome"] == "UNKNOWN"
    case[0]["binding_evidence"]["claims"][claim]["status"] = "INCOMPATIBLE"
    issue(case)
    assert run(case)["outcome"] == "NOT_SUITABLE"


def test_provider_identity_requires_admission_even_with_equal_text(case):
    q, planning, dc, _ = case
    result = run((q, planning, dc, None))
    assert result["outcome"] == "UNKNOWN"
    assert result["entry_domain"] is not None and result["feasible_domain"] is None


@pytest.mark.parametrize("field", ["source_available_at", "evidence_refs"])
def test_missing_binding_original_support_is_not_a_negative(case, field):
    b = case[0]["binding_evidence"]
    if field == "source_available_at":
        b[field] = None
    else:
        b["claims"]["instrument_namespace"][field] = []
    issue(case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert "BINDING_SUPPORT_MISSING" in result["reason_codes"]


@pytest.mark.parametrize("field", ["effective_from", "effective_until"])
def test_noncurrent_binding_is_unknown(case, field):
    case[0]["binding_evidence"][field] = AFTER if field == "effective_from" else T
    issue(case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and "BINDING_NOT_CURRENT" in result["reason_codes"]


def test_account_independent_risk_is_not_positive_composition(case):
    q, planning, _, _ = case
    r = q["risk_basis"]["request"]
    r["account_state"] = None
    r["scenario_evidence"][0]["subjects"]["account"] = None
    r["scenario_evidence"][0]["terms"]["account_scope"] = None
    planning["scope"]["account_scope"] = None
    r["planning_evidence"]["records"][0]["policy_definition"]["account_scope"] = None
    rfixtures.align_policy(r, planning)
    issue(case)
    assert q["risk_basis"]["assessment"]["outcome"] == "ESTABLISHED"
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert "ACCOUNT_APPLICABILITY_UNRESOLVED" in result["reason_codes"]


def test_actual_provider_quantity_rule_is_not_position_compliance(case):
    p = case[0]["risk_policy"]["request"]
    def edit(rule):
        pfixtures.instrument_scope(rule)
        rule["body"] = dict(type="POSITION_LIMIT", limit_kind="PER_POSITION_QUANTITY", quantity_unit=" lot ", maximum="0.2")
    pfixtures.set_rule(p, "POSITION_LIMIT", edit)
    # Reproduce the existing binding with the current financial namespace.
    ns = case[0]["risk_basis"]["assessment"]["reconstruction_evidence"]["selected_specification"]["specification"]["position_namespace"]
    instrument = {key: ns[key] for key in ("source_id", "source_contract", "source_contract_version", "environment", "instrument_id")}
    p["account_rule_regime"]["assessment_input"]["manifest"]["packages"][0]["rules"][0]["instrument_scope"]["instruments"] = [instrument]
    p["account_rule_regime"]["assessment"] = regimes.run(regimes.refresh(p["account_rule_regime"]["assessment_input"]))
    pfixtures.operand(p, "INSTRUMENT_BINDING", dict(candidate=pfixtures.artifact(p["candidate"]["formulation"]), provider_instrument=instrument))
    issue(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["feasible_domain"]["domain"]["last_index"] == "9"
    assert "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE" in result["downstream_obligations"]
    remove(case, "PROVIDER_RULE")
    assert run(case)["outcome"] == "UNKNOWN"


def test_old_receipt_does_not_admit_changed_originals(case):
    old = deepcopy(case[3])
    case[0]["risk_policy"]["request"]["own_policy"]["provenance"]["record_id"] = "changed-original"
    issue(case)
    revised = (case[0], case[1], case[2], old)
    with pytest.raises(ValueError): run(revised)


@pytest.mark.parametrize("part", ["risk_policy", "risk_basis", "quantity_domain"])
def test_nested_owner_tampering_and_rehashing_rejected(case, part):
    assessment = case[0][part]["assessment"]
    assessment["authority"]["execution"] = True
    key = "assessment_identity"
    assessment[key] = digest({k: v for k, v in assessment.items() if k != key})
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("where,field,value", [
    ("request", "approved", True), ("context", "purpose", "EXECUTION_APPROVAL"),
    ("context", "knowledge_boundary", AFTER), ("context", "available_at", AFTER),
    ("context", "admitted_at", EARLY), ("context", "mandate_revision", True),
    ("binding", "observed_at", AFTER), ("binding", "source_available_at", AFTER),
    ("binding", "knowledge_boundary", AFTER), ("binding", "effective_until", EARLY),
])
def test_structural_context_and_binding_rejections(case, where, field, value):
    target = case[0] if where == "request" else case[3] if where == "context" else case[0]["binding_evidence"]
    target[field] = value
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("mutation", ["pin", "subject", "missing-rule", "missing-reason", "duplicate", "missing-ref", "empty-proof", "unavailable-proof", "late-proof", "wrong-source-type"])
def test_forged_or_malformed_admission(case, mutation):
    q, _, _, context = case
    row = context["admissions"][0]
    if mutation == "pin": row["subject_content_sha256"] = "0" * 64
    elif mutation == "subject": q["binding_evidence"]["subjects"]["risk_basis_bundle_sha256"] = "0" * 64
    elif mutation == "missing-rule": row["target"] = dict(kind="PROVIDER_RULE", rule_reference=dict(rule_id="absent", full_content_sha256="0" * 64))
    elif mutation == "missing-reason": row["target"] = dict(kind="RISK_NEGATIVE", reason_code="CANDIDATE_EXPIRED")
    elif mutation == "duplicate": context["admissions"].append(deepcopy(row))
    elif mutation == "missing-ref": row["assurances"]["source_authority"]["evidence_refs"][0]["evidence_id"] = "absent"
    elif mutation == "empty-proof": row["assurances"]["source_authority"]["evidence_refs"] = []
    elif mutation == "unavailable-proof":
        context["evidence"][0]["source_available_at"] = None
        issue(case)
    elif mutation == "late-proof": context["evidence"][0]["observed_at"] = AFTER
    else: context["evidence"][0]["source"] = []
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("which", ["candidate", "account", "direction", "time"])
def test_contradictory_owner_coreferences(case, which):
    q = case[0]
    if which == "candidate":
        q["risk_policy"]["request"]["candidate"]["formulation_input"]["candidate_policy_definition"]["configuration"]["entry_validity_duration_seconds"] += 1
    elif which == "account":
        q["risk_policy"]["request"]["account_state"]["snapshot_input"]["observation"]["account_measures"]["balance"] = "20000"
        pfixtures.refresh_account(q["risk_policy"]["request"])
    elif which == "direction":
        d = q["quantity_domain"]["request"]
        d["scope"]["entry_direction"] = "SHORT"
        d["quantity_inventory"]["scope"] = deepcopy(d["scope"])
        case[2]["scope"] = deepcopy(d["scope"])
        dfixtures.seal(d, case[2])
    else:
        q["assessment_economic_time"] = AFTER
    with pytest.raises(ValueError):
        issue(case)
        run(case)


@pytest.mark.parametrize("state", ["expired", "withdrawn", "future", "missing-history", "branch"])
def test_native_quantity_lifecycle_is_preserved(case, state):
    q, _, dc, _ = case
    d = q["quantity_domain"]["request"]
    inv = d["quantity_inventory"]
    root = inv["records"][0]
    if state == "expired": root["effective_until"] = T
    elif state == "withdrawn":
        inv["records"].append(dfixtures.withdrawal(root, start=T))
        inv["records"][-1]["evidence_refs"] = deepcopy(root["evidence_refs"])
    elif state == "future": root["effective_from"] = AFTER
    elif state == "missing-history":
        root["predecessor"] = dict(kind="UNKNOWN")
        inv["coverage"].update(root_records=[], revision_completeness="LIMITED", starting_basis="INCOMPLETE_OR_UNKNOWN")
    else:
        for name in ("B", "C"):
            child = dfixtures.declaration(name, root, start=T)
            child["evidence_refs"] = deepcopy(root["evidence_refs"])
            inv["records"].append(child)
    dfixtures.seal(d, dc)
    issue(case)
    assert q["quantity_domain"]["assessment"]["outcome"] == "UNKNOWN"
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["entry_domain"] is None


def test_known_future_successor_does_not_replace_current_domain(case):
    d, dc = case[0]["quantity_domain"]["request"], case[2]
    root = d["quantity_inventory"]["records"][0]
    child = dfixtures.declaration("future", root, start=AFTER, domain=dfixtures.grid(maximum="0.2"))
    child["evidence_refs"] = deepcopy(root["evidence_refs"])
    d["quantity_inventory"]["records"].append(child)
    dfixtures.seal(d, dc)
    issue(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["feasible_domain"]["domain"]["last_index"] == "9"


def test_native_risk_stale_quotes_remain_unknown():
    result = run(sample(age=1_000_001))
    assert result["outcome"] == "UNKNOWN"
    assert result["risk_support"] is result["feasible_domain"] is None


def test_fee_changes_require_new_native_assessments_and_admission(case):
    r = case[0]["risk_basis"]["request"]
    row = r["scenario_evidence"][0]["terms"]["charges"][0]
    row.update(fixed="0", minimum="0", per_unit="0")
    rfixtures.align_policy(r, case[1])
    issue(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["feasible_domain"]["domain"]["last_index"] == "10"


@pytest.mark.parametrize("step,origin", [("0.1", "0"), ("0.03", "0.01"), ("0.07", "-0.02")])
def test_against_independent_small_enumeration(case, step, origin):
    result = run(modify_grid(case, origin, step, "0", "1.7"))
    d = result["feasible_domain"]["domain"]
    original_points = {Fraction(origin) + n * Fraction(step) for n in range(-100, 101)}
    expected = {q for q in original_points if 0 < q <= 1 and 10*q + max(Fraction(2), 1+2*q) <= Fraction("11.8")}
    actual = set() if d["kind"] == "EMPTY" else {Fraction(d["origin"]) + k * Fraction(d["increment"])
        for k in range(int(d["first_index"]), int(d["last_index"]) + 1)}
    assert actual == expected


def test_extreme_decimal_grid_and_large_indices_without_enumeration(case):
    step = "0." + "0" * 5000 + "1"
    modify_grid(case, step=step)
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["supported_entry_domain"]["domain"]["last_index"] == "1" + "0" * 5001
    assert result["feasible_domain"]["domain"]["last_index"] == "9" + "0" * 5000
    assert result["outside_risk_support"]["domain"]["first_index"] == "1" + "0" * 5000 + "1"


def test_local_ordering_and_identity(case):
    evidence = original("second", b"another independent review record")
    for catalog in (case[0]["binding_evidence"]["evidence"], case[3]["evidence"]):
        catalog.append(deepcopy(evidence))
    for claim in case[0]["binding_evidence"]["claims"].values():
        claim["evidence_refs"].append(eref(evidence))
    issue(case)
    expected = run(case)
    case[0]["binding_evidence"]["evidence"].reverse()
    for claim in case[0]["binding_evidence"]["claims"].values(): claim["evidence_refs"].reverse()
    case[3]["evidence"].reverse()
    case[3]["admissions"].reverse()
    for receipt in case[3]["admissions"]:
        for assurance in receipt["assurances"].values(): assurance["evidence_refs"].reverse()
    assert run(case) == expected
    assert expected["assessment_identity"] == "current_risk_budget_quantity_feasibility_" + digest(
        {key: value for key, value in expected.items() if key != "assessment_identity"})
    assert set(expected["reason_codes"]) <= owner.REASON_CODES


def test_new_original_bytes_change_identity_and_invalidate_old_receipt(case):
    old_context = deepcopy(case[3])
    b = case[0]["binding_evidence"]
    b["evidence"][0]["content_base64"] = base64.b64encode(b"revised original source bytes").decode()
    for claim in b["claims"].values(): claim["evidence_refs"] = [eref(b["evidence"][0])]
    issue(case)
    changed = run(case)
    with pytest.raises(ValueError): run((case[0], case[1], case[2], old_context))
    assert changed["assessment_identity"] != run(sample())["assessment_identity"]


def test_each_owned_output_leaf_independently_reconstructed(case):
    result = run(case)
    owned = {key: value for key, value in result.items() if key != "reconstruction_evidence"}
    # Native owners exhaustively test their own nested artifact leaves. Here
    # check every new output leaf plus each retained native envelope and context
    # dependency through the public composition validator, without stubbing it.
    targets = list(paths(owned)) + [
        ("reconstruction_evidence", name) for name in (
            "trusted_planning_context_sha256", "trusted_quantity_context_sha256", "trusted_feasibility_context_sha256")
    ] + [("reconstruction_evidence", "request", name, part)
         for name in ("risk_policy", "risk_basis", "quantity_domain") for part in ("assessment", "request")]
    for path in targets:
        changed = deepcopy(result)
        at(changed, path[:-1])[path[-1]] = "tampered"
        if path != ("assessment_identity",):
            changed["assessment_identity"] = "current_risk_budget_quantity_feasibility_" + digest(
                {key: value for key, value in changed.items() if key != "assessment_identity"})
        with pytest.raises(ValueError): validate(changed, case)


def test_detached_result_nonmutation_and_native_original_preservation(case):
    before = deepcopy(case)
    result = run(case)
    detached = validate(result, case)
    result["feasible_domain"]["domain"]["last_index"] = "0"
    detached["reconstruction_evidence"]["request"]["risk_policy"]["request"]["operation_mode"] = "mutated"
    assert case == before
    expected = run(case)
    for name in ("risk_policy", "risk_basis", "quantity_domain"):
        assert expected["reconstruction_evidence"]["request"][name] == case[0][name]


@pytest.mark.parametrize("value", [[], (), True, "assessment", 1])
def test_detached_validator_requires_json_object(case, value):
    with pytest.raises(ValueError): validate(value, case)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), (), {1: "wrong-key"}])
def test_non_json_input_rejected(case, value):
    case[0]["binding_evidence"]["binding_id"] = value
    with pytest.raises(ValueError): run(case)


def test_structural_failure_precedes_admitted_negative(case):
    modify_grid(case, "0.07", "0.1", "0", "0.06")
    case[3]["admissions"][0]["assurances"]["source_authority"]["evidence_refs"][0]["content_sha256"] = "0" * 64
    with pytest.raises(ValueError): run(case)


def test_all_absent_is_unknown():
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T, knowledge_boundary=T,
             risk_policy=None, risk_basis=None, quantity_domain=None, binding_evidence=None)
    result = run((q, None, None, None))
    assert result["outcome"] == "UNKNOWN" and not result["negative_proofs"]
    assert result["reason_codes"] == ["BINDING_MISSING", "OWNER_MISSING"]


def refresh_joined_account(case):
    p = case[0]["risk_policy"]["request"]
    pfixtures.refresh_account(p)
    r = case[0]["risk_basis"]["request"]
    r["account_state"] = deepcopy(p["account_state"])
    r["scenario_evidence"][0]["subjects"]["account"] = risks._ref(p["account_state"]["snapshot"])
    scope = {key: p["account_state"]["snapshot"]["observation"]["account"][key]
             for key in ("environment", "account_id", "currency")}
    r["scenario_evidence"][0]["terms"]["account_scope"] = deepcopy(scope)
    r["planning_evidence"]["records"][0]["policy_definition"]["account_scope"] = deepcopy(scope)
    case[1]["scope"]["account_scope"] = deepcopy(scope)
    rfixtures.align_policy(r, case[1])
    return issue(case)


def test_native_unknown_equity_cannot_be_admitted_into_a_budget(case):
    a = case[0]["risk_policy"]["request"]["account_state"]["snapshot_input"]
    a["observation"]["account_measures"].update(equity=None, completeness="PARTIAL")
    refresh_joined_account(case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["budget"] is result["feasible_domain"] is None
    assert result["supported_entry_domain"] is not None


def test_currency_mismatch_is_scoped_and_does_not_create_a_budget(case):
    p = case[0]["risk_policy"]["request"]
    p["account_state"]["snapshot_input"]["observation"]["account"]["currency"] = "EUR"
    case[0]["binding_evidence"]["claims"]["monetary_denomination"]["status"] = "INCOMPATIBLE"
    refresh_joined_account(case)
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert "BINDING_INCOMPATIBLE" in result["reason_codes"]
    assert "RISK_BASIS_UNUSABLE" in result["reason_codes"]
    assert "OWNER_UNKNOWN" in result["reason_codes"]
    assert result["budget"] is result["feasible_domain"] is None


def test_charge_units_incompatible_without_scaling(case):
    r = case[0]["risk_basis"]["request"]
    r["scenario_evidence"][0]["terms"]["charges"][0]["quantity_unit"] = "contracts"
    rfixtures.align_policy(r, case[1])
    case[0]["binding_evidence"]["claims"]["quantity_denomination"]["status"] = "INCOMPATIBLE"
    issue(case)
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["feasible_domain"] is None
    assert "RISK_BASIS_UNUSABLE" in result["reason_codes"]


@pytest.mark.parametrize("planning_present", [False, True])
def test_planning_dependent_negative_needs_planning_context(case, planning_present):
    r = case[0]["risk_basis"]["request"]
    r["planning_evidence"]["records"][0]["decision"] = "REJECTED"
    rfixtures.repin(r, case[1])
    revised = case if planning_present else (case[0], None, case[2], case[3])
    issue(revised)
    result = run(revised)
    if planning_present:
        assert result["outcome"] == "NOT_SUITABLE"
        assert any(p["target"] == dict(kind="RISK_NEGATIVE", reason_code="PLANNING_REJECTED") for p in result["negative_proofs"])
    else:
        assert result["outcome"] == "UNKNOWN" and not result["negative_proofs"]
        assert "NEGATIVE_NOT_ADMITTED" in result["reason_codes"]


def test_current_successor_replaces_domain_with_exact_new_bounds(case):
    d, dc = case[0]["quantity_domain"]["request"], case[2]
    root = d["quantity_inventory"]["records"][0]
    child = dfixtures.declaration("current", root, start=T, domain=dfixtures.grid(maximum="0.2"))
    child["evidence_refs"] = deepcopy(root["evidence_refs"])
    d["quantity_inventory"]["records"].append(child)
    dfixtures.seal(d, dc)
    issue(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["feasible_domain"]["domain"]["last_index"] == "2"
    assert result["outside_risk_support"]["domain"] == dict(kind="EMPTY")


@pytest.mark.parametrize("path", [
    (), ("risk_policy",), ("risk_basis",), ("quantity_domain",),
    ("binding_evidence",), ("binding_evidence", "source"), ("binding_evidence", "subjects"),
    ("binding_evidence", "claims"), *[("binding_evidence", "claims", name) for name in CLAIMS],
    ("binding_evidence", "evidence", 0), ("binding_evidence", "evidence", 0, "source"),
])
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_local_request_objects_exact_schema(case, path, change):
    target = at(case[0], path)
    if change == "extra": target["unexpected"] = True
    else: del target[next(iter(target))]
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("path", [
    (), ("evidence", 0), ("evidence", 0, "source"), ("admissions", 0),
    ("admissions", 0, "target"), ("admissions", 0, "assurances"),
    *[("admissions", 0, "assurances", name) for name in ASSURANCES],
    ("admissions", 0, "assurances", "source_authority", "evidence_refs", 0),
])
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_local_context_objects_exact_schema(case, path, change):
    target = at(case[3], path)
    if change == "extra": target["unexpected"] = True
    else: del target[next(iter(target))]
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("bad", ["", "a", "!!!!", "aGVsbG8=\n", "aGVsbG8", True])
def test_original_evidence_encoding(case, bad):
    case[0]["binding_evidence"]["evidence"][0]["content_base64"] = bad
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("value", ["2026-01-02T00:32:00", "2026-01-02T00:32:00.0000001Z", "2026-02-30T00:32:00Z", "2026-01-02T00:32:00+25:00", True])
def test_invalid_local_times(case, value):
    case[0]["knowledge_boundary"] = value
    with pytest.raises(ValueError): run(case)


def test_equivalent_local_times_normalize_without_reissuing_context(case):
    expected = run(case)
    case[0]["assessment_economic_time"] = "2026-01-02T01:32:00+01:00"
    case[0]["binding_evidence"]["assessment_economic_time"] = "2026-01-02T01:32:00+01:00"
    case[3]["knowledge_boundary"] = "2026-01-02T01:32:00+01:00"
    assert run(case) == expected


def test_same_account_id_in_another_source_namespace_is_not_the_same_account(case):
    p = case[0]["risk_policy"]["request"]
    def change_source(value):
        if type(value) is dict:
            for key, item in value.items():
                if key == "source_id" and item == "broker":
                    value[key] = "another-account-source"
                else:
                    change_source(item)
        elif type(value) is list:
            for item in value:
                change_source(item)
    change_source(p)
    p["account_rule_regime"]["assessment"] = regimes.run(regimes.refresh(p["account_rule_regime"]["assessment_input"]))
    pfixtures.refresh_account(p)
    issue(case)
    # Both native assessments reconstruct independently and retain the same
    # account ID. The composition still rejects their distinct account pairs.
    policies.validate_account_specific_risk_policy(case[0]["risk_policy"]["assessment"], p)
    with pytest.raises(ValueError): run(case)


def test_equivalent_active_native_scenarios_preserve_established_semantics(case):
    r = case[0]["risk_basis"]["request"]
    equivalent = deepcopy(r["scenario_evidence"][0])
    equivalent["declaration_id"] = "another-source-declaration"
    r["scenario_evidence"].append(equivalent)
    issue(case)
    assert case[0]["risk_basis"]["assessment"]["outcome"] == "ESTABLISHED"
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["feasible_domain"]["domain"]["last_index"] == "9"
