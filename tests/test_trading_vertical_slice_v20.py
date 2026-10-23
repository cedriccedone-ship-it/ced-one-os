"""Slice #20 integration contracts use real bound producers and owner outputs."""
from copy import deepcopy
from dataclasses import replace
import pytest

from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS, CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE
from ced_one.business_divisions.trading.causal_multi_timeframe_context import CAUSAL_MULTI_TIMEFRAME_CONTEXT
from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT, CAPABILITY_ORDER, TIMEFRAME_ORDER
from ced_one.business_divisions.trading.factual_market_context_composition import FactualMarketContextCompositionAnalyzer, validate_factual_composition
from ced_one.business_divisions.trading.causal_factual_event_chronology import CAUSAL_FACTUAL_EVENT_CHRONOLOGY, validate_factual_chronology
from ced_one.business_divisions.trading.causal_market_state_synthesis import (
    CAUSAL_MARKET_STATE_SYNTHESIS as SYNTHESIS, CONFIGURATION_VERSION, DIMENSIONS, SUPPORT_STATES,
)
from tests.test_trading_vertical_slice_v16 import real_matrix
from tests.test_trading_vertical_slice_v19 import integration_fvg_scenario
from tests.test_hardening_causality import liquidity_payload


def bundle(matrix):
    context = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(matrix).to_dict()
    composition = FactualMarketContextCompositionAnalyzer().analyze({"factual_context": context}).to_dict()
    chronology = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context,
        factual_envelopes=matrix["factual_envelopes"], composition=composition)).to_dict()
    return dict(factual_context=context, factual_envelopes=matrix["factual_envelopes"],
                composition=composition, chronology=chronology, configuration={})


def at_boundary(candles, requested, configs=None):
    # Source intake excludes candles that have not opened at the requested boundary.
    # Source #13 alone then decides which supplied candles have completed.
    from ced_one.business_divisions.trading.validation import parse_timestamp
    eligible = [c for c in candles if parse_timestamp(c["timestamp"]) <= parse_timestamp(requested)]
    sources, envelopes = {}, {}
    for tf in TIMEFRAME_ORDER:
        source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe=tf,
            requested_evaluation_timestamp=requested, candle_history=eligible))
        sources[tf] = source
        envelopes[tf] = {}
        for name in CAPABILITY_ORDER:
            adapter = ADAPTERS[f"trading.{name}.v1"]
            envelopes[tf][name] = CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(dict(symbol="XAUUSD", timeframe=tf,
                requested_evaluation_timestamp=requested, causal_source=source, capability=dict(name=name,
                    contract=adapter.contract, rule_version=adapter.rule_version, configuration=(configs or {}).get(name, {})))).to_dict()
    source_context = CAUSAL_MULTI_TIMEFRAME_CONTEXT.analyze(dict(symbol="XAUUSD", requested_evaluation_timestamp=requested,
                                                               timeframe_sources=sources))
    return bundle(dict(symbol="XAUUSD", requested_evaluation_timestamp=requested, source_context=source_context,
                       factual_envelopes=envelopes))


@pytest.fixture(scope="module")
def base():
    return bundle(real_matrix())


def claims(result, dimension, tf="H1"):
    return result["timeframes"][tf]["dimensions"][dimension]


def reversed_maps(value):
    if isinstance(value, dict): return {k: reversed_maps(v) for k,v in reversed(list(value.items()))}
    if isinstance(value, list): return [reversed_maps(v) for v in value]
    return value


def test_determinism_normalization_order_and_input_immutability(base):
    original = deepcopy(base)
    first = SYNTHESIS.analyze(base).to_dict()
    assert first == SYNTHESIS.analyze(base).to_dict()
    assert first == SYNTHESIS.analyze(reversed_maps(base)).to_dict()
    explicit = deepcopy(base); explicit["configuration"] = {"schema_version": CONFIGURATION_VERSION}
    assert first == SYNTHESIS.analyze(explicit).to_dict()
    assert base == original
    assert tuple(first["timeframes"]) == TIMEFRAME_ORDER
    for tf, row in first["timeframes"].items():
        assert tuple(row["dimensions"]) == DIMENSIONS
        assert row["effective_causal_cutoff"] == base["factual_context"]["timeframes"][tf]["effective_causal_cutoff"]
        for rows in row["dimensions"].values():
            assert all(c["support_state"] in SUPPORT_STATES for c in rows)
    assert all(g["within_group_ordering"] == "ORDER_UNPROVEN" for g in first["ordering_groups"])


@pytest.mark.parametrize("kind", ["producer", "envelope_id", "context", "cutoff", "future", "composition", "composition_diagnostic",
    "chronology", "chronology_edge", "coverage", "configuration", "effective_configuration", "matrix", "detached"])
def test_tampering_fails_closed(base, kind):
    value = deepcopy(base)
    env = value["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]
    if kind == "producer": env["authoritative_result"]["evidence"]["reason"] = "tampered"
    elif kind == "envelope_id": env["factual_envelope_id"] = "detached"
    elif kind == "context": value["factual_context"]["factual_context_id"] = "detached"
    elif kind == "cutoff": env["effective_causal_cutoff"] = "2026-08-19T00:00:00Z"
    elif kind == "future": value["factual_context"]["requested_evaluation_timestamp"] = "2020-01-01T00:00:00Z"
    elif kind == "composition": value["composition"]["adjacent_relationships"][0]["relationship_type"] = "ABSENT_ON_BOTH"
    elif kind == "composition_diagnostic": value["composition"]["diagnostics"]["required_timeframe_count"] = 8
    elif kind == "chronology": value["chronology"]["events"][0]["causal_availability_timestamp"] = "2026-08-19T00:00:00Z"
    elif kind == "chronology_edge": value["chronology"]["chronology_edges"][0]["ordering"] = "AFTER"
    elif kind == "coverage": value["chronology"]["timeframes"]["H1"]["coverage"]["liquidity_events"]["coverage_scope"]["source_truncated_event_count"] = 100
    elif kind == "configuration": value["configuration"]["recency_window"] = 10
    elif kind == "effective_configuration": env["capability"]["configuration"]["minimum_gap_size"] = 50
    elif kind == "matrix": del value["factual_envelopes"]["M1"]
    else: value["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"] = env["authoritative_result"]
    with pytest.raises(ValueError): SYNTHESIS.analyze(value)


@pytest.mark.parametrize("field", ["candle_history", "strategy_profile", "market_state", "evaluation_time", "external_data"])
def test_extra_inputs_rejected(base, field):
    value = {**base, field: {}}
    with pytest.raises(ValueError): SYNTHESIS.analyze(value)


@pytest.mark.parametrize("mode", ["NO_CLOSED", "INVALID", "NOT_EVALUATED", "UNKNOWN"])
def test_valid_degraded_bundle_preserves_unknown(mode):
    value = bundle(real_matrix(mode))
    result = SYNTHESIS.analyze(value).to_dict()
    assert result["upstream_context_state"] == value["factual_context"]["context_state"]
    assert all(c["support_state"] == "UNKNOWN" for frame in result["timeframes"].values()
               for rows in frame["dimensions"].values() for c in rows)


def test_classification_failed_retained_payload_not_promoted(monkeypatch):
    contract = "trading.fvg_imbalance_intelligence.v1"
    def fail(*args): raise ValueError("injected classification failure")
    monkeypatch.setitem(ADAPTERS, contract, replace(ADAPTERS[contract], classify=fail))
    value = at_boundary(integration_fvg_scenario(), "2026-08-17T07:00:00Z")
    env = value["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]
    assert env["authoritative_result"]["fair_value_gaps"] and env["authoritative_result_id"]
    result = SYNTHESIS.analyze(value).to_dict()
    assert all(c["support_state"] == "UNKNOWN" for c in claims(result, "fvg_imbalance_intelligence"))
    assert all(c["value"] is None for c in claims(result, "fvg_imbalance_intelligence"))
    changed = at_boundary(integration_fvg_scenario(), "2026-08-17T07:00:00Z",
                          {"fvg_imbalance_intelligence": {"minimum_gap_size": 100}})
    assert result["synthesis_id"] != SYNTHESIS.analyze(changed).synthesis_id


def test_scoped_absence_and_filtered_unknown():
    candles = integration_fvg_scenario()
    filtered = at_boundary(candles, "2026-08-17T07:00:00Z", {"fvg_imbalance_intelligence": {"include_fully_filled": False}})
    rows = claims(SYNTHESIS.analyze(filtered).to_dict(), "fvg_imbalance_intelligence")
    assert all(c["support_state"] == "UNKNOWN" for c in rows)
    flat = [{**c, "open":100., "high":101., "low":99., "close":100.} for c in candles]
    empty = at_boundary(flat, "2026-08-17T07:00:00Z")
    rows = claims(SYNTHESIS.analyze(empty).to_dict(), "fvg_imbalance_intelligence")
    assert all(c["support_state"] == "ABSENT_IN_SCOPE" for c in rows)
    # Unresolved structure cannot borrow FVG's complete chronology coverage.
    assert all(c["support_state"] == "UNKNOWN" for c in claims(SYNTHESIS.analyze(empty).to_dict(), "market_structure"))


def test_mixed_object_states_and_filtered_positive_survive():
    candles = integration_fvg_scenario() + [
        dict(timestamp="2026-08-17T06:00:00Z", open=104., high=106., low=103., close=105.),
        dict(timestamp="2026-08-17T07:00:00Z", open=105., high=108., low=104., close=107.)]
    for include_filled in (True, False):
        value = at_boundary(candles, "2026-08-17T09:00:00Z", {"fvg_imbalance_intelligence": {"include_fully_filled": include_filled}})
        result = SYNTHESIS.analyze(value).to_dict()
        objects = [c for c in claims(result,"fvg_imbalance_intelligence") if c["source_field"] == "fair_value_gaps"]
        assert all(c["support_state"] == "EVIDENCED" for c in objects)
        statuses = {c["value"]["current_status"] for c in objects}
        assert "open" in statuses
        assert ("fully_filled" in statuses) == include_filled
        assert all(c["provenance"]["source_cutoff"] == "2026-08-17T08:00:00Z" for c in objects)


def test_truncation_preserves_positive_and_does_not_prove_absence():
    value = at_boundary(liquidity_payload([105,110,104,110.2,104,110.3,110.4,104])["candle_history"],
        "2026-08-16T09:00:00Z", {"liquidity_events": {"maximum_events": 1}})
    result = SYNTHESIS.analyze(value).to_dict()
    rows = [c for c in claims(result,"liquidity") if c["temporal_scope"].startswith("historical")]
    assert any(c["support_state"] == "EVIDENCED" for c in rows)
    assert all(c["support_state"] != "ABSENT_IN_SCOPE" for c in rows)
    for c in rows:
        assert c["provenance"]["coverage"]["source_truncated_count"] > 0
        if c["support_state"] == "EVIDENCED":
            assert c["value"]["descriptor"]["causal_boundary_id"]


@pytest.mark.parametrize("family", ["fvg", "liquidity", "range"])
def test_future_extensions_do_not_rewrite_historical_bundle(family):
    if family == "fvg":
        candles = integration_fvg_scenario(); boundary = "2026-08-17T03:00:00Z"; cut = 4
        dimension = "fvg_imbalance_intelligence"
    elif family == "liquidity":
        candles = liquidity_payload([105,110,104,110.2,104,110.3,110.4,104])["candle_history"]
        boundary = "2026-08-16T06:00:00Z"; cut = 7
        dimension = "liquidity"
    else:
        from tests.test_trading_vertical_slice_v11 import candle
        candles = [candle(i, high=high, low=low) for i, (high, low) in enumerate([
            (105,100), (110,99), (104,95), (108,98), (112,100), (107,97),
            (115,101), (109,99), (118,102), (112,100), (120,103)])]
        boundary = "2026-08-16T07:00:00Z"; cut = 8
        dimension = "structural_dealing_range_intelligence"
    prefix = at_boundary(candles[:cut], boundary)
    extended = at_boundary(candles, boundary)
    before = SYNTHESIS.analyze(prefix).to_dict()
    assert before == SYNTHESIS.analyze(extended).to_dict()
    later = at_boundary(candles, "2026-08-18T12:00:00Z")
    after = SYNTHESIS.analyze(later).to_dict()
    earlier_objects = [c["value"] for c in claims(before, dimension) if c["temporal_scope"] == "snapshot_current"]
    later_objects = [c["value"] for c in claims(after, dimension) if c["temporal_scope"] == "snapshot_current"]
    assert earlier_objects[0] is not None and later_objects[0] is not None
    assert earlier_objects != later_objects
    if family == "fvg":
        assert earlier_objects[0]["current_status"] == "open"
        assert later_objects[0]["current_status"] == "fully_filled"
    elif family == "liquidity":
        assert earlier_objects[0]["causal_boundary_id"] != later_objects[0]["causal_boundary_id"]
    else:
        assert earlier_objects[0]["range_id"] != later_objects[0]["range_id"]
    # A later-boundary chronology is not usable as an earlier state store.
    invalid = deepcopy(prefix); invalid["chronology"] = later["chronology"]
    with pytest.raises(ValueError): SYNTHESIS.analyze(invalid)


def test_owner_validators_check_all_serialized_content(base):
    assert validate_factual_composition(base["composition"], base["factual_context"]) == base["composition"]
    assert validate_factual_chronology(base["chronology"], base["factual_context"], base["factual_envelopes"], base["composition"]) == base["chronology"]
    for owner in ("composition", "chronology"):
        altered = deepcopy(base[owner]); altered["metadata"]["authority_scope"] = "execute"
        with pytest.raises(ValueError):
            if owner == "composition": validate_factual_composition(altered,base["factual_context"])
            else: validate_factual_chronology(altered,base["factual_context"],base["factual_envelopes"],base["composition"])
    unlinked = deepcopy(base)
    unlinked["chronology"] = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=base["factual_context"], factual_envelopes=base["factual_envelopes"])).to_dict()
    assert SYNTHESIS.analyze(unlinked)


def test_synthesis_never_invokes_detectors_or_execution(base, monkeypatch):
    from ced_one.business_divisions.trading import market_structure, candle_intelligence, volatility_range, liquidity_intelligence, fvg_imbalance_intelligence, displacement_intelligence, liquidity_events, order_block_intelligence, structural_dealing_range_intelligence, premium_discount_intelligence
    owners = [market_structure.MarketStructureAnalyzer,candle_intelligence.CandleIntelligenceAnalyzer,
        volatility_range.VolatilityRangeAnalyzer,liquidity_intelligence.LiquidityIntelligenceAnalyzer,
        fvg_imbalance_intelligence.FVGImbalanceIntelligenceAnalyzer,displacement_intelligence.DisplacementIntelligenceAnalyzer,
        liquidity_events.LiquidityEventsAnalyzer,order_block_intelligence.OrderBlockIntelligenceAnalyzer,
        structural_dealing_range_intelligence.StructuralDealingRangeAnalyzer,premium_discount_intelligence.PremiumDiscountAnalyzer]
    def forbidden(*args, **kwargs): raise AssertionError("Factual/decision execution forbidden")
    for owner in owners: monkeypatch.setattr(owner,"analyze",forbidden)
    monkeypatch.setattr(CAUSAL_SNAPSHOT_AVAILABILITY,"analyze",forbidden)
    from ced_one.mission_control.service import MissionControlService
    monkeypatch.setattr(MissionControlService,"handle_request",forbidden)
    result = SYNTHESIS.analyze(base).to_dict()
    forbidden_keys = {"recommendation","signal","entry","exit","stop_loss","take_profit","position_size",
        "risk_allocation","expected_return","expected_direction","confidence","score","weight","execution_instruction","dominant_regime"}
    def check(value):
        if isinstance(value,dict):
            assert not forbidden_keys.intersection(value)
            for v in value.values(): check(v)
        elif isinstance(value,list):
            for v in value: check(v)
    check(result)
    assert result["metadata"]["authority_scope"] == "read_only"
    assert result["metadata"]["execution_output"] is False
    from ced_one.business_divisions.trading.division import TradingDivision
    assert "causal_market_state_synthesis" not in TradingDivision().get_capability_names()
    assert "trading.causal_market_state_synthesis.v1" not in ADAPTERS
