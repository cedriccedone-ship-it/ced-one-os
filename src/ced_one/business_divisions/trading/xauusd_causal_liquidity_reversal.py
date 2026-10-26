"""Strategy #1 v0.2, Revision 2.1: bounded causal replay, without authority.

The caller supplies five #13 snapshots and a fixed evidence domain. Every
detector invocation uses a completed prefix. This module owns strategy meaning;
the existing factual owners retain ownership of detection.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json

from .causal_snapshot_availability import validate_source, VALID_TIMEFRAME_DURATIONS
from .validation import parse_timestamp
from .market_structure import MarketStructureAnalyzer
from .order_block_intelligence import OrderBlockIntelligenceAnalyzer, OrderBlockIntelligenceConfig
from .liquidity_intelligence import LiquidityIntelligenceAnalyzer, LiquidityIntelligenceConfig
from .liquidity_events import LiquidityEventsAnalyzer
from .displacement_intelligence import DisplacementIntelligenceAnalyzer, DisplacementIntelligenceConfig
from .fvg_imbalance_intelligence import FVGImbalanceIntelligenceAnalyzer, FVGIntelligenceConfig
from . import (market_structure, order_block_intelligence, liquidity_intelligence,
               liquidity_events, displacement_intelligence, fvg_imbalance_intelligence)

CONTRACT = "trading.xauusd_causal_liquidity_reversal.assessment.v0.2"
DEFINITION_CONTRACT = "trading.xauusd_causal_liquidity_reversal.definition.v0.2"
STRATEGY_ID = "xauusd_causal_liquidity_reversal"
STRATEGY_VERSION = "0.2"
RULE_VERSION = "revision_2.1"
TIMEFRAMES = ("H4", "H1", "M15", "M5", "M1")
AUTHORITY = {"trade_decision": False, "financial_risk": False, "execution": False}
FACTUAL_RULES = {module.__name__.rsplit(".", 1)[-1]: module.RULE_VERSION for module in
                 (market_structure, order_block_intelligence, liquidity_intelligence,
                  liquidity_events, displacement_intelligence, fvg_imbalance_intelligence)}


def identity(prefix, value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return prefix + hashlib.sha256(encoded.encode()).hexdigest()


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label} requires exactly {sorted(keys)}.")


def normalize_strategy_definition(value):
    exact(value, {"contract", "strategy_id", "strategy_version", "rule_version", "instrument",
                  "direction", "configuration"}, "Strategy definition")
    for key, expected in (("contract", DEFINITION_CONTRACT), ("strategy_id", STRATEGY_ID),
                          ("strategy_version", STRATEGY_VERSION), ("rule_version", RULE_VERSION),
                          ("instrument", "XAUUSD")):
        if value[key] != expected:
            raise ValueError("Unsupported strategy " + key)
    if value["direction"] not in ("LONG", "SHORT"):
        raise ValueError("Strategy direction must be LONG or SHORT.")
    config = deepcopy(value["configuration"])
    exact(config, {"history_starts", "founding_start", "founding_end", "windows_seconds",
                   "order_block", "liquidity", "displacement", "fvg"}, "Strategy configuration")
    exact(config["history_starts"], TIMEFRAMES, "History starts")
    start, end = (parse_timestamp(config[k]) for k in ("founding_start", "founding_end"))
    if end < start:
        raise ValueError("Founding end precedes start.")
    for tf in TIMEFRAMES:
        left = parse_timestamp(config["history_starts"][tf])
        if left + 3 * VALID_TIMEFRAME_DURATIONS[tf] > start:
            raise ValueError("History domain must include pivot confirmation context before founding.")
        config["history_starts"][tf] = stamp(left)
    config.update(founding_start=stamp(start), founding_end=stamp(end))
    exact(config["windows_seconds"], {"E1", "R1", "K1", "RT1", "T1"}, "Stage windows")
    if any(type(v) is not int or v <= 0 for v in config["windows_seconds"].values()):
        raise ValueError("Windows must be positive integer elapsed seconds.")
    # Normalize defaults through their owners; nested lookback belongs to #10.
    ob = OrderBlockIntelligenceConfig.from_payload(config["order_block"]).as_dict()
    ob["displacement_config"].pop("lookback_candles")
    config["order_block"] = ob
    for key, owner in (("liquidity", LiquidityIntelligenceConfig),
                       ("displacement", DisplacementIntelligenceConfig), ("fvg", FVGIntelligenceConfig)):
        config[key] = owner.from_payload(config[key]).as_dict()
    def validate_numbers(mapping):
        for key, item in mapping.items():
            if isinstance(item, dict):
                validate_numbers(item)
            elif type(item) is bool and not key.startswith("include_"):
                raise ValueError("Boolean is not a numeric configuration value: " + key)
    validate_numbers(config)
    # JSON is the public contract, not arbitrary config instances/nonfinite values.
    identity("", config)
    normalized = {**deepcopy(value), "configuration": config}
    return normalized


@dataclass(frozen=True)
class StrategyAssessment:
    payload: dict

    def to_dict(self):
        return deepcopy(self.payload)


class _Unknown(Exception):
    pass


class _Replay:
    def __init__(self, payload):
        exact(payload, {"strategy_definition", "as_of", "sources", "setup_ordinal"}, "Assessment input")
        self.definition = normalize_strategy_definition(payload["strategy_definition"])
        self.config = self.definition["configuration"]
        self.now = parse_timestamp(payload["as_of"])
        self.ordinal = payload["setup_ordinal"]
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("setup_ordinal must be a nonnegative integer.")
        exact(payload["sources"], TIMEFRAMES, "Causal sources")
        self.histories = {}
        self.starts = {tf: parse_timestamp(v) for tf, v in self.config["history_starts"].items()}
        for tf in TIMEFRAMES:
            source = validate_source(payload["sources"][tf])
            if source["source_availability"] == "INVALID":
                raise ValueError("Invalid factual source: " + tf)
            if source["timeframe"] != tf or parse_timestamp(source["requested_evaluation_timestamp"]) != self.now:
                raise ValueError("Source timeframe/as-of mismatch.")
            candles = [{k: c[k] for k in ("timestamp", "open", "high", "low", "close")}
                       for c in source["approved_candle_history"]]
            for a, b in zip(candles, candles[1:]):
                if parse_timestamp(b["timestamp"]) < parse_timestamp(a["timestamp"]) + VALID_TIMEFRAME_DURATIONS[tf]:
                    raise ValueError("Overlapping source intervals: " + tf)
            self.histories[tf] = [c for c in candles if parse_timestamp(c["timestamp"]) >= self.starts[tf]]
        self.direction = "bullish" if self.definition["direction"] == "LONG" else "bearish"
        self.long = self.direction == "bullish"
        self.cache = {}
        self.bound = {}
        self.birth = None
        self.setup_id = None
        self.seen = set()
        self.exhausted = []
        self.current_ordinal = -1

    def end(self, candle, tf):
        return parse_timestamp(candle["timestamp"]) + VALID_TIMEFRAME_DURATIONS[tf]

    def history(self, tf, at):
        return [c for c in self.histories[tf] if self.end(c, tf) <= at]

    def coverage(self, tf, at):
        history = self.history(tf, at)
        expected = self.starts[tf]
        for c in history:
            if parse_timestamp(c["timestamp"]) != expected:
                raise _Unknown("MISSING_CONTIGUOUS_" + tf)
            expected = self.end(c, tf)
        if expected + VALID_TIMEFRAME_DURATIONS[tf] <= at:
            raise _Unknown("MISSING_CONTIGUOUS_" + tf)
        return history

    def facts(self, kind, tf, at):
        history = self.history(tf, at)
        if len(history) < 3:
            raise _Unknown("INSUFFICIENT_" + tf + "_CONTEXT")
        key = (kind, tf, len(history))
        if key not in self.cache:
            owners = {"structure": MarketStructureAnalyzer, "order_block": OrderBlockIntelligenceAnalyzer,
                      "liquidity": LiquidityIntelligenceAnalyzer, "events": LiquidityEventsAnalyzer,
                      "displacement": DisplacementIntelligenceAnalyzer, "fvg": FVGImbalanceIntelligenceAnalyzer}
            request = {"symbol": "XAUUSD", "timeframe": tf, "evaluation_time": stamp(at), "candle_history": history}
            if kind == "events":
                nested = dict(self.config["liquidity"])
                lookback = nested.pop("lookback_candles")
                request["config"] = {"lookback_candles": lookback, "maximum_events": 1000,
                                     "include_touch_events": True, "liquidity_config": nested}
            elif kind != "structure":
                request["config"] = self.config[kind]
            self.cache[key] = owners[kind]().analyze(request).to_dict()
        return self.cache[key]

    def pivots(self, tf, at, low):
        history = self.history(tf, at)
        rows = self.facts("structure", tf, at)["evidence"]["swing_lows" if low else "swing_highs"]
        return [{"kind": "LOW" if low else "HIGH", "price": p["low" if low else "high"],
                 "candle": history[p["index"]], "confirmation_candle": history[p["index"] + 1],
                 "available_at": stamp(self.end(history[p["index"] + 1], tf))} for p in rows]

    def boundary(self, value):
        # Producer pivot indices and IDs are snapshot-local, never economic identity.
        candles = {c["timestamp"]: c for c in self.histories["M15"]}
        return {**{k: v for k, v in value.items() if k != "members"},
                "members": [{**{k: v for k, v in m.items() if k not in ("pivot_index", "confirmed_at_index")},
                             "pivot_candle": candles[m["pivot_timestamp"]],
                             "confirmation_candle": candles[m["confirmed_at"]]}
                            for m in value["members"]]}

    def event(self, candle, tf):
        return {"candle": candle, "available_at": stamp(self.end(candle, tf))}

    def displacement(self, tf, at, candle):
        history = self.history(tf, at)
        baseline = self.config["displacement"]["baseline_window"]
        index = history.index(candle)
        if index < baseline:
            raise _Unknown("INSUFFICIENT_DISPLACEMENT_BASELINE")
        result = self.facts("displacement", tf, at)
        # Ask the same factual owner for this candidate's coverage. Restricting
        # its candidate scan does not alter the baseline or single-event rule.
        probe = DisplacementIntelligenceAnalyzer().analyze({"symbol": "XAUUSD", "timeframe": tf,
            "evaluation_time": stamp(at), "candle_history": history,
            "config": {**self.config["displacement"], "lookback_candles": 1}}).to_dict()
        if probe["evidence"]["evaluable_candidate_count"] != 1:
            raise _Unknown("UNRESOLVED_DISPLACEMENT_BASELINE")
        return any(e["source_timestamp"] == candle["timestamp"] and e["direction"] == self.direction
                   for e in result["displacement_events"])

    def found(self, at):
        context = self.facts("structure", "H4", at)["structure_state"]
        if context == "unresolved_structure":
            raise _Unknown("UNRESOLVED_H4")
        if context != self.direction + "_structure":
            return False
        anchors = self.pivots("H1", at, self.long)
        if not anchors:
            raise _Unknown("NO_CONFIRMED_CA1")
        if any(self.through(c["close"], anchors[-1]["price"]) for c in self.history("H1", at)
               if self.end(c, "H1") > parse_timestamp(anchors[-1]["available_at"])):
            return False
        if len(self.history("H1", at)) <= self.config["order_block"]["displacement_config"]["baseline_window"]:
            raise _Unknown("INSUFFICIENT_P1_BASELINE")
        blocks_result = self.facts("order_block", "H1", at)
        if blocks_result.get("diagnostics", {}).get("truncated_order_block_count", 0):
            raise _Unknown("TRUNCATED_P1_CANDIDATES")
        blocks = [b for b in blocks_result["order_blocks"] if b["direction"] == self.direction and b["current_state"] == "unvisited"]
        if not blocks:
            return False
        latest = max(b["confirmed_at"] for b in blocks)
        blocks = [b for b in blocks if b["confirmed_at"] == latest]
        if len(blocks) != 1:
            raise _Unknown("AMBIGUOUS_P1")
        block = blocks[0]
        levels = self.facts("liquidity", "M15", at)["liquidity_levels"]
        levels = [l for l in levels if l["level_type"] == ("confirmed_swing_low_level" if self.long else "confirmed_swing_high_level")
                  and l["current_status"] in ("active", "touched")
                  and block["range_low"] <= l["representative_price"] <= block["range_high"]]
        if len(levels) > 1:
            raise _Unknown("AMBIGUOUS_L1")
        if not levels:
            return False
        selected_boundary = self.boundary(levels[0]["causal_boundary"])
        available = parse_timestamp(selected_boundary["available_at"])
        for c in self.history("M15", at):
            boundary = self.end(c, "M15")
            if boundary < available:
                continue
            prior_levels = self.facts("liquidity", "M15", boundary)["liquidity_levels"]
            prior = [l for l in prior_levels if self.boundary(l["causal_boundary"]) == selected_boundary]
            if not prior:
                raise _Unknown("L1_PRIOR_CONTINUITY_UNPROVEN")
            if prior[0]["current_status"] not in ("active", "touched"):
                return False
        h1 = {c["timestamp"]: c for c in self.history("H1", at)}
        p1 = {k: block[k] for k in ("direction", "range_low", "range_high", "body_low", "body_high")}
        p1.update(origin=h1[block["source_timestamp"]], confirmation=h1[block["source_displacement_timestamp"]],
                  available_at=stamp(self.end(h1[block["source_displacement_timestamp"]], "H1")))
        bindings = {"CA1": anchors[-1], "P1": p1, "L1": self.boundary(levels[0]["causal_boundary"])}
        tuple_id = identity("founding_", [self.definition, FACTUAL_RULES, bindings])
        if tuple_id in self.seen:
            return False
        self.seen.add(tuple_id)
        self.bound = {"C1": {"structure_state": context,
                             "swing_highs": self.pivots("H4", at, False)[-2:],
                             "swing_lows": self.pivots("H4", at, True)[-2:]}, **bindings}
        self.birth = at
        self.setup_id = identity("setup_", [tuple_id, stamp(at)])
        self.current_ordinal += 1
        return True

    def deadline(self):
        b = self.bound
        if "E1" not in b:
            stage, start = "E1", self.birth
        elif "R1" not in b:
            stage, start = "R1", parse_timestamp(b["E1"]["available_at"])
        elif "K1" not in b:
            stage, start = "K1", parse_timestamp(b["R1"]["available_at"])
        elif "Q1" not in b:
            return None  # Exact immediate C is enforced independently.
        elif "RT1" not in b:
            stage, start = "RT1", parse_timestamp(b["Q1"]["eligible_at"])
        else:
            stage, start = "T1", parse_timestamp(b["RT1"]["available_at"])
        return stage, start + timedelta(seconds=self.config["windows_seconds"][stage])

    def step(self, at):
        b = self.bound
        invalid = []
        context = self.facts("structure", "H4", at)["structure_state"]
        if context == "unresolved_structure":
            raise _Unknown("UNRESOLVED_H4")
        if context != self.direction + "_structure":
            invalid.append("OPPOSITE_H4")
        h1 = self.history("H1", at)[-1]
        if self.end(h1, "H1") == at and at > self.birth:
            if self.through(h1["close"], b["CA1"]["price"]):
                invalid.append("CA1_CLOSE_THROUGH")
            if self.through(h1["close"], b["P1"]["range_low" if self.long else "range_high"]):
                invalid.append("P1_CLOSE_THROUGH")
        if "E1" not in b:
            levels = self.facts("liquidity", "M15", at)["liquidity_levels"]
            if not any(self.boundary(l["causal_boundary"]) == b["L1"] for l in levels):
                raise _Unknown("L1_CONTINUITY_UNPROVEN")
            event_result = self.facts("events", "M15", at)
            if event_result["diagnostics"]["truncated_event_count"]:
                raise _Unknown("TRUNCATED_E1_EVIDENCE")
            events = event_result["liquidity_events"]
            for e in events:
                if self.boundary(e["causal_boundary"]) != b["L1"]:
                    continue
                opened = parse_timestamp(e["event_timestamp"])
                completed = opened + VALID_TIMEFRAME_DURATIONS["M15"]
                if completed != at:
                    continue
                if opened < self.birth:
                    if completed > self.birth and e["event_type"] != "liquidity_touch":
                        raise _Unknown("E1_SELECTION_ORDER_UNPROVEN")
                    continue
                if e["event_type"] == "liquidity_close_beyond":
                    invalid.append("L1_CLOSE_BEFORE_SWEEP")
                elif e["event_type"] == "liquidity_sweep":
                    candle = next(c for c in self.history("M15", at) if c["timestamp"] == e["event_timestamp"])
                    b["E1"] = self.event(candle, "M15")
                    pivots = [p for p in self.pivots("M5", at, not self.long) if parse_timestamp(p["available_at"]) < opened]
                    if not pivots:
                        invalid.append("ABSENT_PRE_E1_B1")
                    else:
                        b["B1"] = pivots[-1]
                    break
        m5 = self.history("M5", at)[-1]
        if self.end(m5, "M5") == at and "B1" in b:
            opened = parse_timestamp(m5["timestamp"])
            if "R1" not in b and opened >= parse_timestamp(b["E1"]["available_at"]) and self.displacement("M5", at, m5):
                b["R1"] = self.event(m5, "M5")
            if "R1" in b:
                if "K1" not in b and self.through(m5["close"], b["B1"]["price"], reverse=True):
                    b["K1"] = self.event(m5, "M5")
                if "Q1" not in b and at == parse_timestamp(b["R1"]["available_at"]) + VALID_TIMEFRAME_DURATIONS["M5"]:
                    formations = self.facts("fvg", "M5", at)["fair_value_gaps"]
                    matches = [f for f in formations if f["source_timestamp"] == b["R1"]["candle"]["timestamp"] and f["side"] == self.direction]
                    if not matches:
                        invalid.append("ABSENT_FIXED_Q1")
                    else:
                        f = matches[0]
                        source_values = f["evidence"]["source_values"]
                        if source_values["b"] != b["R1"]["candle"]:
                            raise ValueError("Factual R1/Q1 source contradiction.")
                        b["Q1"] = {"gap_lower": f["gap_lower"], "gap_upper": f["gap_upper"],
                                   "formation": source_values, "available_at": stamp(at), "eligible_at": None}
        if "Q1" in b:
            q = b["Q1"]
            if "K1" in b and q["eligible_at"] is None:
                q["eligible_at"] = max(q["available_at"], b["K1"]["available_at"])
            if self.end(m5, "M5") == at and at > parse_timestamp(q["available_at"]):
                opened = parse_timestamp(m5["timestamp"])
                far = q["gap_lower" if self.long else "gap_upper"]
                overlap = m5["high"] >= q["gap_lower"] and m5["low"] <= q["gap_upper"]
                eligible = q["eligible_at"] is not None and opened >= parse_timestamp(q["eligible_at"])
                full = m5["low"] <= far if self.long else m5["high"] >= far
                if not eligible and full:
                    invalid.append("PRE_ELIGIBILITY_FULL_FILL")
                if self.through(m5["close"], far):
                    if eligible and overlap and "RT1" not in b:
                        raise _Unknown("RT1_INVALIDATION_ORDER_UNPROVEN")
                    invalid.append("Q1_CLOSE_THROUGH")
                if eligible and overlap and "RT1" not in b:
                    b["RT1"] = self.event(m5, "M5")
        if "RT1" in b:
            m1 = self.history("M1", at)[-1]
            if self.end(m1, "M1") == at and parse_timestamp(m1["timestamp"]) >= parse_timestamp(b["RT1"]["available_at"]):
                if self.displacement("M1", at, m1):
                    b["T1"] = self.event(m1, "M1")
        if "T1" in b and invalid:
            raise _Unknown("COMPLETION_INVALIDATION_ORDER_UNPROVEN")
        if invalid:
            return "INVALIDATED", invalid[0]
        if "T1" in b:
            return "COMPLETE", "FIRST_CANONICAL_COMPLETION"
        return None

    def through(self, price, boundary, reverse=False):
        return price < boundary if self.long != reverse else price > boundary

    def result(self, status, reason, at):
        selected = self.current_ordinal == self.ordinal
        payload = {"contract": CONTRACT, "rule_version": RULE_VERSION,
                   "factual_rules": dict(FACTUAL_RULES),
                   "strategy_definition": self.definition,
                   "configuration_fingerprint": identity("configuration_", self.config),
                   "evaluation_boundary": stamp(self.now), "knowledge_boundary": stamp(self.now),
                   "setup_ordinal": self.ordinal, "status": status, "reason": reason,
                   "status_boundary": stamp(at), "birth_boundary": None if self.birth is None or not selected else stamp(self.birth),
                   "setup_identity": self.setup_id if selected else None, "completion_identity": None,
                   "bindings": deepcopy(self.bound) if selected else {}, "prior_exhausted_setups": self.exhausted[:],
                   "authority": dict(AUTHORITY), "execution": False}
        if status == "COMPLETE":
            payload["completion_identity"] = identity("completion_", [self.setup_id, self.bound["T1"], stamp(at)])
        payload["assessment_identity"] = identity("assessment_", payload)
        return StrategyAssessment(payload)

    def restore(self, instance):
        self.birth, self.setup_id, self.bound, self.current_ordinal = instance["state"]

    def finish(self, instance, outcome):
        instance["outcome"] = outcome
        if self.current_ordinal == self.ordinal:
            return self.result(*outcome)
        if outcome[0] in ("COMPLETE", "INVALIDATED", "EXPIRED"):
            self.exhausted.append({"setup_identity": self.setup_id, "status": outcome[0], "boundary": stamp(outcome[2])})
        return None

    def run(self):
        start, end = (parse_timestamp(self.config[k]) for k in ("founding_start", "founding_end"))
        if self.now < start:
            raise ValueError("As-of precedes founding domain.")
        # Include absent expected completions, not merely observed candles. Gaps
        # must stop replay at their first mandatory boundary.
        times = {start, self.now}
        for tf in TIMEFRAMES:
            tick = self.starts[tf] + VALID_TIMEFRAME_DURATIONS[tf]
            while tick <= self.now:
                if tick >= start:
                    times.add(tick)
                tick += VALID_TIMEFRAME_DURATIONS[tf]
        at = start
        # Local Strategy #1 instances only. Distinct tuples have independent
        # canonical births, even when an earlier tuple has not terminated yet.
        instances = []
        try:
            for at in sorted(times):
                for instance in instances:
                    if instance["outcome"] is not None:
                        continue
                    self.restore(instance)
                    deadline = self.deadline()
                    if deadline and deadline[1] < at:
                        for tf in TIMEFRAMES:
                            self.coverage(tf, deadline[1])
                        result = self.finish(instance, ("EXPIRED", deadline[0] + "_DEADLINE", deadline[1]))
                        if result:
                            return result
                for tf in TIMEFRAMES:
                    self.coverage(tf, at)
                if len(instances) <= self.ordinal and at <= end:
                    self.current_ordinal = len(instances) - 1
                    if self.found(at):
                        instances.append({"state": (self.birth, self.setup_id, self.bound, self.current_ordinal), "outcome": None})
                for instance in instances:
                    if instance["outcome"] is not None:
                        continue
                    self.restore(instance)
                    try:
                        step = self.step(at)
                        new_deadline = self.deadline()
                        if step:
                            outcome = (*step, at)
                        elif new_deadline and at >= new_deadline[1]:
                            outcome = ("EXPIRED", new_deadline[0] + "_DEADLINE", new_deadline[1])
                        else:
                            continue
                    except _Unknown as exc:
                        outcome = ("UNKNOWN", str(exc), at)
                    result = self.finish(instance, outcome)
                    if result:
                        return result
            if len(instances) > self.ordinal:
                self.restore(instances[self.ordinal])
                return self.result("WAITING", "NEXT_PREREQUISITE_ABSENT", self.now)
            self.birth, self.setup_id, self.bound, self.current_ordinal = None, None, {}, -1
            return self.result("WAITING", "NO_NEW_FOUNDING_TUPLE", self.now)
        except _Unknown as exc:
            if len(instances) > self.ordinal:
                self.restore(instances[self.ordinal])
            return self.result("UNKNOWN", str(exc), at)


class XAUUSDCausalLiquidityReversalAssessor:
    def analyze(self, payload):
        return _Replay(payload).run()


def validate_strategy_assessment(assessment, assessment_input):
    if isinstance(assessment, StrategyAssessment):
        assessment = assessment.to_dict()
    if type(assessment) is not dict:
        raise ValueError("StrategyAssessment must be a serialized dictionary.")
    expected = XAUUSDCausalLiquidityReversalAssessor().analyze(assessment_input).to_dict()
    # Canonical full-content comparison also distinguishes booleans from numbers.
    if identity("", assessment) != identity("", expected) or assessment != expected:
        raise ValueError("StrategyAssessment differs from owner reconstruction.")
    return deepcopy(expected)


XAUUSD_CAUSAL_LIQUIDITY_REVERSAL = XAUUSDCausalLiquidityReversalAssessor()
