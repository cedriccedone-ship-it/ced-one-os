from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    ADAPTERS,
    AVAILABILITY_STATES,
    CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE,
)
from ced_one.business_divisions.trading.causal_snapshot_availability import (
    CausalSnapshotAvailabilityAnalyzer,
)


def ts(index: int) -> str:
    return (datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(hours=index)).isoformat().replace("+00:00", "Z")


def candle(index: int, *, close: float = 100.0, high: float = 101.0, low: float = 99.0):
    return {"timestamp": ts(index), "open": 100.0, "high": high, "low": low, "close": close}


def history():
    return [candle(index) for index in range(25)]


def source_result(*, timeframe="H1", availability="AVAILABLE", completion="COMPLETED", candles=None, snapshot_id="source_h1", requested="2026-08-17T02:00:00Z"):
    approved = history() if candles is None else candles
    cutoff = ts(25)
    return {
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff if availability == "AVAILABLE" else None,
        "source_snapshot_id": snapshot_id if availability == "AVAILABLE" else None,
        "source_availability": availability,
        "availability_reason": "sufficient_causal_source" if availability == "AVAILABLE" else availability.lower(),
        "completion_state": completion,
        "approved_candle_history": approved if availability == "AVAILABLE" else [],
        "diagnostics": {},
        "evidence": {},
        "metadata": {"contract": "trading.causal_snapshot_availability.v1", "identity_scope": "snapshot_deterministic"},
    }


def request(contract: str, *, name: str | None = None, rule_version: str | None = None, configuration=None, source=None, context_id=None):
    adapter = ADAPTERS[contract]
    return {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "requested_evaluation_timestamp": "2026-08-17T02:00:00Z",
        "causal_source": source or source_result(),
        "capability": {
            "name": adapter.name if name is None else name,
            "contract": contract,
            "rule_version": adapter.rule_version if rule_version is None else rule_version,
            "configuration": {} if configuration is None else configuration,
        },
        "context_id": context_id,
    }


def analyze(contract: str, **kwargs):
    return CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(request(contract, **kwargs))


def test_v15_allowlist_contains_only_slices_three_through_twelve():
    assert len(ADAPTERS) == 10
    assert "trading.market_observation.v1" not in ADAPTERS
    assert "trading.causal_snapshot_availability.v1" not in ADAPTERS
    assert "trading.causal_multi_timeframe_context.v1" not in ADAPTERS
    assert AVAILABILITY_STATES == {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}


def test_v15_candle_adapter_invokes_authoritative_result_and_preserves_it():
    result = analyze("trading.candle_intelligence.v1")
    assert result.factual_availability == "AVAILABLE_PRESENT"
    assert result.factual_envelope_id is not None
    assert result.authoritative_result_id is not None
    assert result.source_snapshot_id == "source_h1"
    assert result.provenance["controlled_invocation"] is True
    assert result.authoritative_result["timeframe"] == "H1"
    assert result.metadata["identity_scope"] == "snapshot_deterministic"


@pytest.mark.parametrize("contract", [
    "trading.market_structure.v1",
    "trading.candle_intelligence.v1",
    "trading.volatility_range.v1",
    "trading.liquidity_intelligence.v1",
    "trading.fvg_imbalance_intelligence.v1",
    "trading.displacement_intelligence.v1",
    "trading.liquidity_events.v1",
    "trading.order_block_intelligence.v1",
    "trading.structural_dealing_range_intelligence.v1",
    "trading.premium_discount_intelligence.v1",
])
def test_v15_all_allowlisted_adapters_have_controlled_paths(contract):
    result = analyze(contract)
    assert result.factual_availability in AVAILABILITY_STATES
    assert result.provenance["controlled_invocation"] is True
    assert result.capability["contract"] == contract


@pytest.mark.parametrize("state", ["UNAVAILABLE", "INVALID", "NOT_EVALUATED"])
def test_v15_source_failure_states_do_not_invoke_capability(state):
    result = analyze("trading.candle_intelligence.v1", source=source_result(availability=state))
    assert result.factual_availability == state
    assert result.authoritative_result is None
    assert result.factual_envelope_id is None
    assert result.diagnostics["controlled_invocation_performed"] is False


def test_v15_available_incomplete_source_is_preserved_and_uses_approved_history():
    result = analyze("trading.candle_intelligence.v1", source=source_result(completion="INCOMPLETE"))
    assert result.factual_availability == "AVAILABLE_PRESENT"
    assert result.source_completion_state == "INCOMPLETE"
    assert result.evidence["source_completion_state"] == "INCOMPLETE"


def test_v15_unknown_source_completion_fails_closed_without_result():
    result = analyze("trading.candle_intelligence.v1", source=source_result(completion="UNKNOWN"))
    assert result.factual_availability == "UNAVAILABLE"
    assert result.factual_envelope_id is None
    assert result.availability_reason == "unknown_source_completion"


@pytest.mark.parametrize("field,value", [("symbol", "EURUSD"), ("timeframe", "M5"), ("requested_evaluation_timestamp", "2026-08-17T03:00:00Z")])
def test_v15_source_pairing_mismatch_is_rejected(field, value):
    source = source_result()
    source[field] = value
    kwargs = {"source": source}
    with pytest.raises(ValueError):
        analyze("trading.candle_intelligence.v1", **kwargs)


def test_v15_unsupported_or_mismatched_capability_is_rejected():
    unsupported = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "requested_evaluation_timestamp": "2026-08-17T02:00:00Z",
        "causal_source": source_result(),
        "capability": {"name": "market_observation", "contract": "trading.market_observation.v1", "rule_version": "market_observation_v1", "configuration": {}},
    }
    with pytest.raises(ValueError, match="Unsupported"):
        CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(unsupported)
    with pytest.raises(ValueError, match="mismatched"):
        analyze("trading.candle_intelligence.v1", name="liquidity_intelligence")
    with pytest.raises(ValueError, match="mismatched"):
        analyze("trading.candle_intelligence.v1", rule_version="wrong")


def test_v15_detached_result_input_is_not_accepted():
    detached = request("trading.candle_intelligence.v1")
    detached["capability_result"] = {"symbol": "XAUUSD", "timeframe": "H1"}
    with pytest.raises(ValueError, match="unsupported fields"):
        CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(detached)


def test_v15_dependency_provenance_is_retained_for_dependent_capabilities():
    liquidity_events = analyze("trading.liquidity_events.v1")
    order_blocks = analyze("trading.order_block_intelligence.v1")
    structural_range = analyze("trading.structural_dealing_range_intelligence.v1")
    assert liquidity_events.dependency_provenance[0]["capability_contract"] == "trading.liquidity_intelligence.v1"
    assert order_blocks.dependency_provenance[0]["capability_contract"] == "trading.displacement_intelligence.v1"
    assert structural_range.dependency_provenance[0]["capability_contract"] == "trading.market_structure.v1"
    assert all(item["source_snapshot_id"] == "source_h1" for item in structural_range.dependency_provenance)


def test_v15_premium_discount_preserves_full_dependency_chain():
    result = analyze("trading.premium_discount_intelligence.v1")
    contracts = [item["capability_contract"] for item in result.dependency_provenance]
    assert contracts == ["trading.market_structure.v1", "trading.structural_dealing_range_intelligence.v1"]
    assert result.provenance["controlled_invocation"] is True
    assert result.source_snapshot_id == "source_h1"


def test_v15_identity_is_deterministic_and_configuration_sensitive():
    first = analyze("trading.candle_intelligence.v1")
    second = analyze("trading.candle_intelligence.v1")
    changed_source = analyze("trading.candle_intelligence.v1", source=source_result(snapshot_id="source_changed"))
    changed_context = analyze("trading.candle_intelligence.v1", context_id="context_1")
    assert first.to_dict() == second.to_dict()
    assert first.factual_envelope_id == second.factual_envelope_id
    assert first.factual_envelope_id != changed_source.factual_envelope_id
    assert first.factual_envelope_id != changed_context.factual_envelope_id


def test_v15_failure_identity_is_null_but_evidence_is_deterministic():
    first = analyze("trading.candle_intelligence.v1", source=source_result(availability="UNAVAILABLE"))
    second = analyze("trading.candle_intelligence.v1", source=source_result(availability="UNAVAILABLE"))
    assert first.factual_envelope_id is None
    assert first.authoritative_result is None
    assert first.to_dict() == second.to_dict()
    assert first.evidence["availability_reason"] == "source_unavailable"


def test_v15_configuration_passes_to_authoritative_capability():
    result = analyze("trading.volatility_range.v1", configuration={"atr_window": 2, "range_window": 3, "short_volatility_window": 1, "long_volatility_window": 2})
    assert result.factual_availability == "AVAILABLE_PRESENT"
    assert result.capability["configuration"]["atr_window"] == 2


def test_v15_no_strategy_or_multitimeframe_semantics():
    result = analyze("trading.candle_intelligence.v1").to_dict()
    text = str(result).lower()
    for forbidden in ["buy", "sell", "signal", "setup", "confidence", "recommendation", "trade_bias", "confirmation", "confluence", "execution_command", "d1", "m1"]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None
    assert result["metadata"]["authority_scope"] == "read_only"


def test_v15_public_shape_preserves_opaque_authoritative_payload():
    result = analyze("trading.candle_intelligence.v1")
    assert set(result.to_dict()) == {
        "factual_envelope_id", "factual_availability", "symbol", "timeframe", "requested_evaluation_timestamp",
        "effective_causal_cutoff", "source_snapshot_id", "source_completion_state", "context_id", "capability",
        "authoritative_result", "authoritative_result_id", "dependency_provenance", "availability_reason",
        "provenance", "diagnostics", "evidence", "metadata",
    }
    assert "candle_direction" in result.authoritative_result
    assert "approved_candle_history" not in result.evidence