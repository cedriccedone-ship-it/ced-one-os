"""Slice #22 uses real owner bundles; policy semantics do not evaluate facts."""
from copy import deepcopy

import pytest

from ced_one.business_divisions.trading import causal_factual_condition_evaluation as conditions
from ced_one.business_divisions.trading import causal_trading_policy_prerequisite_assessment as owner
from tests.test_trading_vertical_slice_v21 import (
    real, empty_real, scalar, condition, conjunction, object_condition, observed,
)
from tests.test_trading_vertical_slice_v20 import (
    SYNTHESIS, at_boundary, bundle, real_matrix, reversed_maps, integration_fvg_scenario,
)


def policy(definition, **changes):
    value = dict(policy_definition_contract=owner.DEFINITION_CONTRACT,
        policy_definition_rule_version=owner.DEFINITION_RULE_VERSION, policy_id="p1", policy_version=1,
        instrument="XAUUSD", timeframe=definition["timeframe"], required_condition=deepcopy(definition))
    return {**value, **changes}


def request(real, definition):
    evaluation = conditions.CAUSAL_FACTUAL_CONDITION_EVALUATION.analyze({**real,"condition":definition}).to_dict()
    return {**real,"condition":definition,"condition_evaluation":evaluation,"policy_definition":policy(definition)}


def run(value):
    return owner.CAUSAL_TRADING_POLICY_PREREQUISITE_ASSESSMENT.analyze(value).to_dict()


@pytest.fixture(scope="module")
def sample(real):
    return request(real, conjunction([
        scalar(expected=observed(real,"structure_state"), identifier="a"),
        condition(family=conditions.CLAIM, identifier="b")]))


def test_roundtrip_full_schema_identity_and_detachment(sample):
    original = deepcopy(sample)
    result = run(sample)
    assert result == run(reversed_maps(sample))
    assert result == run(sample)
    assert sample == original
    assert set(result) == {"contract","rule_version","identity_scope","assessment_id","policy_definition",
        "evaluated_instrument","condition_evaluation","applicability","prerequisite_assessment","reason_codes","authority"}
    assert result["prerequisite_assessment"] == "PREREQUISITE_ESTABLISHED"
    assert result["condition_evaluation"] == sample["condition_evaluation"]
    assert result["condition_evaluation"] is not sample["condition_evaluation"]
    result["condition_evaluation"]["constituent_results"].clear()
    assert sample == original
    validated = conditions.validate_causal_factual_condition_evaluation(sample["condition_evaluation"],
        sample["synthesis"],sample["upstream_bundle"],sample["condition"])
    assert validated == sample["condition_evaluation"] and validated is not sample["condition_evaluation"]
    assert conditions.condition_identity(sample["condition"]) == validated["condition_identity"]


@pytest.mark.parametrize("change", ["outcome","constituent","evidence","observed","reason","identity","condition_identity",
    "synthesis","upstream","cutoff_missing","cutoff_changed","extra","metadata","version"])
def test_owner_rejects_tampering_even_on_instrument_mismatch(sample, change):
    value = deepcopy(sample)
    value["policy_definition"]["instrument"] = "EURUSD"
    evaluation = value["condition_evaluation"]
    if change == "outcome": evaluation["outcome"] = "UNKNOWN"
    elif change == "constituent": evaluation["constituent_results"][0]["outcome"] = "UNKNOWN"
    elif change == "evidence": evaluation["constituent_results"][0]["evidence"][0]["locator"]["claim_index"] = 99
    elif change == "observed": evaluation["constituent_results"][0]["evidence"][0]["observed_value"] = "tampered"
    elif change == "reason": evaluation["reason_codes"] = ["altered"]
    elif change == "identity": evaluation["evaluation_id"] = "other"
    elif change == "condition_identity": evaluation["condition_identity"] = "other"
    elif change == "synthesis": value["synthesis"]["symbol"] = "EURUSD"
    elif change == "upstream": value["upstream_bundle"]["configuration"]["schema_version"] = "other"
    elif change == "cutoff_missing": del evaluation["effective_causal_cutoff"]
    elif change == "cutoff_changed": evaluation["effective_causal_cutoff"] = None
    elif change == "extra": evaluation["extra"] = True
    elif change == "metadata": evaluation["metadata"]["execution_output"] = True
    else: evaluation["rule_version"] = "other"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field,bad", [
    ("policy_id",None),("policy_id",""),("policy_version",True),("policy_version",0),("policy_version",-1),
    ("policy_version",1.0),("instrument",""),("instrument","xauusd"),("instrument"," XAUUSD"),
    ("instrument","XAU USD"),("instrument","XAUUSD\n"),("instrument","123"),("instrument",12),
    ("timeframe","H2"),("timeframe",None),("policy_definition_contract","other"),
    ("policy_definition_rule_version","other"),("required_condition",{})])
def test_policy_invalid_types_and_values(field,bad):
    with pytest.raises(ValueError): owner.normalize_policy_definition(policy(scalar(), **{field:bad}))


@pytest.mark.parametrize("key", ["extra","required_condition_identity","complete_definition_fingerprint"])
def test_unknown_and_derived_input_keys_rejected(key):
    with pytest.raises(ValueError): owner.normalize_policy_definition({**policy(scalar()),key:"untrusted"})


def test_definition_keys_order_snapshot_and_material_fingerprints():
    original = policy(scalar())
    before = deepcopy(original)
    normalized = owner.normalize_policy_definition(original)
    assert normalized == owner.normalize_policy_definition(reversed_maps(original))
    assert original == before
    assert set(normalized) == set(original) | {"required_condition_identity","complete_definition_fingerprint"}
    variants = [policy(scalar(),policy_id=" p1 "),policy(scalar(),policy_version=2),policy(scalar(),instrument="EURUSD"),
        policy({**scalar(),"timeframe":"M1"}), policy(scalar(expected="bearish_structure")),policy(scalar(identifier="other"))]
    assert all(owner.normalize_policy_definition(v)["complete_definition_fingerprint"] != normalized["complete_definition_fingerprint"] for v in variants)
    normalized["required_condition"]["expected_value"] = "changed"
    assert original == before
    # Contract/rule changes are unsupported inputs, not alternative valid versions.
    for key in original:
        missing = deepcopy(original); del missing[key]
        with pytest.raises(ValueError): owner.normalize_policy_definition(missing)


@pytest.mark.parametrize("change", ["changed_scalar","shortened","substituted","reordered","policy_timeframe","evaluation_timeframe"])
def test_exact_condition_and_timeframe_binding(sample, real, change):
    value = deepcopy(sample)
    value["policy_definition"]["instrument"] = "EURUSD"
    required = value["policy_definition"]["required_condition"]
    if change == "changed_scalar": required["constituents"][0]["expected_value"] = "different"
    elif change == "shortened": required["constituents"].pop()
    elif change == "substituted": value["policy_definition"]["required_condition"] = scalar()
    elif change == "reordered": required["constituents"].reverse()
    elif change == "policy_timeframe": value["policy_definition"]["timeframe"] = "M1"
    else:
        definition = deepcopy(value["condition"])
        definition["timeframe"] = "M1"
        for child in definition["constituents"]: child["timeframe"] = "M1"
        later = request(real,definition)
        value.update(condition=later["condition"],condition_evaluation=later["condition_evaluation"])
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("outcome", ["SATISFIED","NOT_SATISFIED","UNKNOWN"])
def test_mapping_and_instrument_applicability(real,empty_real,outcome):
    if outcome == "UNKNOWN": value = request(empty_real,condition(family=conditions.CLAIM))
    else: value = request(real,scalar(expected=observed(real,"structure_state") if outcome == "SATISFIED" else "not_matching"))
    result = run(value)
    assert result["applicability"] == "APPLICABLE"
    assert result["prerequisite_assessment"] == {"SATISFIED":"PREREQUISITE_ESTABLISHED",
        "NOT_SATISFIED":"PREREQUISITE_NOT_ESTABLISHED","UNKNOWN":"PREREQUISITE_UNKNOWN"}[outcome]
    assert result["reason_codes"] == ["POLICY_SCOPE_MATCH"]
    value["policy_definition"]["instrument"] = "EURUSD"
    mismatch = run(value)
    assert mismatch["applicability"] == "NOT_APPLICABLE"
    assert mismatch["prerequisite_assessment"] is None
    assert mismatch["evaluated_instrument"] == "XAUUSD"
    assert mismatch["reason_codes"] == ["INSTRUMENT_SCOPE_MISMATCH"]
    assert result["assessment_id"] != mismatch["assessment_id"]
    assert mismatch["condition_evaluation"] == result["condition_evaluation"]


def test_unknown_constituent_preserved_under_false_root(empty_real):
    obj = object_condition(); obj["condition_id"] = "empty_objects"
    definition = conjunction([obj,condition(family=conditions.CLAIM,identifier="unresolved_structure")])
    value = request(empty_real,definition)
    result = run(value)
    assert result["prerequisite_assessment"] == "PREREQUISITE_NOT_ESTABLISHED"
    assert result["condition_evaluation"] == value["condition_evaluation"]
    assert result["condition_evaluation"]["constituent_results"][1]["outcome"] == "UNKNOWN"


def test_valid_degraded_null_cutoff_and_missing_field():
    upstream = bundle(real_matrix("NO_CLOSED"))
    real = dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(),upstream_bundle=upstream)
    value = request(real,condition(family=conditions.CLAIM))
    result = run(value)
    assert result["applicability"] == "APPLICABLE"
    assert result["prerequisite_assessment"] == "PREREQUISITE_UNKNOWN"
    assert result["condition_evaluation"]["effective_causal_cutoff"] is None
    del value["condition_evaluation"]["effective_causal_cutoff"]
    with pytest.raises(ValueError): run(value)


def test_historical_and_later_causal_bindings():
    candles = integration_fvg_scenario()
    requests = []
    for boundary in ("2026-08-17T03:00:00Z","2026-08-17T07:00:00Z"):
        upstream = at_boundary(candles,boundary)
        requests.append(request(dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(),upstream_bundle=upstream),object_condition()))
    early,later = map(run,requests)
    assert early["assessment_id"] != later["assessment_id"]
    assert early["condition_evaluation"]["effective_causal_cutoff"] != later["condition_evaluation"]["effective_causal_cutoff"]
    assert run(requests[0]) == early and run(requests[1]) == later
    mixed = {**requests[0],"synthesis":requests[1]["synthesis"]}
    with pytest.raises(ValueError): run(mixed)
    mixed = {**requests[0],"condition_evaluation":requests[1]["condition_evaluation"]}
    with pytest.raises(ValueError): run(mixed)


def test_no_detectors_execution_legacy_or_registry_changes(sample, real, monkeypatch):
    from tests.test_trading_vertical_slice_v21 import test_no_detectors_legacy_or_execution
    test_no_detectors_legacy_or_execution(real,monkeypatch)
    from ced_one.business_divisions.trading.division import TradingDivision
    from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS
    before = (list(TradingDivision().get_capability_names()),TradingDivisionResolver().get_capability_names(),list(ADAPTERS))
    result = run(sample)
    assert result["authority"] == {"trade_decision":False,"financial_risk":False,"execution":False}
    assert before == (list(TradingDivision().get_capability_names()),TradingDivisionResolver().get_capability_names(),list(ADAPTERS))
    assert result["condition_evaluation"] == sample["condition_evaluation"]
    assert "authority" not in result["condition_evaluation"]  # No upstream semantic rewriting.


def test_no_independent_normalization_identity_or_predicate_logic(sample, monkeypatch):
    calls = []
    normalize, identity = conditions.normalize_condition, conditions.condition_identity
    def tracked_normalize(value, **kwargs):
        calls.append("normalize")
        return normalize(value,**kwargs)
    def tracked_identity(value):
        calls.append("identity")
        return identity(value)
    monkeypatch.setattr(conditions,"normalize_condition",tracked_normalize)
    monkeypatch.setattr(conditions,"condition_identity",tracked_identity)
    policy_normalized = owner.normalize_policy_definition(sample["policy_definition"])
    assert "normalize" in calls and "identity" in calls
    assert policy_normalized["required_condition_identity"] == sample["condition_evaluation"]["condition_identity"]
    # Isolate #22 after the owner boundary: it must use the validated root outcome,
    # without calling the predicate evaluator or inspecting constituent truth.
    def forbidden(*args,**kwargs): raise AssertionError("Independent predicate execution")
    monkeypatch.setattr(conditions,"_evaluate",forbidden)
    monkeypatch.setattr(conditions,"validate_causal_factual_condition_evaluation",lambda *args: deepcopy(sample["condition_evaluation"]))
    assert run(sample)["prerequisite_assessment"] == "PREREQUISITE_ESTABLISHED"


def test_top_level_caller_symbol_is_rejected(sample):
    with pytest.raises(ValueError): run({**sample,"evaluated_instrument":"XAUUSD"})


def test_policy_revision_changes_assessment_identity_without_changing_facts(sample):
    original = run(sample)
    revised = deepcopy(sample)
    revised["policy_definition"]["policy_version"] = 2
    result = run(revised)
    assert result["condition_evaluation"] == original["condition_evaluation"]
    assert result["prerequisite_assessment"] == original["prerequisite_assessment"]
    assert result["assessment_id"] != original["assessment_id"]
    assert result["policy_definition"]["complete_definition_fingerprint"] != original["policy_definition"]["complete_definition_fingerprint"]
