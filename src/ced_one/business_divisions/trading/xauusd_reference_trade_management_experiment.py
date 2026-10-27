"""Frozen, reference-only management research. Never an execution authority.

All prices are exact rationals of decimal representations; no binary floating
arithmetic, mutable replay service, or production decision-chain integration.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
import math

from .causal_snapshot_availability import validate_source, VALID_TIMEFRAME_DURATIONS
from .validation import parse_timestamp
from .xauusd_technical_trade_candidate import validate_technical_candidate_formulation

_ROOT = "trading.xauusd_reference_trade_management_experiment"
POLICY_CONTRACT = _ROOT + ".policy.v1"
SCENARIO_CONTRACT = _ROOT + ".scenario.v1"
AGGREGATE_CONTRACT = _ROOT + ".aggregate.v1"
DATASET_RELATIONSHIP_CONTRACT = _ROOT + ".dataset_relationship.v1"
RULE_VERSION = "xauusd_reference_trade_management_experiment_v1"
RELATIONSHIP_RULE_VERSION = "xauusd_reference_trade_management_dataset_relationship_v1"
BASE_RELATIONSHIP = "CANDIDATE_ORIGIN_TO_M1_SAME_RESEARCH_PRICE_DOMAIN"
M5_RELATIONSHIP = "M1_TO_M5_COMMON_RESEARCH_DATASET"
_AUTHORITY = dict(trade_decision=False, financial_risk=False, execution=False)
_DECL_AUTHORITY = dict(authenticated_source_truth=False, **_AUTHORITY)
_VARIANTS = ("A", "B", "C", "D", "E")
_STATUSES = ("RESOLVED", "AMBIGUOUS", "HORIZON_CENSORED", "MISSING_DATA_CENSORED", "END_OF_DATA_UNRESOLVED")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MINUTE = timedelta(minutes=1)
_EXCURSION_LABEL = "CONSERVATIVE OBSERVED-PREFIX LOWER-BOUND EXCURSIONS"
_POLICY = {
    "contract": POLICY_CONTRACT, "rule_version": RULE_VERSION,
    "observation_duration_minutes": 1440, "touch_timeframe": "M1",
    "milestones_r": [1, 2], "target_r": 3,
    "variants": {"A": "INITIAL", "B": "ONE_R_TO_BE", "C": "R_STAGES",
                 "D": "M1_DIRECTIONAL_PIVOT_R_STAGES", "E": "M5_DIRECTIONAL_PIVOT_R_STAGES"},
    "pivot": "STRICT_THREE_CONSECUTIVE_CANDLES_CENTER_OPEN_GE_ENTRY",
    "gate": "CONFIRMATION_COMPLETION_STRICTLY_AFTER_FIRST_1R_ESTABLISHMENT",
    "catch_up": "HIGHEST_LATCHED_STAGE_AT_COMPLETION",
    "activation": "NEXT_M1_INTERVAL", "equality": "TOUCH",
    "gap": "OPENING_TERMINAL_MARK_OTHERWISE_EXACT_LEVEL",
    "ambiguity": "COMPLETE_ALTERNATIVES_SHARED_NESTED_BARRIER_PATHS",
    "censoring": "FIRST_CONSEQUENTIAL_DEPENDENCY_NO_REPAIR",
    "numeric_rule": "CANDIDATE_PRICE_DECIMAL_INTERPRETATION_V1",
    "ratio_rule": "REDUCED_RATIONAL_V1", "excursions": _EXCURSION_LABEL,
    "relationship_rule": RELATIONSHIP_RULE_VERSION,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return sha256(_canonical(value).encode()).hexdigest()


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(label + " has unsupported/missing fields.")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty identifier.")
    return value


def _time(value):
    moment = parse_timestamp(value)
    if value != _stamp(moment):
        raise ValueError("Noncanonical UTC timestamp.")
    return moment


def _stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def _price(value):
    if type(value) is int:
        result = Fraction(value)
    elif type(value) is float and math.isfinite(value):
        result = Fraction(repr(value))
    else:
        raise ValueError("Unsupported numeric representation.")
    if result <= 0:
        raise ValueError("Prices must be positive.")
    return result


def _decimal(value):
    """Canonical finite decimal, obtained without Decimal context or rounding."""
    value = Fraction(value)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValueError("Nondecimal price.")
    scale = max(twos, fives)
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(abs(coefficient)).zfill(scale + 1)
    if scale:
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if coefficient < 0 else "") + digits


def _ratio(value):
    if value is None:
        return None
    value = Fraction(value)
    return dict(numerator=value.numerator, denominator=value.denominator)


def _fraction(value):
    return Fraction(value["numerator"], value["denominator"])


def _source_ref(source):
    return dict(contract=source["metadata"]["contract"], rule_version=source["metadata"]["rule_version"],
                symbol=source["symbol"], timeframe=source["timeframe"],
                source_snapshot_id=source["source_snapshot_id"], full_artifact_sha256=_hash(source))


def _origin_ref(formulation, request):
    return dict(contract=formulation["contract"], rule_version=formulation["rule_version"],
                candidate_identity=formulation["candidate"]["candidate_identity"],
                full_artifact_sha256=_hash(formulation), reconstruction_input_sha256=_hash(request),
                original_m1_source=_source_ref(formulation["m1_origin_source"]),
                price_references=["entry_reference", "stop_reference"])


def _same(value, expected, label):
    if _canonical(value) != _canonical(expected):
        raise ValueError(label + " mismatch.")


def _source(value, tf, boundary):
    value = deepcopy(validate_source(value))
    if value["symbol"] != "XAUUSD" or value["timeframe"] != tf:
        raise ValueError("Wrong instrument/timeframe.")
    if _time(value["requested_evaluation_timestamp"]) > boundary:
        raise ValueError("Source beyond research boundary.")
    if value["source_availability"] not in ("AVAILABLE", "UNAVAILABLE"):
        raise ValueError("Inadmissible source state.")
    rows = {}
    previous = None
    duration = VALID_TIMEFRAME_DURATIONS[tf]
    for candle in value["approved_candle_history"]:
        at = _time(candle["timestamp"])
        if previous is not None and (at <= previous or (at - previous) % duration):
            raise ValueError("Overlapping/off-grid source chronology.")
        previous = at
        prices = {key: _price(candle[key]) for key in ("open", "high", "low", "close")}
        if prices["low"] > min(prices["open"], prices["close"]) or prices["high"] < max(prices["open"], prices["close"]):
            raise ValueError("Impossible exact OHLC.")
        rows[at] = prices
    return value, rows


def _declarations(values, formulation, formulation_input, sources, boundary, start, horizon):
    if type(values) is not list:
        raise ValueError("Declarations must be a list.")
    result, revisions, descriptors, grids, coverages = {}, {}, None, {}, {}
    for raw in values:
        d = deepcopy(raw)
        _exact(d, {"contract", "rule_version", "declaration_id", "declaration_revision", "relationship_type",
                   "source_namespace", "dataset_revision", "price_domain", "available_at", "subject_bindings",
                   "timeframe_grid_bindings", "coverage_declarations", "declaration_provenance", "authority"}, "Declaration")
        if d["contract"] != DATASET_RELATIONSHIP_CONTRACT or d["rule_version"] != RELATIONSHIP_RULE_VERSION:
            raise ValueError("Unsupported relationship contract.")
        for key in ("declaration_id", "source_namespace", "dataset_revision", "price_domain"):
            _text(d[key])
        if type(d["declaration_revision"]) is not int or d["declaration_revision"] < 1:
            raise ValueError("Invalid declaration revision.")
        if _time(d["available_at"]) > boundary:
            raise ValueError("Post-boundary declaration.")
        _exact(d["authority"], _DECL_AUTHORITY, "Declaration authority")
        if any(value is not False for value in d["authority"].values()):
            raise ValueError("Declaration cannot grant authority.")
        provenance = d["declaration_provenance"]
        _exact(provenance, {"declarant_namespace", "record_id"}, "Declaration provenance")
        for value in provenance.values():
            _text(value)
        revision = (provenance["declarant_namespace"], d["declaration_id"], d["declaration_revision"])
        # Conflicting content is never superseded by higher revisions.
        if revision in revisions and revisions[revision] != _canonical(raw):
            raise ValueError("Conflicting declaration revision.")
        revisions[revision] = _canonical(raw)
        descriptor = tuple(d[k] for k in ("source_namespace", "dataset_revision", "price_domain"))
        if descriptors is not None and descriptor != descriptors:
            raise ValueError("Conflicting price domain or dataset lineage.")
        descriptors = descriptor
        kind = d["relationship_type"]
        if kind == BASE_RELATIONSHIP:
            expected = {"candidate_origin": _origin_ref(formulation, formulation_input), "m1": _source_ref(sources["M1"])}
            tfs = ("M1",)
        elif kind == M5_RELATIONSHIP and "M5" in sources:
            expected = {"m1": _source_ref(sources["M1"]), "m5": _source_ref(sources["M5"])}
            tfs = ("M1", "M5")
        else:
            raise ValueError("Unsupported/irrelevant relationship type.")
        _same(d["subject_bindings"], expected, "Relationship subject")
        _exact(d["timeframe_grid_bindings"], tfs, "Grid bindings")
        _exact(d["coverage_declarations"], tfs, "Coverage declarations")
        local_grids = {}
        for tf in tfs:
            grid = d["timeframe_grid_bindings"][tf]
            _exact(grid, {"timeframe", "anchor_open", "duration_seconds"}, "Grid")
            seconds = 60 if tf == "M1" else 300
            if grid["timeframe"] != tf or type(grid["duration_seconds"]) is not int or grid["duration_seconds"] != seconds:
                raise ValueError("Invalid timeframe duration.")
            duration = timedelta(seconds=seconds)
            anchor = _time(grid["anchor_open"])
            anchor = _EPOCH + (anchor - _EPOCH) % duration
            grid["anchor_open"] = _stamp(anchor)
            local_grids[tf] = anchor
            if tf in grids and grids[tf] != grid:
                raise ValueError("Conflicting grids.")
            grids[tf] = deepcopy(grid)
            if tf == "M1" and (start - anchor) % duration:
                raise ValueError("M1 grid differs from candidate.")
            for candle in sources[tf]["approved_candle_history"]:
                if (_time(candle["timestamp"]) - anchor) % duration:
                    raise ValueError("Off-grid observation.")
            cov = d["coverage_declarations"][tf]
            _exact(cov, {"requested_start", "requested_end", "declared_coverage_start", "declared_coverage_end", "dataset_end"}, "Coverage")
            a, b, c, e = (_time(cov[k]) for k in ("requested_start", "requested_end", "declared_coverage_start", "declared_coverage_end"))
            if a >= b or c >= e or b != horizon:
                raise ValueError("Invalid research coverage interval.")
            first_center = start + ((anchor - start) % duration)
            if a > first_center - duration:
                raise ValueError("Requested coverage omits warm-up.")
            endpoint = None if cov["dataset_end"] is None else _time(cov["dataset_end"])
            if endpoint is not None and endpoint < c:
                raise ValueError("Dataset endpoint precedes declared coverage.")
            for candle in sources[tf]["approved_candle_history"]:
                opened = _time(candle["timestamp"])
                if opened < c or opened + duration > e or (endpoint is not None and opened + duration > endpoint):
                    raise ValueError("Observation contradicts coverage/endpoint.")
            if tf in coverages and coverages[tf] != cov:
                raise ValueError("Conflicting coverage/endpoint.")
            coverages[tf] = deepcopy(cov)
        if "M5" in local_grids and (local_grids["M5"] - local_grids["M1"]) % _MINUTE:
            raise ValueError("Incompatible M1/M5 grids.")
        result[_canonical(d)] = d
    return [result[key] for key in sorted(result)]


def _available(declarations, kind, at):
    return [d for d in declarations if d["relationship_type"] == kind and _time(d["available_at"]) <= at]


def _excursions(mae, mfe, prices, entry, sign):
    movements = [(price - entry) * sign for price in prices]
    return max([mae] + [-x for x in movements]), max([mfe] + movements)


def _excursion_output(mae, mfe, risk):
    return dict(label=_EXCURSION_LABEL, mae=_decimal(mae), mfe=_decimal(mfe), mae_r=_ratio(mae / risk), mfe_r=_ratio(mfe / risk))


def _pivot(rows, center, duration, low):
    """True/False/None: missing neighbors matter only if predicate is possible."""
    points = [rows.get(center + i * duration) for i in (-1, 0, 1)]
    key = "low" if low else "high"
    middle = points[1]
    if middle is not None:
        for neighbor in (points[0], points[2]):
            if neighbor is not None and (middle[key] >= neighbor[key] if low else middle[key] <= neighbor[key]):
                return False
    if any(p is None for p in points):
        return None
    return True


def evaluate_reference_scenario(request: dict) -> dict:
    """Reconstruct the frozen candidate and replay one research variant."""
    try:
        return _evaluate(deepcopy(request))
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed research scenario.") from exc


def _evaluate(request):
    _exact(request, {"contract", "rule_version", "variant", "candidate_formulation", "formulation_input", "research_boundary", "evidence"}, "Scenario request")
    if request["contract"] != SCENARIO_CONTRACT or request["rule_version"] != RULE_VERSION or request["variant"] not in _VARIANTS:
        raise ValueError("Unsupported scenario policy/variant.")
    variant = request["variant"]
    formulation = validate_technical_candidate_formulation(request["candidate_formulation"], request["formulation_input"])
    candidate = formulation["candidate"]
    if candidate is None:
        raise ValueError("No admissible candidate.")
    start = _time(candidate["valid_from"])
    horizon = start + timedelta(minutes=1440)
    boundary = _time(request["research_boundary"])
    if boundary < horizon or boundary < _time(formulation["upstream_formulation"]["knowledge_boundary"]):
        raise ValueError("Research boundary precedes required horizon/evidence.")
    if _time(candidate["entry_reference"]["evidence"]["candle"]["timestamp"]) + _MINUTE != start:
        raise ValueError("Entry is not T1 completion.")
    entry, initial = (_price(candidate[k]["value"]) for k in ("entry_reference", "stop_reference"))
    sign = 1 if candidate["direction"] == "LONG" else -1
    risk = (entry - initial) * sign
    if risk <= 0:
        raise ValueError("Interpreted geometry inconsistency.")
    levels = [initial, entry, entry + sign * risk]
    target = entry + sign * 3 * risk
    _exact(request["evidence"], {"m1", "m5", "declarations"}, "Evidence")
    evidence = request["evidence"]
    sources, histories = {}, {}
    sources["M1"], histories["M1"] = _source(evidence["m1"], "M1", boundary)
    if variant == "E" and evidence["m5"] is not None:
        sources["M5"], histories["M5"] = _source(evidence["m5"], "M5", boundary)
    elif evidence["m5"] is not None:
        raise ValueError("M5 evidence is only admitted for E.")
    for opened in histories["M1"]:
        if (opened - start) % _MINUTE:
            raise ValueError("Off-grid M1 observation.")
    original = {c["timestamp"]: c for c in formulation["m1_origin_source"]["approved_candle_history"]}
    raw_rows = {c["timestamp"]: c for c in sources["M1"]["approved_candle_history"]}
    for timestamp in original.keys() & raw_rows.keys():
        _same(raw_rows[timestamp], original[timestamp], "Frozen M1 history")
    declarations = _declarations(evidence["declarations"], formulation, request["formulation_input"], sources, boundary, start, horizon)
    normalized_input = deepcopy(request)
    normalized_input["candidate_formulation"] = formulation
    normalized_input["evidence"]["declarations"] = declarations
    state = dict(stage=0, first_1r=None, latched_2r=False, gate_open=variant in ("A", "B", "C"))
    transitions, alternatives = [], []
    mae = mfe = Fraction(0)
    status, reason, completed = "HORIZON_CENSORED", "OBSERVATION_HORIZON", horizon
    gate_evidence = None
    # Full supplied artifacts participate in validation and identity. Selection
    # cannot claim they were known before their declared research boundaries.
    used_available = [start, _time(formulation["upstream_formulation"]["knowledge_boundary"])]
    used_available.extend(_time(s["requested_evaluation_timestamp"]) for s in sources.values())
    used_available.extend(_time(d["available_at"]) for d in declarations)
    first_processed = None
    last_processed = None
    for minute in range(1440):
        opened = start + minute * _MINUTE
        at = opened + _MINUTE
        base = _available(declarations, BASE_RELATIONSHIP, at)
        if not base:
            status, reason, completed = "MISSING_DATA_CENSORED", "MISSING_CANDIDATE_M1_RELATIONSHIP", at
            break
        used_available.append(min(_time(d["available_at"]) for d in base))
        cov = base[0]["coverage_declarations"]["M1"]
        endpoint = None if cov["dataset_end"] is None else _time(cov["dataset_end"])
        if endpoint is not None and at > endpoint:
            status, reason, completed = "END_OF_DATA_UNRESOLVED", "DECLARED_M1_DATASET_END", at
            break
        row = histories["M1"].get(opened)
        anchor = candidate["entry_reference"]["evidence"]["candle"]["timestamp"]
        if anchor not in raw_rows or row is None or opened < _time(cov["declared_coverage_start"]) or at > _time(cov["declared_coverage_end"]):
            status, reason, completed = "MISSING_DATA_CENSORED", "MISSING_REQUIRED_M1_EVIDENCE", at
            break
        first_processed = first_processed or opened
        last_processed = at
        used_available.append(at)
        stop = levels[state["stage"]]
        stop_mechanism = ("INITIAL_RISK_STOP", "BREAK_EVEN_STOP", "PROTECTED_PROFIT_STOP")[state["stage"]]
        open_stop = (row["open"] - stop) * sign <= 0
        open_target = (row["open"] - target) * sign >= 0
        stop_touch = row["low"] <= stop if sign == 1 else row["high"] >= stop
        target_touch = row["high"] >= target if sign == 1 else row["low"] <= target
        events = []
        if open_stop or open_target:
            events = [(stop_mechanism if open_stop else "FINAL_TARGET", row["open"], "OPENING", None)]
        elif stop_touch or target_touch:
            if stop_touch:
                events.append((stop_mechanism, stop, "INTRABAR", "STOP_BEFORE_TARGET" if target_touch else None))
            if target_touch:
                events.append(("FINAL_TARGET", target, "INTRABAR", "TARGET_BEFORE_STOP" if stop_touch else None))
        if events:
            raw_candle = raw_rows[_stamp(opened)]
            for mechanism, mark, kind, order in events:
                a, f = _excursions(mae, mfe, [row["open"], mark], entry, sign)
                alternatives.append(dict(mechanism=mechanism, terminal_mark=_decimal(mark), reference_r=_ratio(sign * (mark - entry) / risk),
                    occurrence_kind=kind, occurrence_time=_stamp(opened) if kind == "OPENING" else None,
                    evidence_completion=_stamp(at), candle=deepcopy(raw_candle), candle_sha256=_hash(raw_candle),
                    path_condition=None if order is None else dict(order=order, stop=_decimal(stop), target=_decimal(target), candle_sha256=_hash(raw_candle)),
                    excursion_lower_bounds=_excursion_output(a, f, risk)))
            status = "AMBIGUOUS" if len(events) > 1 else "RESOLVED"
            reason, completed = "TERMINAL_REFERENCE_EVENT", at
            break
        mae, mfe = _excursions(mae, mfe, [row["low"], row["high"]], entry, sign)
        favorable = row["high"] if sign == 1 else row["low"]
        movement = (favorable - entry) * sign
        if movement >= risk and state["first_1r"] is None:
            state["first_1r"] = _stamp(at)
        state["latched_2r"] |= movement >= 2 * risk
        if at == horizon:
            break  # No structural dependency can change an in-window stop now.
        if variant in ("D", "E") and not state["gate_open"] and state["first_1r"] is not None and at > _time(state["first_1r"]):
            tf = "M1" if variant == "D" else "M5"
            duration = VALID_TIMEFRAME_DURATIONS[tf]
            relations = base if tf == "M1" else _available(declarations, M5_RELATIONSHIP, at)
            # Without a grid, an M5 center cannot precede T and needs two full candles.
            if relations:
                anchor_grid = _time(relations[0]["timeframe_grid_bindings"][tf]["anchor_open"])
                is_confirmation = (at - anchor_grid) % duration == timedelta(0)
                center = at - 2 * duration
                possible = is_confirmation and center >= start
            else:
                possible = at >= start + 2 * duration
                center = at - 2 * duration
            if possible:
                verdict = None
                structural_endpoint = None
                if relations and tf in histories:
                    grid_cov = relations[0]["coverage_declarations"][tf]
                    if grid_cov["dataset_end"] is not None:
                        structural_endpoint = _time(grid_cov["dataset_end"])
                    left, right_end = center - duration, at
                    in_coverage = left >= _time(grid_cov["declared_coverage_start"]) and right_end <= _time(grid_cov["declared_coverage_end"])
                    if in_coverage:
                        verdict = _pivot(histories[tf], center, duration, sign == 1)
                    used_available.append(min(_time(d["available_at"]) for d in relations))
                if verdict is None:
                    if structural_endpoint is not None and at > structural_endpoint:
                        status, reason = "END_OF_DATA_UNRESOLVED", "DECLARED_" + tf + "_DATASET_END"
                    else:
                        status, reason = "MISSING_DATA_CENSORED", "MISSING_CONSEQUENTIAL_" + tf + "_GATE_EVIDENCE"
                    completed = at
                    break
                if verdict:
                    state["gate_open"] = True
                    gate_evidence = dict(timeframe=tf, center_open=_stamp(center), confirmation_completion=_stamp(at),
                        candles=[next(c for c in sources[tf]["approved_candle_history"] if _time(c["timestamp"]) == center + i * duration) for i in (-1, 0, 1)])
        next_stage = state["stage"]
        if variant != "A" and state["gate_open"] and state["first_1r"] is not None:
            next_stage = 2 if state["latched_2r"] and variant != "B" else 1
        if next_stage > state["stage"]:
            transitions.append(dict(established_at=_stamp(at), active_from_open=_stamp(at), from_stage=state["stage"], to_stage=next_stage,
                                    stop=_decimal(levels[next_stage]), gate_evidence=deepcopy(gate_evidence)))
            state["stage"] = next_stage
    output = dict(contract=SCENARIO_CONTRACT, rule_version=RULE_VERSION, policy=deepcopy(_POLICY),
        candidate_identity=candidate["candidate_identity"], variant=variant, reconstruction=normalized_input,
        terms=dict(T=_stamp(start), H=_stamp(horizon), direction=candidate["direction"], entry=_decimal(entry), initial_stop=_decimal(initial),
                   original_r=_decimal(risk), be=_decimal(entry), plus_1r=_decimal(entry + sign * risk), plus_2r=_decimal(entry + sign * 2 * risk), plus_3r=_decimal(target)),
        completion_status=status, completion_reason=reason, completion_boundary=_stamp(completed),
        terminal_mechanisms=sorted({a["mechanism"] for a in alternatives}) or ["NONE"], terminal_alternatives=alternatives,
        reference_result=None if not alternatives else dict(lower_r=_ratio(min(_fraction(a["reference_r"]) for a in alternatives)), upper_r=_ratio(max(_fraction(a["reference_r"]) for a in alternatives))),
        observed_prefix_excursions=_excursion_output(mae, mfe, risk), transitions=transitions, final_state=state, gate_evidence=gate_evidence,
        coverage=dict(first_processed_open=None if first_processed is None else _stamp(first_processed), last_processed_completion=None if last_processed is None else _stamp(last_processed)),
        evidence_available_through=_stamp(max(used_available)), authority=deepcopy(_AUTHORITY), execution=False)
    output["scenario_identity"] = "reference_scenario_" + _hash(output)
    return output


def validate_reference_scenario(assessment: dict, request: dict) -> dict:
    """Detached assessments never bypass full owner reconstruction/replay."""
    expected = evaluate_reference_scenario(request)
    _same(assessment, expected, "Scenario reconstruction")
    return expected


def _compatible(left, right, sign):
    a, b = left["path_condition"], right["path_condition"]
    if a is None or b is None or a["candle_sha256"] != b["candle_sha256"]:
        return True
    # From an interior opening, the nearer adverse barrier is touched before
    # the farther one. A target cannot precede the nearer but follow the farther.
    near, far = sorted((a, b), key=lambda x: -sign * Fraction(x["stop"]))
    if near["stop"] == far["stop"]:
        return near["order"] == far["order"]
    return not (near["order"] == "TARGET_BEFORE_STOP" and far["order"] == "STOP_BEFORE_TARGET")


def _classification(values):
    if not values:
        return "INDETERMINATE"
    if all(values):
        return "DEFINITE"
    if any(values):
        return "POSSIBLE"
    return "NO"


def _summary(rows):
    counts = {status: sum(r["completion_status"] == status for r in rows) for status in _STATUSES}
    resolved = [r for r in rows if r["completion_status"] == "RESOLVED"]
    values = sorted(_fraction(r["terminal_alternatives"][0]["reference_r"]) for r in resolved)
    count = len(values)
    median = None if not count else (values[(count - 1) // 2] + values[count // 2]) / 2
    mechanisms = {m: sum(r["terminal_mechanisms"] == [m] for r in resolved) for m in ("INITIAL_RISK_STOP", "BREAK_EVEN_STOP", "PROTECTED_PROFIT_STOP", "FINAL_TARGET")}
    increments = {}
    for row in resolved:
        at = row["completion_boundary"]
        increments[at] = increments.get(at, Fraction(0)) + _fraction(row["terminal_alternatives"][0]["reference_r"])
    cumulative = peak = drawdown = Fraction(0)
    for at in sorted(increments, key=_time):
        cumulative += increments[at]
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    excursion = {}
    for key in ("mae_r", "mfe_r"):
        bounds = []
        for row in rows:
            items = [a["excursion_lower_bounds"] for a in row["terminal_alternatives"]] or [row["observed_prefix_excursions"]]
            vals = [_fraction(x[key]) for x in items]
            bounds.append((min(vals), max(vals)))
        excursion[key] = dict(count=len(bounds), mean_lower=None if not bounds else _ratio(sum(x[0] for x in bounds) / len(bounds)),
                              mean_upper=None if not bounds else _ratio(sum(x[1] for x in bounds) / len(bounds)))
    full_bounds = None
    if rows and all(r["terminal_alternatives"] for r in rows):
        full_bounds = dict(lower=_ratio(sum(_fraction(r["reference_result"]["lower_r"]) for r in rows) / len(rows)),
                           upper=_ratio(sum(_fraction(r["reference_result"]["upper_r"]) for r in rows) / len(rows)))
    return dict(total_cohort=len(rows), counts=counts, resolved_coverage=_ratio(Fraction(count, len(rows))) if rows else None,
                resolved_mechanism_counts=mechanisms, resolved_subset_mean_r=_ratio(sum(values) / count) if count else None,
                median_resolved_r=_ratio(median), full_cohort_terminal_mean_bounds=full_bounds,
                excursion_summaries=dict(label=_EXCURSION_LABEL, **excursion),
                drawdown=dict(label="DESCRIPTIVE RESOLVED-SCENARIO CLOSED-R DRAWDOWN", value_r=_ratio(drawdown) if resolved else None,
                              resolved_count=count, unresolved_count=len(rows) - count))


def aggregate_reference_experiment(request: dict) -> dict:
    """Validate a complete matched cohort, then aggregate exact research results."""
    try:
        return _aggregate(deepcopy(request))
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed research aggregate.") from exc


def _aggregate(request):
    _exact(request, {"contract", "rule_version", "cohort", "scenarios", "partitions"}, "Aggregate request")
    if request["contract"] != AGGREGATE_CONTRACT or request["rule_version"] != RULE_VERSION:
        raise ValueError("Unsupported aggregate policy.")
    if type(request["cohort"]) is not list or type(request["scenarios"]) is not list or type(request["partitions"]) is not list:
        raise ValueError("Aggregate collections must be lists.")
    cohort = sorted(_text(x) for x in request["cohort"])
    if len(set(cohort)) != len(cohort) or not cohort:
        raise ValueError("Duplicate/empty cohort.")
    matrix = {}
    for item in request["scenarios"]:
        _exact(item, {"assessment", "request"}, "Scenario evidence")
        row = validate_reference_scenario(item["assessment"], item["request"])
        key = row["candidate_identity"], row["variant"]
        if key in matrix or key[0] not in cohort:
            raise ValueError("Duplicate/unlisted scenario.")
        matrix[key] = row
    if set(matrix) != set(product(cohort, _VARIANTS)):
        raise ValueError("Incomplete A-E cohort matrix.")
    for candidate in cohort:
        baseline = matrix[candidate, "A"]["reconstruction"]
        for variant in _VARIANTS:
            other = matrix[candidate, variant]["reconstruction"]
            for key in ("candidate_formulation", "formulation_input"):
                _same(other[key], baseline[key], "Matched candidate")
            _same(other["evidence"]["m1"], baseline["evidence"]["m1"], "Matched M1")
            a = [d for d in baseline["evidence"]["declarations"] if d["relationship_type"] == BASE_RELATIONSHIP]
            b = [d for d in other["evidence"]["declarations"] if d["relationship_type"] == BASE_RELATIONSHIP]
            _same(a, b, "Matched base declarations")
    paired = {}
    for variant in _VARIANTS[1:]:
        comparisons = []
        for candidate in cohort:
            a, b = matrix[candidate, "A"], matrix[candidate, variant]
            sign = 1 if a["terms"]["direction"] == "LONG" else -1
            pairs = [(x, y) for x, y in product(a["terminal_alternatives"], b["terminal_alternatives"]) if _compatible(x, y, sign)]
            deltas = [_fraction(y["reference_r"]) - _fraction(x["reference_r"]) for x, y in pairs]
            comparisons.append(dict(candidate_identity=candidate, compatible_alternative_pairs=[dict(baseline=x, comparison=y) for x, y in pairs],
                delta_r_bounds=None if not deltas else dict(lower=_ratio(min(deltas)), upper=_ratio(max(deltas))),
                initial_risk_stop_mechanism_avoided=_classification([x["mechanism"] == "INITIAL_RISK_STOP" and y["mechanism"] != "INITIAL_RISK_STOP" for x, y in pairs]),
                economic_loss_avoided=_classification([_fraction(x["reference_r"]) < 0 <= _fraction(y["reference_r"]) for x, y in pairs])))
        paired[variant] = dict(jointly_assessable_count=sum(bool(c["compatible_alternative_pairs"]) for c in comparisons), comparisons=comparisons,
            mechanism_avoidance_counts={state: sum(c["initial_risk_stop_mechanism_avoided"] == state for c in comparisons) for state in ("DEFINITE", "POSSIBLE", "INDETERMINATE", "NO")},
            economic_loss_avoidance_counts={state: sum(c["economic_loss_avoided"] == state for c in comparisons) for state in ("DEFINITE", "POSSIBLE", "INDETERMINATE", "NO")})
    partitions = sorted(request["partitions"], key=lambda p: _time(p["entry_start_inclusive"]))
    previous, names = None, set()
    partition_output = []
    assigned = set()
    for p in partitions:
        _exact(p, {"partition_id", "entry_start_inclusive", "entry_end_exclusive", "selection_boundary"}, "Partition")
        name = _text(p["partition_id"])
        lo, hi = _time(p["entry_start_inclusive"]), _time(p["entry_end_exclusive"])
        if name in names or lo >= hi or (previous is not None and lo < previous):
            raise ValueError("Overlapping/invalid partitions.")
        names.add(name)
        previous = hi
        boundary = None if p["selection_boundary"] is None else _time(p["selection_boundary"])
        members = [c for c in cohort if lo <= _time(matrix[c, "A"]["terms"]["T"]) < hi]
        assigned.update(members)
        selection = {v: [c for c in members if boundary is not None and _time(matrix[c, v]["terms"]["H"]) <= boundary and _time(matrix[c, v]["evidence_available_through"]) <= boundary] for v in _VARIANTS}
        partition_output.append(dict(definition=p, descriptive_cohort=members, selection_eligible_cohort=selection,
            descriptive_metrics={v: _summary([matrix[c, v] for c in members]) for v in _VARIANTS},
            selection_metrics={v: _summary([matrix[c, v] for c in selection[v]]) for v in _VARIANTS}))
    if partitions and assigned != set(cohort):
        raise ValueError("Candidate outside declared partitions.")
    output = dict(contract=AGGREGATE_CONTRACT, rule_version=RULE_VERSION, policy=deepcopy(_POLICY), cohort=cohort,
        scenarios=[matrix[key] for key in sorted(matrix)], partitions=partition_output,
        metrics={v: _summary([matrix[c, v] for c in cohort]) for v in _VARIANTS}, paired_against_a=paired,
        authority=deepcopy(_AUTHORITY), execution=False)
    output["aggregate_identity"] = "reference_experiment_" + _hash(output)
    return output


def validate_reference_experiment(assessment: dict, request: dict) -> dict:
    expected = aggregate_reference_experiment(request)
    _same(assessment, expected, "Aggregate reconstruction")
    return expected
