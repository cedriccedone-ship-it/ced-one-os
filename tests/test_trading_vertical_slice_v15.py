from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
    ADAPTERS,
    AVAILABILITY_STATES,
    CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE,
    _configuration_fingerprint,
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
    selected_source = source or source_result()
    return {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "requested_evaluation_timestamp": selected_source["requested_evaluation_timestamp"],
        "causal_source": selected_source,
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


def structured_source():
    rows = [
        {"timestamp": ts(index), "open": open_price, "high": high, "low": low, "close": close}
        for index, (open_price, high, low, close) in enumerate([
            (100.0, 103.0, 96.0, 101.0), (101.0, 104.0, 97.0, 102.0), (102.0, 103.5, 98.0, 101.0),
            (101.0, 105.0, 99.0, 104.0), (104.0, 104.5, 100.0, 103.0), (103.0, 106.0, 101.0, 105.0),
            (105.0, 106.2, 101.2, 105.5), (105.5, 107.0, 102.0, 106.0), (106.0, 106.5, 101.8, 105.8),
            (105.8, 108.0, 103.0, 107.0), (107.0, 108.1, 103.5, 107.5), (107.5, 109.0, 104.0, 108.4),
        ])
    ]
    result = source_result(candles=rows, snapshot_id="source_structured", requested=ts(14))
    result["effective_causal_cutoff"] = ts(12)
    return result


def displacement_source():
    rows = [candle(index, close=100, high=101, low=99) for index in range(20)]
    rows.extend([candle(20, close=100, high=103, low=99), candle(21, close=105, high=106, low=99)])
    return source_result(candles=rows, snapshot_id="source_displacement", requested=ts(23))


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
    kwargs = {"source": source}
    if field == "requested_evaluation_timestamp":
        request_payload = request("trading.candle_intelligence.v1", source=source)
        request_payload["requested_evaluation_timestamp"] = value
        with pytest.raises(ValueError):
            CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(request_payload)
        return
    source[field] = value
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
    liquidity_events = analyze("trading.liquidity_events.v1", source=structured_source())
    order_blocks = analyze("trading.order_block_intelligence.v1", source=displacement_source())
    structural_range = analyze("trading.structural_dealing_range_intelligence.v1", source=structured_source())
    assert liquidity_events.dependency_provenance[0]["capability_contract"] == "trading.liquidity_intelligence.v1"
    assert order_blocks.dependency_provenance[0]["capability_contract"] == "trading.displacement_intelligence.v1"
    assert structural_range.dependency_provenance[0]["capability_contract"] == "trading.market_structure.v1"
    assert all(item["source_snapshot_id"] == "source_structured" for item in structural_range.dependency_provenance)


def test_v15_premium_discount_preserves_full_dependency_chain():
    result = analyze("trading.premium_discount_intelligence.v1", source=structured_source())
    contracts = [item["capability_contract"] for item in result.dependency_provenance]
    assert contracts == ["trading.market_structure.v1", "trading.structural_dealing_range_intelligence.v1"]
    assert result.provenance["controlled_invocation"] is True
    assert result.source_snapshot_id == "source_structured"


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


def test_v15_dependency_records_expose_complete_source_provenance():
    result = analyze("trading.liquidity_events.v1", source=structured_source())
    dependency = result.dependency_provenance[0]
    assert dependency["dependency_order"] == 1
    assert dependency["capability_name"] == "liquidity_intelligence"
    assert dependency["capability_contract"] == "trading.liquidity_intelligence.v1"
    assert dependency["capability_rule_version"] == "liquidity_intelligence_v1"
    assert dependency["factual_availability"] in AVAILABILITY_STATES
    assert dependency["authoritative_result_id"] == dependency["result_identity"]
    assert dependency["source_snapshot_id"] == "source_structured"
    assert dependency["symbol"] == "XAUUSD"
    assert dependency["timeframe"] == "H1"
    assert dependency["requested_evaluation_timestamp"] == ts(14)
    assert dependency["effective_causal_cutoff"] == ts(12)
    assert dependency["configuration_fingerprint"].startswith("configuration_")
    assert dependency["controlled_invocation"] is True
    assert dependency["provenance_validation"] == "validated_controlled_dependency"


@pytest.mark.parametrize("contract", [
    "trading.liquidity_events.v1",
    "trading.order_block_intelligence.v1",
    "trading.structural_dealing_range_intelligence.v1",
])
def test_v15_dependent_records_have_expected_order_and_shared_source(contract):
    result = analyze(contract, source=displacement_source() if contract == "trading.order_block_intelligence.v1" else structured_source())
    assert [item["dependency_order"] for item in result.dependency_provenance] == [1]
    expected_source = "source_displacement" if contract == "trading.order_block_intelligence.v1" else "source_structured"
    assert all(item["source_snapshot_id"] == expected_source for item in result.dependency_provenance)
    assert all(item["symbol"] == "XAUUSD" and item["timeframe"] == "H1" for item in result.dependency_provenance)


def test_v15_premium_dependency_records_are_ordered_and_complete():
    result = analyze("trading.premium_discount_intelligence.v1", source=structured_source())
    assert [item["dependency_order"] for item in result.dependency_provenance] == [1, 2]
    assert [item["capability_name"] for item in result.dependency_provenance] == ["market_structure", "structural_dealing_range_intelligence"]
    assert all(item["authoritative_result_id"] for item in result.dependency_provenance)
    assert all(item["source_snapshot_id"] == "source_structured" for item in result.dependency_provenance)
    assert all(item["controlled_invocation"] for item in result.dependency_provenance)


def test_v15_dependency_provenance_is_deterministic_and_identity_sensitive():
    first = analyze("trading.premium_discount_intelligence.v1", source=structured_source())
    second = analyze("trading.premium_discount_intelligence.v1", source=structured_source())
    changed = analyze("trading.premium_discount_intelligence.v1", source=structured_source(), configuration={"maximum_ranges": 1})
    assert first.dependency_provenance == second.dependency_provenance
    assert first.factual_envelope_id == second.factual_envelope_id
    assert first.factual_envelope_id != changed.factual_envelope_id


def test_v15_dependent_unavailable_source_does_not_claim_success():
    result = analyze("trading.structural_dealing_range_intelligence.v1", source=source_result(availability="UNAVAILABLE"))
    assert result.factual_availability == "UNAVAILABLE"
    assert result.factual_envelope_id is None
    assert result.authoritative_result is None


def test_v15_unavailable_dependency_propagates_without_becoming_absent():
    short_source = source_result(candles=[candle(0)])
    result = analyze("trading.order_block_intelligence.v1", source=short_source)
    assert result.factual_availability == "UNAVAILABLE"
    assert result.factual_envelope_id is None


def test_v15_dependency_configuration_fingerprint_changes_with_effective_configuration():
    default = analyze("trading.liquidity_events.v1", source=structured_source())
    configured = analyze("trading.liquidity_events.v1", source=structured_source(), configuration={"lookback_candles": 50})
    assert default.dependency_provenance[0]["configuration_fingerprint"] != configured.dependency_provenance[0]["configuration_fingerprint"]


def test_v15_source_provenance_fields_cannot_be_detached_from_controlled_source():
    mismatched = structured_source()
    mismatched["source_snapshot_id"] = "different_source"
    result = analyze("trading.structural_dealing_range_intelligence.v1", source=mismatched)
    assert result.source_snapshot_id == "different_source"
    assert result.dependency_provenance[0]["source_snapshot_id"] == "different_source"
    assert result.dependency_provenance[0]["source_snapshot_id"] == result.source_snapshot_id


@pytest.mark.parametrize("contract", sorted(ADAPTERS))
def test_v15_terminal_configuration_fingerprint_uses_effective_adapter_configuration(contract):
    result = analyze(contract, source=structured_source() if contract in {"trading.structural_dealing_range_intelligence.v1", "trading.premium_discount_intelligence.v1", "trading.liquidity_events.v1"} else None)
    expected = _configuration_fingerprint(ADAPTERS[contract].normalize_configuration({}))
    assert result.provenance["configuration_fingerprint"] == expected
    assert result.evidence["configuration_fingerprint"] == expected


def test_v15_terminal_fingerprint_equates_omitted_and_explicit_defaults():
    default = analyze("trading.candle_intelligence.v1")
    explicit = analyze(
        "trading.candle_intelligence.v1",
        configuration=ADAPTERS["trading.candle_intelligence.v1"].normalize_configuration({}),
    )
    assert default.provenance["configuration_fingerprint"] == explicit.provenance["configuration_fingerprint"]


def test_v15_terminal_fingerprint_changes_for_material_effective_configuration():
    default = analyze("trading.candle_intelligence.v1")
    changed = analyze("trading.candle_intelligence.v1", configuration={"sequence_window": 6})
    assert default.provenance["configuration_fingerprint"] != changed.provenance["configuration_fingerprint"]


def test_v15_nested_configuration_uses_effective_terminal_and_dependency_fingerprints():
    result = analyze(
        "trading.liquidity_events.v1",
        source=structured_source(),
        configuration={"liquidity_config": {"equal_level_tolerance": 0.75}},
    )
    terminal_config = ADAPTERS["trading.liquidity_events.v1"].normalize_configuration({"liquidity_config": {"equal_level_tolerance": 0.75}})
    dependency_config = terminal_config["liquidity_config"]
    assert result.provenance["configuration_fingerprint"] == _configuration_fingerprint(terminal_config)
    assert result.dependency_provenance[0]["configuration_fingerprint"] == _configuration_fingerprint(dependency_config)


@pytest.mark.parametrize("contract", ["trading.market_structure.v1", "trading.premium_discount_intelligence.v1"])
def test_v15_no_configuration_capabilities_have_canonical_empty_fingerprint(contract):
    result = analyze(contract, source=structured_source())
    assert result.provenance["configuration_fingerprint"] == _configuration_fingerprint({})