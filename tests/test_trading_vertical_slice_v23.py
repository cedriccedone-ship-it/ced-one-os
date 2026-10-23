"""Real owner bundles exercise declaration-only formulation and trust boundaries."""
from copy import deepcopy

import pytest

from ced_one.business_divisions.trading import causal_factual_condition_evaluation as conditions
from ced_one.business_divisions.trading import causal_trading_policy_action_formulation as actions
from ced_one.business_divisions.trading import causal_trading_policy_prerequisite_assessment as owner
from tests.test_trading_vertical_slice_v22 import policy, request, run, sample
from tests.test_trading_vertical_slice_v21 import real, empty_real, scalar, condition, conjunction, observed, object_condition
from tests.test_trading_vertical_slice_v20 import SYNTHESIS, at_boundary, bundle, real_matrix, reversed_maps, integration_fvg_scenario


def declaration(prerequisite, direction="LONG"):
    return dict(action_policy_contract=actions.DEFINITION_CONTRACT,
        action_policy_rule_version=actions.DEFINITION_RULE_VERSION,
        action_policy_id=" a1 ", action_policy_version=1,
        prerequisite_definition=deepcopy(prerequisite),
        declared_action=dict(action_type="DIRECTIONAL_ENTRY_INTENT", direction=direction))


def inputs(value, direction="LONG"):
    return dict(action_policy_definition=declaration(value["policy_definition"], direction),
        prerequisite_assessment=run(value), assessment_input=deepcopy(value))


def formulate(value):
    return actions.CAUSAL_TRADING_POLICY_ACTION_FORMULATION.analyze(value).to_dict()


@pytest.fixture(scope="module")
def states(real, empty_real, sample):
    false = request(real, scalar(expected="not_matching"))
    unknown = request(empty_real, condition(family=conditions.CLAIM))
    mismatch = deepcopy(sample)
    mismatch["policy_definition"]["instrument"] = "EURUSD"
    return [inputs(v) for v in (sample, false, unknown, mismatch)]


@pytest.mark.parametrize("index,reason", list(enumerate([
    "ACTION_FORMULATED", "PREREQUISITE_NOT_ESTABLISHED", "PREREQUISITE_UNKNOWN", "POLICY_NOT_APPLICABLE"])))
def test_truth_identity_direction_and_schema(states, index, reason):
    value = states[index]
    before = deepcopy(value)
    result = formulate(value)
    assert result == formulate(reversed_maps(value)) == formulate(value)
    assert set(result) == {"contract", "rule_version", "identity_scope", "formulation_id",
        "action_policy_definition", "prerequisite_assessment", "formulation_status", "formulated_action", "reason_codes", "authority"}
    assert result["reason_codes"] == [reason]
    assert result["formulation_status"] == ("FORMULATED" if index == 0 else "NOT_FORMULATED")
    declared = value["action_policy_definition"]["declared_action"]
    assert result["formulated_action"] == (declared if index == 0 else None)
    assert result["action_policy_definition"]["declared_action"] == declared
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["prerequisite_assessment"] == value["prerequisite_assessment"]
    changed = deepcopy(value)
    changed["action_policy_definition"]["declared_action"]["direction"] = "SHORT"
    other = formulate(changed)
    assert other["prerequisite_assessment"] == result["prerequisite_assessment"]
    assert other["formulation_id"] != result["formulation_id"]
    assert other["action_policy_definition"]["complete_action_policy_fingerprint"] != result["action_policy_definition"]["complete_action_policy_fingerprint"]
    assert other["formulated_action"] == (dict(action_type="DIRECTIONAL_ENTRY_INTENT", direction="SHORT") if index == 0 else None)
    assert value == before


@pytest.mark.parametrize("field", ["contract", "rule_version", "identity_scope", "assessment_id", "policy_definition",
    "evaluated_instrument", "condition_evaluation", "applicability", "prerequisite_assessment", "reason_codes", "authority"])
@pytest.mark.parametrize("operation", ["remove", "change"])
def test_owner_complete_serialized_fields(states, field, operation):
    value = states[0]
    supplied = deepcopy(value["prerequisite_assessment"])
    if operation == "remove": del supplied[field]
    else: supplied[field] = "tampered"
    with pytest.raises(ValueError):
        owner.validate_causal_trading_policy_prerequisite_assessment(supplied, value["assessment_input"])


@pytest.mark.parametrize("change", ["extra", "bool", "number", "nan", "infinity", "nested", "nested_extra", "list_order"])
def test_owner_nested_serialized_tampering(states, change):
    value = states[0]
    supplied = deepcopy(value["prerequisite_assessment"])
    if change == "extra": supplied["extra"] = 1
    elif change == "bool": supplied["policy_definition"]["policy_version"] = True
    elif change == "number": supplied["authority"]["execution"] = 0
    elif change in {"nan", "infinity"}: supplied["policy_definition"]["policy_version"] = float("nan" if change == "nan" else "inf")
    elif change == "nested": supplied["condition_evaluation"]["constituent_results"][0]["outcome"] = "UNKNOWN"
    elif change == "nested_extra": supplied["condition_evaluation"]["metadata"]["extra"] = True
    else: supplied["condition_evaluation"]["constituent_results"].reverse()
    with pytest.raises(ValueError): owner.validate_causal_trading_policy_prerequisite_assessment(supplied, value["assessment_input"])


@pytest.mark.parametrize("bad", [None, [], {}, {"extra": 1}])
def test_owner_malformed_reconstruction(states, bad):
    with pytest.raises(ValueError): owner.validate_causal_trading_policy_prerequisite_assessment(states[0]["prerequisite_assessment"], bad)


@pytest.mark.parametrize("field,bad", [
    ("action_policy_contract", "other"), ("action_policy_rule_version", "other"),
    ("action_policy_id", ""), ("action_policy_id", None), ("action_policy_version", True),
    ("action_policy_version", 0), ("action_policy_version", -1), ("action_policy_version", 1.0),
    ("declared_action", None), ("prerequisite_definition", {})])
def test_definition_types(field, bad):
    value = declaration(policy(scalar()))
    value[field] = bad
    with pytest.raises(ValueError): actions.normalize_action_policy_definition(value)


@pytest.mark.parametrize("direction", ["BUY", "SELL", "HOLD", "FLAT", "EXIT", "CLOSE", "REDUCE", "INCREASE", "REVERSE", "long", " LONG", None, True, []])
def test_invalid_direction(direction):
    with pytest.raises(ValueError): actions.normalize_action_policy_definition(declaration(policy(scalar()), direction))


def test_exact_keys_and_normalized_shape():
    value = declaration(policy(scalar()))
    before = deepcopy(value)
    normalized = actions.normalize_action_policy_definition(value)
    assert set(normalized) == set(value) | {"complete_action_policy_fingerprint"}
    assert len(normalized["prerequisite_definition"]) == 9
    assert normalized["action_policy_id"] == " a1 "
    assert normalized == actions.normalize_action_policy_definition(reversed_maps(value))
    assert value == before
    for path in ((), ("declared_action",), ("prerequisite_definition",)):
        target = value
        for key in path: target = target[key]
        for key in list(target) + ["extra"]:
            changed = deepcopy(value)
            current = changed
            for part in path: current = current[part]
            if key == "extra": current[key] = 1
            else: del current[key]
            with pytest.raises(ValueError): actions.normalize_action_policy_definition(changed)
    for key in ("complete_action_policy_fingerprint", "declared_action_identity", "prerequisite_definition_fingerprint"):
        with pytest.raises(ValueError): actions.normalize_action_policy_definition({**value, key: "forged"})
    for key in ("required_condition_identity", "complete_definition_fingerprint"):
        changed = deepcopy(value); changed["prerequisite_definition"][key] = "forged"
        with pytest.raises(ValueError): actions.normalize_action_policy_definition(changed)
    changed = deepcopy(value); changed["declared_action"]["action_type"] = "BUY"
    with pytest.raises(ValueError): actions.normalize_action_policy_definition(changed)


@pytest.mark.parametrize("index", [1, 2, 3])
@pytest.mark.parametrize("change", ["malformed", "tampered", "binding"])
def test_blocked_validation_precedes_branch(states, index, change):
    value = deepcopy(states[index])
    if change == "malformed": del value["action_policy_definition"]["declared_action"]
    elif change == "tampered": value["prerequisite_assessment"]["authority"]["execution"] = True
    else: value["action_policy_definition"]["prerequisite_definition"]["policy_id"] = "different"
    with pytest.raises(ValueError): formulate(value)


@pytest.mark.parametrize("change", ["condition", "instrument", "timeframe", "order"])
def test_exact_binding_same_identifiers(states, change):
    value = deepcopy(states[0])
    definition = value["action_policy_definition"]["prerequisite_definition"]
    if change == "condition": definition["required_condition"]["constituents"][0]["expected_value"] = "changed"
    elif change == "instrument": definition["instrument"] = "EURUSD"
    elif change == "timeframe": definition["timeframe"] = "M1"
    else: definition["required_condition"]["constituents"].reverse()
    with pytest.raises(ValueError): formulate(value)


def test_fingerprint_alone_insufficient(states, monkeypatch):
    value = deepcopy(states[0])
    normalized = actions.normalize_action_policy_definition(value["action_policy_definition"])
    normalized["prerequisite_definition"]["required_condition"]["constituents"][0]["expected_value"] = "changed"
    monkeypatch.setattr(actions, "normalize_action_policy_definition", lambda _: normalized)
    with pytest.raises(ValueError): formulate(value)


def test_isolation_and_owner_delegation(states, monkeypatch):
    value = deepcopy(states[0]); before = deepcopy(value)
    validated = owner.validate_causal_trading_policy_prerequisite_assessment(value["prerequisite_assessment"], value["assessment_input"])
    validated["policy_definition"]["policy_id"] = "changed"
    assert value == before
    result = actions.CAUSAL_TRADING_POLICY_ACTION_FORMULATION.analyze(value)
    first, second = result.to_dict(), result.to_dict()
    first["formulated_action"]["direction"] = "SHORT"
    assert first["action_policy_definition"]["declared_action"]["direction"] == "LONG"
    first["prerequisite_assessment"]["condition_evaluation"]["constituent_results"].clear()
    assert second == result.to_dict() and value == before
    normalized = actions.normalize_action_policy_definition(value["action_policy_definition"])
    normalized["prerequisite_definition"]["required_condition"]["constituents"].clear()
    assert value == before
    # The semantic layer must not inspect reconstruction data after the owner boundary.
    calls = []
    def validate(supplied, reconstruction):
        calls.append(reconstruction)
        return deepcopy(before["prerequisite_assessment"])
    monkeypatch.setattr(owner, "validate_causal_trading_policy_prerequisite_assessment", validate)
    value["assessment_input"] = object()
    assert formulate(value)["formulation_status"] == "FORMULATED"
    assert calls == [value["assessment_input"]]


def test_historical_later_and_null_cutoff():
    candles = integration_fvg_scenario(); values = []
    for boundary in ("2026-08-17T03:00:00Z", "2026-08-17T07:00:00Z"):
        upstream = at_boundary(candles, boundary)
        values.append(inputs(request(dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(), upstream_bundle=upstream), object_condition())))
    early, later = map(formulate, values)
    assert early["formulation_id"] != later["formulation_id"]
    assert early == formulate(values[0]) and later == formulate(values[1])
    mixed = deepcopy(values[0]); mixed["assessment_input"] = values[1]["assessment_input"]
    with pytest.raises(ValueError): formulate(mixed)
    upstream = bundle(real_matrix("NO_CLOSED"))
    value = inputs(request(dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(), upstream_bundle=upstream), condition(family=conditions.CLAIM)))
    result = formulate(value)
    assert result["formulation_status"] == "NOT_FORMULATED"
    assert result["prerequisite_assessment"]["condition_evaluation"]["effective_causal_cutoff"] is None
    del value["assessment_input"]["condition_evaluation"]["effective_causal_cutoff"]
    with pytest.raises(ValueError): formulate(value)


def test_no_detectors_legacy_runtime_or_routes(states, real, monkeypatch):
    from tests.test_trading_vertical_slice_v21 import test_no_detectors_legacy_or_execution
    from ced_one.business_divisions.trading.division import TradingDivision
    from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
    test_no_detectors_legacy_or_execution(real, monkeypatch)
    before = (list(TradingDivision().get_capability_names()), TradingDivisionResolver().get_capability_names())
    assert formulate(states[0])["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert before == (list(TradingDivision().get_capability_names()), TradingDivisionResolver().get_capability_names())


def test_exact_analyzer_inputs(states):
    for key in list(states[0]) + ["extra"]:
        value = deepcopy(states[0])
        if key == "extra": value[key] = True
        else: del value[key]
        with pytest.raises(ValueError): formulate(value)
