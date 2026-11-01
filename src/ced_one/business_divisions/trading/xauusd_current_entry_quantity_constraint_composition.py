"""Exact conditional quantity-set composition under native, independent admissions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import re

from .xauusd_current_risk_budget_quantity_feasibility import validate_current_risk_budget_quantity_feasibility
from .xauusd_current_terminal_position_limits import validate_current_terminal_position_limits


CONTRACT = "trading.xauusd_current_entry_quantity_constraint_composition.v1"
RULE_VERSION = "xauusd_current_entry_quantity_constraint_composition_v1"
IDENTITY_PREFIX = "current_entry_quantity_constraint_composition_"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
JOIN_REQUIREMENTS = tuple(sorted((
    "ACCOUNT_ORIGINALS", "REGIME_ORIGINALS", "ACCOUNT_IDENTITY", "PROVIDER_AND_VENUE",
    "INSTRUMENT_IDENTITY", "DIRECTION_AND_MECHANISM", "QUANTITY_DENOMINATION",
    "MONETARY_DENOMINATION", "CURRENT_BOUNDARY", "CANDIDATE_AND_HISTORY", "INDEPENDENT_SCOPE_ADMISSION",
)))
CONDITIONS = (
    "ACCEPTED_ENTRY_FULLY_FILLED", "ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS",
    "NO_UNRELATED_INTERVENING_STATE_CHANGE", "ADMITTED_MECHANICS_REMAIN_APPLICABLE",
    "ADMITTED_RULES_REMAIN_APPLICABLE_AT_TERMINAL_STATE", "CONDITIONAL_ON_RECONSTRUCTED_RISK_BASIS",
)
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                          "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
DOWNSTREAM_OBLIGATIONS = sorted((
    "ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL", "CANDIDATE_VALIDITY",
    "CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION", "ENTRY_QUANTITY_DOMAIN_MEMBERSHIP",
    "EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE", "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY",
    "MARKET_ORDER_AND_FILL_FEASIBILITY", "MISSION_CONTROL_CURRENT_AUTHORIZATION",
    "ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES", "OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE",
    "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE", "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM",
    "QUANTITY_SELECTION_POLICY_AND_SELECTION", "RISK_BUDGET_QUANTITY_FEASIBILITY",
))
REASON_CODES = frozenset((
    "CONDITIONAL_QUANTITY_DOMAIN_ESTABLISHED", "NATIVE_PREREQUISITE_NOT_SUITABLE", "EMPTY_COMMON_SUPPORT",
    "NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY", "EMPTY_TERMINAL_INTERSECTION",
    "TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE", "OWNER_MISSING", "OWNER_UNKNOWN",
    "JOIN_UNRESOLVED", "NATIVE_UNRESOLVED",
))
_CONTEXT_KEYS = (
    "trusted_planning_context_sha256", "trusted_quantity_context_sha256", "trusted_feasibility_context_sha256",
    "trusted_position_effect_context_sha256", "trusted_position_limit_context_sha256",
)
_NAMESPACE = "source_id source_contract source_contract_version"
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields.")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty opaque UTF-8 text.")
    value.encode("utf-8")


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported closed value.")


def _integer_text(value):
    if value == 0:
        return "0"
    sign, value = ("-" if value < 0 else ""), abs(value)
    parts = []
    while value:
        value, part = divmod(value, 10 ** 9)
        parts.append(part)
    return sign + str(parts[-1]) + "".join(str(part).zfill(9) for part in reversed(parts[:-1]))


def _integer(digits):
    sign = -1 if digits.startswith("-") else 1
    digits = digits.lstrip("-")
    result = 0
    for offset in range(0, len(digits), 9):
        part = digits[offset:offset + 9]
        result = result * 10 ** len(part) + int(part)
    return sign * result


def _canonical(value):
    """Standard compact JSON, with unbounded integer rendering and strict types."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings.")
        return "{" + ",".join(_canonical(key) + ":" + _canonical(value[key]) for key in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if type(value) is str:
        value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return _integer_text(value)
    if type(value) is float and math.isfinite(value):
        return json.dumps(value, allow_nan=False)
    raise ValueError("Expected finite serialized JSON.")


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " mismatch.")


def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Expected timezone-qualified timestamp with at most microseconds.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _scope(value):
    _keys(value, "account provider_namespace provider_id venue_id instrument entry_direction entry_mechanism quantity_unit")
    _keys(value["account"], _NAMESPACE + " account_id environment currency")
    _keys(value["instrument"], _NAMESPACE + " environment instrument_id")
    _keys(value["provider_namespace"], _NAMESPACE)
    for name in ("account", "instrument", "provider_namespace"):
        for item in value[name].values():
            _text(item)
    for name in ("provider_id", "venue_id", "quantity_unit"):
        _text(value[name])
    for name in ("account", "instrument"):
        _enum(value[name]["environment"], ("DEMO", "LIVE"))
    if re.fullmatch(r"[A-Z]{3}", value["account"]["currency"]) is None:
        raise ValueError("Currency requires three uppercase ASCII letters.")
    _same(value["account"]["environment"], value["instrument"]["environment"], "Environment")
    _enum(value["entry_direction"], ("LONG", "SHORT"))
    _enum(value["entry_mechanism"], (MECHANISM,))


def _get(value, *path):
    """Only fixed internal paths into already replayed native structures."""
    for key in path:
        if value is None:
            return None
        value = value.get(key)
    return value


def _compare(values, label):
    available = [value for value in values if value is not None]
    for value in available[1:]:
        _same(available[0], value, label)
    return bool(values) and len(available) == len(values)


def _joins(q, financial, terminal, planning):
    """Check every known literal before computing admission-dependent join facts."""
    fr = _get(q["risk_budget_feasibility"], "request")
    tr = _get(q["terminal_position_limits"], "request")
    # Native results in the original envelopes are usable only after top-level replay.
    rp, rb, qd = (_get(fr, key) for key in ("risk_policy", "risk_basis", "quantity_domain"))
    pe = _get(tr, "position_effect")
    pa = _get(pe, "assessment")
    scope, at = q["scope"], q["knowledge_boundary"]
    checks = dict.fromkeys(JOIN_REQUIREMENTS, False)
    account_pairs = [_get(pair, "request", "account_state") for pair in (rp, rb, pe)]
    checks["ACCOUNT_ORIGINALS"] = _compare(account_pairs, "Original account pair")
    regimes = [_get(rp, "request", "account_rule_regime"), _get(tr, "account_rule_regime")]
    checks["REGIME_ORIGINALS"] = _compare(regimes, "Original regime pair")

    account_complete = True
    for pair in account_pairs:
        observation = _get(pair, "snapshot", "observation")
        identity = None
        if observation is not None:
            identity = {key: observation["source"][key] for key in _NAMESPACE.split()}
            identity.update({key: observation["account"][key] for key in ("account_id", "environment", "currency")})
        account_complete = _compare([scope["account"], identity], "Qualified account") and account_complete
    selected = []
    for pair in regimes:
        native_account = _get(pair, "assessment", "account")
        expected = {key: scope["account"][key] for key in (_NAMESPACE + " account_id environment").split()}
        account_complete = _compare([expected, native_account], "Regime account") and account_complete
        selected.append(_get(pair, "assessment", "selected_regime"))
    checks["ACCOUNT_IDENTITY"] = account_complete

    ps, ts, ds = _get(pa, "scope"), _get(terminal, "scope"), _get(qd, "assessment", "scope")
    scopes_complete = True
    for actual in (ps, ts):
        scopes_complete = _compare([scope, actual], "Qualified entry scope") and scopes_complete
    grid_complete = True
    for field in ("provider_id", "venue_id", "account_id", "environment", "instrument_id",
                  "entry_direction", "entry_mechanism", "quantity_unit"):
        expected = scope["account"][field] if field in ("account_id", "environment") else (
            scope["instrument"][field] if field == "instrument_id" else scope[field])
        grid_complete = _compare([expected, _get(ds, field)], "Entry-grid " + field) and grid_complete

    rb_result = _get(rb, "assessment")
    spec = _get(rb_result, "reconstruction_evidence", "selected_specification", "specification")
    namespace = _get(spec, "position_namespace")
    qualified = None if namespace is None else {key: namespace[key] for key in scope["instrument"]}
    instrument_complete = _compare([scope["instrument"], qualified], "Financial instrument")
    venue_complete = _compare([scope["venue_id"], _get(planning, "scope", "venue_id")], "Planning venue")
    providers_complete = True
    for regime in selected:
        for key in ("assignment", "package"):
            providers_complete = _compare([scope["provider_id"], _get(regime, key, "provider_id")],
                                          "Selected provider") and providers_complete

    candidates = [_get(pair, "request", "candidate") for pair in (rp, rb)]
    history_complete = _compare(candidates, "Original candidate pair")
    history_complete = (history_complete and _get(rb, "request", "validity") is not None and
                        _get(rp, "request", "financial_measurement") is not None)
    checks["CANDIDATE_AND_HISTORY"] = history_complete
    direction_complete = True
    for pair in candidates:
        direction_complete = _compare([scope["entry_direction"], _get(pair, "formulation", "candidate", "direction")],
                                      "Candidate direction") and direction_complete
    scenario = _get(rb_result, "scenario")
    effect = _get(pa, "effect_basis")
    direction_complete = _compare([scope["entry_direction"], _get(scenario, "direction"),
                                   _get(effect, "resulting_direction")], "Scenario direction") and direction_complete
    mechanism_complete = _compare([scope["entry_mechanism"], _get(scenario, "mechanism")], "Entry mechanism")

    function = _get(rb_result, "risk_function")
    units = [scope["quantity_unit"], _get(namespace, "quantity_unit"), _get(function, "quantity_unit"),
             _get(effect, "quantity_unit")]
    for name in ("entry_domain", "supported_entry_domain", "feasible_domain", "outside_risk_support", "risk_support"):
        units.append(_get(financial, name, "quantity_unit"))
    units_complete = _compare(units, "Quantity denomination")
    currencies_complete = _compare([scope["account"]["currency"], _get(financial, "budget", "currency"),
                                   _get(function, "pnl_currency"), _get(spec, "payoff", "pnl_currency")],
                                  "Monetary denomination")
    current_complete = True
    for result in (financial, terminal, pa):
        for field in ("assessment_economic_time", "knowledge_boundary"):
            actual = _get(result, field)
            current_complete = _compare([at, None if actual is None else _time(actual)], "Current boundary") and current_complete
    checks["CURRENT_BOUNDARY"] = current_complete

    # These two native establishments imply their original, scoped semantic admissions.
    admitted = (_get(financial, "outcome") == "ESTABLISHED" and _get(pa, "outcome") == "ESTABLISHED")
    checks["INDEPENDENT_SCOPE_ADMISSION"] = admitted
    checks["PROVIDER_AND_VENUE"] = admitted and checks["REGIME_ORIGINALS"] and grid_complete and scopes_complete and venue_complete and providers_complete
    checks["INSTRUMENT_IDENTITY"] = admitted and instrument_complete and grid_complete and scopes_complete
    checks["DIRECTION_AND_MECHANISM"] = admitted and direction_complete and mechanism_complete and grid_complete and scopes_complete
    checks["QUANTITY_DENOMINATION"] = admitted and units_complete and grid_complete and scopes_complete
    checks["MONETARY_DENOMINATION"] = admitted and currencies_complete and checks["ACCOUNT_ORIGINALS"]
    support = _get(effect, "quantity_range")
    reported = _get(terminal, "position_effect_support", "interval")
    _compare([support, reported], "Position-effect support")
    return checks, support


def _number(value):
    whole, _, part = value.lstrip("-").partition(".")
    return Fraction((-1 if value.startswith("-") else 1) * _integer(whole + part), 10 ** len(part))


def _slice(grid, first, last):
    if first > last:
        return dict(kind="EMPTY")
    return dict(kind="REGULAR_GRID", origin=grid["origin"], increment=grid["increment"],
                first_index=_integer_text(first), last_index=_integer_text(last))


def _clip(grid, interval):
    if grid["kind"] == "EMPTY" or interval["kind"] == "EMPTY":
        return dict(kind="EMPTY")
    origin, step = _number(grid["origin"]), _number(grid["increment"])
    lower = (_number(interval["minimum"]) - origin) / step
    upper = (_number(interval["maximum"]) - origin) / step
    first = max(_integer(grid["first_index"]), -((-lower.numerator) // lower.denominator))
    last = min(_integer(grid["last_index"]), upper.numerator // upper.denominator)
    return _slice(grid, first, last)


def _outside(grid, interval):
    origin, step = _number(grid["origin"]), _number(grid["increment"])
    lo = (_number(interval["minimum"]) - origin) / step
    hi = (_number(interval["maximum"]) - origin) / step
    first, last = _integer(grid["first_index"]), _integer(grid["last_index"])
    segments = [_slice(grid, first, min(last, -((-lo.numerator) // lo.denominator) - 1)),
                _slice(grid, max(first, hi.numerator // hi.denominator + 1), last)]
    return [segment for segment in segments if segment["kind"] != "EMPTY"]


def _reference(owner, collection, index, item):
    return dict(owner=owner, collection=collection, index=index, content_sha256=_digest(item))


def _ref_key(ref):
    return ref["owner"], ref["collection"], ref["index"]


def _sorted_unique(rows):
    return sorted({_canonical(row): row for row in rows}.values(), key=_canonical)


def _evaluate(request, contexts):
    _canonical(request)
    for context in contexts:
        _canonical(context)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope risk_budget_feasibility terminal_position_limits")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for field in ("assessment_economic_time", "knowledge_boundary"):
        q[field] = _time(q[field])
    _same(q["assessment_economic_time"], q["knowledge_boundary"], "Current T/K")
    _scope(q["scope"])
    owners = dict.fromkeys(("FINANCIAL", "TERMINAL"))
    for label, key, supplied_contexts in (("FINANCIAL", "risk_budget_feasibility", contexts[:3]),
                                          ("TERMINAL", "terminal_position_limits", contexts[3:])):
        pair = q[key]
        if pair is None:
            if any(context is not None for context in supplied_contexts):
                raise ValueError("Orphaned context for absent native owner.")
            continue
        _keys(pair, "assessment request")
        if type(pair["assessment"]) is not dict or type(pair["request"]) is not dict:
            raise ValueError("Native owner pair requires serialized JSON objects.")
        if label == "FINANCIAL":
            owners[label] = validate_current_risk_budget_quantity_feasibility(
                pair["assessment"], pair["request"], trusted_planning_context=contexts[0],
                trusted_quantity_context=contexts[1], trusted_feasibility_context=contexts[2])
        else:
            owners[label] = validate_current_terminal_position_limits(
                pair["assessment"], pair["request"], trusted_position_effect_context=contexts[3],
                trusted_position_limit_context=contexts[4])
    financial, terminal = owners.values()
    checks, support = _joins(q, financial, terminal, contexts[0])
    # All supplied native material and known cross-owner contradictions were checked.
    proofs, findings, native_negatives = [], [], []
    owner_refs = dict(financial=None, terminal=None)
    fingerprints = dict.fromkeys(_CONTEXT_KEYS)
    for label, result in owners.items():
        if result is None:
            findings.append(dict(reason_code="OWNER_MISSING", subject=label, native_reference=None))
            continue
        key = "risk_budget_feasibility" if label == "FINANCIAL" else "terminal_position_limits"
        owner_refs[label.lower()] = dict(assessment_identity=result["assessment_identity"], owner_bundle_sha256=_digest(q[key]))
        for field in (_CONTEXT_KEYS[:3] if label == "FINANCIAL" else _CONTEXT_KEYS[3:]):
            fingerprints[field] = result["reconstruction_evidence"][field]
        if result["outcome"] == "UNKNOWN":
            findings.append(dict(reason_code="OWNER_UNKNOWN", subject=label, native_reference=None))
        for index, item in enumerate(result["negative_proofs"]):
            ref = _reference(label, "negative_proofs", index, item)
            native_negatives.append(ref)
            sufficient = label == "FINANCIAL" or item["excluded_domain"]["kind"] == "ALL_SUPPORT"
            if result["outcome"] == "NOT_SUITABLE" and sufficient:
                proofs.append(dict(kind="NATIVE_PREREQUISITE_NOT_SUITABLE", native_proof=ref))
        for index, item in enumerate(result["unresolved_findings"]):
            findings.append(dict(reason_code="NATIVE_UNRESOLVED", subject=label,
                                 native_reference=_reference(label, "unresolved_findings", index, item)))
    for name, proven in checks.items():
        if not proven:
            findings.append(dict(reason_code="JOIN_UNRESOLVED", subject=name, native_reference=None))
    common = composed = None
    limitations = dict(outside_risk_support=None, financially_feasible_outside_position_support=None)
    if all(checks.values()):
        interval = dict(kind="CLOSED_INTERVAL", **support)
        f = financial["feasible_domain"]["domain"]
        s = _clip(financial["supported_entry_domain"]["domain"], interval)
        b = _clip(f, interval)
        unit = q["scope"]["quantity_unit"]
        common = dict(quantity_unit=unit, domain=s)
        limitations = dict(outside_risk_support=deepcopy(financial["outside_risk_support"]),
                            financially_feasible_outside_position_support=_outside(f, interval))
        reason = None
        if s["kind"] == "EMPTY":
            reason, c = "EMPTY_COMMON_SUPPORT", dict(kind="EMPTY")
        elif b["kind"] == "EMPTY":
            reason, c = "NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY", dict(kind="EMPTY")
        elif terminal["outcome"] == "ESTABLISHED":
            c = _clip(f, terminal["terminal_satisfying_domain"])
            if c["kind"] == "EMPTY":
                reason = "EMPTY_TERMINAL_INTERSECTION"
        else:
            c, witnesses = None, []
            first_quantity = _number(b["origin"]) + _integer(b["first_index"]) * _number(b["increment"])
            for index, item in enumerate(terminal["negative_proofs"]):
                excluded = item["excluded_domain"]
                covers = excluded["kind"] == "ALL_SUPPORT" or (
                    excluded["kind"] == "UPPER_TAIL" and _number(excluded["upper_inclusive"]) == _number(support["maximum"])
                    and first_quantity > _number(excluded["lower_exclusive"]))
                if covers:
                    witnesses.append(_reference("TERMINAL", "negative_proofs", index, item))
            if witnesses:
                c = dict(kind="EMPTY")
                proofs.append(dict(kind="TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE",
                                   covered_domain=dict(quantity_unit=unit, domain=b), native_proofs=sorted(witnesses, key=_ref_key)))
        if reason is not None:
            proofs.append(dict(kind=reason))
        if c is not None:
            composed = dict(quantity_unit=unit, domain=c)
    proofs, findings = _sorted_unique(proofs), _sorted_unique(findings)
    if proofs:
        outcome = "NOT_SUITABLE"
    elif findings:
        outcome = "UNKNOWN"
    elif composed is not None and composed["domain"]["kind"] == "REGULAR_GRID":
        outcome = "ESTABLISHED"
    else:
        raise ValueError("Incomplete composition proof without an unresolved finding.")
    reasons = {row["kind"] for row in proofs} | {row["reason_code"] for row in findings}
    if outcome == "ESTABLISHED":
        reasons.add("CONDITIONAL_QUANTITY_DOMAIN_ESTABLISHED")
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=q["assessment_economic_time"],
                  knowledge_boundary=q["knowledge_boundary"], scope=q["scope"], outcome=outcome, reason_codes=sorted(reasons),
                  owner_references=owner_refs,
                  join_checks=[dict(requirement=name, status="PROVEN" if checks[name] else "UNKNOWN") for name in JOIN_REQUIREMENTS],
                  common_supported_domain=common, composed_domain=composed, support_limitations=limitations,
                  native_negative_proof_references=sorted(native_negatives, key=_ref_key), negative_proofs=proofs,
                  unresolved_findings=findings, conditions=list(CONDITIONS),
                  reconstruction_evidence=dict(request=q, **fingerprints), downstream_obligations=list(DOWNSTREAM_OBLIGATIONS),
                  source_authentication=SOURCE_AUTHENTICATION, authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = IDENTITY_PREFIX + _digest(result)
    return result


def evaluate_current_entry_quantity_constraint_composition(
    request: dict, *, trusted_planning_context=None, trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
) -> dict:
    """Replay native proofs and derive bounded conditional sets; never select an order."""
    try:
        return deepcopy(_evaluate(request, (trusted_planning_context, trusted_quantity_context, trusted_feasibility_context,
                                           trusted_position_effect_context, trusted_position_limit_context)))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed current entry quantity-constraint composition request.") from exc


def validate_current_entry_quantity_constraint_composition(
    assessment: dict, request: dict, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None, trusted_position_limit_context=None,
) -> dict:
    """Reevaluate every field; a caller-recomputed identity grants no trust."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be a serialized JSON object.")
        _canonical(assessment)
        expected = evaluate_current_entry_quantity_constraint_composition(
            request, trusted_planning_context=trusted_planning_context, trusted_quantity_context=trusted_quantity_context,
            trusted_feasibility_context=trusted_feasibility_context, trusted_position_effect_context=trusted_position_effect_context,
            trusted_position_limit_context=trusted_position_limit_context)
        _same(assessment, expected, "Quantity composition assessment")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized quantity-constraint composition assessment.") from exc
