from __future__ import annotations

import pytest

from ced_one.business_divisions.trading.factual_market_context_composition import (
    CAPABILITY_ORDER,
    FactualMarketContextCompositionAnalyzer,
    FactualMarketContextSpecialist,
    TIMEFRAME_ORDER,
)
from ced_one.business_divisions.trading.resolver import TradingDivisionResolver
from ced_one.business_divisions.trading.division import TradingDivision
from ced_one.mission_control.types import MissionRequest


REQUESTED = "2026-08-17T02:00:00Z"


def envelope(timeframe: str, capability: str, *, state: str = "AVAILABLE_PRESENT", envelope_id: str | None = None):
    return {
        "factual_availability": state,
        "factual_envelope_id": envelope_id or f"envelope_{timeframe.lower()}_{capability}",
        "authoritative_result_id": f"result_{timeframe.lower()}_{capability}",
        "source_snapshot_id": f"source_{timeframe.lower()}",
        "capability": {
            "name": capability,
            "contract": f"trading.{capability}.v1",
            "rule_version": f"{capability}_v1",
        },
        "availability_reason": "classified",
        "dependency_provenance": [],
    }


def context(*, state: str = "COMPLETE", completion: str = "COMPLETED", requested: str = REQUESTED, context_id: str = "factual_context_1"):
    timeframes = {}
    for timeframe in TIMEFRAME_ORDER:
        timeframes[timeframe] = {
            "timeframe": timeframe,
            "source_snapshot_id": f"source_{timeframe.lower()}",
            "effective_causal_cutoff": "2026-08-17T01:00:00Z",
            "source_availability": "AVAILABLE",
            "source_completion_state": completion,
            "factual_context_state": state,
            "factual_capabilities": {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER},
        }
    return {
        "symbol": "XAUUSD",
        "requested_evaluation_timestamp": requested,
        "source_context_id": "source_context_1",
        "factual_context_id": context_id,
        "identity_scope": "snapshot_deterministic",
        "context_state": state,
        "timeframes": timeframes,
        "diagnostics": {},
        "evidence": {},
        "metadata": {
            "contract": "trading.causal_factual_multi_timeframe_context.v1",
            "identity_scope": "snapshot_deterministic",
        },
    }


def analyze(factual_context=None):
    return FactualMarketContextCompositionAnalyzer().analyze({"factual_context": factual_context or context()})


def test_v18_accepts_complete_slice16_context_and_preserves_hierarchy():
    result = analyze()
    assert result.composition_state == "COMPLETE"
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    assert len(result.adjacent_relationships) == 60
    assert result.diagnostics["required_timeframe_count"] == 7
    assert result.diagnostics["relationship_count"] == 60


def test_v18_considers_all_ten_capabilities_on_all_timeframes():
    result = analyze()
    assert all(list(record["capability_observations"]) == list(CAPABILITY_ORDER) for record in result.timeframes.values())
    assert result.diagnostics["timeframe_record_count"] == 7


def test_v18_available_absent_is_evaluated_and_composes():
    factual_context = context()
    factual_context["timeframes"]["H4"]["factual_capabilities"]["fvg_imbalance_intelligence"] = envelope("H4", "fvg_imbalance_intelligence", state="AVAILABLE_ABSENT")
    result = analyze(factual_context)
    assert result.composition_state == "COMPLETE"
    relation = next(item for item in result.adjacent_relationships if item["parent_timeframe"] == "H4" and item["child_timeframe"] == "H1" and item["capability_name"] == "fvg_imbalance_intelligence")
    assert relation["relationship_type"] == "PRESENT_ON_CHILD_ONLY"


@pytest.mark.parametrize("state", ["INCOMPLETE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"])
def test_v18_degraded_slice16_context_never_claims_complete(state):
    result = analyze(context(state=state, completion="INCOMPLETE" if state == "INCOMPLETE" else "COMPLETED"))
    assert result.composition_state == state
    assert result.timeframes["D1"]["factual_context_state"] == state


def test_v18_relationship_vocabulary_is_factual_only():
    factual_context = context()
    for timeframe in TIMEFRAME_ORDER:
        factual_context["timeframes"][timeframe]["factual_capabilities"]["liquidity_events"] = envelope(timeframe, "liquidity_events", state="AVAILABLE_ABSENT")
    result = analyze(factual_context)
    assert all(item["relationship_type"] == "ABSENT_ON_BOTH" for item in result.adjacent_relationships if item["capability_name"] == "liquidity_events")
    text = str(result.to_dict()).lower()
    for forbidden in ["bullish", "bearish", "confirmation", "confluence", "trade_bias", "setup", "recommendation"]:
        assert forbidden not in text


def test_v18_parent_only_child_only_and_unavailable_relationships():
    factual_context = context()
    factual_context["timeframes"]["H4"]["factual_capabilities"]["market_structure"] = envelope("H4", "market_structure", state="AVAILABLE_ABSENT")
    factual_context["timeframes"]["H1"]["factual_capabilities"]["market_structure"] = envelope("H1", "market_structure", state="UNAVAILABLE", envelope_id=None)
    result = analyze(factual_context)
    parent_only = next(item for item in result.adjacent_relationships if item["parent_timeframe"] == "D1" and item["child_timeframe"] == "H4" and item["capability_name"] == "market_structure")
    unavailable = next(item for item in result.adjacent_relationships if item["parent_timeframe"] == "H4" and item["child_timeframe"] == "H1" and item["capability_name"] == "market_structure")
    assert parent_only["relationship_type"] == "PRESENT_ON_PARENT_ONLY"
    assert unavailable["relationship_type"] == "UNAVAILABLE"


def test_v18_provenance_is_preserved_without_payload_duplication():
    result = analyze()
    record = result.timeframes["D1"]["capability_observations"]["market_structure"]
    assert record["source_snapshot_id"] == "source_d1"
    assert record["factual_envelope_id"] == "envelope_d1_market_structure"
    assert record["authoritative_result_id"] == "result_d1_market_structure"
    assert "authoritative_result" not in record
    relation = result.adjacent_relationships[0]
    assert set(relation) >= {
        "parent_timeframe", "child_timeframe", "capability_name", "parent_source_snapshot_id",
        "child_source_snapshot_id", "parent_capability_envelope_id", "child_capability_envelope_id", "relationship_type",
    }


def test_v18_identity_is_deterministic_and_context_sensitive():
    first = analyze()
    second = analyze()
    changed = context(context_id="factual_context_changed")
    assert first.to_dict() == second.to_dict()
    assert first.composition_id == second.composition_id
    assert first.composition_id != analyze(changed).composition_id
    assert first.identity_scope == "snapshot_deterministic"


def test_v18_historical_context_requires_matching_internal_timestamp():
    historical = context(requested="2024-01-02T03:04:05Z")
    result = analyze(historical)
    assert result.requested_evaluation_timestamp == "2024-01-02T03:04:05Z"
    historical["timeframes"]["M1"]["factual_capabilities"]["market_structure"]["source_snapshot_id"] = "wrong_source"
    with pytest.raises(ValueError):
        analyze(historical)


def test_v18_rejects_raw_or_detached_inputs():
    with pytest.raises(ValueError):
        FactualMarketContextCompositionAnalyzer().analyze({"factual_context": {"symbol": "XAUUSD"}})
    raw = context()
    raw["timeframes"]["D1"]["factual_capabilities"]["market_structure"] = {"structure_state": "bullish_structure"}
    with pytest.raises(ValueError):
        analyze(raw)


def test_v18_specialist_boundary_and_registration():
    specialist = FactualMarketContextSpecialist()
    assert specialist.validate_binding(
        division_name="trading",
        specialist_name="factual_market_context_analyst",
        capability_name="factual_market_context_composition",
        permission_scope="read_only",
    )
    assert specialist.can_mutate_task_lifecycle() is False
    assert specialist.is_final_authority() is False
    assert specialist.requires_external_execution() is False
    assert "factual_market_context_composition" in TradingDivision().get_capability_names()
    assert "factual_market_context_analyst" in TradingDivision().get_specialist_names()


def test_v18_resolver_phrases_are_narrow_and_preserve_slice2_behavior():
    resolver = TradingDivisionResolver()
    for goal in ["factual market context", "factual context composition", "compose factual market context"]:
        request = MissionRequest(user_goal=goal, request_type="analysis", business_division="trading")
        assert resolver.resolve_capability(request)["name"] == "factual_market_context_composition"
        assert resolver.resolve_specialist(request)["name"] == "factual_market_context_analyst"
    generic = MissionRequest(user_goal="top down analysis", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(generic)["name"] == "market_observation"
    generic_context = MissionRequest(user_goal="market context", request_type="analysis", business_division="trading")
    assert resolver.resolve_capability(generic_context)["name"] == "market_observation"


def test_v18_no_detector_or_execution_semantics():
    result = analyze().to_dict()
    text = str(result).lower()
    for forbidden in [
        "buy", "sell", "long", "short", "signal", "setup", "confidence", "probability",
        "recommendation", "trade_bias", "confirmation", "confluence", "execution_command",
    ]:
        assert forbidden not in text
    assert result["metadata"]["authority_scope"] == "read_only"