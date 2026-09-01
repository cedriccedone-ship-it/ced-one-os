"""Causally available factual event chronology over Slice #16 and #15."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable

TIMEFRAME_ORDER = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
TIMEFRAME_RANK = {timeframe: index for index, timeframe in enumerate(TIMEFRAME_ORDER)}
MANIFEST_VERSION = "causal_available_factual_event_manifest_v1"
RULE_VERSION = "causal_available_factual_event_chronology_v1"
CONTRACT = "trading.causal_available_factual_event_chronology.v1"
IDENTITY_SCOPE = "snapshot_deterministic"
FACTUAL_STATES = {"AVAILABLE_PRESENT", "AVAILABLE_ABSENT", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
CHRONOLOGY_STATES = {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"}
COVERAGE_STATES = {"FULLY_COVERED", "SOURCE_BOUNDED", "TRUNCATED", "UNKNOWN_COVERAGE"}
EVENT_FAMILIES = {
    "liquidity_events": ("liquidity_touch", "liquidity_sweep", "liquidity_close_beyond"),
    "fvg_imbalance_intelligence": ("fvg_created", "fvg_touched", "fvg_partial_fill", "fvg_fully_filled"),
    "displacement_intelligence": ("displacement",),
    "order_block_intelligence": ("order_block_created", "order_block_wick_touch", "order_block_body_revisit", "order_block_close_through"),
    "structural_dealing_range_intelligence": ("structural_range_created",),
}
EVENT_CAPABILITIES = tuple(EVENT_FAMILIES)
FAMILY_RANK = {family: index for index, family in enumerate(family for families in EVENT_FAMILIES.values() for family in families)}


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed.astimezone(timezone.utc)


def _text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _hash(prefix: str, value: Any) -> str:
    encoded = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise ValueError("Expected a typed or serialized repository result.")
    return value


@dataclass
class CausalFactualEventChronologyResult:
    symbol: str
    requested_evaluation_timestamp: str
    chronology_id: str | None
    identity_scope: str
    chronology_state: str
    coverage_state: str
    source_factual_context_id: str
    source_composition_id: str | None
    event_source_manifest_version: str
    timeframes: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    ordering_groups: list[dict[str, Any]] = field(default_factory=list)
    chronology_edges: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "requested_evaluation_timestamp": self.requested_evaluation_timestamp,
            "chronology_id": self.chronology_id, "identity_scope": self.identity_scope,
            "chronology_state": self.chronology_state, "coverage_state": self.coverage_state,
            "source_factual_context_id": self.source_factual_context_id,
            "source_composition_id": self.source_composition_id,
            "event_source_manifest_version": self.event_source_manifest_version,
            "timeframes": self.timeframes, "events": self.events, "ordering_groups": self.ordering_groups,
            "chronology_edges": self.chronology_edges, "diagnostics": self.diagnostics,
            "evidence": self.evidence, "metadata": self.metadata,
        }


class CausalFactualEventChronologyAnalyzer:
    def analyze(self, payload: dict[str, Any]) -> CausalFactualEventChronologyResult:
        if not isinstance(payload, dict) or set(payload) - {"factual_context", "factual_envelopes", "composition"}:
            raise ValueError("Chronology input requires only factual_context, factual_envelopes, and optional composition.")
        context = _as_dict(payload.get("factual_context"))
        envelopes = payload.get("factual_envelopes")
        if not isinstance(envelopes, dict) or set(envelopes) != set(TIMEFRAME_ORDER):
            raise ValueError("factual_envelopes must contain exactly the seven canonical timeframes.")
        self._validate_context(context)
        composition_id = self._validate_composition(payload.get("composition"), context)
        events: list[dict[str, Any]] = []
        timeframe_records: dict[str, dict[str, Any]] = {}
        coverage: dict[str, dict[str, Any]] = {}
        state_rank = {"COMPLETE": 0, "INCOMPLETE": 1, "NOT_EVALUATED": 2, "UNAVAILABLE": 3, "INVALID": 4}
        states: list[str] = []
        for timeframe in TIMEFRAME_ORDER:
            context_record = _as_dict(context["timeframes"][timeframe])
            group = envelopes[timeframe]
            if not isinstance(group, dict) or set(group) != set(context_record["factual_capabilities"]):
                raise ValueError(f"Envelope matrix does not exactly match Slice #16 capability profile for {timeframe}.")
            family_states: dict[str, str] = {}
            family_ids: dict[str, list[str]] = {}
            coverage[timeframe] = {}
            for capability in EVENT_CAPABILITIES:
                envelope = self._validate_envelope(group[capability], context_record, capability, context)
                normalized = self._normalize(envelope, context["factual_context_id"])
                events.extend(normalized)
                family_state = envelope["factual_availability"]
                family_states[capability] = family_state
                family_ids[capability] = [item["chronology_event_id"] for item in normalized]
                coverage[timeframe][capability] = self._coverage(envelope, normalized)
            state = self._timeframe_state(context_record, family_states)
            states.append(state)
            timeframe_records[timeframe] = {
                "timeframe": timeframe,
                "source_snapshot_id": context_record["source_snapshot_id"],
                "effective_causal_cutoff": context_record["effective_causal_cutoff"],
                "event_source_states": family_states,
                "coverage": coverage[timeframe],
                "event_ids": family_ids,
            }
        chronology_state = max(states, key=lambda state: state_rank[state])
        events = self._deduplicate(events)
        events.sort(key=lambda item: (_parse_timestamp(item["event_timestamp"]), item["timeframe_rank"], FAMILY_RANK[item["event_family"]], item["source_event_id"], item["chronology_event_id"]))
        groups = self._groups(events)
        edges = self._edges(groups)
        coverage_values = [item["coverage_state"] for by_capability in coverage.values() for item in by_capability.values()]
        coverage_state = "TRUNCATED" if "TRUNCATED" in coverage_values else "SOURCE_BOUNDED" if "SOURCE_BOUNDED" in coverage_values else "UNKNOWN_COVERAGE" if "UNKNOWN_COVERAGE" in coverage_values else "FULLY_COVERED"
        chronology_id = _hash("factual_event_chronology_", [RULE_VERSION, MANIFEST_VERSION, context["factual_context_id"], composition_id, context["symbol"], context["requested_evaluation_timestamp"], events, coverage, groups])
        return CausalFactualEventChronologyResult(
            symbol=context["symbol"], requested_evaluation_timestamp=context["requested_evaluation_timestamp"], chronology_id=chronology_id,
            identity_scope=IDENTITY_SCOPE, chronology_state=chronology_state, coverage_state=coverage_state,
            source_factual_context_id=context["factual_context_id"], source_composition_id=composition_id,
            event_source_manifest_version=MANIFEST_VERSION, timeframes=timeframe_records, events=events,
            ordering_groups=groups, chronology_edges=edges,
            diagnostics={"required_timeframe_count": 7, "event_source_capability_count": len(EVENT_CAPABILITIES), "normalized_event_count": len(events), "ordering_group_count": len(groups), "chronology_edge_count": len(edges), "chronology_truncated_count": 0},
            evidence={"source_factual_context_id": context["factual_context_id"], "source_composition_id": composition_id, "event_source_manifest": EVENT_FAMILIES, "coverage": coverage, "chronology_state": chronology_state, "coverage_state": coverage_state, "identity_scope": IDENTITY_SCOPE},
            metadata={"contract": CONTRACT, "rule_version": RULE_VERSION, "identity_scope": IDENTITY_SCOPE, "internal_factual_infrastructure": True, "chronology_only": True, "observation_only": True, "advisory_output": False, "strategy_output": False, "execution_output": False, "authority_scope": "read_only"},
        )

    @staticmethod
    def _validate_context(context: dict[str, Any]) -> None:
        if context.get("metadata", {}).get("contract") != "trading.causal_factual_multi_timeframe_context.v1" or context.get("identity_scope") != IDENTITY_SCOPE:
            raise ValueError("Unsupported Slice #16 factual context.")
        if context.get("context_state") not in {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "INVALID", "NOT_EVALUATED"} or set(context.get("timeframes", {})) != set(TIMEFRAME_ORDER):
            raise ValueError("Malformed Slice #16 factual context.")
        _parse_timestamp(context.get("requested_evaluation_timestamp"))

    @staticmethod
    def _validate_composition(composition: Any, context: dict[str, Any]) -> str | None:
        if composition is None:
            return None
        value = _as_dict(composition)
        if value.get("metadata", {}).get("contract") != "trading.factual_market_context_composition.v1" or value.get("source_factual_context_id") != context["factual_context_id"]:
            raise ValueError("Optional Slice #18 composition does not match Slice #16 context.")
        return value.get("composition_id")

    def _validate_envelope(self, value: Any, context_record: dict[str, Any], capability: str, context: dict[str, Any]) -> dict[str, Any]:
        envelope = _as_dict(value)
        reference = context_record["factual_capabilities"].get(capability)
        if not isinstance(reference, dict) or envelope.get("metadata", {}).get("contract") != "trading.causal_factual_intelligence_envelope.v1":
            raise ValueError("Malformed or detached Slice #15 envelope.")
        terminal_fingerprint = envelope.get("provenance", {}).get("configuration_fingerprint")
        if not terminal_fingerprint or terminal_fingerprint != envelope.get("evidence", {}).get("configuration_fingerprint"):
            raise ValueError("Slice #15 terminal configuration fingerprint is missing or inconsistent.")
        matches = [
            envelope.get("symbol") == context["symbol"], envelope.get("timeframe") == context_record["timeframe"],
            envelope.get("requested_evaluation_timestamp") == context["requested_evaluation_timestamp"],
            envelope.get("source_snapshot_id") == context_record["source_snapshot_id"],
            envelope.get("effective_causal_cutoff") == context_record["effective_causal_cutoff"],
            envelope.get("factual_envelope_id") == reference.get("factual_envelope_id"),
            envelope.get("authoritative_result_id") == reference.get("authoritative_result_id"),
            envelope.get("factual_availability") == reference.get("factual_availability"),
            envelope.get("capability", {}).get("name") == capability,
        ]
        if not all(matches) or envelope.get("factual_availability") not in FACTUAL_STATES:
            raise ValueError("Slice #15 envelope does not match its authoritative Slice #16 reference.")
        if envelope["factual_availability"] == "AVAILABLE_PRESENT" and not isinstance(envelope.get("authoritative_result"), dict):
            raise ValueError("Available event source envelope requires an authoritative result.")
        return envelope

    def _normalize(self, envelope: dict[str, Any], factual_context_id: str) -> list[dict[str, Any]]:
        if envelope["factual_availability"] != "AVAILABLE_PRESENT":
            return []
        capability = envelope["capability"]["name"]
        normalizers: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
            "liquidity_events": self._liquidity_events,
            "fvg_imbalance_intelligence": self._fvg,
            "displacement_intelligence": self._displacement,
            "order_block_intelligence": self._order_blocks,
            "structural_dealing_range_intelligence": self._ranges,
        }
        result = envelope["authoritative_result"]
        rows = normalizers[capability](result)
        events = []
        for row in rows:
            timestamp = _text(_parse_timestamp(row.pop("event_timestamp")))
            cutoff = _parse_timestamp(envelope["effective_causal_cutoff"])
            if _parse_timestamp(timestamp) > cutoff:
                raise ValueError("Normalized event is after its causal cutoff.")
            descriptor = {**row, "event_timestamp": timestamp}
            event = {
                "source_event_id": row["source_event_id"], "event_family": row["event_family"], "source_event_type": row["source_event_type"],
                "capability_name": capability, "capability_contract": envelope["capability"]["contract"], "capability_rule_version": envelope["capability"]["rule_version"],
                "symbol": envelope["symbol"], "timeframe": envelope["timeframe"], "timeframe_rank": TIMEFRAME_RANK[envelope["timeframe"]], "event_time_semantics": row["event_time_semantics"],
                "event_timestamp": timestamp, "created_at": row.get("created_at"), "confirmed_at": row.get("confirmed_at"),
                "requested_evaluation_timestamp": envelope["requested_evaluation_timestamp"], "effective_causal_cutoff": envelope["effective_causal_cutoff"],
                "source_snapshot_id": envelope["source_snapshot_id"], "factual_envelope_id": envelope["factual_envelope_id"], "authoritative_result_id": envelope["authoritative_result_id"],
                "configuration_fingerprint": envelope["provenance"]["configuration_fingerprint"], "factual_availability": envelope["factual_availability"],
                "source_event_state": row.get("source_event_state"), "dependency_provenance_reference": envelope["dependency_provenance"], "descriptor": descriptor,
            }
            event["chronology_event_id"] = _hash("factual_event_", [RULE_VERSION, MANIFEST_VERSION, factual_context_id, event])
            events.append(event)
        return events

    @staticmethod
    def _liquidity_events(result: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"source_event_id": item["event_id"], "event_family": item["event_type"], "source_event_type": item["source_interaction_type"], "event_time_semantics": "event_timestamp", "event_timestamp": item["event_timestamp"], "created_at": item.get("level_created_at"), "confirmed_at": None, "source_event_state": None} for item in result.get("liquidity_events", [])]

    @staticmethod
    def _fvg(result: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for fvg in result.get("fair_value_gaps", []):
            rows.append({"source_event_id": fvg["fvg_id"], "event_family": "fvg_created", "source_event_type": fvg["rule_branch"], "event_time_semantics": "created_at", "event_timestamp": fvg["created_at"], "created_at": fvg["created_at"], "confirmed_at": fvg.get("confirmed_at"), "source_event_state": fvg.get("current_status")})
            for interaction in fvg.get("interactions", []):
                event_type = interaction.get("event_type")
                family = {"fvg_wick_touch": "fvg_touched", "fvg_partial_fill": "fvg_partial_fill", "fvg_fully_filled": "fvg_fully_filled"}.get(event_type)
                if family:
                    rows.append({"source_event_id": f"{fvg['fvg_id']}:{interaction['candle_timestamp']}:{event_type}", "event_family": family, "source_event_type": event_type, "event_time_semantics": "candle_timestamp", "event_timestamp": interaction["candle_timestamp"], "created_at": fvg["created_at"], "confirmed_at": None, "source_event_state": interaction.get("resulting_status")})
        return rows

    @staticmethod
    def _displacement(result: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"source_event_id": item["event_id"], "event_family": "displacement", "source_event_type": item["direction"], "event_time_semantics": "created_at", "event_timestamp": item["created_at"], "created_at": item["created_at"], "confirmed_at": item.get("confirmed_at"), "source_event_state": None} for item in result.get("displacement_events", [])]

    @staticmethod
    def _order_blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for block in result.get("order_blocks", []):
            rows.append({"source_event_id": block["order_block_id"], "event_family": "order_block_created", "source_event_type": block["direction"], "event_time_semantics": "created_at", "event_timestamp": block["created_at"], "created_at": block["created_at"], "confirmed_at": block.get("confirmed_at"), "source_event_state": block.get("current_state")})
            for interaction in block.get("interactions", []):
                rows.append({"source_event_id": interaction["interaction_id"], "event_family": interaction["event_type"], "source_event_type": interaction["event_type"], "event_time_semantics": "candle_timestamp", "event_timestamp": interaction["candle_timestamp"], "created_at": block["created_at"], "confirmed_at": None, "source_event_state": interaction.get("resulting_state")})
        return rows

    @staticmethod
    def _ranges(result: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"source_event_id": item["range_id"], "event_family": "structural_range_created", "source_event_type": item["chronological_order"], "event_time_semantics": "created_at", "event_timestamp": item["created_at"], "created_at": item["created_at"], "confirmed_at": item.get("confirmed_at"), "source_event_state": None} for item in result.get("structural_ranges", [])]

    @staticmethod
    def _coverage(envelope: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        result = envelope.get("authoritative_result") or {}
        diagnostics = result.get("diagnostics", {})
        truncated = sum(value for key, value in diagnostics.items() if "truncated" in key and isinstance(value, int))
        state = "TRUNCATED" if truncated else "SOURCE_BOUNDED" if any(key in diagnostics for key in ["pre_retention_range_count", "source_interaction_count", "candidate_index_range"]) else "UNKNOWN_COVERAGE"
        if envelope["factual_availability"] == "AVAILABLE_ABSENT":
            state = "FULLY_COVERED"
        timestamps = [item["event_timestamp"] for item in events]
        return {"factual_availability": envelope["factual_availability"], "coverage_state": state, "evaluated_empty_event_set": envelope["factual_availability"] == "AVAILABLE_ABSENT", "source_event_count": len(events), "normalized_event_count": len(events), "deduplicated_event_count": 0, "source_truncated_count": truncated, "chronology_truncated_count": 0, "earliest_available_event_timestamp": min(timestamps) if timestamps else None, "latest_available_event_timestamp": max(timestamps) if timestamps else None}

    @staticmethod
    def _timeframe_state(record: dict[str, Any], family_states: dict[str, str]) -> str:
        if record["factual_context_state"] == "INVALID" or "INVALID" in family_states.values(): return "INVALID"
        if record["factual_context_state"] == "UNAVAILABLE" or "UNAVAILABLE" in family_states.values(): return "UNAVAILABLE"
        if record["factual_context_state"] == "NOT_EVALUATED" or "NOT_EVALUATED" in family_states.values(): return "NOT_EVALUATED"
        return "INCOMPLETE" if record["factual_context_state"] == "INCOMPLETE" else "COMPLETE"

    @staticmethod
    def _deduplicate(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for event in events:
            key = (event["source_snapshot_id"], event["capability_contract"], event["event_family"], event["source_event_id"])
            existing = deduplicated.get(key)
            if existing is not None and _canonical(existing) != _canonical(event):
                raise ValueError("Conflicting duplicate normalized event identity.")
            deduplicated[key] = event
        return list(deduplicated.values())

    @staticmethod
    def _groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for event in events:
            if not groups or groups[-1]["event_timestamp"] != event["event_timestamp"]:
                groups.append({"chronology_group_index": len(groups), "event_timestamp": event["event_timestamp"], "event_ids": []})
            groups[-1]["event_ids"].append(event["chronology_event_id"])
        return groups

    @staticmethod
    def _edges(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        edges = []
        for previous, following in zip(groups, groups[1:]):
            edges.append({"from_group_index": previous["chronology_group_index"], "to_group_index": following["chronology_group_index"], "ordering": "BEFORE"})
        return edges


CAUSAL_FACTUAL_EVENT_CHRONOLOGY = CausalFactualEventChronologyAnalyzer()

__all__ = ["CAUSAL_FACTUAL_EVENT_CHRONOLOGY", "CausalFactualEventChronologyAnalyzer", "CausalFactualEventChronologyResult", "CONTRACT", "EVENT_FAMILIES", "MANIFEST_VERSION", "RULE_VERSION"]