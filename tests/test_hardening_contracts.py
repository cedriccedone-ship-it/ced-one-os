"""H1/H4/H5 contract regressions across real producer and serialized boundaries."""
from copy import deepcopy
from dataclasses import replace
import pytest

from ced_one.business_divisions.trading.causal_snapshot_availability import (
    CAUSAL_SNAPSHOT_AVAILABILITY, validate_source, snapshot_identity, candle_completion,
)
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    ADAPTERS, CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE, validate_factual_envelope,
)
from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
    CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT, validate_factual_context,
)
from ced_one.business_divisions.trading.causal_factual_event_chronology import CAUSAL_FACTUAL_EVENT_CHRONOLOGY
from ced_one.business_divisions.trading.factual_market_context_composition import FactualMarketContextCompositionAnalyzer
from tests.test_trading_vertical_slice_v15 import source_result, candle, ts
from tests.test_trading_vertical_slice_v16 import real_matrix
from tests.test_trading_vertical_slice_v19 import (
    matrix, envelope, real_context, CAPABILITIES, REQUESTED, integration_fvg_scenario,
)
from tests.test_hardening_causality import liquidity_payload


def produce(name, candles, config=None):
    source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="H1",
        requested_evaluation_timestamp=REQUESTED, candle_history=candles))
    adapter = ADAPTERS[f"trading.{name}.v1"]
    return CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(dict(symbol="XAUUSD", timeframe="H1",
        requested_evaluation_timestamp=REQUESTED, causal_source=source,
        capability=dict(name=name, contract=adapter.contract, rule_version=adapter.rule_version,
                        configuration=config or {}))).to_dict()


def chronology_for(produced):
    values = matrix()
    values["H1"] = {name: envelope("H1", name, state="AVAILABLE_ABSENT",
        source_id=produced["source_snapshot_id"], cutoff=produced["effective_causal_cutoff"]) for name in CAPABILITIES}
    values["H1"][produced["capability"]["name"]] = produced
    context = real_context(values, h1_cutoff=produced["effective_causal_cutoff"])
    return CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context, factual_envelopes=values))


def test_h1_ordering_uses_completion_and_keeps_original_labels():
    result = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=real_context(matrix()), factual_envelopes=matrix()))
    daily = next(e for e in result.events if e["timeframe"] == "D1" and e["event_family"] == "displacement")
    minute = next(e for e in result.events if e["timeframe"] == "M1" and e["event_family"] == "fvg_created")
    assert daily["event_timestamp"] < minute["event_timestamp"]
    assert daily["causal_availability_timestamp"] > minute["causal_availability_timestamp"]
    assert result.events.index(daily) > result.events.index(minute)
    assert result.metadata["contract"] == "trading.causal_available_factual_event_chronology.v2"
    for group in result.ordering_groups:
        assert group["within_group_ordering"] == "ORDER_UNPROVEN"
        members = [e for e in result.events if e["chronology_event_id"] in group["event_ids"]]
        assert {e["causal_availability_timestamp"] for e in members} == {group["causal_availability_timestamp"]}
    for edge in result.chronology_edges:
        assert edge["ordering_basis"] == "causal_availability_timestamp"
    for event in result.events:
        assert event["causal_availability_timestamp"] <= event["effective_causal_cutoff"] <= event["requested_evaluation_timestamp"]


def test_h1_real_creation_state_is_snapshot_current_and_interactions_complete_later():
    produced = produce("fvg_imbalance_intelligence", integration_fvg_scenario())
    result = chronology_for(produced)
    events = [e for e in result.events if e["timeframe"] == "H1"]
    creation = events[0]
    assert creation["snapshot_current_state"] == "fully_filled"
    assert creation["source_event_state"] is None
    assert creation["causal_availability_timestamp"] == "2026-08-17T03:00:00Z"
    assert events[-1]["causal_availability_timestamp"] == "2026-08-17T06:00:00Z"


def test_h2_h1_chronology_consumes_boundary_without_redetection(monkeypatch):
    produced = produce("liquidity_events", liquidity_payload([105,110,104,110.2,104,110.3,110.4,104])["candle_history"])
    from ced_one.business_divisions.trading.liquidity_intelligence import LiquidityIntelligenceAnalyzer
    def forbidden(*args, **kwargs):
        raise AssertionError("Chronology must not invoke a detector")
    monkeypatch.setattr(LiquidityIntelligenceAnalyzer, "analyze", forbidden)
    result = chronology_for(produced)
    source = next(e for e in produced["authoritative_result"]["liquidity_events"]
                  if e["event_timestamp"] == ts(5) and "cluster" in e["level_type"])
    event = next(e for e in result.events if e["source_event_id"] == source["event_id"])
    assert event["event_family"] == "liquidity_sweep"
    assert event["descriptor"]["causal_boundary"] == source["causal_boundary"]
    assert event["causal_availability_timestamp"] == ts(6)
    assert event["causal_availability_basis"]["causal_boundary_id"] == source["causal_boundary_id"]


@pytest.mark.parametrize("change", ["price", "id", "cutoff", "completion", "count", "duration", "empty", "metadata"])
def test_h4_source_content_and_derived_evidence_cannot_drift(change):
    value = source_result()
    if change == "price": value["approved_candle_history"][0]["close"] = 100.5
    elif change == "id": value["source_snapshot_id"] = "replacement"
    elif change == "cutoff": value["effective_causal_cutoff"] = ts(26)
    elif change == "completion": value["completion_state"] = "INCOMPLETE"
    elif change == "count": value["diagnostics"]["approved_candle_count"] += 1
    elif change == "duration": value["evidence"]["timeframe_duration"] = 1
    elif change == "empty": value["approved_candle_history"] = []
    else: value["metadata"]["candle_timestamp_semantics"] = "close_time"
    with pytest.raises(ValueError): validate_source(value)


def test_h4_source_identity_unchanged_and_incomplete_semantics_survive():
    value = source_result(completion="INCOMPLETE")
    assert validate_source(value) == value
    assert value["source_snapshot_id"] == snapshot_identity(value)
    assert value["diagnostics"]["incomplete_candle_count"] == 1
    assert value["completion_state"] == "INCOMPLETE"
    replay = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol=value["symbol"], timeframe=value["timeframe"],
        requested_evaluation_timestamp=value["requested_evaluation_timestamp"], candle_history=value["approved_candle_history"]))
    assert replay.completion_state == "COMPLETED"
    assert replay.source_snapshot_id == value["source_snapshot_id"]


@pytest.mark.parametrize("change", ["result", "result_id", "config", "envelope_id", "legacy"])
def test_h4_envelope_rejects_detached_content(change):
    value = produce("fvg_imbalance_intelligence", integration_fvg_scenario())
    assert validate_factual_envelope(value) == value
    if change == "result": value["authoritative_result"]["fair_value_gaps"][0]["current_status"] = "open"
    elif change == "result_id": value["authoritative_result_id"] = "replacement"
    elif change == "config": value["capability"]["configuration"]["lookback_candles"] = 17
    elif change == "envelope_id": value["factual_envelope_id"] = "replacement"
    else: value["metadata"]["rule_version"] = "causal_factual_intelligence_envelope_v2"
    with pytest.raises(ValueError): validate_factual_envelope(value)


def test_h4_normalized_defaults_have_identical_envelope_identity():
    candles = integration_fvg_scenario()
    default = produce("fvg_imbalance_intelligence", candles)
    explicit = produce("fvg_imbalance_intelligence", candles, default["capability"]["configuration"])
    assert default == explicit


def test_h4_retained_failed_result_is_validated_and_binds_degraded_context(monkeypatch):
    contract = "trading.fvg_imbalance_intelligence.v1"
    def broken(*args): raise ValueError("injected terminal classification failure")
    monkeypatch.setitem(ADAPTERS, contract, replace(ADAPTERS[contract], classify=broken))
    data = real_matrix()
    failed = data["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]
    assert failed["factual_envelope_id"] is None
    assert failed["authoritative_result_id"] and failed["authoritative_result"]
    assert validate_factual_envelope(failed) == failed
    first = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    changed = real_matrix(configurations={"fvg_imbalance_intelligence": {"minimum_gap_size": 50}})
    second = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(changed)
    assert first.factual_context_id != second.factual_context_id
    assert second.context_state == first.context_state == "INVALID"
    failed["authoritative_result"]["evidence"]["tampered"] = True
    with pytest.raises(ValueError, match="identity/content"):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)


@pytest.mark.parametrize("consumer", ["owner", "composition", "chronology"])
def test_h4_context_material_cannot_drift_with_same_identity(consumer):
    values = matrix()
    context = real_context(values)
    assert validate_factual_context(context) == context
    context["timeframes"]["H1"]["factual_capabilities"]["candle_intelligence"]["content_fingerprint"] = "replacement"
    with pytest.raises(ValueError):
        if consumer == "owner": validate_factual_context(context)
        elif consumer == "composition": FactualMarketContextCompositionAnalyzer().analyze(dict(factual_context=context))
        else: CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context, factual_envelopes=values))


def test_h4_chronology_checks_non_event_envelope_references():
    values = matrix(); context = real_context(values)
    values["H1"]["candle_intelligence"]["authoritative_result"]["tampered"] = True
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context, factual_envelopes=values))


def test_h5_filtered_absence_is_scoped_and_object_count_is_not_event_count():
    produced = produce("fvg_imbalance_intelligence", integration_fvg_scenario(), {"include_fully_filled": False})
    result = chronology_for(produced)
    coverage = result.timeframes["H1"]["coverage"]["fvg_imbalance_intelligence"]
    assert produced["factual_availability"] == "AVAILABLE_ABSENT"
    assert coverage["coverage_state"] == "FULLY_COVERED"
    scope = coverage["coverage_scope"]
    assert scope["output_filters"]["include_fully_filled"] is False
    assert scope["filter_omissions"] == {"filtered_object_count": 1, "filtered_event_count": None}
    assert scope["source_bounds"]["candle_count"] == 6
    assert coverage["earliest_retained_event_timestamp"] is None
    assert scope["absence_meaning"] == "no_output_in_configured_domain_only"
    assert result.coverage_state == "UNKNOWN_COVERAGE"  # Other reference fixtures lack coverage evidence.


def test_h5_lookback_and_retention_have_separate_domains():
    candles = liquidity_payload([105,110,104,110.2,104,110.3,104,104,104,104], lookback=3)["candle_history"]
    produced = produce("liquidity_events", candles, {"lookback_candles": 3, "maximum_events": 1})
    coverage = chronology_for(produced).timeframes["H1"]["coverage"]["liquidity_events"]
    scope = coverage["coverage_scope"]
    assert coverage["coverage_state"] == "TRUNCATED"
    assert scope["source_bounded"] is True
    assert scope["candidate_domain"]["basis"] == "per_interaction_prefix"
    assert scope["candidate_domain"]["reporting_domain"]["retention_limit"] is None
    assert scope["retention"]["maximum_events"] == 1
    assert scope["source_truncated_event_count"] > 0


@pytest.mark.parametrize("field", ["context_id", "cutoff", "edges", "diagnostics", "evidence"])
def test_h4_source_context_validates_own_identity_and_derived_fields(field):
    from ced_one.business_divisions.trading.causal_multi_timeframe_context import validate_source_context
    from tests.test_trading_vertical_slice_v16 import source_context
    value = source_context()
    assert validate_source_context(value) == value
    if field == "context_id": value["context_id"] = "replacement"
    elif field == "cutoff": value["timeframes"]["H1"]["effective_causal_cutoff"] = ts(23)
    elif field == "edges": value["edges"][0]["alignment_status"] = "UNAVAILABLE"
    elif field == "diagnostics": value["diagnostics"]["available_timeframe_count"] = 6
    else: value["evidence"]["context_state"] = "INVALID"
    with pytest.raises(ValueError): validate_source_context(value)


def test_h4_recomputed_source_identity_does_not_make_an_unclosed_candle_valid():
    value = source_result(candles=[candle(0)], requested=ts(1))
    value["approved_candle_history"][0]["timestamp"] = ts(1)
    value["source_snapshot_id"] = snapshot_identity(value)
    value["evidence"]["source_snapshot_id"] = value["source_snapshot_id"]
    with pytest.raises(ValueError, match="completion/cutoff"):
        validate_source(value)


def test_h4_degraded_configuration_binds_context_even_without_any_result_id():
    first_data = real_matrix("NO_CLOSED")
    second_data = real_matrix("NO_CLOSED", configurations={"fvg_imbalance_intelligence": {"minimum_gap_size": 50}})
    first = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(first_data)
    second = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(second_data)
    assert first.source_context_id == second.source_context_id
    assert first.context_state == second.context_state == "UNAVAILABLE"
    for data in (first_data, second_data):
        value = data["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"]
        assert value["factual_envelope_id"] is None and value["authoritative_result_id"] is None
        assert value["authoritative_result"] is None
    assert first.factual_context_id != second.factual_context_id
