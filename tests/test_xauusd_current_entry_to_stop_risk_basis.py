"""Current conditional loss expression with complete upstream reconstruction."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import localcontext
from fractions import Fraction

import pytest

from ced_one.business_divisions.trading import xauusd_current_entry_to_stop_risk_basis as owner
from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as candidates
from ced_one.business_divisions.trading import causal_financial_price_observation_snapshot as price_owner
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account_owner
from ced_one.business_divisions.trading import causal_instrument_specification_applicability_resolver as resolver
from tests.test_xauusd_technical_trade_candidate import formulation_input, validity_input, ts, set_breach
from tests.test_causal_instrument_specification_applicability_resolver_v2 import sample as financial_sample, refresh
from tests.test_xauusd_candidate_gross_reference_financial_measurement import shift
from tests.test_trading_vertical_slice_v24 import sample as account_sample


def moment(minutes, seconds=0, microseconds=0):
    return (datetime(2026, 1, 2, tzinfo=timezone.utc) + timedelta(
        minutes=minutes, seconds=seconds, microseconds=microseconds
    )).isoformat(timespec="microseconds").replace("+00:00", "Z")


def moved(value):
    if type(value) is dict:
        return {key: moved(item) for key, item in value.items()}
    if type(value) is list:
        return [moved(item) for item in value]
    if type(value) is str and value.startswith("2026-01-02T"):
        return (datetime.fromisoformat(value.replace("Z", "+00:00")) - timedelta(
            hours=2, minutes=30
        )).isoformat().replace("+00:00", "Z")
    return value


def financial(at=32, *, versions=None, payoff_change=None):
    value = moved(shift(financial_sample(versions=versions)))
    k = moment(at)
    value["requested_knowledge_boundary"] = k
    value["economic_timestamp"] = k
    lifecycle = value["lifecycle_evidence"]["snapshot_input"]
    lifecycle["requested_evaluation_timestamp"] = k
    lifecycle["evidence"]["target_namespace"]["instrument_id"] = "XAUUSD"
    lifecycle["evidence"]["timing"] = {"observed_at": k, "source_available_at": k}
    lifecycle["evidence"]["coverage"]["timing"] = {"observed_at": k, "source_available_at": k}
    lifecycle["evidence"]["coverage"]["source_information_cutoff"] = k
    for entry in value["specification_revisions"]:
        entry["snapshot_input"]["specification"]["position_namespace"]["instrument_id"] = "XAUUSD"
        if payoff_change is not None and "payoff" in entry["snapshot_input"]["specification"]:
            payoff_change(entry["snapshot_input"]["specification"]["payoff"])
    refresh(value)
    return value, resolver.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2.analyze(value).to_dict()


def prices(spec, at=32, *, long=True, age_microseconds=500_000):
    k = moment(at)
    occurrence = (datetime.fromisoformat(k.replace("Z", "+00:00")) - timedelta(
        microseconds=age_microseconds
    )).isoformat(timespec="microseconds").replace("+00:00", "Z")
    ns = {key: spec["specification"]["position_namespace"][key] for key in (
        "source_id", "source_contract", "source_contract_version", "environment", "instrument_id"
    )}
    body = spec["specification"]
    denomination = {"specification_source": deepcopy(body["source"]),
                    "reference_asset_id": body["economics"]["reference_asset_id"],
                    "reference_unit": body["economics"]["reference_unit"],
                    "price_currency": body["economics"]["price_currency"]}
    result = []
    for side, value in (("BID", "124" if long else "175"), ("ASK", "125" if long else "176")):
        payload = {"contract": price_owner.CONTRACT, "rule_version": price_owner.RULE_VERSION,
                   "requested_evaluation_timestamp": k,
                   "observation": {"source": {"source_id": "quote-supplier", "source_contract": "quote-report",
                                              "source_contract_version": "1", "source_snapshot_id": "event-1-" + side},
                                   "target_namespace": deepcopy(ns), "denomination": deepcopy(denomination),
                                   "timing": {"price_time": occurrence, "observed_at": k,
                                              "source_available_at": k},
                                   "price_type": side, "availability": "AVAILABLE", "price": value}}
        result.append({"snapshot_input": payload,
                       "snapshot": price_owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(payload).to_dict()})
    return result


def terms():
    return {"entry_mechanism": owner.MECHANISM, "account_scope": None,
            "price_domain_relationship": "DIRECT_UNTRANSFORMED", "quote_event_id": "quote-event-1",
            "maximum_age_microseconds": 1_000_000, "maximum_supported_quantity": "2",
            "stop_trigger_side": "BID", "stop_trigger_comparator": "LESS_THAN_OR_EQUAL",
            "price_tick": "0.1", "price_grid_origin": "0", "minimum_trigger_distance": "0.5",
            "adverse_entry_allowance": "0.2", "adverse_stop_allowance": "0.3",
            "continuation_assumption": "CURRENT_PAYOFF_AND_EXECUTION_TERMS_THROUGH_STOP",
            "cost_scope": "WHOLE_ENTRY_TO_TERMINAL_STOP",
            "cost_coverage": {"opening_commission": "INCLUDED", "closing_commission": "INCLUDED",
                              "other_charges": "NOT_APPLICABLE", "financing": "NOT_APPLICABLE"},
            "charges": [
                {"charge_id": "opening", "category": "opening_commission", "basis": "SOURCE_SCHEDULE",
                 "currency": "USD", "quantity_unit": " lot ", "fixed": "1", "per_unit": "2", "minimum": "3"},
                {"charge_id": "closing", "category": "closing_commission", "basis": "SOURCE_SCHEDULE",
                 "currency": "USD", "quantity_unit": " lot ", "fixed": "0.5", "per_unit": "1", "minimum": "2"},
            ]}


def source_row(term, value, subjects, observed, *, locator):
    return {"kind": "SOURCE_DECLARED_TERM",
            "source": {"source_id": "scenario-source", "source_contract": "scenario-declaration",
                       "source_contract_version": "1"},
            "observed_at": observed, "source_available_at": observed, "locator": locator,
            "content": {"term": term, "value": value, "subjects": subjects}}


def sample(direction="LONG", *, at=32, history=None, age_microseconds=500_000,
           versions=None, payoff_change=None):
    p, h = formulation_input(direction)
    if history is not None:
        history(h, direction)
    formulation = candidates.XAUUSD_TECHNICAL_TRADE_CANDIDATE.analyze(p).to_dict()
    validity_request = validity_input(p, h, at=at, formulated=formulation)
    validity = candidates.XAUUSD_TECHNICAL_TRADE_CANDIDATE.evaluate_validity(validity_request).to_dict()
    app_input, app = financial(at, versions=versions, payoff_change=payoff_change)
    spec = next((row["snapshot"] for row in app_input["specification_revisions"]
                 if row["snapshot"]["specification"]["source"] == app["selected_revision"]), None)
    price_pairs = prices(spec, at, long=direction == "LONG", age_microseconds=age_microseconds)
    t = terms()
    if direction == "SHORT":
        t["stop_trigger_side"] = "ASK"
        t["stop_trigger_comparator"] = "GREATER_THAN_OR_EQUAL"
    candidate_ref, spec_ref = owner._ref(formulation), owner._ref(spec)
    bid_ref, ask_ref = (owner._ref(row["snapshot"]) for row in price_pairs)
    static = {key: deepcopy(t[key]) for key in owner.SCENARIO_FIELDS if key != "quote_event_id"}
    source_static = owner._source_terms(owner._terms(t))
    adopted = moment(31, 1)
    static_row = source_row("STATIC_SOURCE_TERMS", source_static, [candidate_ref, spec_ref],
                            adopted, locator="static-terms-v1")
    spec_row = source_row("SPECIFICATION_ARTIFACT",
                          {"snapshot": spec, "snapshot_input": app_input["specification_revisions"][0]["snapshot_input"]},
                          [spec_ref], adopted, locator="payoff-revision-v1")
    policy = {"candidate_formulation_reference": candidate_ref, "specification_reference": spec_ref,
              "venue_id": "venue-1", "account_scope": None,
              "quote_source_binding": {"source_id": "quote-supplier", "source_contract": "quote-report",
                                       "source_contract_version": "1"},
              "terms": static, "source_term_evidence": [static_row, spec_row],
              "limitations": list(owner.LIMITATIONS)}
    authority = {"authority_id": "planning-authority-1", "authority_role": "governance",
                 "mandate_id": "planning-only", "mandate_revision": 1,
                 "purpose": "CONDITIONAL_PLANNING_ASSUMPTION_USE_ONLY"}
    record = {"approval_id": "approval-1", "approval_revision": 1, "policy_version": 1,
              "decision": "APPROVED", "decided_at": moment(31, 5), "observed_at": moment(31, 5),
              "source_available_at": moment(31, 5), "effective_from": moment(31, 5),
              "effective_until": None, "supersedes": None, "policy_definition": policy,
              "source": {"source_id": "governance-source", "source_contract": "planning-approval",
                         "source_contract_version": "1", "source_snapshot_id": "decision-1"},
              "authority": authority}
    inventory_source = {"source_id": "governance-source", "source_contract": "approval-inventory",
                        "source_contract_version": "1", "source_snapshot_id": "inventory-1"}
    inventory = {"contract": owner.PLANNING_CONTRACT, "rule_version": owner.PLANNING_RULE,
                 "source": inventory_source, "observed_at": moment(at), "source_available_at": moment(at),
                 "authority_id": authority["authority_id"], "authority_role": authority["authority_role"],
                 "mandate_id": authority["mandate_id"], "mandate_revision": authority["mandate_revision"],
                 "policy_id": "planning-policy-1",
                 "coverage": {"completeness": "COMPLETE", "economic_from": moment(30),
                              "economic_until": moment(40), "source_information_cutoff": moment(at)},
                 "records": [record]}
    quote_event = {"quote_event_id": t["quote_event_id"], "venue_id": "venue-1",
                   "bid_reference": bid_ref, "ask_reference": ask_ref}
    quote_row = source_row("COHERENT_BID_ASK_EVENT", quote_event, [bid_ref, ask_ref],
                           moment(at), locator="event-1")
    quote_row["source"] = deepcopy(policy["quote_source_binding"])
    scenario = {"contract": owner.SCENARIO_CONTRACT, "rule_version": owner.RULE_VERSION,
                "declaration_id": "scenario-1", "declaration_revision": 1,
                "source": {"source_id": "scenario-source", "source_contract": "scenario-declaration",
                           "source_contract_version": "1"},
                "observed_at": moment(at), "source_available_at": moment(at),
                "effective_from": moment(31), "effective_until": None,
                "subjects": {"candidate": candidate_ref, "validity": owner._ref(validity),
                             "applicability": owner._ref(app), "specification": spec_ref,
                             "bid": bid_ref, "ask": ask_ref, "account": None},
                "status": "DECLARED", "terms": t, "reason": None,
                "supporting_evidence": [quote_row]}
    request = {"contract": owner.CONTRACT, "rule_version": owner.RULE_VERSION,
               "assessment_economic_time": moment(at), "knowledge_boundary": moment(at),
               "candidate": {"formulation": formulation, "formulation_input": p},
               "validity": {"assessment": validity, "validity_input": validity_request},
               "applicability": {"assessment": app, "resolver_input": app_input},
               "price_observations": price_pairs, "scenario_evidence": [scenario],
               "planning_evidence": inventory, "account_state": None}
    trusted = {**authority, "policy_id": "planning-policy-1",
               "scope": {"candidate_formulation_reference": candidate_ref,
                         "financial_namespace": deepcopy(spec["specification"]["position_namespace"]),
                         "venue_id": "venue-1", "account_scope": None},
               "effective_from": moment(31), "effective_until": None,
               "available_at": moment(at), "inventory_source": inventory_source,
               "inventory_content_sha256": owner._digest(owner._planning_inventory(inventory, boundary=moment(at))),
               "knowledge_boundary": moment(at)}
    return request, trusted


def evaluate(request, trusted):
    return owner.evaluate_current_entry_to_stop_risk_basis(request, trusted_planning_context=trusted)


def repin(request, trusted):
    trusted["inventory_content_sha256"] = owner._digest(owner._planning_inventory(
        request["planning_evidence"], boundary=request["knowledge_boundary"]
    ))


def align_policy(request, trusted):
    declaration = request["scenario_evidence"][0]
    policy = request["planning_evidence"]["records"][-1]["policy_definition"]
    policy["terms"] = {key: deepcopy(declaration["terms"][key]) for key in owner.SCENARIO_FIELDS
                       if key != "quote_event_id"}
    source_static = owner._source_terms(owner._terms(declaration["terms"]))
    row = next(row for row in policy["source_term_evidence"]
               if row["content"]["term"] == "STATIC_SOURCE_TERMS")
    row["content"]["value"] = source_static
    repin(request, trusted)


def revise_price(request, side, *, value=None, occurrence=None, source=None):
    pair = next(pair for pair in request["price_observations"]
                if pair["snapshot"]["observation"]["price_type"] == side)
    observation = pair["snapshot_input"]["observation"]
    if value is not None:
        observation["price"] = value
    if occurrence is not None:
        observation["timing"]["price_time"] = occurrence
    if source is not None:
        observation["source"]["source_id"] = source
    pair["snapshot"] = price_owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(
        pair["snapshot_input"]
    ).to_dict()
    reference = owner._ref(pair["snapshot"])
    request["scenario_evidence"][0]["subjects"][side.lower()] = reference
    row = request["scenario_evidence"][0]["supporting_evidence"][0]
    row["content"]["value"][side.lower() + "_reference"] = reference
    row["content"]["subjects"][0 if side == "BID" else 1] = reference


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_exact_current_function_and_owner_reconstruction(direction):
    request, trusted = sample(direction)
    result = evaluate(request, trusted)
    assert result["outcome"] == "ESTABLISHED"
    assert result["scenario"]["price_distance"] == "18.5"
    assert result["scenario"]["order_entry_constraint"] == "NONE"
    assert result["scenario"]["original_stop"] == (107.0 if direction == "LONG" else 193.0)
    assert result["risk_function"]["price_loss_per_quantity_unit"] == "462.5"
    assert result["risk_function"]["maximum_supported_quantity"] == "2"
    assert owner.validate_current_entry_to_stop_risk_basis(result, request, trusted_planning_context=trusted) == result
    assert not any(result["authority"].values()) and result["execution"] is False
    for q, expected in [("0", "0"), ("0.1", "51.25"), ("1", "467.5"), ("2", "932.5")]:
        if q == "0":
            actual = Fraction(result["risk_function"]["zero_quantity_loss"])
        else:
            actual = Fraction(result["risk_function"]["price_loss_per_quantity_unit"]) * Fraction(q)
            for charge in result["risk_function"]["charges"]:
                actual += max(Fraction(charge["minimum"]), Fraction(charge["fixed"]) +
                              Fraction(charge["per_unit"]) * Fraction(q))
        assert actual == Fraction(expected)


def test_frozen_entry_is_not_current_entry_and_quote_changes_risk():
    request, trusted = sample()
    historical = request["candidate"]["formulation"]["candidate"]["entry_reference"]["value"]
    first = evaluate(request, trusted)
    revise_price(request, "ASK", value="126")
    second = evaluate(request, trusted)
    assert historical == 124.0
    assert first["scenario"]["entry_reference"] == "125"
    assert second["scenario"]["entry_reference"] == "126"
    assert second["risk_function"]["price_loss_per_quantity_unit"] == "487.5"
    assert request["candidate"]["formulation"]["candidate"]["entry_reference"]["value"] == historical


@pytest.mark.parametrize("change,expected", [
    (lambda h, d: set_breach(h, d, minute=31), "CANDIDATE_INVALIDATED"),
    (lambda h, d: h["M1"].__setitem__(slice(None), [row for row in h["M1"] if row["timestamp"] != ts(31)]),
     "CANDIDATE_VALIDITY_UNKNOWN"),
])
def test_owner_validity_statuses(change, expected):
    request, trusted = sample(history=change)
    result = evaluate(request, trusted)
    assert expected in result["reasons"]
    assert result["outcome"] == ("UNKNOWN" if expected.endswith("UNKNOWN") else "NOT_SUITABLE")
    assert result["risk_function"] is None


def test_expiry_and_exact_expiry_boundary():
    at_expiry, trusted = sample(at=33)
    assert at_expiry["validity"]["assessment"]["status"] == "VALID"
    assert evaluate(at_expiry, trusted)["outcome"] == "ESTABLISHED"
    expired, later_context = sample(at=34)
    result = evaluate(expired, later_context)
    assert result["outcome"] == "NOT_SUITABLE"
    assert "CANDIDATE_EXPIRED" in result["reasons"]


@pytest.mark.parametrize("age,expected", [(1_000_000, "ESTABLISHED"),
                                            (1_000_001, "UNKNOWN")])
def test_exact_quote_age_boundary(age, expected):
    request, trusted = sample(age_microseconds=age)
    result = evaluate(request, trusted)
    assert result["outcome"] == expected
    assert ("CURRENT_QUOTE_STALE" in result["reasons"]) == (expected == "UNKNOWN")


def test_missing_quote_or_coherence_is_unknown():
    request, trusted = sample()
    request["scenario_evidence"][0]["supporting_evidence"] = []
    result = evaluate(request, trusted)
    assert result["outcome"] == "UNKNOWN"
    assert "COHERENT_QUOTE_EVENT_NOT_ESTABLISHED" in result["reasons"]
    request, trusted = sample()
    request["price_observations"].pop()
    declaration = request["scenario_evidence"][0]
    declaration["subjects"]["ask"] = None
    declaration["supporting_evidence"] = []
    result = evaluate(request, trusted)
    assert "MISSING_BID_ASK_PAIR" in result["reasons"]


@pytest.mark.parametrize("side,value,reason", [
    ("BID", "107", "ORIGINAL_STOP_ALREADY_TRIGGERED"),
    ("BID", "0", "INADMISSIBLE_CURRENT_QUOTE_GEOMETRY"),
    ("BID", "126", "INADMISSIBLE_CURRENT_QUOTE_GEOMETRY"),
    ("ASK", "-1", "INADMISSIBLE_CURRENT_QUOTE_GEOMETRY"),
])
def test_current_geometry_is_decisive(side, value, reason):
    request, trusted = sample()
    revise_price(request, side, value=value)
    result = evaluate(request, trusted)
    assert result["outcome"] == "NOT_SUITABLE"
    assert reason in result["reasons"]


def test_quote_time_source_and_owner_proof():
    request, trusted = sample()
    revise_price(request, "ASK", occurrence=moment(31, 59))
    assert "BID_ASK_ECONOMIC_TIME_MISMATCH" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    revise_price(request, "ASK", source="another-provider")
    assert "BID_ASK_SUPPLIER_MISMATCH" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    request["scenario_evidence"][0]["supporting_evidence"][0]["content"]["value"]["ask_reference"] = (
        request["scenario_evidence"][0]["subjects"]["bid"]
    )
    with pytest.raises(ValueError):
        evaluate(request, trusted)


@pytest.mark.parametrize("field,value,reason", [
    ("price_tick", "0.3", "ORIGINAL_STOP_OFF_TICK_GRID"),
    ("minimum_trigger_distance", "18", "MINIMUM_TRIGGER_DISTANCE_NOT_MET"),
    ("stop_trigger_side", "ASK", "STOP_TRIGGER_INCOMPATIBLE"),
    ("entry_mechanism", "LIMIT_ENTRY", "UNSUPPORTED_ENTRY_MECHANISM"),
])
def test_stop_and_entry_mechanism(field, value, reason):
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"][field] = value
    align_policy(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == "NOT_SUITABLE"
    assert reason in result["reasons"]
    assert request["candidate"]["formulation"]["candidate"]["stop_reference"]["value"] == 107.0


def test_approved_zero_allowances_are_conditional():
    request, trusted = sample()
    t = request["scenario_evidence"][0]["terms"]
    t["adverse_entry_allowance"] = "0"
    t["adverse_stop_allowance"] = "0"
    align_policy(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == "ESTABLISHED"
    assert result["scenario"]["price_distance"] == "18"
    assert result["risk_function"]["price_loss_per_quantity_unit"] == "450"
    assert "FILL_AND_STOP_EXECUTION_NOT_GUARANTEED" in result["reconstruction_evidence"]["planning_evidence"]["records"][0]["policy_definition"]["limitations"]


def test_missing_trust_and_forged_approval():
    request, trusted = sample()
    positive = evaluate(request, trusted)
    without = evaluate(request, None)
    assert without["outcome"] == "UNKNOWN"
    assert without["risk_function"] is None
    assert "MISSING_TRUSTED_PLANNING_CONTEXT" in without["reasons"]
    with pytest.raises(ValueError):
        owner.validate_current_entry_to_stop_risk_basis(positive, request)
    request["planning_evidence"]["records"][0]["approval_id"] = "forged-approval"
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_wrong_issuer_digest_and_scope():
    request, trusted = sample()
    wrong = deepcopy(trusted)
    wrong["authority_id"] = "forged"
    with pytest.raises(ValueError):
        evaluate(request, wrong)
    wrong = deepcopy(trusted)
    wrong["inventory_content_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        evaluate(request, wrong)
    wrong = deepcopy(trusted)
    wrong["scope"]["venue_id"] = "different-venue"
    assert evaluate(request, wrong)["outcome"] == "NOT_SUITABLE"


def test_approved_quantity_domain_cannot_be_extended():
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"]["maximum_supported_quantity"] = "10"
    result = evaluate(request, trusted)
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["risk_function"] is None


@pytest.mark.parametrize("category,state,expected", [
    ("financing", "UNKNOWN", "UNKNOWN"),
    ("financing", "UNSUPPORTED", "NOT_SUITABLE"),
    ("other_charges", "UNKNOWN", "UNKNOWN"),
])
def test_cost_coverage(category, state, expected):
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"]["cost_coverage"][category] = state
    align_policy(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == expected
    assert result["risk_function"] is None


def test_approval_expiry_rejection_and_revocation():
    request, trusted = sample()
    record = request["planning_evidence"]["records"][0]
    record["effective_until"] = moment(31, 30)
    repin(request, trusted)
    assert "PLANNING_APPROVAL_EXPIRED" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    record = request["planning_evidence"]["records"][0]
    record["decision"] = "REJECTED"
    repin(request, trusted)
    assert "PLANNING_REJECTED" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    predecessor = request["planning_evidence"]["records"][0]
    successor = deepcopy(predecessor)
    successor.update(approval_id="revocation-1", approval_revision=2, decision="REVOKED",
                     decided_at=moment(31, 30), observed_at=moment(31, 30),
                     source_available_at=moment(31, 30), effective_from=moment(31, 30),
                     supersedes={"approval_id": predecessor["approval_id"],
                                 "approval_revision": predecessor["approval_revision"],
                                 "content_sha256": owner._digest(owner._record(predecessor, boundary=moment(32)))})
    successor["source"]["source_snapshot_id"] = "revocation-1"
    request["planning_evidence"]["records"].append(successor)
    repin(request, trusted)
    assert "PLANNING_REVOKED" in evaluate(request, trusted)["reasons"]
    successor["effective_from"] = moment(33)
    repin(request, trusted)
    assert evaluate(request, trusted)["outcome"] == "ESTABLISHED"


def test_missing_predecessor_branch_and_cycle_reject():
    request, trusted = sample()
    first = request["planning_evidence"]["records"][0]
    second = deepcopy(first)
    second.update(approval_id="second", approval_revision=2, decided_at=moment(31, 30),
                  observed_at=moment(31, 30), source_available_at=moment(31, 30),
                  effective_from=moment(31, 30),
                  supersedes={"approval_id": first["approval_id"], "approval_revision": 1,
                              "content_sha256": owner._digest(owner._record(first, boundary=moment(32)))})
    second["source"]["source_snapshot_id"] = "second"
    request["planning_evidence"]["records"].append(second)
    repin(request, trusted)
    assert evaluate(request, trusted)["outcome"] == "ESTABLISHED"
    missing = deepcopy(request)
    missing["planning_evidence"]["records"][1]["supersedes"]["approval_id"] = "missing"
    repin(missing, trusted := deepcopy(trusted))
    with pytest.raises(ValueError):
        evaluate(missing, trusted)
    branch = deepcopy(request)
    third = deepcopy(second)
    third["approval_id"] = "third"
    third["source"]["source_snapshot_id"] = "third"
    branch["planning_evidence"]["records"].append(third)
    repin(branch, trusted := deepcopy(trusted))
    with pytest.raises(ValueError):
        evaluate(branch, trusted)
    cycle = deepcopy(request)
    cycle["planning_evidence"]["records"][0]["supersedes"] = {
        "approval_id": "second", "approval_revision": 2, "content_sha256": owner._digest(
            owner._record(second, boundary=moment(32))
        )}
    repin(cycle, trusted := deepcopy(trusted))
    with pytest.raises(ValueError):
        evaluate(cycle, trusted)


def test_post_k_evidence_and_precedence():
    request, trusted = sample(history=lambda h, d: set_breach(h, d, minute=31))
    request["scenario_evidence"][0]["observed_at"] = moment(32, 1)
    with pytest.raises(ValueError):
        evaluate(request, trusted)
    request, trusted = sample(history=lambda h, d: set_breach(h, d, minute=31))
    request["scenario_evidence"][0]["supporting_evidence"] = []
    result = evaluate(request, trusted)
    assert result["outcome"] == "NOT_SUITABLE"
    assert "COHERENT_QUOTE_EVENT_NOT_ESTABLISHED" in result["reasons"]


def test_identity_permutation_and_detached_tampering():
    request, trusted = sample()
    baseline = evaluate(request, trusted)
    flipped = deepcopy(request)
    flipped["price_observations"].reverse()
    assert evaluate(flipped, trusted)["assessment_identity"] == baseline["assessment_identity"]
    changed = deepcopy(baseline)
    changed["authority"]["execution"] = True
    changed["assessment_identity"] = "current_entry_to_stop_risk_basis_" + owner._digest(
        {key: value for key, value in changed.items() if key != "assessment_identity"}
    )
    with pytest.raises(ValueError):
        owner.validate_current_entry_to_stop_risk_basis(changed, request, trusted_planning_context=trusted)


def test_selected_metadata_v1_is_decisive():
    request, trusted = sample(versions=set())
    result = evaluate(request, trusted)
    assert result["outcome"] == "NOT_SUITABLE"
    assert "SELECTED_METADATA_HAS_NO_PAYOFF" in result["reasons"]


def test_changed_current_payoff_and_missing_payoff():
    baseline, trusted = sample()
    first = evaluate(baseline, trusted)
    changed, changed_context = sample(payoff_change=lambda payoff: payoff.update(
        payoff_units_per_quantity_unit="30"
    ))
    second = evaluate(changed, changed_context)
    assert second["outcome"] == "ESTABLISHED"
    assert second["risk_function"]["price_loss_per_quantity_unit"] == "555"
    assert second["assessment_identity"] != first["assessment_identity"]
    old_policy = deepcopy(baseline["planning_evidence"]["records"][0]["policy_definition"])
    changed["planning_evidence"]["records"][0]["policy_definition"] = old_policy
    repin(changed, changed_context)
    mismatch = evaluate(changed, changed_context)
    assert mismatch["outcome"] == "NOT_SUITABLE"
    assert "APPROVED_SCENARIO_SCOPE_OR_TERMS_MISMATCH" in mismatch["reasons"]
    partial, partial_context = sample(payoff_change=lambda payoff: payoff.update(
        payoff_units_per_quantity_unit=None
    ))
    assert evaluate(partial, partial_context)["outcome"] == "UNKNOWN"
    unsupported, unsupported_context = sample(payoff_change=lambda payoff: payoff.update(
        model="inverse-payoff", payoff_units_per_quantity_unit=None, pnl_currency=None
    ))
    assert evaluate(unsupported, unsupported_context)["outcome"] == "NOT_SUITABLE"


def test_approved_replacement_changes_allowance_only_with_new_version():
    request, trusted = sample()
    first = request["planning_evidence"]["records"][0]
    second = deepcopy(first)
    second.update(approval_id="approval-2", approval_revision=2, policy_version=2,
                  decided_at=moment(31, 30), observed_at=moment(31, 30),
                  source_available_at=moment(31, 30), effective_from=moment(31, 30),
                  supersedes={"approval_id": first["approval_id"], "approval_revision": 1,
                              "content_sha256": owner._digest(owner._record(first, boundary=moment(32)))})
    second["source"]["source_snapshot_id"] = "decision-2"
    request["planning_evidence"]["records"].append(second)
    request["scenario_evidence"][0]["terms"]["adverse_entry_allowance"] = "0.4"
    align_policy(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == "ESTABLISHED"
    assert result["risk_function"]["price_loss_per_quantity_unit"] == "467.5"
    request["planning_evidence"]["records"][1]["policy_version"] = 1
    with pytest.raises(ValueError):
        repin(request, trusted)


def test_account_binding_is_conditional_and_complete():
    request, trusted = sample()
    account_input = moved(shift(account_sample()))
    account = account_owner.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(account_input).to_dict()
    request["account_state"] = {"snapshot": account, "snapshot_input": account_input}
    scope = {key: account["observation"]["account"][key] for key in
             ("account_id", "environment", "currency")}
    request["scenario_evidence"][0]["subjects"]["account"] = owner._ref(account)
    request["scenario_evidence"][0]["terms"]["account_scope"] = scope
    request["planning_evidence"]["records"][0]["policy_definition"]["account_scope"] = scope
    trusted["scope"]["account_scope"] = scope
    align_policy(request, trusted)
    assert evaluate(request, trusted)["outcome"] == "ESTABLISHED"
    request["account_state"]["snapshot"]["observation"]["account"]["currency"] = "EUR"
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_wrong_mandate_account_scope_and_price_namespace():
    request, trusted = sample()
    wrong = deepcopy(trusted)
    wrong["mandate_id"] = "not-the-pinned-mandate"
    with pytest.raises(ValueError):
        evaluate(request, wrong)
    wrong = deepcopy(trusted)
    wrong["scope"]["account_scope"] = {"environment": "DEMO", "account_id": "another",
                                         "currency": "USD"}
    assert evaluate(request, wrong)["outcome"] == "NOT_SUITABLE"
    request, trusted = sample()
    ask = request["price_observations"][1]
    ask["snapshot_input"]["observation"]["target_namespace"]["instrument_id"] = "different"
    revise_price(request, "ASK")
    assert "PRICE_SPECIFICATION_DIMENSION_MISMATCH" in evaluate(request, trusted)["reasons"]


def test_exact_tiny_and_large_decimal_terms_ignore_ambient_context():
    request, trusted = sample()
    t = request["scenario_evidence"][0]["terms"]
    t["adverse_entry_allowance"] = "0.0000000000000000000000001"
    t["maximum_supported_quantity"] = "1000000000000000000000000000000.0001"
    align_policy(request, trusted)
    with localcontext() as context:
        context.prec = 2
        result = evaluate(request, trusted)
    assert result["outcome"] == "ESTABLISHED"
    assert result["risk_function"]["price_loss_per_quantity_unit"] == "457.5000000000000000000000025"
    assert result["risk_function"]["maximum_supported_quantity"] == "1000000000000000000000000000000.0001"


def test_structural_owner_and_planning_availability_reject():
    request, trusted = sample()
    request["price_observations"][0]["snapshot"]["observation"]["price"] = "999"
    with pytest.raises(ValueError):
        evaluate(request, trusted)
    request, trusted = sample()
    request["planning_evidence"]["records"][0]["observed_at"] = moment(32, 1)
    with pytest.raises(ValueError):
        evaluate(request, trusted)
    request, trusted = sample()
    request["planning_evidence"]["records"][0]["policy_definition"]["source_term_evidence"][0]["observed_at"] = moment(32)
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_financing_whole_scenario_envelope_and_missing_charge():
    request, trusted = sample()
    terms = request["scenario_evidence"][0]["terms"]
    terms["cost_coverage"]["financing"] = "INCLUDED"
    align_policy(request, trusted)
    assert evaluate(request, trusted)["outcome"] == "UNKNOWN"
    terms["charges"].append({"charge_id": "financing-envelope", "category": "financing",
                             "basis": "SUPPORTED_SCENARIO_ENVELOPE", "currency": "USD",
                             "quantity_unit": " lot ", "fixed": "0", "per_unit": "0.1", "minimum": "0"})
    align_policy(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == "ESTABLISHED"
    assert {row["category"] for row in result["risk_function"]["charges"]} == {
        "opening_commission", "closing_commission", "financing"
    }
    assert Fraction(result["risk_function"]["price_loss_per_quantity_unit"]) + sum(
        max(Fraction(row["minimum"]), Fraction(row["fixed"]) + Fraction(row["per_unit"]))
        for row in result["risk_function"]["charges"]
    ) == Fraction("467.6")


def test_unsupported_charge_dimensions_and_negative_charge():
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"]["charges"][0]["currency"] = "EUR"
    align_policy(request, trusted)
    assert "COST_DIMENSION_MISMATCH" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"]["charges"][0]["fixed"] = "-1"
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_limited_planning_coverage_and_missing_static_source():
    request, trusted = sample()
    request["planning_evidence"]["coverage"]["completeness"] = "LIMITED"
    repin(request, trusted)
    assert evaluate(request, trusted)["outcome"] == "UNKNOWN"
    request, trusted = sample()
    request["planning_evidence"]["records"][0]["policy_definition"]["source_term_evidence"] = []
    repin(request, trusted)
    result = evaluate(request, trusted)
    assert result["outcome"] == "UNKNOWN"
    assert "SOURCE_DECLARED_STATIC_TERMS_NOT_ESTABLISHED" in result["reasons"]


def test_out_of_scope_allowance_and_static_source_conflict():
    request, trusted = sample()
    request["scenario_evidence"][0]["terms"]["adverse_stop_allowance"] = "0.4"
    assert "APPROVED_SCENARIO_SCOPE_OR_TERMS_MISMATCH" in evaluate(request, trusted)["reasons"]
    request, trusted = sample()
    row = next(row for row in request["planning_evidence"]["records"][0]["policy_definition"]["source_term_evidence"]
               if row["content"]["term"] == "STATIC_SOURCE_TERMS")
    row["content"]["value"]["minimum_trigger_distance"] = "5"
    repin(request, trusted)
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_owner_valid_post_k_price_and_conflicting_revision_reject():
    request, trusted = sample()
    pair = request["price_observations"][0]
    pair["snapshot_input"]["requested_evaluation_timestamp"] = moment(32, 1)
    pair["snapshot_input"]["observation"]["timing"]["observed_at"] = moment(32, 1)
    pair["snapshot_input"]["observation"]["timing"]["source_available_at"] = moment(32, 1)
    pair["snapshot"] = price_owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(
        pair["snapshot_input"]
    ).to_dict()
    with pytest.raises(ValueError):
        evaluate(request, trusted)
    request, trusted = sample()
    other = deepcopy(request["price_observations"][0])
    other["snapshot_input"]["observation"]["price"] = "123"
    other["snapshot"] = price_owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(
        other["snapshot_input"]
    ).to_dict()
    request["price_observations"].append(other)
    with pytest.raises(ValueError):
        evaluate(request, trusted)


def test_set_like_duplicate_evidence_keeps_identity():
    request, trusted = sample()
    first = evaluate(request, trusted)
    duplicate = deepcopy(request)
    duplicate["scenario_evidence"].append(deepcopy(duplicate["scenario_evidence"][0]))
    duplicate["planning_evidence"]["records"].append(deepcopy(duplicate["planning_evidence"]["records"][0]))
    assert evaluate(duplicate, trusted)["assessment_identity"] == first["assessment_identity"]


def test_nonestablished_assessment_cannot_be_relabelled_positive():
    request, trusted = sample()
    result = evaluate(request, None)
    result["outcome"] = "ESTABLISHED"
    result["risk_function"] = {"model": owner.RISK_MODEL}
    result["assessment_identity"] = "current_entry_to_stop_risk_basis_" + owner._digest(
        {key: value for key, value in result.items() if key != "assessment_identity"}
    )
    with pytest.raises(ValueError):
        owner.validate_current_entry_to_stop_risk_basis(result, request)
