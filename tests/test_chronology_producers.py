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
