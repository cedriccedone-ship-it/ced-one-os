from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from ced_one.business_divisions.trading.causal_snapshot_availability import (
    CANDLE_TIMESTAMP_SEMANTICS,
    RULE_VERSION,
    TIMEFRAME_DURATION_RULE_VERSION,
    VALID_TIMEFRAME_DURATIONS,
    CausalSnapshotAvailabilityAnalyzer,
)


TIMEFRAMES = list(VALID_TIMEFRAME_DURATIONS)


def timestamp(hours: int = 0) -> str:
    return (datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def candle(open_timestamp: str, *, open_price: float = 100.0, high: float = 101.0, low: float = 99.0, close: float = 100.5):
    return {
        "timestamp": open_timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def payload(*, timeframe: str = "H1", evaluation_timestamp: str = timestamp(3), history=None, symbol: str = "XAUUSD"):
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_evaluation_timestamp": evaluation_timestamp,
        "candle_history": [candle(timestamp(index)) for index in range(3)] if history is None else history,
    }


def analyze(**kwargs):
    return CausalSnapshotAvailabilityAnalyzer().analyze(payload(**kwargs))


def test_v13_contract_and_source_only_boundary():
    result = analyze()
    assert result.source_availability == "AVAILABLE"
    assert result.completion_state == "COMPLETED"
    assert result.effective_causal_cutoff == timestamp(3)
    assert result.source_snapshot_id
    assert result.metadata["contract"] == "trading.causal_snapshot_availability.v1"
    assert result.metadata["identity_scope"] == "snapshot_deterministic"
    assert result.metadata["candle_timestamp_semantics"] == "open_time"
    assert result.metadata["timeframe_duration_rule_version"] == TIMEFRAME_DURATION_RULE_VERSION
    assert result.approved_candle_history
    assert all("source_snapshot_id" not in candle_row for candle_row in result.approved_candle_history)


@pytest.mark.parametrize("timeframe", TIMEFRAMES)
def test_v13_accepts_each_supported_timeframe_and_applies_its_duration(timeframe):
    duration = VALID_TIMEFRAME_DURATIONS[timeframe]
    evaluation = datetime(2026, 8, 16, tzinfo=timezone.utc) + duration
    result = analyze(timeframe=timeframe, evaluation_timestamp=evaluation.isoformat().replace("+00:00", "Z"), history=[candle(timestamp())])
    assert result.source_availability == "AVAILABLE"
    assert result.effective_causal_cutoff == evaluation.isoformat().replace("+00:00", "Z")
    assert result.evidence["timeframe_duration"] == duration.total_seconds()


def test_v13_open_time_semantics_and_exact_completion_boundary():
    result = analyze(
        timeframe="M30",
        evaluation_timestamp="2026-08-16T00:30:00Z",
        history=[candle("2026-08-16T00:00:00Z")],
    )
    assert result.source_availability == "AVAILABLE"
    assert result.completion_state == "COMPLETED"
    assert result.effective_causal_cutoff == "2026-08-16T00:30:00Z"
    assert result.evidence["candle_timestamp_semantics"] == CANDLE_TIMESTAMP_SEMANTICS


def test_v13_incomplete_current_candle_is_excluded_with_prior_completed_history():
    result = analyze(
        timeframe="H1",
        evaluation_timestamp="2026-08-16T01:30:00Z",
        history=[candle("2026-08-16T00:00:00Z"), candle("2026-08-16T01:00:00Z")],
    )
    assert result.source_availability == "AVAILABLE"
    assert result.completion_state == "INCOMPLETE"
    assert result.diagnostics["incomplete_candle_count"] == 1
    assert result.diagnostics["approved_candle_count"] == 1
    assert [item["timestamp"] for item in result.approved_candle_history] == ["2026-08-16T00:00:00Z"]
    assert result.effective_causal_cutoff == "2026-08-16T01:00:00Z"


def test_v13_no_completed_history_is_unavailable_without_identity_or_cutoff():
    result = analyze(
        timeframe="H1",
        evaluation_timestamp="2026-08-16T00:30:00Z",
        history=[candle("2026-08-16T00:00:00Z")],
    )
    assert result.source_availability == "UNAVAILABLE"
    assert result.availability_reason == "incomplete_current_candle"
    assert result.completion_state == "INCOMPLETE"
    assert result.approved_candle_history == []
    assert result.effective_causal_cutoff is None
    assert result.source_snapshot_id is None


def test_v13_future_open_candle_is_invalid_and_not_filtered():
    history = [candle("2026-08-16T00:00:00Z"), candle("2026-08-16T03:00:00Z")]
    result = analyze(evaluation_timestamp="2026-08-16T02:00:00Z", history=history)
    assert result.source_availability == "INVALID"
    assert result.availability_reason == "future_source_data"
    assert result.approved_candle_history == []
    assert result.effective_causal_cutoff is None
    assert result.source_snapshot_id is None
    assert result.diagnostics["future_candle_count"] == 1


@pytest.mark.parametrize(
    "history",
    [
        [],
        [candle("2026-08-16T01:00:00Z"), candle("2026-08-16T00:00:00Z")],
        [candle("2026-08-16T00:00:00Z"), candle("2026-08-16T00:00:00Z")],
        [{"timestamp": "2026-08-16T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0}],
        [candle("2026-08-16T00:00:00Z", high=98.0)],
        [candle("2026-08-16T00:00:00Z", close=float("nan"))],
        [candle("2026-08-16T00:00:00Z", close=0.0)],
        [candle("not-a-timestamp")],
    ],
)
def test_v13_invalid_or_empty_history_is_fail_closed(history):
    result = analyze(evaluation_timestamp="2026-08-16T03:00:00Z", history=history)
    if history:
        assert result.source_availability == "INVALID"
        assert result.source_snapshot_id is None
    else:
        assert result.source_availability == "UNAVAILABLE"
        assert result.availability_reason == "empty_source_history"
    assert result.approved_candle_history == []


@pytest.mark.parametrize("field,value", [("symbol", "EURUSD"), ("timeframe", "W2")])
def test_v13_rejects_unsupported_symbol_or_timeframe(field, value):
    values = {"symbol": "XAUUSD", "timeframe": "H1"}
    values[field] = value
    result = CausalSnapshotAvailabilityAnalyzer().analyze({**payload(), **values})
    assert result.source_availability == "INVALID"
    assert result.availability_reason == "invalid_source"
    assert result.source_snapshot_id is None


@pytest.mark.parametrize("evaluation_timestamp", ["", "not-a-timestamp", "2026-08-16T03:00:00"])
def test_v13_rejects_malformed_or_timezone_naive_evaluation_timestamp(evaluation_timestamp):
    result = analyze(evaluation_timestamp=evaluation_timestamp)
    assert result.source_availability == "INVALID"
    assert result.availability_reason == "invalid_timestamp"
    assert result.source_snapshot_id is None


def test_v13_normalizes_timezone_aware_comparisons_without_lexical_ordering():
    result = analyze(
        evaluation_timestamp="2026-08-16T04:00:00+01:00",
        history=[candle("2026-08-16T02:00:00Z")],
    )
    assert result.source_availability == "AVAILABLE"
    assert result.effective_causal_cutoff == "2026-08-16T03:00:00Z"


def test_v13_identity_is_deterministic_and_sensitive_to_relevant_inputs():
    first = analyze()
    second = analyze()
    changed_history = analyze(history=[candle(timestamp(), close=101.0), candle(timestamp(1), close=102.0)])
    changed_time = analyze(evaluation_timestamp=timestamp(4))
    changed_timeframe = analyze(timeframe="M30", evaluation_timestamp="2026-08-16T03:00:00Z")
    assert first.to_dict() == second.to_dict()
    assert first.source_snapshot_id == second.source_snapshot_id
    assert first.source_snapshot_id != changed_history.source_snapshot_id
    assert first.source_snapshot_id != changed_time.source_snapshot_id
    assert first.source_snapshot_id != changed_timeframe.source_snapshot_id
    assert first.metadata["identity_scope"] == "snapshot_deterministic"


def test_v13_evidence_is_minimal_and_deterministic_without_history_duplication():
    result = analyze()
    required = {
        "candle_timestamp_semantics", "timeframe_duration", "timeframe_duration_rule_version",
        "requested_evaluation_timestamp", "effective_causal_cutoff", "first_approved_candle_timestamp",
        "last_approved_candle_timestamp", "last_completed_candle_timestamp", "source_snapshot_id",
        "availability_reason",
    }
    assert set(result.evidence) >= required
    assert "approved_candle_history" not in result.evidence
    assert result.evidence == analyze().evidence
    assert result.diagnostics == analyze().diagnostics


def test_v13_does_not_report_detector_availability_or_compose_timeframes():
    result = analyze().to_dict()
    text = str(result).lower()
    assert "available_present" not in text
    assert "available_absent" not in text
    assert "htf" not in text
    assert "mtf" not in text
    assert "ltf" not in text
    assert "hierarchy" not in text
    for forbidden in [
        "buy", "sell", "long", "short", "entry", "exit", "stop_loss", "take_profit", "signal",
        "setup", "confidence", "probability", "recommendation", "expected_direction", "execution_command",
    ]:
        assert re.search(rf"\b{re.escape(forbidden)}\b", text) is None


def test_v13_is_source_boundary_only_and_does_not_invoke_market_analyzers():
    result = analyze()
    assert result.metadata["observation_only"] is True
    assert result.metadata["authority_scope"] == "read_only"
    assert set(result.to_dict()) == {
        "symbol", "timeframe", "requested_evaluation_timestamp", "effective_causal_cutoff",
        "source_snapshot_id", "source_availability", "availability_reason", "completion_state",
        "approved_candle_history", "diagnostics", "evidence", "metadata",
    }


def test_v13_approved_history_is_copied_and_chronological():
    original = candle("2026-08-16T00:00:00Z")
    result = analyze(evaluation_timestamp="2026-08-16T02:00:00Z", history=[original, candle("2026-08-16T01:00:00Z")])
    assert result.source_availability == "AVAILABLE"
    assert result.approved_candle_history[0] is not original
    original["close"] = 999.0
    assert result.approved_candle_history[0]["close"] != 999.0
    assert [item["timestamp"] for item in result.approved_candle_history] == sorted(item["timestamp"] for item in result.approved_candle_history)


def test_v13_does_not_add_package_or_registry_integration():
    result = analyze()
    assert result.metadata["contract"] == "trading.causal_snapshot_availability.v1"
    assert "specialist" not in result.metadata
    assert "resolver" not in result.metadata
    assert RULE_VERSION == "causal_snapshot_availability_v1"