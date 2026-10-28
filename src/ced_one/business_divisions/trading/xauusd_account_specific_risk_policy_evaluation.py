"""Causal pre-quantity policy evaluation; no quantity or authorization authority."""
import base64
import binascii
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
import re
import struct
from zoneinfo import ZoneInfo

from .causal_financial_account_state_snapshot import validate_causal_financial_account_state_snapshot
from .causal_account_rule_regime_assessment import validate_causal_account_rule_regime_assessment
from .xauusd_technical_trade_candidate import validate_technical_candidate_formulation
from .xauusd_candidate_gross_reference_financial_measurement import validate_candidate_gross_reference_financial_measurement

CONTRACT = "trading.xauusd_account_specific_risk_policy_evaluation.v1"
RULE_VERSION = "xauusd_account_specific_risk_policy_evaluation_v1"
POLICY_CONTRACT = "trading.xauusd_account_specific_risk_policy_evaluation.policy.v1"
POLICY_RULE = "own_account_risk_policy_v1"
TRADE_CONTRACT = "trading.account_actual_trade_outcome_evidence.v1"
TRADE_RULE = "account_actual_trade_outcome_evidence_v1"
COVERAGE_CONTRACT = "trading.account_actual_trade_outcome_coverage.v1"
COVERAGE_RULE = "account_actual_trade_outcome_coverage_v1"
COMPATIBILITY_CONTRACT = "trading.xauusd_account_specific_risk_policy_evaluation.reference_compatibility.v1"
COMPATIBILITY_RULE = "frozen_reference_account_compatibility_v1"
_UNIT = "SINGLE_ENTRY_SINGLE_TERMINAL_EXIT_TRADE_UNIT_V1"
_NET = "ACTUAL_REALIZED_NET_PNL_FINAL_V1"
_USE = "PRE_QUANTITY_FROZEN_REFERENCE_RISK_CALCULATION"
_AUTHORITY = dict(trade_decision=False, financial_risk=False, execution=False)
_MECHANISMS = ("INITIAL_PROTECTIVE_STOP", "BREAK_EVEN_STOP", "PROTECTED_PROFIT_STOP", "AMENDED_STOP", "TARGET", "MANUAL", "OTHER", "UNRESOLVED")
_STRUCTURES = ("SUPPORTED", "SCALE_IN", "PARTIAL_EXIT", "MIXED_EXIT", "INSEPARABLE_NETTING", "INSEPARABLE_REVERSAL", "UNRESOLVED")
_FIXED = dict(equity_policy="OWN_EQUITY_RISK_POLICY_V1", target_risk_fraction="0.01", maximum_risk_fraction="0.01",
              trading_day="OWN_POLICY_TRADING_DAY_EUROPE_AMSTERDAM_V1", trade_unit=_UNIT, net_interpretation=_NET,
              daily_policy="OWN_DAILY_INITIAL_RISK_STOP_LOSS_GATE_V1", threshold=2,
              correction_policy="AS_KNOWN_AT_K_REASSESSABLE_DAILY_GATE_V1")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode()).hexdigest()


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields: " + fields)


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty identifier.")
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported enum value.")
    return value


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid integer.")
    return value


def _bool(value):
    if type(value) is not bool:
        raise ValueError("Expected boolean.")
    return value


def _time(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})", value):
        raise ValueError("Timestamp requires seconds and explicit offset.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timestamp offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _stamp(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp(row, key, k=None):
    at = _time(row[key])
    row[key] = _stamp(at)
    if k is not None and at > k:
        raise ValueError("Post-K admitted evidence.")
    return at


def _number(value):
    if type(value) is not str or not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value):
        raise ValueError("Financial values require plain decimal strings.")
    return Fraction(value)


def _plain(value):
    value = Fraction(value)
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValueError("Nondecimal financial result.")
    scale = max(twos, fives)
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(abs(coefficient)).zfill(scale + 1)
    if scale:
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if coefficient < 0 else "") + digits


def _amount(row, key):
    row[key] = _plain(_number(row[key]))
    return _number(row[key])


def _currency(value):
    if type(value) is not str or not re.fullmatch("[A-Z]{3}", value):
        raise ValueError("Invalid currency.")


def _same(value, expected, label):
    if _json(value) != _json(expected):
        raise ValueError(label + " content/binding mismatch.")


def _source(value):
    _keys(value, "source_id source_contract source_contract_version source_snapshot_id")
    for field in value.values():
        _text(field)


def _provenance(value):
    _keys(value, "source record_id")
    _source(value["source"])
    _text(value["record_id"])


def _artifact(value):
    return dict(contract=value["contract"], rule_version=value["rule_version"], full_content_sha256=_hash(value))


def _contract(row, contract, rule):
    if row["contract"] != contract or row["rule_version"] != rule:
        raise ValueError("Unsupported local contract/rule.")


def _set(values, key=_json):
    if type(values) is not list:
        raise ValueError("Expected list.")
    found = {}
    for value in values:
        ident = key(value)
        if ident in found:
            _same(value, found[ident], "Duplicate identity")
        found[ident] = value
    return [found[key] for key in sorted(found)]


def _gate(outcome, reason, refs=(), **details):
    return dict(outcome=outcome, reasons=[reason], evidence_references=list(refs), **details)


def _combined(gates):
    states = [g["outcome"] for g in gates]
    return "NOT_SATISFIED" if "NOT_SATISFIED" in states else "UNKNOWN" if "UNKNOWN" in states else "SATISFIED"


def _account(snapshot):
    observation = snapshot["observation"]
    return {**{f: observation["source"][f] for f in ("source_id", "source_contract", "source_contract_version")},
            **{f: observation["account"][f] for f in ("account_id", "environment")}}


def _policy(value, account, snapshot, t, k):
    _keys(value, "contract rule_version policy_id policy_revision account_binding effective_from effective_until available_at provenance equity_admissibility timezone_binding")
    _contract(value, POLICY_CONTRACT, POLICY_RULE)
    _text(value["policy_id"])
    _integer(value["policy_revision"], 1)
    _same(value["account_binding"], account, "Policy account")
    _provenance(value["provenance"])
    _timestamp(value, "available_at", k)
    start = _timestamp(value, "effective_from")
    end = None if value["effective_until"] is None else _timestamp(value, "effective_until")
    if end is not None and end <= start:
        raise ValueError("Invalid policy interval.")
    mode = value["equity_admissibility"]
    _enum(mode.get("mode"), ("EXACT_TIME", "MAX_AGE"))
    _keys(mode, "mode account_measure_source_binding" + (" maximum_age_microseconds" if mode["mode"] == "MAX_AGE" else ""))
    _same(mode["account_measure_source_binding"], snapshot["observation"]["source"], "Equity source")
    if mode["mode"] == "MAX_AGE":
        _integer(mode["maximum_age_microseconds"])
    _keys(value["timezone_binding"], "timezone_id tzdb_release tzif_sha256")
    return start <= t and (end is None or t < end)


def _day(evidence, policy, t, k):
    _keys(evidence, "timezone_id tzdb_release tzif_sha256 tzif_base64 provenance available_at")
    _enum(evidence["timezone_id"], ("Europe/Amsterdam",))
    _text(evidence["tzdb_release"])
    _provenance(evidence["provenance"])
    _timestamp(evidence, "available_at", k)
    _same(policy["timezone_binding"], {f: evidence[f] for f in ("timezone_id", "tzdb_release", "tzif_sha256")}, "Timezone policy")
    if type(evidence["tzif_base64"]) is not str:
        raise ValueError("TZif must be base64 text.")
    try:
        raw = base64.b64decode(evidence["tzif_base64"], validate=True)
        if sha256(raw).hexdigest() != evidence["tzif_sha256"]:
            raise ValueError("TZif digest mismatch.")
        zone = ZoneInfo.from_file(BytesIO(raw), key="Europe/Amsterdam")
    except (ValueError, TypeError, EOFError, binascii.Error, struct.error, AssertionError) as exc:
        raise ValueError("Invalid bound TZif artifact.") from exc
    evidence["tzif_base64"] = base64.b64encode(raw).decode()
    date = t.astimezone(zone).date()
    following = date + timedelta(days=1)
    lo = datetime(date.year, date.month, date.day, tzinfo=zone).astimezone(timezone.utc)
    hi = datetime(following.year, following.month, following.day, tzinfo=zone).astimezone(timezone.utc)
    return dict(timezone_id="Europe/Amsterdam", tzdb_release=evidence["tzdb_release"], tzif_sha256=evidence["tzif_sha256"],
                local_date=date.isoformat(), utc_start=_stamp(lo), utc_end_exclusive=_stamp(hi))


def _supporting(values, k):
    for row in values:
        _keys(row, "evidence_id source available_at content")
        _text(row["evidence_id"])
        _source(row["source"])
        _timestamp(row, "available_at", k)
        if type(row["content"]) is not dict:
            raise ValueError("Supporting evidence requires structured content.")
    return _set(values, lambda x: x["evidence_id"])


def _evidence_ref(row):
    return dict(evidence_id=row["evidence_id"], full_content_sha256=_hash(row))


def _support(ref, evidence, expected, available):
    _keys(ref, "evidence_id full_content_sha256")
    found = next((x for x in evidence if x["evidence_id"] == ref["evidence_id"]), None)
    if found is None:
        raise ValueError("Dangling supporting evidence.")
    _same(ref, _evidence_ref(found), "Supporting evidence")
    _same(found["content"], expected, "Supporting interpretation")
    if _time(found["available_at"]) > available:
        raise ValueError("Classification predates supporting evidence.")


def _group(group, role, trade, evidence, available):
    _keys(group, "group_id role grouping_interpretation member_execution_references evidence_reference")
    _text(group["group_id"])
    _text(group["grouping_interpretation"])
    _enum(group["role"], (role,))
    for ref in group["member_execution_references"]:
        _keys(ref, "source_id execution_id full_content_sha256")
        for v in ref.values():
            _text(v)
    group["member_execution_references"] = _set(group["member_execution_references"], lambda x: (x["source_id"], x["execution_id"]))
    if not group["member_execution_references"]:
        raise ValueError("Execution grouping requires members.")
    _support(group["evidence_reference"], evidence, dict(kind="EXECUTION_GROUP", trade_identity=trade,
        **{f: group[f] for f in ("group_id", "role", "grouping_interpretation", "member_execution_references")}), available)


def _trade_ref(row):
    return dict(trade_identity=row["trade_identity"], evidence_revision=row["evidence_revision"], full_content_sha256=_hash(row))


def _trades(values, account, k):
    if type(values) is not list:
        raise ValueError("Trade evidence must be a list.")
    for row in values:
        _keys(row, "contract rule_version account_binding trade_identity evidence_revision source available_at predecessor_reference episode terminal_attribution realized_net_result supporting_evidence")
        _contract(row, TRADE_CONTRACT, TRADE_RULE)
        _same(row["account_binding"], account, "Trade account")
        _text(row["trade_identity"])
        _integer(row["evidence_revision"], 1)
        _source(row["source"])
        available = _timestamp(row, "available_at", k)
        row["supporting_evidence"] = _supporting(row["supporting_evidence"], k)
        if any(_time(e["available_at"]) > available for e in row["supporting_evidence"]):
            raise ValueError("Trade revision predates support.")
        ep = row["episode"]
        _keys(ep, "model structure completed actual_terminal_close_time instrument entry_group terminal_group structure_evidence")
        _enum(ep["model"], (_UNIT,))
        _enum(ep["structure"], _STRUCTURES)
        _bool(ep["completed"])
        _text(ep["instrument"])
        if ep["actual_terminal_close_time"] is not None:
            if _timestamp(ep, "actual_terminal_close_time", available) > k:
                raise ValueError("Future close.")
        if ep["completed"] and ep["actual_terminal_close_time"] is None:
            raise ValueError("Completed episode requires close time.")
        if ep["structure"] == "SUPPORTED":
            for role, field in (("ENTRY", "entry_group"), ("TERMINAL", "terminal_group")):
                _group(ep[field], role, row["trade_identity"], row["supporting_evidence"], available)
            if not ep["completed"]:
                raise ValueError("Supported outcome must be completed.")
            _support(ep["structure_evidence"], row["supporting_evidence"], dict(kind="EPISODE_STRUCTURE", trade_identity=row["trade_identity"],
                model=_UNIT, entry_group_sha256=_hash(ep["entry_group"]), terminal_group_sha256=_hash(ep["terminal_group"]),
                scale_in=False, partial_exit=False, mixed_exit=False, completed=True), available)
        else:
            if ep["entry_group"] is not None or ep["terminal_group"] is not None:
                raise ValueError("Unsupported population cannot claim supported groups.")
            _support(ep["structure_evidence"], row["supporting_evidence"], dict(kind="UNSUPPORTED_EPISODE", trade_identity=row["trade_identity"], structure=ep["structure"]), available)
        attribution = row["terminal_attribution"]
        _keys(attribution, "mechanism original_instruction evidence_reference")
        _enum(attribution["mechanism"], _MECHANISMS)
        if attribution["mechanism"] != "UNRESOLVED":
            if ep["structure"] != "SUPPORTED":
                raise ValueError("Unsupported episode cannot claim resolved mechanism.")
            instruction = attribution["original_instruction"]
            if attribution["mechanism"] == "INITIAL_PROTECTIVE_STOP":
                _keys(instruction, "instruction_id instruction_revision full_content_sha256")
                _text(instruction["instruction_id"])
                _text(instruction["full_content_sha256"])
                _integer(instruction["instruction_revision"], 1)
            elif instruction is not None:
                raise ValueError("Noninitial mechanism cannot claim original-stop attribution.")
            _support(attribution["evidence_reference"], row["supporting_evidence"], dict(kind="TERMINAL_CAUSATION", trade_identity=row["trade_identity"],
                terminal_group_sha256=_hash(ep["terminal_group"]), mechanism=attribution["mechanism"], original_instruction=instruction), available)
        elif attribution["original_instruction"] is not None or attribution["evidence_reference"] is not None:
            raise ValueError("Unresolved attribution must not assert causation.")
        net = row["realized_net_result"]
        _keys(net, "interpretation_id interpretation_version status amount currency episode_reference terminal_execution_group_reference provenance available_at interpretation_evidence")
        net_available = _timestamp(net, "available_at", available)
        _provenance(net["provenance"])
        _enum(net["status"], ("FINAL_COMPLETE", "PROVISIONAL", "UNAVAILABLE"))
        if net["amount"] is not None:
            _amount(net, "amount")
        if net["currency"] is not None:
            _currency(net["currency"])
        _same(net["episode_reference"], row["trade_identity"], "Net episode")
        _same(net["terminal_execution_group_reference"], None if ep["terminal_group"] is None else _hash(ep["terminal_group"]), "Net terminal group")
        if net["status"] == "FINAL_COMPLETE":
            if ep["structure"] != "SUPPORTED" or net["amount"] is None or net["currency"] is None:
                raise ValueError("Incomplete final net result.")
            if net_available < _time(ep["actual_terminal_close_time"]):
                raise ValueError("Final economics predates terminal close.")
            _enum(net["interpretation_id"], (_NET,))
            _text(net["interpretation_version"])
            _support(net["interpretation_evidence"], row["supporting_evidence"], dict(kind="NET_ECONOMICS", trade_identity=row["trade_identity"],
                terminal_group_sha256=_hash(ep["terminal_group"]), interpretation_id=_NET, interpretation_version=net["interpretation_version"],
                all_required_components_incorporated=True, amount=net["amount"], currency=net["currency"]), net_available)
        else:
            if net["interpretation_evidence"] is not None:
                raise ValueError("Nonfinal result cannot supply final economics proof.")
            for f in ("interpretation_id", "interpretation_version"):
                if net[f] is not None:
                    _text(net[f])
    values = _set(values, lambda x: (x["trade_identity"], x["evidence_revision"]))
    by_key = {(r["trade_identity"], r["evidence_revision"]): r for r in values}
    successors, roots = {}, {}
    executions = {}
    for row in values:
        trade = row["trade_identity"]
        for field in ("entry_group", "terminal_group"):
            group = row["episode"][field]
            if group is not None:
                for member in group["member_execution_references"]:
                    key = (member["source_id"], member["execution_id"])
                    binding = (trade, field, member["full_content_sha256"])
                    if key in executions and executions[key] != binding:
                        raise ValueError("Execution evidence reused/contradicted.")
                    executions[key] = binding
        pred = row["predecessor_reference"]
        key = (trade, row["evidence_revision"])
        if pred is None:
            if trade in roots:
                raise ValueError("Multiple unsuperseded roots.")
            roots[trade] = key
        else:
            _keys(pred, "trade_identity evidence_revision full_content_sha256")
            parent = by_key.get((pred["trade_identity"], pred["evidence_revision"]))
            if parent is None or pred["trade_identity"] != trade:
                raise ValueError("Missing/cross-trade predecessor.")
            _same(pred, _trade_ref(parent), "Correction predecessor")
            parent_key = (trade, pred["evidence_revision"])
            if parent_key in successors:
                raise ValueError("Contradictory correction branches.")
            if _time(row["available_at"]) < _time(parent["available_at"]):
                raise ValueError("Correction predates predecessor.")
            successors[parent_key] = key
    effective, visited = [], set()
    for trade, root in sorted(roots.items()):
        key = root
        while True:
            if key in visited:
                raise ValueError("Correction cycle.")
            visited.add(key)
            if key not in successors:
                effective.append(by_key[key])
                break
            key = successors[key]
    if visited != set(by_key):
        raise ValueError("Correction cycle/disconnected chain.")
    return values, effective


def _interval(row):
    _keys(row, "start end start_inclusive end_inclusive")
    lo, hi = _timestamp(row, "start"), _timestamp(row, "end")
    _bool(row["start_inclusive"])
    _bool(row["end_inclusive"])
    if lo > hi:
        raise ValueError("Reversed interval.")
    return lo, hi


def _relevant(row, day, t):
    ep = row["episode"]
    if not ep["completed"]:
        return False
    close = _time(ep["actual_terminal_close_time"])
    return _time(day["utc_start"]) <= close <= t and close < _time(day["utc_end_exclusive"])


def _coverage(values, account, day, t, k, effective):
    needed = [r for r in effective if _relevant(r, day, t)]
    required_refs = sorted((_trade_ref(r) for r in needed), key=_json)
    requested = dict(start=day["utc_start"], end=_stamp(t), start_inclusive=True, end_inclusive=True)
    adequate, extra_unknown = False, False
    for row in values:
        _keys(row, "contract rule_version coverage_id coverage_revision account_binding source available_at trade_unit_model day_binding requested_close_interval covered_close_interval inventory_completeness effective_population_references unresolved_population correction_knowledge_cutoff")
        _contract(row, COVERAGE_CONTRACT, COVERAGE_RULE)
        _text(row["coverage_id"])
        _integer(row["coverage_revision"], 1)
        _same(row["account_binding"], account, "Coverage account")
        _source(row["source"])
        available = _timestamp(row, "available_at", k)
        _enum(row["trade_unit_model"], (_UNIT,))
        _same(row["day_binding"], day, "Coverage day")
        _interval(row["requested_close_interval"])
        _same(row["requested_close_interval"], requested, "Requested coverage")
        lo, hi = _interval(row["covered_close_interval"])
        if hi > available:
            raise ValueError("Coverage predates covered interval.")
        _enum(row["inventory_completeness"], ("COMPLETE", "PARTIAL", "UNKNOWN"))
        refs = row["effective_population_references"] = _set(row["effective_population_references"], lambda x: (x["trade_identity"], x["evidence_revision"]))
        for ref in refs:
            if ref not in required_refs:
                raise ValueError("Coverage references non-effective/non-relevant trade.")
        _enum(row["unresolved_population"], ("NONE", "UNBOUNDED"))
        if row["inventory_completeness"] == "COMPLETE":
            _same(sorted(refs, key=_json), required_refs, "Complete population")
            if row["unresolved_population"] != "NONE":
                raise ValueError("Complete inventory cannot omit unresolved population.")
        cutoff = None if row["correction_knowledge_cutoff"] is None else _timestamp(row, "correction_knowledge_cutoff", available)
        covers = (lo < _time(day["utc_start"]) or (lo == _time(day["utc_start"]) and row["covered_close_interval"]["start_inclusive"])) and (hi > t or (hi == t and row["covered_close_interval"]["end_inclusive"]))
        if row["inventory_completeness"] == "COMPLETE" and covers and cutoff == k:
            adequate = True
        extra_unknown |= row["unresolved_population"] == "UNBOUNDED"
    values = _set(values, lambda x: (x["source"]["source_id"], x["coverage_id"], x["coverage_revision"]))
    # Distinct assertions may corroborate but cannot assert incompatible account populations.
    if adequate and extra_unknown:
        raise ValueError("Contradictory complete/unbounded account coverage.")
    return values, needed, adequate


def _daily(needed, adequate, coverage):
    classifications, definite, possible, unbounded = [], 0, 0, not adequate
    for row in needed:
        ep, net, attr = row["episode"], row["realized_net_result"], row["terminal_attribution"]
        classification = "POTENTIALLY_QUALIFYING"
        if ep["structure"] != "SUPPORTED":
            unbounded = True
        elif attr["mechanism"] not in ("INITIAL_PROTECTIVE_STOP", "UNRESOLVED"):
            classification = "NONQUALIFYING"
        elif net["status"] == "FINAL_COMPLETE" and _number(net["amount"]) >= 0:
            classification = "NONQUALIFYING"
        elif attr["mechanism"] == "INITIAL_PROTECTIVE_STOP" and net["status"] == "FINAL_COMPLETE":
            classification = "QUALIFYING"
            definite += 1
        if classification != "NONQUALIFYING":
            possible += 1
        classifications.append(dict(trade_reference=_trade_ref(row), classification=classification))
    outcome = "NOT_SATISFIED" if definite >= 2 else "SATISFIED" if not unbounded and possible < 2 else "UNKNOWN"
    return _gate(outcome, "DAILY_LOSS_THRESHOLD" if definite >= 2 else "DAILY_LOSS_BELOW_THRESHOLD" if outcome == "SATISFIED" else "DAILY_LOSS_EVIDENCE_INSUFFICIENT",
        [_artifact(c) for c in coverage], established_qualifying_count=definite, possible_qualifying_upper_bound=None if unbounded else possible,
        classifications=classifications, inventory_coverage_adequate=adequate)


def _compatibility(values, account_snapshot, candidate, measurement, t, k):
    selected = measurement["selected_specification"]
    expected = dict(account_snapshot=_artifact(account_snapshot), candidate=_artifact(candidate), measurement=_artifact(measurement),
        specification=None if selected is None else _artifact(selected), quantity_unit=measurement["quantity_unit"],
        measurement_pnl_currency=measurement["pnl_currency"], account_equity_currency=account_snapshot["observation"]["account"]["currency"])
    for row in values:
        _keys(row, "contract rule_version assertion_id assertion_revision subjects intended_use assessment_economic_time knowledge_boundary source available_at")
        _contract(row, COMPATIBILITY_CONTRACT, COMPATIBILITY_RULE)
        _text(row["assertion_id"])
        _integer(row["assertion_revision"], 1)
        _source(row["source"])
        _timestamp(row, "available_at", k)
        _timestamp(row, "assessment_economic_time")
        _timestamp(row, "knowledge_boundary")
        _same(row["assessment_economic_time"], _stamp(t), "Compatibility T")
        _same(row["knowledge_boundary"], _stamp(k), "Compatibility K")
        _enum(row["intended_use"], (_USE,))
        _same(row["subjects"], expected, "Compatibility subject")
    values = _set(values, lambda x: (x["source"]["source_id"], x["assertion_id"], x["assertion_revision"]))
    good = bool(values) and measurement["outcome"] == "MEASURED" and expected["measurement_pnl_currency"] == expected["account_equity_currency"]
    reason = "FROZEN_REFERENCE_COMPATIBLE" if good else "MISSING_COMPATIBILITY" if not values else "MEASUREMENT_NOT_SUPPORTED" if measurement["outcome"] != "MEASURED" else "CURRENCY_CONVERSION_UNSUPPORTED"
    return values, _gate("SATISFIED" if good else "UNKNOWN", reason, [_artifact(v) for v in values], intended_use=_USE,
                         historical_economic_time=measurement["economic_timestamp"], establishes_current_executable_risk=False)


def _rule_ref(rule):
    return dict(rule_id=rule["rule_id"], full_content_sha256=_hash(rule))


def _operands(values, rules, account, snapshot, candidate, t, k):
    if type(values) is not list:
        raise ValueError("Provider operands must be a list.")
    rules_by_id = {r["rule_id"]: r for r in rules}
    roles = {}
    for row in values:
        _keys(row, "tag rule_reference account_binding effective_from effective_until source available_at supporting_evidence body")
        tag = _enum(row["tag"], ("MEASURE_BINDING", "INITIAL_REFERENCE", "RESET_ANCHOR", "COST_ADJUSTMENTS", "ACCOUNT_FACT", "POSITION_COUNT_CONTEXT", "INSTRUMENT_BINDING"))
        _same(row["account_binding"], account, "Provider operand account")
        rule = rules_by_id.get(row["rule_reference"].get("rule_id"))
        if rule is None:
            raise ValueError("Provider operand requires a selected rule.")
        _same(row["rule_reference"], _rule_ref(rule), "Provider rule")
        _source(row["source"])
        available = _timestamp(row, "available_at", k)
        lo, hi = _timestamp(row, "effective_from"), _timestamp(row, "effective_until")
        if lo >= hi:
            raise ValueError("Invalid operand interval.")
        row["supporting_evidence"] = _supporting(row["supporting_evidence"], available)
        if not row["supporting_evidence"]:
            raise ValueError("Provider operand lacks evidence.")
        body = row["body"]
        role = tag
        if tag == "MEASURE_BINDING":
            _keys(body, "account_snapshot measure_kind currency definition_refs cost_treatment")
            _same(body["account_snapshot"], _artifact(snapshot), "Provider measure snapshot")
            measure = rule["body"].get("measure")
            if measure is None:
                raise ValueError("Measure operand for non-measure rule.")
            _same({"kind": body["measure_kind"], **{f: body[f] for f in ("currency", "definition_refs", "cost_treatment")}}, measure, "Provider measure definition")
            if body["currency"] != snapshot["observation"]["account"]["currency"]:
                raise ValueError("Provider measure denomination mismatch.")
        elif tag == "INITIAL_REFERENCE":
            _keys(body, "reference amount currency")
            _enum(body["reference"], ("INITIAL_BALANCE", "INITIAL_EQUITY"))
            _amount(body, "amount")
            _currency(body["currency"])
            role += ":" + body["reference"]
        elif tag == "RESET_ANCHOR":
            _keys(body, "reset_boundary measure_kind amount currency unrepresented_adjustments")
            _timestamp(body, "reset_boundary", available)
            _enum(body["measure_kind"], ("BALANCE", "EQUITY"))
            _amount(body, "amount")
            _currency(body["currency"])
            _bool(body["unrepresented_adjustments"])
        elif tag == "COST_ADJUSTMENTS":
            _keys(body, "currency commissions financing other_charges")
            _currency(body["currency"])
            for field in ("commissions", "financing", "other_charges"):
                if body[field] is not None:
                    _amount(body, field)
        elif tag == "ACCOUNT_FACT":
            _keys(body, "fact value")
            _enum(body["fact"], ("ACCOUNT_ACTIVE", "PHASE_OPEN_FOR_TRADING", "NO_PRIOR_DISQUALIFYING_BREACH"))
            if body["value"] is not None:
                _bool(body["value"])
            role += ":" + body["fact"]
        elif tag == "POSITION_COUNT_CONTEXT":
            _keys(body, "account_snapshot inventory_complete commitments_complete committed_additional_positions count_effect")
            _same(body["account_snapshot"], _artifact(snapshot), "Position inventory")
            _bool(body["inventory_complete"])
            _bool(body["commitments_complete"])
            _integer(body["committed_additional_positions"])
            _enum(body["count_effect"], ("NEW_SEPARATE_POSITION", "NO_COUNT_CHANGE", "QUANTITY_DEPENDENT", "UNKNOWN"))
            if body["inventory_complete"] and snapshot["observation"]["positions"]["completeness"] != "COMPLETE":
                raise ValueError("Contradictory inventory completeness.")
        else:
            _keys(body, "candidate provider_instrument")
            _same(body["candidate"], _artifact(candidate), "Provider instrument candidate")
            _keys(body["provider_instrument"], "source_id source_contract source_contract_version environment instrument_id")
            for v in body["provider_instrument"].values():
                _text(v)
            if body["provider_instrument"]["environment"] != account["environment"]:
                raise ValueError("Instrument environment mismatch.")
        # Source evidence must bind the complete typed assertion, not a bare boolean.
        expected = dict(kind="PROVIDER_OPERAND", tag=tag, rule_reference=row["rule_reference"], account_binding=account,
                        effective_from=row["effective_from"], effective_until=row["effective_until"], body=body)
        if not any(_json(e["content"]) == _json(expected) for e in row["supporting_evidence"]):
            raise ValueError("Provider operand supporting content mismatch.")
        key = (rule["rule_id"], role)
        semantic = {f: row[f] for f in ("tag", "rule_reference", "account_binding", "effective_from", "effective_until", "body")}
        if key in roles and roles[key] != semantic:
            raise ValueError("Conflicting provider operands.")
        roles[key] = semantic
    return _set(values)


def _providers(regime, operands, snapshot, candidate, mode, t):
    selected = regime["selected_regime"]
    unique = regime["outcome"] == "UNIQUE_APPLICABLE_APPROVED_REGIME"
    complete = unique and selected["package"]["coverage"]["completeness"] == "COMPLETE"
    regime_gate = _gate("SATISFIED" if complete else "UNKNOWN", "REGIME_ESTABLISHED" if complete else "REGIME_OR_COVERAGE_UNRESOLVED", [_artifact(regime)])
    results, obligations = [], []
    if not unique:
        return dict(regime_gate=regime_gate, rule_results=results), obligations
    action = "ENTRY_LONG" if candidate["candidate"]["direction"] == "LONG" else "ENTRY_SHORT"
    for rule in selected["package"]["rules"]:
        ref, body = _rule_ref(rule), rule["body"]
        def operand(tag, **filters):
            return next((x["body"] for x in operands if x["tag"] == tag and x["rule_reference"] == ref and
                _time(x["effective_from"]) <= t < _time(x["effective_until"]) and all(x["body"].get(f) == v for f, v in filters.items())), None)
        def record(state, reason, **details):
            refs = [ref] + [dict(provider_operand_sha256=_hash(x)) for x in operands if x["rule_reference"] == ref]
            result = _gate(state, reason, refs, **details)
            result["rule_reference"] = ref
            results.append(result)
        def defer(reason):
            obligations.append(dict(kind=reason, rule=deepcopy(rule), rule_reference=ref))
        if body["type"] == "POSITION_LIMIT" and body["limit_kind"] == "PER_POSITION_QUANTITY":
            defer("QUANTITY_LIMIT")
        if "UNKNOWN" in rule["effects"]:
            record("UNKNOWN", "RULE_EFFECT_UNRESOLVED")
            continue
        # Unknown effects cannot be dismissed. Non-entry lifetime effects remain obligations.
        if not set(rule["effects"]) & {"ENTRY", "ACCOUNT_ELIGIBILITY", "UNKNOWN"}:
            defer("LATER_RULE_APPLICABILITY")
            record("SATISFIED", "OUTSIDE_ENTRY_SCOPE_RETAINED")
            continue
        if rule["instrument_scope"]["kind"] == "EXACT_INSTRUMENTS":
            binding = operand("INSTRUMENT_BINDING")
            if binding is None:
                record("UNKNOWN", "MISSING_INSTRUMENT_BINDING")
                continue
            if binding["provider_instrument"] not in rule["instrument_scope"]["instruments"]:
                record("SATISFIED", "RULE_OUTSIDE_BOUND_INSTRUMENT_SCOPE")
                continue
        if rule["representation"] == "UNSUPPORTED":
            record("UNKNOWN", "UNSUPPORTED_MANDATORY_RULE")
            continue
        kind = body["type"]
        if kind in ("INSTRUMENT_ACTION_PERMISSION", "AUTOMATION_PERMISSION"):
            applies = action in body["actions"] if kind == "INSTRUMENT_ACTION_PERMISSION" else mode == body["operation_mode"]
            passed = not applies or body["permission"] == "PERMITTED"
            record("SATISFIED" if passed else "NOT_SATISFIED", "PERMISSION_ESTABLISHED" if passed else "EXPLICIT_PROHIBITION")
        elif kind == "ACTION_WINDOW":
            period = body["schedule_period"]
            if action not in body["actions"]:
                record("SATISFIED", "ACTION_OUTSIDE_RULE")
            elif not (_time(period["effective_from"]) <= t < _time(period["effective_until"])):
                record("UNKNOWN", "WINDOW_COVERAGE_MISSING")
            else:
                inside = any(_time(x["effective_from"]) <= t < _time(x["effective_until"]) for x in body["intervals"])
                passed = inside if body["mode"] == "PERMITTED_ONLY_WITHIN" else not inside
                record("SATISFIED" if passed else "NOT_SATISFIED", "ACTION_WINDOW")
        elif kind == "ACCOUNT_STATE_REQUIREMENT":
            facts = [operand("ACCOUNT_FACT", fact=f) for f in body["required_facts"]]
            vals = [None if f is None else f["value"] for f in facts]
            state = "NOT_SATISFIED" if False in vals else "UNKNOWN" if None in vals else "SATISFIED"
            record(state, "ACCOUNT_STATE_FACTS", required_facts=body["required_facts"])
        elif kind == "POSITION_LIMIT":
            if body["limit_kind"] == "PER_POSITION_QUANTITY":
                record("SATISFIED", "QUANTITY_COMPLIANCE_OUTSTANDING")
            else:
                context = operand("POSITION_COUNT_CONTEXT")
                if context is None or not context["inventory_complete"] or not context["commitments_complete"]:
                    record("UNKNOWN", "POSITION_INVENTORY_OR_COMMITMENTS_MISSING")
                else:
                    positions = snapshot["observation"]["positions"]["items"]
                    if rule["instrument_scope"]["kind"] == "EXACT_INSTRUMENTS":
                        instruments = rule["instrument_scope"]["instruments"]
                        account = _account(snapshot)
                        if any(any(i[f] != account[f] for f in ("source_id", "source_contract", "source_contract_version", "environment")) for i in instruments):
                            record("UNKNOWN", "POSITION_INSTRUMENT_NAMESPACE_UNRESOLVED")
                            continue
                        ids = {i["instrument_id"] for i in instruments}
                        positions = [p for p in positions if p["instrument_id"] in ids]
                    count = len(positions) + context["committed_additional_positions"]
                    effect = context["count_effect"]
                    if count > body["maximum"]:
                        record("NOT_SATISFIED", "POSITION_COUNT_EXCEEDED")
                    elif effect == "QUANTITY_DEPENDENT":
                        defer("QUANTITY_DEPENDENT_POSITION_COUNT")
                        record("SATISFIED", "POSITION_COUNT_EFFECT_OUTSTANDING")
                    elif effect == "UNKNOWN":
                        record("UNKNOWN", "POSITION_COUNT_EFFECT_UNKNOWN")
                    else:
                        count += int(effect == "NEW_SEPARATE_POSITION")
                        record("SATISFIED" if count <= body["maximum"] else "NOT_SATISFIED", "PROSPECTIVE_POSITION_COUNT", projected_count=count)
        elif kind in ("STATIC_FLOOR", "DAILY_RESET_FLOOR"):
            binding = operand("MEASURE_BINDING")
            measure = body["measure"]
            amount = snapshot["observation"]["account_measures"][measure["kind"].lower()]
            if binding is None or amount is None:
                record("UNKNOWN", "COMPATIBLE_MEASURE_MISSING")
                continue
            value = _number(amount)
            costs = operand("COST_ADJUSTMENTS")
            missing = False
            for field, treatment in measure["cost_treatment"].items():
                if treatment == "SUBTRACT_SEPARATELY":
                    if costs is None or costs["currency"] != measure["currency"] or costs[field] is None:
                        missing = True
                    else:
                        value -= _number(costs[field])
            threshold = body["threshold" if kind == "STATIC_FLOOR" else "deduction"]
            if threshold["kind"] == "ABSOLUTE":
                floor = _number(threshold["amount"])
            else:
                initial = operand("INITIAL_REFERENCE", reference=threshold["reference"])
                if initial is None or initial["currency"] != measure["currency"]:
                    missing = True
                    floor = Fraction(0)
                else:
                    floor = _number(initial["amount"]) * _number(threshold["fraction"])
            if kind == "DAILY_RESET_FLOOR":
                boundaries = [_time(x) for x in body["reset_schedule"]["boundaries"]]
                reset = next((lo for lo, hi in zip(boundaries, boundaries[1:]) if lo <= t < hi), None)
                anchor = operand("RESET_ANCHOR")
                if reset is None or anchor is None or _time(anchor["reset_boundary"]) != reset or anchor["measure_kind"] != body["reset_anchor"] or anchor["currency"] != measure["currency"] or anchor["unrepresented_adjustments"]:
                    missing = True
                else:
                    floor = _number(anchor["amount"]) - floor
            if missing:
                record("UNKNOWN", "FLOOR_OPERANDS_MISSING_OR_UNSUPPORTED")
            else:
                passed = value > floor if body["compliant_when"] == "GREATER_THAN" else value >= floor
                record("SATISFIED" if passed else "NOT_SATISFIED", "CURRENT_STATE_FLOOR", compared_measure=_plain(value), threshold=_plain(floor), establishes_post_entry_headroom=False)
                defer("POST_ENTRY_FLOOR_COMPLIANCE")
        else:
            record("UNKNOWN", "UNSUPPORTED_MANDATORY_RULE")
        if set(rule["effects"]) & {"HOLDING", "EXIT", "PHASE_TRANSITION", "PAYOUT"}:
            defer("LIFETIME_RULE_APPLICABILITY")
    return dict(regime_gate=regime_gate, rule_results=results), obligations


def evaluate_account_specific_risk_policy(request: dict) -> dict:
    """Evaluate all supplied material before returning any decisive policy result."""
    try:
        return _evaluate(deepcopy(request))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed account-specific risk request.") from exc


def _evaluate(q):
    _keys(q, "contract rule_version assessment_economic_time knowledge_boundary operation_mode account_state candidate financial_measurement account_rule_regime own_policy timezone_evidence actual_trade_evidence trade_coverage financial_compatibility provider_operands")
    _contract(q, CONTRACT, RULE_VERSION)
    _enum(q["operation_mode"], ("MANUAL", "AUTOMATED"))
    for key, fields in (("account_state", "snapshot snapshot_input"), ("candidate", "formulation formulation_input"),
                        ("financial_measurement", "assessment measurement_input"), ("account_rule_regime", "assessment assessment_input")):
        _keys(q[key], fields)
    account_snapshot = validate_causal_financial_account_state_snapshot(q["account_state"]["snapshot"], q["account_state"]["snapshot_input"])
    candidate = validate_technical_candidate_formulation(q["candidate"]["formulation"], q["candidate"]["formulation_input"])
    measurement = validate_candidate_gross_reference_financial_measurement(q["financial_measurement"]["assessment"], q["financial_measurement"]["measurement_input"])
    regime = validate_causal_account_rule_regime_assessment(q["account_rule_regime"]["assessment"], q["account_rule_regime"]["assessment_input"])
    if candidate["candidate"] is None:
        raise ValueError("No formulated candidate.")
    _same(measurement["candidate_formulation"], candidate, "Measurement candidate")
    _same(q["financial_measurement"]["measurement_input"]["formulation_input"], q["candidate"]["formulation_input"], "Candidate reconstruction input")
    t, k = _timestamp(q, "assessment_economic_time"), _timestamp(q, "knowledge_boundary")
    if t > k:
        raise ValueError("Assessment time exceeds K.")
    account = _account(account_snapshot)
    _same(regime["account"], account, "Regime account")
    if _time(regime["economic_timestamp"]) != t or _time(regime["requested_knowledge_boundary"]) != k:
        raise ValueError("Regime T/K mismatch.")
    observation = account_snapshot["observation"]
    account_time = _time(observation["timing"]["effective_at"])
    if account_time > t or _time(account_snapshot["requested_evaluation_timestamp"]) > k or _time(measurement["knowledge_boundary"]) > k:
        raise ValueError("Future effective/account/measurement evidence.")
    if _time(candidate["candidate"]["valid_from"]) > t:
        raise ValueError("Candidate postdates assessment.")
    applicable = _policy(q["own_policy"], account, account_snapshot, t, k)
    day = _day(q["timezone_evidence"], q["own_policy"], t, k)
    q["actual_trade_evidence"], effective = _trades(q["actual_trade_evidence"], account, k)
    q["trade_coverage"], needed, adequate = _coverage(q["trade_coverage"], account, day, t, k, effective)
    q["financial_compatibility"], compatible = _compatibility(q["financial_compatibility"], account_snapshot, candidate, measurement, t, k)
    rules = [] if regime["selected_regime"] is None else regime["selected_regime"]["package"]["rules"]
    q["provider_operands"] = _operands(q["provider_operands"], rules, account, account_snapshot, candidate, t, k)
    # All material validation is complete. Only now calculate owner-valid gates.
    equity = observation["account_measures"]["equity"]
    mode = q["own_policy"]["equity_admissibility"]
    age = t - account_time
    age_us = (age.days * 86400 + age.seconds) * 1000000 + age.microseconds
    fresh = age_us == 0 if mode["mode"] == "EXACT_TIME" else age_us <= mode["maximum_age_microseconds"]
    budget = None
    if not applicable:
        equity_gate = _gate("UNKNOWN", "OWN_POLICY_NOT_APPLICABLE")
    elif equity is None or not fresh:
        equity_gate = _gate("UNKNOWN", "EQUITY_MISSING" if equity is None else "EQUITY_STALE", [_artifact(account_snapshot)])
    elif _number(equity) <= 0:
        equity_gate = _gate("NOT_SATISFIED", "NONPOSITIVE_EQUITY", [_artifact(account_snapshot)])
    else:
        budget = _plain(_number(equity) / 100)
        equity_gate = _gate("SATISFIED", "EQUITY_BUDGET_ESTABLISHED", [_artifact(account_snapshot)])
    daily = _daily(needed, adequate, q["trade_coverage"])
    if not applicable:
        daily = _gate("UNKNOWN", "OWN_POLICY_NOT_APPLICABLE", factual_classification=daily)
    provider, obligations = _providers(regime, q["provider_operands"], account_snapshot, candidate, q["operation_mode"], t)
    obligations.extend([dict(kind="CURRENT_CANDIDATE_VALIDITY"), dict(kind="CURRENT_INSTRUMENT_AND_EXECUTABLE_RISK_SUITABILITY"),
                        dict(kind="RISK_CONSTRAINED_QUANTITY_SELECTION"), dict(kind="MISSION_CONTROL_CURRENT_AUTHORIZATION")])
    gates = [equity_gate, daily, compatible, provider["regime_gate"], *provider["rule_results"]]
    output = dict(contract=CONTRACT, rule_version=RULE_VERSION, account_binding=account, candidate_identity=candidate["candidate"]["candidate_identity"],
        assessment_economic_time=_stamp(t), knowledge_boundary=_stamp(k), reconstruction_evidence=q,
        fixed_policy=deepcopy(_FIXED), derived_day=day, selected_effective_trade_revisions=[_trade_ref(r) for r in effective],
        own_policy=dict(equity_gate=equity_gate, daily_loss_gate=daily, target_monetary_risk=budget, maximum_monetary_risk=budget,
                        currency=observation["account"]["currency"], budget_is_provider_safe_headroom=False),
        financial_compatibility=compatible, provider_policy=provider, outstanding_obligations=_set(obligations),
        overall_outcome=_combined(gates), reason_codes=sorted({reason for gate in gates for reason in gate["reasons"]}),
        authority=deepcopy(_AUTHORITY), execution=False)
    output["assessment_identity"] = "account_specific_risk_policy_" + _hash(output)
    return output


def validate_account_specific_risk_policy(assessment: dict, request: dict) -> dict:
    """Never trust detached identities: reconstruct and compare complete content."""
    expected = evaluate_account_specific_risk_policy(request)
    _same(assessment, expected, "Risk policy assessment")
    return expected
