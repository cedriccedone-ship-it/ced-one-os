"""Contract tests across real source, detector, envelope and chronology boundaries."""
import pytest
from tests.test_trading_vertical_slice_v19 import matrix, envelope, source_context, CAPABILITIES, REQUESTED
from tests.test_trading_vertical_slice_v10 import history as displacement_history
from tests.test_trading_vertical_slice_v15 import structured_source
from tests.test_trading_vertical_slice_v19 import integration_fvg_scenario
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY
from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS, CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE
from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT
from ced_one.business_divisions.trading.causal_factual_event_chronology import CAUSAL_FACTUAL_EVENT_CHRONOLOGY


@pytest.mark.parametrize("capability,history_factory,family", [
    ("liquidity_events", lambda: structured_source()["approved_candle_history"], "liquidity_close_beyond"),
    ("fvg_imbalance_intelligence", integration_fvg_scenario, "fvg_created"),
    ("displacement_intelligence", displacement_history, "displacement"),
    ("order_block_intelligence", displacement_history, "order_block_created"),
    ("structural_dealing_range_intelligence", lambda: structured_source()["approved_candle_history"], "structural_range_created"),
])
def test_real_producer_event_families_reach_chronology(capability, history_factory, family):
    source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp=REQUESTED, candle_history=history_factory()))
    assert source.source_availability == "AVAILABLE"
    adapter = ADAPTERS[f"trading.{capability}.v1"]
    produced = CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(dict(symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp=REQUESTED, causal_source=source, capability=dict(name=capability, contract=adapter.contract, rule_version=adapter.rule_version)))
    assert produced.factual_availability == "AVAILABLE_PRESENT", produced.evidence
    envelopes = matrix()
    envelopes["H1"] = {name: envelope("H1", name, state="AVAILABLE_ABSENT", source_id=source.source_snapshot_id, cutoff=source.effective_causal_cutoff) for name in CAPABILITIES}
    envelopes["H1"][capability] = produced.to_dict()
    sources = source_context(h1_cutoff=source.effective_causal_cutoff)
    sources["timeframes"]["H1"]["source_snapshot_id"] = source.source_snapshot_id
    context = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(dict(symbol="XAUUSD", requested_evaluation_timestamp=REQUESTED, source_context=sources, factual_envelopes=envelopes))
    result = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context, factual_envelopes=envelopes))
    events = [event for event in result.events if event["timeframe"] == "H1"]
    assert family in {event["event_family"] for event in events}
    assert all(event["authoritative_result_id"] == produced.authoritative_result_id for event in events)
    assert all(event["source_snapshot_id"] == source.source_snapshot_id for event in events)


@pytest.mark.parametrize("interaction_limit,omitted", [(1, 2), (100, 0)])
def test_real_order_block_retention_counts_omitted_events_once(interaction_limit, omitted):
    from tests.test_trading_vertical_slice_v10 import candle
    candles = displacement_history() + [
        candle(22, open_price=98.5, high=100.5, low=98, close=98.5),
        candle(23, open_price=99.5, high=101, low=99, close=100.5),
        candle(24, open_price=98, high=100, low=97, close=98),
    ]
    source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(
        symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp=REQUESTED, candle_history=candles))
    assert source.source_availability == "AVAILABLE"
    assert len(source.approved_candle_history) == len(candles)
    name = "order_block_intelligence"
    adapter = ADAPTERS[f"trading.{name}.v1"]
    produced = CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(dict(
        symbol="XAUUSD", timeframe="H1", requested_evaluation_timestamp=REQUESTED,
        causal_source=source, capability=dict(name=name, contract=adapter.contract,
            rule_version=adapter.rule_version, configuration={"maximum_interactions_per_block": interaction_limit})))
    assert produced.factual_availability == "AVAILABLE_PRESENT"
    diagnostics = produced.authoritative_result["diagnostics"]
    assert diagnostics["truncated_order_block_count"] == 0
    assert diagnostics["truncated_interaction_count"] == omitted
    assert diagnostics["blocks_with_truncated_interactions"] == (1 if omitted else 0)
    envelopes = matrix()
    envelopes["H1"] = {capability: envelope("H1", capability, state="AVAILABLE_ABSENT",
        source_id=source.source_snapshot_id, cutoff=source.effective_causal_cutoff) for capability in CAPABILITIES}
    envelopes["H1"][name] = produced.to_dict()
    sources = source_context(h1_cutoff=source.effective_causal_cutoff)
    sources["timeframes"]["H1"]["source_snapshot_id"] = source.source_snapshot_id
    context = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(dict(symbol="XAUUSD",
        requested_evaluation_timestamp=REQUESTED, source_context=sources, factual_envelopes=envelopes))
    result = CAUSAL_FACTUAL_EVENT_CHRONOLOGY.analyze(dict(factual_context=context, factual_envelopes=envelopes))
    coverage = result.timeframes["H1"]["coverage"][name]
    assert coverage["source_truncated_count"] == omitted
    assert coverage["chronology_truncated_count"] == 0
    assert coverage["normalized_event_count"] == 4 - omitted
    assert (coverage["coverage_state"] == "TRUNCATED") == bool(omitted)
    assert len(result.timeframes) == 7
