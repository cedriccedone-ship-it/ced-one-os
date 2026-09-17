from __future__ import annotations

import pytest

from ced_one.business_divisions.trading.causal_factual_multi_timeframe_context import (
    CAPABILITY_CONTRACTS,
    CAPABILITY_ORDER,
    CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT,
    TIMEFRAME_ORDER,
)


REQUESTED = "2026-08-17T02:00:00Z"


def source_context(*, source_state="AVAILABLE", completion="COMPLETED", context_id="source_context_1", requested=REQUESTED):
    timeframes = {}
    for index, timeframe in enumerate(TIMEFRAME_ORDER):
        timeframes[timeframe] = {
            "timeframe": timeframe,
            "requested_evaluation_timestamp": requested,
            "effective_causal_cutoff": f"2026-08-17T{index + 1:02d}:00:00Z" if source_state == "AVAILABLE" else None,
            "source_snapshot_id": f"source_{timeframe.lower()}" if source_state == "AVAILABLE" else None,
            "source_availability": source_state,
            "availability_reason": "sufficient_causal_source" if source_state == "AVAILABLE" else source_state.lower(),
            "completion_state": completion,
        }
    return {
        "symbol": "XAUUSD",
        "requested_evaluation_timestamp": requested,
        "context_id": context_id,
        "identity_scope": "snapshot_deterministic",
        "context_state": "COMPLETE",
        "timeframes": timeframes,
        "edges": [],
        "diagnostics": {},
        "evidence": {},
        "metadata": {"contract": "trading.causal_multi_timeframe_context.v1", "identity_scope": "snapshot_deterministic"},
    }


def migrate_test_envelope(value):
    """Explicit synthetic consumer fixture, not evidence of real execution."""
    from copy import deepcopy
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import (
        ADAPTERS, RULE_VERSION, execution_diagnostics, dependency_configurations, _configuration_fingerprint,
    )
    adapter = ADAPTERS[value["capability"]["contract"]]
    config = adapter.normalize_configuration({})
    value["capability"].update(rule_version=adapter.rule_version, configuration=config)
    value.setdefault("context_id", None)
    value["metadata"]["rule_version"] = RULE_VERSION
    state = value["factual_availability"]
    terminal = "INVOCATION_FAILED" if state == "INVALID" else "COMPLETED"
    if state == "NOT_EVALUATED":
        raise ValueError("Use authentic source-rejected matrices for NOT_EVALUATED.")
    progress = {"terminal": terminal, "dependencies": []}
    records = value["dependency_provenance"]
    for index, (contract, dep_config) in enumerate(zip(adapter.dependencies, dependency_configurations(adapter.contract, config))):
        owner = ADAPTERS[contract]
        record = records[index]
        record.update(capability_rule_version=owner.rule_version,
                      configuration_fingerprint=_configuration_fingerprint(dep_config),
                      result_identity=record["authoritative_result_id"])
        progress["dependencies"].append({"capability_contract": contract, "state": "COMPLETED",
                                         "authoritative_result_id": record["authoritative_result_id"]})
    if terminal == "COMPLETED":
        if value["authoritative_result"] is None:
            value["authoritative_result"] = {"diagnostics": {}}
        value["authoritative_result_id"] = value["authoritative_result_id"] or "synthetic_result"
    else:
        value["authoritative_result"] = value["authoritative_result_id"] = None
    fingerprint = _configuration_fingerprint(config)
    value["provenance"] = {"controlled_invocation": True, "configuration_fingerprint": fingerprint,
        "source_contract": "trading.causal_snapshot_availability.v1", "source_snapshot_id": value["source_snapshot_id"],
        "identity_scope": "snapshot_deterministic", "dependency_contracts": list(adapter.dependencies),
        "dependency_provenance": deepcopy(records), "execution_progress": progress}
    value["evidence"].update(configuration_fingerprint=fingerprint, dependency_provenance=deepcopy(records))
    value["diagnostics"] = {**execution_diagnostics(progress), "source_usable": True, "adapter_selected": True}
    return value


def dependency(capability, source_id, order, *, timeframe="H1", requested=REQUESTED, cutoff="2026-08-17T01:00:00Z"):
    return {
        "dependency_order": order,
        "capability_name": capability,
        "capability_contract": CAPABILITY_CONTRACTS[capability],
        "capability_rule_version": f"{capability}_v1",
        "factual_availability": "AVAILABLE_PRESENT",
        "authoritative_result_id": f"result_{capability}",
        "source_snapshot_id": source_id,
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff,
        "configuration_fingerprint": f"configuration_{capability}",
        "controlled_invocation": True,
        "provenance_validation": "validated_controlled_dependency",
    }


def envelope(timeframe, capability, *, state="AVAILABLE_PRESENT", source_id=None, requested=REQUESTED, cutoff=None, dependencies=None):
    source_id = source_id or f"source_{timeframe.lower()}"
    cutoff = cutoff or f"2026-08-17T{(TIMEFRAME_ORDER.index(timeframe) + 1) if timeframe in TIMEFRAME_ORDER else 1:02d}:00:00Z"
    dependency_map = {
        "liquidity_events": [dependency("liquidity_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "order_block_intelligence": [dependency("displacement_intelligence", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "structural_dealing_range_intelligence": [dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff)],
        "premium_discount_intelligence": [
            dependency("market_structure", source_id, 1, timeframe=timeframe, requested=requested, cutoff=cutoff),
            dependency("structural_dealing_range_intelligence", source_id, 2, timeframe=timeframe, requested=requested, cutoff=cutoff),
        ],
    }
    return migrate_test_envelope({
        "factual_envelope_id": f"envelope_{timeframe.lower()}_{capability}" if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "factual_availability": state,
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "requested_evaluation_timestamp": requested,
        "effective_causal_cutoff": cutoff,
        "source_snapshot_id": source_id,
        "source_completion_state": "COMPLETED",
        "context_id": None,
        "capability": {"name": capability, "contract": CAPABILITY_CONTRACTS[capability], "rule_version": f"{capability}_v1", "configuration": {}},
        "authoritative_result": {} if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "authoritative_result_id": f"result_{timeframe.lower()}_{capability}" if state in {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT"} else None,
        "dependency_provenance": dependency_map.get(capability, []) if dependencies is None else dependencies,
        "availability_reason": "classified",
        "provenance": {"controlled_invocation": True},
        "diagnostics": {},
        "evidence": {},
        "metadata": {"contract": "trading.causal_factual_intelligence_envelope.v1", "identity_scope": "snapshot_deterministic"},
    })


def payload(*, context=None, envelopes=None, symbol="XAUUSD", requested=REQUESTED):
    return {
        "symbol": symbol,
        "requested_evaluation_timestamp": requested,
        "source_context": context or source_context(requested=requested),
        "factual_envelopes": envelopes or {
            timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER}
            for timeframe in TIMEFRAME_ORDER
        },
    }


def analyze(**kwargs):
    return CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(payload(**kwargs))


def test_v16_complete_context_has_exact_canonical_shape():
    result = analyze()
    assert result.context_state == "COMPLETE"
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    assert all(list(result.timeframes[name]["factual_capabilities"]) == list(CAPABILITY_ORDER) for name in TIMEFRAME_ORDER)
    assert result.diagnostics["required_timeframe_count"] == 7
    assert result.diagnostics["required_capability_count_per_timeframe"] == 10
    assert result.diagnostics["complete_timeframe_count"] == 7


@pytest.mark.parametrize("missing", TIMEFRAME_ORDER)
def test_v16_missing_timeframe_is_rejected(missing):
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER if timeframe != missing}
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


def test_v16_extra_timeframe_and_capability_are_rejected():
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    envelopes["W2"] = {capability: envelope("W2", capability) for capability in CAPABILITY_ORDER}
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)
    del envelopes["W2"]
    envelopes["H1"]["unknown"] = envelope("H1", "market_structure")
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


@pytest.mark.parametrize("field", ["source_snapshot_id", "effective_causal_cutoff", "timeframe", "requested_evaluation_timestamp"])
def test_v16_source_envelope_matching_is_exact(field):
    envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    if field == "source_snapshot_id":
        envelopes["H4"]["market_structure"][field] = "wrong_source"
    elif field == "effective_causal_cutoff":
        envelopes["H4"]["market_structure"][field] = "2026-08-17T99:00:00Z"
    elif field == "timeframe":
        envelopes["H4"]["market_structure"][field] = "H1"
    else:
        envelopes["H4"]["market_structure"][field] = "2026-08-17T03:00:00Z"
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


@pytest.mark.parametrize("state", ["AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"])
def test_v16_factual_states_are_preserved_and_complete_for_absence_only(state):
    if state == "NOT_EVALUATED":
        data = real_matrix("NOT_EVALUATED")
        result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    else:
        envelopes = {timeframe: {capability: envelope(timeframe, capability) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
        envelopes["H1"]["fvg_imbalance_intelligence"] = envelope("H1", "fvg_imbalance_intelligence", state=state)
        result = analyze(envelopes=envelopes)
    assert result.timeframes["H1"]["factual_capabilities"]["fvg_imbalance_intelligence"]["factual_availability"] == state
    expected = "COMPLETE" if state == "AVAILABLE_ABSENT" else state
    assert result.context_state == expected


def test_v16_incomplete_source_is_preserved_and_degrades_context():
    data = payload(context=source_context(completion="INCOMPLETE"))
    for group in data["factual_envelopes"].values():
        for value in group.values():
            value["source_completion_state"] = "INCOMPLETE"
    result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    assert result.context_state == "INCOMPLETE"
    assert result.timeframes["D1"]["source_completion_state"] == "INCOMPLETE"


def test_v16_dependent_provenance_is_validated():
    result = analyze()
    premium = result.timeframes["D1"]["factual_capabilities"]["premium_discount_intelligence"]
    assert [item["capability_name"] for item in premium["dependency_provenance"]] == ["market_structure", "structural_dealing_range_intelligence"]

    envelopes = payload()["factual_envelopes"]
    envelopes["D1"]["premium_discount_intelligence"]["dependency_provenance"][0]["source_snapshot_id"] = "wrong"
    with pytest.raises(ValueError):
        analyze(envelopes=envelopes)


def test_v16_identity_is_deterministic_and_source_or_envelope_sensitive():
    first = analyze()
    second = analyze()
    assert first.to_dict() == second.to_dict()
    changed = payload()["factual_envelopes"]
    changed["M5"]["candle_intelligence"]["factual_envelope_id"] = "changed"
    assert first.factual_context_id != analyze(envelopes=changed).factual_context_id
    assert first.identity_scope == "snapshot_deterministic"


def test_v16_historical_timestamp_requires_consistent_context_and_envelopes():
    historical = "2024-01-02T03:04:05Z"
    context = source_context(requested=historical)
    envelopes = {timeframe: {capability: envelope(timeframe, capability, requested=historical) for capability in CAPABILITY_ORDER} for timeframe in TIMEFRAME_ORDER}
    result = analyze(context=context, envelopes=envelopes, requested=historical)
    assert result.requested_evaluation_timestamp == historical
    envelopes["M1"]["market_structure"]["requested_evaluation_timestamp"] = REQUESTED
    with pytest.raises(ValueError):
        analyze(context=context, envelopes=envelopes, requested=historical)


def test_v16_rejects_raw_candles_and_raw_detector_results():
    invalid = payload()
    invalid["candle_history"] = []
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(invalid)
    invalid = payload()
    invalid["factual_envelopes"]["D1"]["market_structure"] = {"structure_state": "bullish_structure"}
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(invalid)


def test_v16_has_no_strategy_or_cross_timeframe_interpretation():
    result = analyze().to_dict()
    text = str(result).lower()
    for forbidden in ["buy", "sell", "signal", "setup", "confidence", "recommendation", "trade_bias", "confirmation", "confluence", "bullish_alignment", "bearish_alignment"]:
        assert forbidden not in text
    assert result["metadata"]["authority_scope"] == "read_only"


def test_v16_public_contract_is_bounded():
    result = analyze().to_dict()
    assert set(result) == {"symbol", "requested_evaluation_timestamp", "source_context_id", "factual_context_id", "identity_scope", "context_state", "timeframes", "diagnostics", "evidence", "metadata"}
    assert "approved_candle_history" not in result["evidence"]

def real_matrix(mode="AVAILABLE", *, configurations=None):
    """Actual snapshots/envelopes; NOT_EVALUATED/UNKNOWN are explicit source fixtures."""
    from copy import deepcopy
    from tests.test_trading_vertical_slice_v15 import structured_source
    from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY
    from ced_one.business_divisions.trading.causal_multi_timeframe_context import CAUSAL_MULTI_TIMEFRAME_CONTEXT
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS, CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE
    requested = "2026-08-18T12:00:00Z"
    sources, envelopes = {}, {}
    for timeframe in TIMEFRAME_ORDER:
        candles = deepcopy(structured_source()["approved_candle_history"])
        if mode in {"NO_CLOSED", "NOT_EVALUATED"}:
            candles = [dict(candles[0], timestamp=requested)]
        if mode == "INVALID":
            candles[0]["close"] = float("nan")
        source = CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe=timeframe,
            requested_evaluation_timestamp=requested, candle_history=candles)).to_dict()
        if mode == "NOT_EVALUATED":
            source.update(source_availability="NOT_EVALUATED", completion_state="UNKNOWN", availability_reason="explicit_not_evaluated_fixture")
        elif mode == "UNKNOWN":
            source["completion_state"] = "UNKNOWN"
        sources[timeframe] = source
        envelopes[timeframe] = {}
        for name in CAPABILITY_ORDER:
            adapter = ADAPTERS[CAPABILITY_CONTRACTS[name]]
            envelopes[timeframe][name] = CAUSAL_FACTUAL_INTELLIGENCE_ENVELOPE.analyze(dict(
                symbol="XAUUSD", timeframe=timeframe, requested_evaluation_timestamp=requested,
                causal_source=source, capability=dict(name=name, contract=adapter.contract, rule_version=adapter.rule_version,
                    configuration=(configurations or {}).get(name, {})))).to_dict()
    source = CAUSAL_MULTI_TIMEFRAME_CONTEXT.analyze(dict(symbol="XAUUSD", requested_evaluation_timestamp=requested, timeframe_sources=sources)).to_dict()
    return dict(symbol="XAUUSD", requested_evaluation_timestamp=requested, source_context=source, factual_envelopes=envelopes)


@pytest.mark.parametrize("mode,expected", [("NO_CLOSED", "UNAVAILABLE"), ("INVALID", "INVALID"), ("NOT_EVALUATED", "NOT_EVALUATED"), ("UNKNOWN", "UNAVAILABLE")])
def test_v2_authentic_nonexecution_matrix_preserves_seven_slots(mode, expected):
    data = real_matrix(mode)
    result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    assert result.context_state == expected
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    for group in data["factual_envelopes"].values():
        for value in group.values():
            assert value["factual_availability"] == expected
            assert value["provenance"]["controlled_invocation"] is False
            assert value["provenance"]["execution_progress"]["terminal"] == "NOT_STARTED"
            assert value["dependency_provenance"] == []


def test_v2_real_completed_and_dependency_unavailable_results_are_valid():
    data = real_matrix()
    result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    assert list(result.timeframes) == list(TIMEFRAME_ORDER)
    candle = data["factual_envelopes"]["H1"]["candle_intelligence"]
    assert candle["factual_availability"] == "AVAILABLE_PRESENT"
    assert candle["provenance"]["execution_progress"]["terminal"] == "COMPLETED"
    assert candle["authoritative_result_id"] and candle["factual_envelope_id"]


@pytest.mark.parametrize("change", ["legacy", "missing_progress", "invocation", "diagnostic", "identity", "version", "configuration", "dependency_id", "later_execution", "source", "context"])
def test_v2_deliberately_corrupted_envelopes_fail_closed(change):
    data = real_matrix("NO_CLOSED")
    value = data["factual_envelopes"]["H1"]["order_block_intelligence"]
    if change == "legacy":
        value["metadata"]["rule_version"] = "causal_factual_intelligence_envelope_v1"
    elif change == "missing_progress":
        value["provenance"].pop("execution_progress")
    elif change == "invocation":
        value["provenance"]["controlled_invocation"] = True
    elif change == "diagnostic":
        value["diagnostics"]["dependency_invocation_count"] = 1
    elif change == "identity":
        value["authoritative_result_id"] = "fabricated"
    elif change == "version":
        value["capability"]["rule_version"] = "wrong"
    elif change == "configuration":
        value["provenance"]["configuration_fingerprint"] = "wrong"
    elif change == "dependency_id":
        value["provenance"]["execution_progress"]["dependencies"][0]["authoritative_result_id"] = "fabricated"
    elif change == "later_execution":
        value["provenance"]["execution_progress"]["terminal"] = "COMPLETED"
    elif change == "context":
        value["context_id"] = "detached"
    else:
        value["source_completion_state"] = "COMPLETED"
    with pytest.raises(ValueError):
        CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)


@pytest.mark.parametrize("stage", ["INVOCATION_FAILED", "RESULT_VALIDATION_FAILED", "CLASSIFICATION_FAILED"])
def test_v2_actual_dependency_fault_envelopes_reach_consumer(monkeypatch, stage):
    from dataclasses import replace
    from ced_one.business_divisions.trading.displacement_intelligence import DisplacementIntelligenceAnalyzer
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import ADAPTERS
    contract = "trading.displacement_intelligence.v1"
    if stage == "CLASSIFICATION_FAILED":
        def broken_classifier(*args):
            raise ValueError("injected dependency classification failure")
        monkeypatch.setitem(ADAPTERS, contract, replace(ADAPTERS[contract], classify=broken_classifier))
    else:
        def broken_analyzer(*args):
            if stage == "INVOCATION_FAILED":
                raise ValueError("injected dependency invocation failure")
            return object()
        monkeypatch.setattr(DisplacementIntelligenceAnalyzer, "analyze", broken_analyzer)
    data = real_matrix()
    value = data["factual_envelopes"]["H1"]["order_block_intelligence"]
    progress = value["provenance"]["execution_progress"]
    assert progress["terminal"] == "NOT_STARTED"
    assert progress["dependencies"][0]["state"] == stage
    assert (progress["dependencies"][0]["authoritative_result_id"] is not None) == (stage == "CLASSIFICATION_FAILED")
    assert value["dependency_provenance"] == []
    result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    assert result.context_state == "INVALID"


def test_v2_later_terminal_failure_preserves_dependencies_and_context_identity(monkeypatch):
    from ced_one.business_divisions.trading.premium_discount_intelligence import PremiumDiscountAnalyzer
    baseline_data = real_matrix()
    baseline = baseline_data["factual_envelopes"]["H1"]["premium_discount_intelligence"]
    def broken(*args):
        raise ValueError("injected terminal failure after validated dependencies")
    monkeypatch.setattr(PremiumDiscountAnalyzer, "analyze", broken)
    failed_data = real_matrix()
    failed = failed_data["factual_envelopes"]["H1"]["premium_discount_intelligence"]
    assert failed["provenance"]["execution_progress"]["terminal"] == "INVOCATION_FAILED"
    assert failed["dependency_provenance"] == baseline["dependency_provenance"]
    first = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(failed_data)
    assert first.context_state == "INVALID"
    assert CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(real_matrix()).factual_context_id == first.factual_context_id
    assert CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(baseline_data).factual_context_id != first.factual_context_id


def test_v2_real_absent_and_completed_unavailable_are_distinct():
    from tests.test_trading_vertical_slice_v15 import source_result, candle, analyze as produce
    for count, expected in [(1, "UNAVAILABLE"), (25, "AVAILABLE_ABSENT")]:
        source = source_result(candles=[candle(i) for i in range(count)])
        produced = produce("trading.fvg_imbalance_intelligence.v1", source=source).to_dict()
        data = payload()
        slot = data["source_context"]["timeframes"]["H1"]
        slot.update(source_snapshot_id=source["source_snapshot_id"], effective_causal_cutoff=source["effective_causal_cutoff"])
        data["factual_envelopes"]["H1"] = {name: envelope("H1", name, source_id=source["source_snapshot_id"], cutoff=source["effective_causal_cutoff"]) for name in CAPABILITY_ORDER}
        data["factual_envelopes"]["H1"]["fvg_imbalance_intelligence"] = produced
        result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
        assert produced["factual_availability"] == expected
        assert produced["provenance"]["execution_progress"]["terminal"] == "COMPLETED"
        assert produced["authoritative_result"] is not None and produced["authoritative_result_id"]
        assert (produced["factual_envelope_id"] is not None) == (expected == "AVAILABLE_ABSENT")
        assert result.timeframes["H1"]["factual_capabilities"]["fvg_imbalance_intelligence"]["factual_availability"] == expected


@pytest.mark.parametrize("name,nested_key", [
    ("liquidity_events", "liquidity_config"),
    ("order_block_intelligence", "displacement_config"),
])
@pytest.mark.parametrize("configured", [False, True])
def test_v2_effective_configuration_real_producer_validation(name, nested_key, configured):
    from copy import deepcopy
    from ced_one.business_divisions.trading.causal_factual_intelligence_envelope import _configuration_fingerprint
    configuration = {"lookback_candles": 50} if configured else {}
    if configured and name == "liquidity_events":
        configuration[nested_key] = {"equal_level_tolerance": 0.75}
    original_request = deepcopy(configuration)
    data = real_matrix(configurations={name: configuration})
    produced = data["factual_envelopes"]["H1"][name]
    assert configuration == original_request
    assert produced["provenance"]["execution_progress"]["dependencies"][0]["state"] == "COMPLETED"
    before = deepcopy(data)
    result = CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(data)
    assert data == before
    assert result.timeframes["H1"]["factual_capabilities"][name]["factual_availability"] == produced["factual_availability"]
    for corruption in ("shape", "missing", "inconsistent", "unknown", "nested_unknown", "terminal_fingerprint", "dependency_fingerprint"):
        invalid = deepcopy(data)
        value = invalid["factual_envelopes"]["H1"][name]
        config = value["capability"]["configuration"]
        if corruption == "shape":
            value["capability"]["configuration"] = []
        elif corruption == "missing":
            del config[nested_key]["lookback_candles"]
        elif corruption == "inconsistent":
            config[nested_key]["lookback_candles"] += 1
        elif corruption == "unknown":
            config["unknown_field"] = 1
        elif corruption == "nested_unknown":
            config[nested_key]["unknown_field"] = 1
        elif corruption == "terminal_fingerprint":
            value["provenance"]["configuration_fingerprint"] = "configuration_wrong"
        else:
            for records in (value["dependency_provenance"], value["provenance"]["dependency_provenance"], value["evidence"]["dependency_provenance"]):
                records[0]["configuration_fingerprint"] = "configuration_wrong"
        if corruption in {"missing", "inconsistent", "unknown", "nested_unknown"}:
            for section in ("provenance", "evidence"):
                value[section]["configuration_fingerprint"] = _configuration_fingerprint(config)
        unchanged = deepcopy(invalid)
        with pytest.raises(ValueError):
            CAUSAL_FACTUAL_MULTI_TIMEFRAME_CONTEXT.analyze(invalid)
        assert invalid == unchanged
