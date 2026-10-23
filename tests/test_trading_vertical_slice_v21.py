"""Real-bundle integration and isolated truth-table tests for Slice #21."""
from copy import deepcopy

import pytest

from ced_one.business_divisions.trading import causal_factual_condition_evaluation as owner
from ced_one.business_divisions.trading.causal_market_state_synthesis import (
    CAUSAL_MARKET_STATE_SYNTHESIS as SYNTHESIS, validate_market_state_synthesis,
)
from tests.test_trading_vertical_slice_v20 import (
    at_boundary, bundle, integration_fvg_scenario, real_matrix, reversed_maps,
)


def condition(target="structure_state", family=owner.SCALAR, *, identifier="c1", **kwargs):
    value = dict(contract=owner.CONDITION_CONTRACT, condition_id=identifier,
                 timeframe="H1", predicate_type=family)
    if family != owner.ALL:
        value["target"] = target
    value.update(kwargs)
    return value


def scalar(target="structure_state", expected="bullish_structure", operator="EQ", **kwargs):
    return condition(target, operator=operator, expected_value=expected, **kwargs)


def conjunction(children):
    return condition(family=owner.ALL, constituents=children)


def object_condition(target="fair_value_gaps", filters=None):
    return condition(target, owner.OBJECT, filters=[] if filters is None else filters)


def filter_value(field, expected, operator="EQ"):
    return dict(field=field, operator=operator, expected_value=expected)


@pytest.fixture(scope="module")
def real():
    upstream = bundle(real_matrix())
    return dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(), upstream_bundle=upstream)


@pytest.fixture(scope="module")
def empty_real():
    candles = [{**c, "open":100., "high":101., "low":99., "close":100.} for c in integration_fvg_scenario()]
    upstream = at_boundary(candles, "2026-08-17T07:00:00Z")
    return dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(), upstream_bundle=upstream)


def run(real, definition):
    return owner.CAUSAL_FACTUAL_CONDITION_EVALUATION.analyze({**real, "condition": definition}).to_dict()


def observed(real, target):
    spec = owner.TARGETS[target]
    return next(row["value"] for row in real["synthesis"]["timeframes"]["H1"]["dimensions"][spec.dimension]
                if row["source_field"] == spec.source_field)


def test_real_determinism_identity_and_locators(real):
    actual = observed(real, "structure_state")
    definition = scalar(expected=actual)
    original = deepcopy(real)
    result = run(real, definition)
    assert result["outcome"] == "SATISFIED"
    assert run(reversed_maps(real), reversed_maps(definition)) == result
    assert run(real, definition) == result
    assert real == original
    assert run(real, scalar(expected=actual, operator="NE"))["evaluation_id"] != result["evaluation_id"]
    assert run(real, scalar(expected=actual, identifier="other"))["condition_identity"] != result["condition_identity"]
    for evidence in result["evidence"]:
        loc = evidence["locator"]
        row = real["synthesis"]["timeframes"][loc["timeframe"]]["dimensions"][loc["dimension"]][loc["claim_index"]]
        assert loc["synthesis_id"] == real["synthesis"]["synthesis_id"]
        assert row["source_field"] == loc["source_field"]
        assert row["value"] == evidence["observed_value"]
        assert row["support_state"] == evidence["support_state"]
        assert row["provenance"]["object_event_locator"] == loc["source_object_locator"]


@pytest.mark.parametrize("change", ["value", "support", "provenance", "cutoff", "configuration", "binding", "missing", "extra", "identity", "metadata", "coverage", "degradation", "upstream", "missing_singleton", "duplicate_singleton"])
def test_owner_rejects_complete_content_tampering(real, change):
    value = deepcopy(real)
    s = value["synthesis"]
    claim = s["timeframes"]["H1"]["dimensions"]["market_structure"][0]
    if change == "value": claim["value"] = "altered"
    elif change == "support": claim["support_state"] = "UNKNOWN"
    elif change == "provenance": claim["provenance"]["source_snapshot_id"] = "other"
    elif change == "cutoff": s["timeframes"]["H1"]["effective_causal_cutoff"] = "2020-01-01T00:00:00Z"
    elif change == "configuration": s["configuration"]["schema_version"] = "other"
    elif change == "binding": s["source_factual_context_id"] = "other"
    elif change == "missing": del s["ordering_groups"]
    elif change == "extra": s["extra"] = True
    elif change == "identity": s["synthesis_id"] = "other"
    elif change == "metadata": s["metadata"]["authority_scope"] = "execute"
    elif change == "coverage": claim["provenance"]["coverage"]["extra"] = True
    elif change == "degradation": claim["provenance"]["degradation"]["factual_availability"] = "INVALID"
    elif change == "missing_singleton": s["timeframes"]["H1"]["dimensions"]["market_structure"].pop(0)
    elif change == "duplicate_singleton": s["timeframes"]["H1"]["dimensions"]["market_structure"].append(deepcopy(claim))
    else: value["upstream_bundle"]["configuration"] = {"schema_version": "other"}
    with pytest.raises(ValueError): run(value, scalar())


def test_owner_accepts_legitimate_degraded_and_detaches():
    upstream = bundle(real_matrix("NO_CLOSED"))
    supplied = SYNTHESIS.analyze(upstream).to_dict()
    validated = validate_market_state_synthesis(supplied, upstream)
    assert validated == supplied and validated is not supplied
    result = run(dict(synthesis=supplied, upstream_bundle=upstream), condition(family=owner.CLAIM))
    assert result["outcome"] == "UNKNOWN"
    assert result["effective_causal_cutoff"] is None


def test_real_explicit_absence_and_unavailable_claim(empty_real):
    assert run(empty_real, object_condition())["outcome"] == "NOT_SATISFIED"
    assert run(empty_real, condition(family=owner.CLAIM))["outcome"] == "UNKNOWN"
    assert run(empty_real, object_condition("displacement_sequences"))["outcome"] == "UNKNOWN"


def test_real_mixed_objects_filtered_positive_and_all_witnesses():
    candles = integration_fvg_scenario() + [
        dict(timestamp="2026-08-17T06:00:00Z", open=104., high=106., low=103., close=105.),
        dict(timestamp="2026-08-17T07:00:00Z", open=105., high=108., low=104., close=107.)]
    for include_filled in (True, False):
        upstream = at_boundary(candles, "2026-08-17T09:00:00Z", {"fvg_imbalance_intelligence": {"include_fully_filled": include_filled}})
        real = dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(), upstream_bundle=upstream)
        result = run(real, object_condition(filters=[filter_value("current_status", "open")]))
        assert result["outcome"] == "SATISFIED"
        expected = [i for i, c in enumerate(real["synthesis"]["timeframes"]["H1"]["dimensions"]["fvg_imbalance_intelligence"])
                    if c["source_field"] == "fair_value_gaps" and c["value"]["current_status"] == "open"]
        assert [e["locator"]["claim_index"] for e in result["evidence"] if e.get("matches")] == expected
        nonmatch = run(real, object_condition(filters=[filter_value("current_status", "not_a_matching_state")]))
        assert nonmatch["outcome"] == "UNKNOWN"


# These unit fixtures exercise truth/cardinality defenses independently of owner
# reconstruction. They are never passed off as authentic upstream producer output.
def isolated(target, value=None, support="EVIDENCED", *, duplicate=False, missing=False):
    spec = owner.TARGETS[target]
    claim = dict(source_field=spec.source_field, temporal_scope="snapshot_current", value=value,
                 support_state=support, provenance={"object_event_locator": {"local_id": "test"}})
    rows = [] if missing else [claim, deepcopy(claim)] if duplicate else [claim]
    return dict(synthesis_id="unit_synthesis", requested_evaluation_timestamp="2026-08-18T12:00:00Z",
                timeframes={"H1": {"effective_causal_cutoff": "2026-08-18T11:00:00Z", "dimensions": {spec.dimension: rows}}})


def evaluate_unit(state, definition):
    return owner._evaluate(state, owner.normalize_condition(definition))


@pytest.mark.parametrize("operator,expected,outcome", [("EQ","x","SATISFIED"),("EQ","y","NOT_SATISFIED"),
    ("NE","x","NOT_SATISFIED"),("NE","y","SATISFIED"),("EQ","X","NOT_SATISFIED"),("EQ"," x","NOT_SATISFIED")])
def test_scalar_truth_and_exact_strings(operator, expected, outcome):
    assert evaluate_unit(isolated("structure_state", "x"), scalar(expected=expected, operator=operator))["outcome"] == outcome


def test_boolean_false_is_known_and_claim_exists():
    state = isolated("abnormal_range", False)
    assert evaluate_unit(state, scalar("abnormal_range", False))["outcome"] == "SATISFIED"
    assert evaluate_unit(state, condition("abnormal_range", owner.CLAIM))["outcome"] == "SATISFIED"


@pytest.mark.parametrize("operator", ["EQ", "NE"])
@pytest.mark.parametrize("support", ["ABSENT_IN_SCOPE", "UNKNOWN"])
def test_absent_parent_is_not_inequality(operator, support):
    state = isolated("current_range_order", support=support)
    assert evaluate_unit(state, scalar("current_range_order", "low_to_high", operator))["outcome"] == "UNKNOWN"
    expected = "NOT_SATISFIED" if support == "ABSENT_IN_SCOPE" else "UNKNOWN"
    assert evaluate_unit(state, condition("current_structural_range", owner.CLAIM))["outcome"] == expected


@pytest.mark.parametrize("target", list(owner.TARGETS))
def test_entire_allowlist_accessors(target):
    spec = owner.TARGETS[target]
    if owner.OBJECT in spec.families:
        value = {field: "owner_value" for field in spec.filter_fields}
        definition = object_condition(target)
    elif spec.projection:
        value = {spec.projection: "owner_value"}
        definition = scalar(target, "owner_value")
    elif spec.value_type is dict:
        value, definition = {}, condition(target, owner.CLAIM)
    else:
        value = False if spec.value_type is bool else "owner_value"
        definition = scalar(target, value)
    assert evaluate_unit(isolated(target, value), definition)["outcome"] == "SATISFIED"


@pytest.mark.parametrize("missing,duplicate", [(True,False),(False,True)])
def test_singular_cardinality_before_support(missing, duplicate):
    for support in ("EVIDENCED", "UNKNOWN"):
        state = isolated("structure_state", "x" if support == "EVIDENCED" else None, support, missing=missing, duplicate=duplicate)
        with pytest.raises(ValueError): evaluate_unit(state, scalar())


@pytest.mark.parametrize("target,value", [("abnormal_range",1),("structure_state",False),
    ("current_range_order",{}),("fair_value_gaps",{"side":"bullish","current_status":None})])
def test_evidenced_wrong_type_fails_closed(target, value):
    definition = object_condition(target) if target == "fair_value_gaps" else scalar(target, False if target == "abnormal_range" else "x")
    with pytest.raises(ValueError): evaluate_unit(isolated(target,value), definition)


def test_unknown_placeholder_empty_sequences_and_scoped_filters():
    assert evaluate_unit(isolated("fair_value_gaps",support="UNKNOWN"), object_condition())["outcome"] == "UNKNOWN"
    assert evaluate_unit(isolated("displacement_sequences", missing=True), object_condition("displacement_sequences"))["outcome"] == "UNKNOWN"
    definition = object_condition(filters=[filter_value("side","bullish"),filter_value("current_status","open","NE")])
    assert evaluate_unit(isolated("fair_value_gaps", support="ABSENT_IN_SCOPE"),definition)["outcome"] == "NOT_SATISFIED"
    assert evaluate_unit(isolated("fair_value_gaps", {"side":"bullish","current_status":"open"}),definition)["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("kind", ["int_bool","null","extra","target","path","operator","missing","filter_duplicate",
    "filter_extra","filter_type","filter_field","family","projection_claim","numeric","filters_missing","empty_all",
    "large_all","nested","duplicate_ids","cross_timeframe","version","forbidden_fields"])
def test_invalid_definitions(kind):
    value = scalar()
    if kind == "int_bool": value = scalar("abnormal_range", 1)
    elif kind == "null": value["expected_value"] = None
    elif kind == "extra": value["score"] = 1
    elif kind == "target": value["target"] = "adjacent_timeframe_availability"
    elif kind == "path": value["target"] = "value.provenance.foo"
    elif kind == "operator": value["operator"] = "GT"
    elif kind == "missing": del value["timeframe"]
    elif kind.startswith("filter"):
        value = object_condition(filters=[filter_value("side", "bullish")])
        if kind == "filter_duplicate": value["filters"] *= 2
        elif kind == "filter_extra": value["filters"][0]["extra"] = 1
        elif kind == "filter_type": value["filters"][0]["expected_value"] = 1
        elif kind == "filter_field": value["filters"][0]["field"] = "fvg_id"
        else: del value["filters"]
    elif kind == "family": value["predicate_type"] = "OR"
    elif kind == "projection_claim": value = condition("current_range_order", owner.CLAIM)
    elif kind == "numeric": value["expected_value"] = 1.0
    elif kind == "empty_all": value = conjunction([])
    elif kind == "large_all": value = conjunction([scalar(identifier=str(i)) for i in range(33)])
    elif kind == "nested": value = conjunction([conjunction([scalar()])])
    elif kind == "duplicate_ids": value = conjunction([scalar(),scalar()])
    elif kind == "cross_timeframe": value = conjunction([{**scalar(),"timeframe":"M1"}])
    elif kind == "version": value["contract"] = "legacy"
    else: value = {**condition(family=owner.CLAIM), "operator":"EQ"}
    with pytest.raises(ValueError): owner.normalize_condition(value)


@pytest.mark.parametrize("expected,unknown,outcome", [("x",False,"SATISFIED"),("y",False,"NOT_SATISFIED"),
    ("x",True,"UNKNOWN"),("y",True,"NOT_SATISFIED")])
def test_all_of_truth_preserves_order_and_unknown(expected, unknown, outcome):
    state = isolated("structure_state", "x")
    second = isolated("volatility_state", None if unknown else "low", "UNKNOWN" if unknown else "EVIDENCED")
    state["timeframes"]["H1"]["dimensions"].update(second["timeframes"]["H1"]["dimensions"])
    definition = conjunction([scalar(expected=expected,identifier="first"),scalar("volatility_state","low",identifier="second")])
    result = evaluate_unit(state, definition)
    assert result["outcome"] == outcome
    assert [c["condition_id"] for c in result["constituent_results"]] == ["first","second"]
    assert result["constituent_results"][1]["outcome"] == ("UNKNOWN" if unknown else "SATISFIED")


def test_historical_binding_and_later_validity():
    candles = integration_fvg_scenario()
    early = at_boundary(candles, "2026-08-17T03:00:00Z")
    later = at_boundary(candles, "2026-08-17T07:00:00Z")
    early_s, later_s = SYNTHESIS.analyze(early).to_dict(), SYNTHESIS.analyze(later).to_dict()
    definition = object_condition(filters=[filter_value("current_status","open")])
    before = run(dict(synthesis=early_s,upstream_bundle=early),definition)
    after = run(dict(synthesis=later_s,upstream_bundle=later),definition)
    assert before["outcome"] == "SATISFIED" and after["outcome"] == "UNKNOWN"
    assert before["evaluation_id"] != after["evaluation_id"]
    assert before["effective_causal_cutoff"] != after["effective_causal_cutoff"]
    with pytest.raises(ValueError): run(dict(synthesis=later_s,upstream_bundle=early),definition)
    assert run(dict(synthesis=early_s,upstream_bundle=early),definition) == before


def test_no_detectors_legacy_or_execution(real, monkeypatch):
    from tests.test_trading_vertical_slice_v20 import test_synthesis_never_invokes_detectors_or_execution
    test_synthesis_never_invokes_detectors_or_execution(real["upstream_bundle"], monkeypatch)
    from ced_one.business_divisions.trading import market_context, market_observation
    def forbidden(*args, **kwargs): raise AssertionError("Legacy semantics are forbidden")
    for module in (market_context, market_observation):
        for name, value in vars(module).items():
            if isinstance(value, type) and value.__module__ == module.__name__:
                for method in ("analyze", "observe", "observe_market_context"):
                    if hasattr(value, method): monkeypatch.setattr(value, method, forbidden)
    result = run(real, scalar(expected=observed(real,"structure_state")))
    assert result["outcome"] == "SATISFIED"
    assert result["metadata"] == {"observation_only":True,"authority_scope":"read_only",
        "strategy_output":False,"advisory_output":False,"execution_output":False}
    assert set(result) == {"evaluation_id","contract","rule_version","identity_scope","condition_id","condition",
        "condition_identity","timeframe","effective_causal_cutoff","requested_evaluation_timestamp","source_synthesis_id",
        "predicate_type","evidence","constituent_results","metadata","outcome","reason_codes"}


def test_upstream_bundle_is_opaque_to_evaluator(real, monkeypatch):
    opaque = object()
    def validate(supplied, upstream):
        assert upstream is opaque
        return deepcopy(real["synthesis"])
    monkeypatch.setattr(owner,"validate_market_state_synthesis",validate)
    assert run(dict(synthesis=real["synthesis"],upstream_bundle=opaque), condition(family=owner.CLAIM))["outcome"] == "SATISFIED"


def test_conjunction_public_boundary_and_list_identity(real):
    children = [scalar(expected=observed(real,"structure_state"),identifier="first"),
                condition("structure_state",owner.CLAIM,identifier="second")]
    result = run(real,conjunction(children))
    assert result["outcome"] == "SATISFIED"
    reversed_result = run(real,conjunction(list(reversed(children))))
    assert reversed_result["outcome"] == "SATISFIED"
    assert reversed_result["evaluation_id"] != result["evaluation_id"]
    assert [c["condition_id"] for c in reversed_result["constituent_results"]] == ["second","first"]


def test_filter_order_and_maximum_conjunction():
    state = isolated("fair_value_gaps", {"side":"bullish","current_status":"open"})
    filters = [filter_value("side","bullish"),filter_value("current_status","open")]
    first = evaluate_unit(state,object_condition(filters=filters))
    second = evaluate_unit(state,object_condition(filters=list(reversed(filters))))
    assert first["outcome"] == second["outcome"] == "SATISFIED"
    assert first["evaluation_id"] != second["evaluation_id"]
    assert second["condition"]["filters"] == list(reversed(filters))
    definition = conjunction([scalar(expected="x",identifier=str(i)) for i in range(32)])
    assert len(evaluate_unit(isolated("structure_state","x"),definition)["constituent_results"]) == 32


def test_retained_classification_failure_cannot_supply_condition_evidence(monkeypatch):
    from dataclasses import replace
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS
    contract = "trading.fvg_imbalance_intelligence.v1"
    def fail(*args): raise ValueError("injected classification failure")
    monkeypatch.setitem(ADAPTERS,contract,replace(ADAPTERS[contract],classify=fail))
    upstream = at_boundary(integration_fvg_scenario(),"2026-08-17T07:00:00Z")
    assert upstream["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]["authoritative_result"]["fair_value_gaps"]
    real = dict(synthesis=SYNTHESIS.analyze(upstream).to_dict(),upstream_bundle=upstream)
    result = run(real,object_condition())
    assert result["outcome"] == "UNKNOWN"
    assert all(e["observed_value"] is None for e in result["evidence"])
