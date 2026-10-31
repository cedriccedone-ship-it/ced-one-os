"""Independently admitted conditional terminal position facts; no order authority."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import re

from .causal_financial_account_state_snapshot import validate_causal_financial_account_state_snapshot


CONTRACT = "trading.xauusd_current_entry_position_effect_basis.v1"
RULE_VERSION = "xauusd_current_entry_position_effect_basis_v1"
INVENTORY_CONTRACT = "trading.xauusd_current_entry_position_effect_basis.inventory.v1"
INVENTORY_RULE = "xauusd_current_entry_position_effect_basis_inventory_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_entry_position_effect_basis.admission.v1"
ADMISSION_RULE = "xauusd_current_entry_position_effect_basis_admission_v1"
PURPOSE = "POSITION_EFFECT_FACT_ADMISSION_ONLY"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
MODEL = "ONE_NEW_SEPARATE_POSITION"
AGGREGATION = "ALL_ENTRY_FILLS_TO_ONE_POSITION"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
ASSURANCES = (
    "source_authority", "original_positions_and_commitments", "coverage_and_common_state",
    "mechanics_and_revisions", "identity_and_quantity_semantics", "causal_availability",
)
BINDINGS = ("account_provider_venue", "instrument_namespace", "quantity_denomination", "direction_and_mechanism")
CATEGORIES = (
    "PENDING_SUBMISSIONS", "ACCEPTED_UNFILLED_ORDERS", "PARTIALLY_FILLED_ORDERS",
    "CANCELLATIONS_AWAITING_CONFIRMATION", "POSITION_RESERVATIONS", "POSITION_ALLOCATIONS",
    "OTHER_PROVIDER_OR_ACCOUNT_PENDING_EFFECTS",
)
CONDITIONS = (
    "ACCEPTED_ENTRY_FULLY_FILLED", "ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS",
    "NO_UNRELATED_INTERVENING_STATE_CHANGE", "ADMITTED_MECHANICS_REMAIN_APPLICABLE",
)
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                           "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
DOWNSTREAM_OBLIGATIONS = sorted((
    "ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL", "CANDIDATE_VALIDITY",
    "CURRENT_STATE_AND_MECHANICS_REVALIDATION", "ENTRY_QUANTITY_DOMAIN_MEMBERSHIP",
    "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY", "MARKET_ORDER_AND_FILL_FEASIBILITY",
    "MISSION_CONTROL_CURRENT_AUTHORIZATION", "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE",
    "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM", "QUANTITY_SELECTION_POLICY_AND_SELECTION",
    "RISK_BUDGET_QUANTITY_FEASIBILITY",
))
REASON_CODES = frozenset((
    "MISSING_ACCOUNT_STATE", "MISSING_EFFECT_INVENTORY", "MISSING_HOST_ADMISSION", "ADMISSION_NOT_CURRENT",
    "ASSURANCE_UNRESOLVED", "SOURCE_AVAILABILITY_UNKNOWN", "SUPPORTING_EVIDENCE_MISSING",
    "COVERAGE_INCOMPLETE", "COVERAGE_NOT_CURRENT", "REVISION_HISTORY_INCOMPLETE", "REVISION_ORDER_UNSUPPORTED",
    "COMPETING_REVISION_CHAINS", "NO_CURRENT_DECLARATION", "CURRENT_DECLARATION_WITHDRAWN",
    "CURRENT_DECLARATION_EXPIRED", "ACCOUNT_STATE_NOT_CURRENT", "POSITION_INVENTORY_INCOMPLETE",
    "ACCOUNT_NOT_FLAT", "ACCOUNT_MODE_UNRESOLVED", "BINDING_UNRESOLVED", "BINDING_INCOMPATIBLE",
    "MECHANICS_UNSUPPORTED_OR_UNKNOWN", "QUANTITY_RANGE_UNESTABLISHED", "COMMITMENT_REPORT_MISSING",
    "COMMITMENT_COVERAGE_INCOMPLETE", "COMMITMENT_PRESENT", "COMMITMENT_STATUS_UNKNOWN",
    "POSITION_EFFECT_BASIS_ESTABLISHED",
))
_COMPLETENESS = ("COMPLETE", "LIMITED", "UNKNOWN")
_MODES = ("NETTING", "HEDGING", "UNKNOWN")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields.")


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected a nonempty opaque identifier.")
    value.encode("utf-8")
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported closed value.")
    return value


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected a serialized JSON list.")
    return value


def _integer(digits):
    result = 0
    for offset in range(0, len(digits), 9):
        chunk = digits[offset:offset + 9]
        result = result * 10 ** len(chunk) + int(chunk)
    return result


def _integer_text(value):
    if value == 0:
        return "0"
    sign, value = ("-" if value < 0 else ""), abs(value)
    chunks = []
    while value:
        value, chunk = divmod(value, 10 ** 9)
        chunks.append(chunk)
    return sign + str(chunks[-1]) + "".join(str(chunk).zfill(9) for chunk in reversed(chunks[:-1]))


def _canonical(value):
    """Strict JSON, including unbounded integer rendering without interpreter changes."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON keys must be strings.")
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
    raise ValueError("Expected finite serialized JSON values.")


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " mismatch.")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected a lowercase SHA-256 fingerprint.")


def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Timestamp requires seconds, timezone and at most microseconds.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _optional_time(value):
    return None if value is None else _time(value)


def _timing(row, at):
    row["observed_at"] = _time(row["observed_at"])
    row["source_available_at"] = _optional_time(row["source_available_at"])
    if row["observed_at"] > at or (row["source_available_at"] is not None and
                                     row["source_available_at"] > row["observed_at"]):
        raise ValueError("Evidence was not causally available by K.")


def _interval(row, first="effective_from", last="effective_until"):
    row[first], row[last] = _time(row[first]), _optional_time(row[last])
    if row[last] is not None and row[first] >= row[last]:
        raise ValueError("Interval must be nonempty.")


def _contains(row, at, first="effective_from", last="effective_until"):
    return row[first] <= at and (row[last] is None or at < row[last])


def _cutoff(row, container, at):
    row["source_information_cutoff"] = _optional_time(row["source_information_cutoff"])
    cutoff = row["source_information_cutoff"]
    if cutoff is not None and (cutoff > at or cutoff > container["observed_at"] or
                              (container["source_available_at"] is not None and cutoff > container["source_available_at"])):
        raise ValueError("Information cutoff exceeds its observation/publication boundary.")


def _state(row, container):
    row["state_at"] = _time(row["state_at"])
    if row["state_at"] > container["observed_at"] or (
        container["source_available_at"] is not None and row["state_at"] > container["source_available_at"]
    ):
        raise ValueError("State assertion postdates its observation/publication.")


def _namespace(value, snapshot=False):
    _keys(value, "source_id source_contract source_contract_version" + (" source_snapshot_id" if snapshot else ""))
    for item in value.values():
        _text(item)


def _scope(scope):
    _keys(scope, "account provider_namespace provider_id venue_id instrument entry_direction entry_mechanism quantity_unit")
    account, instrument = scope["account"], scope["instrument"]
    _keys(account, "source_id source_contract source_contract_version account_id environment currency")
    _keys(instrument, "source_id source_contract source_contract_version environment instrument_id")
    for node in (account, instrument):
        for item in node.values():
            _text(item)
        _enum(node["environment"], ("DEMO", "LIVE"))
    if re.fullmatch(r"[A-Z]{3}", account["currency"]) is None:
        raise ValueError("Currency requires three uppercase ASCII letters.")
    _same(instrument["environment"], account["environment"], "Instrument environment")
    _namespace(scope["provider_namespace"])
    for key in ("provider_id", "venue_id", "quantity_unit"):
        _text(scope[key])
    _enum(scope["entry_direction"], ("LONG", "SHORT"))
    _enum(scope["entry_mechanism"], (MECHANISM,))


def _unique(rows, key):
    rows = _list(rows)
    ids = [row[key] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate identity/reference.")
    return sorted(rows, key=lambda row: row[key])


def _refs(value, key="evidence_id"):
    for row in _list(value):
        _keys(row, key + " content_sha256")
        _text(row[key])
        _hash(row["content_sha256"])
    return _unique(value, key)


def _reference_arrays(node, path=""):
    """Traverse only local objects; native reconstruction representations stay untouched."""
    if type(node) is dict:
        for key, item in node.items():
            child = path + "/" + key
            if key in ("evidence_refs", "binding_evidence_refs"):
                yield child, item
            else:
                yield from _reference_arrays(item, child)
    elif type(node) is list:
        for index, item in enumerate(node):
            yield from _reference_arrays(item, path + "/" + str(index))


def _normalize_refs(node):
    for _, refs in _reference_arrays(node):
        refs[:] = _refs(refs)


def _check_refs(refs, catalog, deadline):
    for ref in refs:
        target = catalog.get(ref["evidence_id"])
        if target is None or _digest(target) != ref["content_sha256"]:
            raise ValueError("Missing or mismatched original evidence reference.")
        if target["observed_at"] > deadline:
            raise ValueError("Supporting evidence postdates its containing assertion.")


def _decimal(value):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Quantity bounds require plain decimal strings.")
    result = value.rstrip("0").rstrip(".") if "." in value else value
    return "0" if result in ("0", "-0") else result


def _fraction(value):
    whole, _, part = value.lstrip("-").partition(".")
    return Fraction((-1 if value.startswith("-") else 1) * _integer(whole + part), 10 ** len(part))


def _range(value):
    if value is None:
        return
    _keys(value, "minimum maximum")
    for key in value:
        value[key] = _decimal(value[key])
    if not 0 < _fraction(value["minimum"]) <= _fraction(value["maximum"]):
        raise ValueError("Quantity interval must be finite, positive and ordered.")


def _body(body, record, at):
    _keys(body, "account_bundle_sha256 positions bindings mechanics commitments")
    _hash(body["account_bundle_sha256"])
    positions, bindings, mechanics, commitments = (body[k] for k in ("positions", "bindings", "mechanics", "commitments"))
    _keys(positions, "state_at source_information_cutoff inventory_completeness revision_completeness population_scope evidence_refs")
    _enum(positions["population_scope"], ("ALL_ACCOUNT_POSITIONS",))
    for key in ("inventory_completeness", "revision_completeness"):
        _enum(positions[key], _COMPLETENESS)
    _state(positions, record)
    _cutoff(positions, record, at)
    _keys(bindings, " ".join(BINDINGS))
    for claim in bindings.values():
        _keys(claim, "status evidence_refs")
        _enum(claim["status"], ("COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"))
    _keys(mechanics, "position_mode model fill_aggregation quantity_range source_information_cutoff revision_completeness evidence_refs")
    _enum(mechanics["position_mode"], _MODES)
    _enum(mechanics["model"], (MODEL, "OTHER", "UNKNOWN"))
    _enum(mechanics["fill_aggregation"], (AGGREGATION, "OTHER", "UNKNOWN"))
    _range(mechanics["quantity_range"])
    _enum(mechanics["revision_completeness"], _COMPLETENESS)
    _cutoff(mechanics, record, at)
    _keys(commitments, "state_at source_information_cutoff population_scope source_universe_completeness actor_coverage inventory_roster reports evidence_refs")
    _enum(commitments["population_scope"], ("ALL_ACCOUNT_POSITION_AFFECTING_COMMITMENTS",))
    _enum(commitments["source_universe_completeness"], _COMPLETENESS)
    _enum(commitments["actor_coverage"], ("ALL_ACCOUNT_ACTORS", "UNKNOWN"))
    _state(commitments, record)
    _cutoff(commitments, record, at)
    for member in _list(commitments["inventory_roster"]):
        _keys(member, "inventory_id source_namespace source_account_id role binding_evidence_refs")
        _text(member["inventory_id"])
        _text(member["source_account_id"])
        _namespace(member["source_namespace"])
        _enum(member["role"], ("PROVIDER", "SUBMISSION_CHANNEL", "RESERVATION_OR_ALLOCATION", "OTHER_POSITION_EFFECT_SOURCE"))
    commitments["inventory_roster"] = _unique(commitments["inventory_roster"], "inventory_id")
    roster = {row["inventory_id"]: row for row in commitments["inventory_roster"]}
    for report in _list(commitments["reports"]):
        _keys(report, "inventory_id source state_at source_information_cutoff inventory_completeness revision_completeness source_available_at observed_at categories evidence_refs")
        _text(report["inventory_id"])
        _namespace(report["source"], True)
        member = roster.get(report["inventory_id"])
        if member is None:
            raise ValueError("Commitment report is absent from the roster.")
        _same(member["source_namespace"], {k: report["source"][k] for k in member["source_namespace"]}, "Report namespace")
        _timing(report, at)
        if report["observed_at"] > record["observed_at"]:
            raise ValueError("Declaration precedes a contained report.")
        _state(report, report)
        _cutoff(report, report, at)
        for key in ("inventory_completeness", "revision_completeness"):
            _enum(report[key], _COMPLETENESS)
        _keys(report["categories"], " ".join(CATEGORIES))
        for category in report["categories"].values():
            _keys(category, "status evidence_refs")
            _enum(category["status"], ("EMPTY", "NONEMPTY", "UNKNOWN"))
    commitments["reports"] = _unique(commitments["reports"], "inventory_id")


def _inventory(value, scope, at):
    if value is None:
        return None
    _keys(value, "contract rule_version source scope source_available_at observed_at evidence coverage records")
    _enum(value["contract"], (INVENTORY_CONTRACT,))
    _enum(value["rule_version"], (INVENTORY_RULE,))
    _namespace(value["source"], True)
    _scope(value["scope"])
    _same(value["scope"], scope, "Inventory scope")
    _timing(value, at)
    for item in _list(value["evidence"]):
        _keys(item, "evidence_id source media_type content_base64 source_available_at observed_at")
        _text(item["evidence_id"])
        _text(item["media_type"])
        _namespace(item["source"], True)
        if type(item["content_base64"]) is not str:
            raise ValueError("Original evidence requires canonical base64.")
        raw = base64.b64decode(item["content_base64"], validate=True)
        if not raw or base64.b64encode(raw).decode("ascii") != item["content_base64"]:
            raise ValueError("Original bytes must be nonempty and canonically encoded.")
        _timing(item, at)
    value["evidence"] = _unique(value["evidence"], "evidence_id")
    coverage = value["coverage"]
    _keys(coverage, "economic_from economic_until source_information_cutoff declaration_completeness revision_completeness starting_basis root_records missing_record_ids records_omitted history_truncated source_available_at observed_at evidence_refs")
    _timing(coverage, at)
    _interval(coverage, "economic_from", "economic_until")
    _cutoff(coverage, coverage, at)
    for key in ("declaration_completeness", "revision_completeness"):
        _enum(coverage[key], _COMPLETENESS)
    _enum(coverage["starting_basis"], ("FROM_INCEPTION", "INCOMPLETE_OR_UNKNOWN"))
    coverage["root_records"] = _refs(coverage["root_records"], "record_id")
    missing = [_text(item) for item in _list(coverage["missing_record_ids"])]
    if len(set(missing)) != len(missing):
        raise ValueError("Duplicate missing-record identity.")
    coverage["missing_record_ids"] = sorted(missing)
    for key in ("records_omitted", "history_truncated"):
        if coverage[key] is not None and type(coverage[key]) is not bool:
            raise ValueError("Omission flags require booleans or null.")
    for record in _list(value["records"]):
        if type(record) is not dict:
            raise ValueError("Expected a revision record.")
        kind = _enum(record.get("kind"), ("DECLARE", "WITHDRAW"))
        _keys(record, "record_id kind predecessor effective_from source_available_at observed_at evidence_refs" +
              (" effective_until body" if kind == "DECLARE" else ""))
        _text(record["record_id"])
        _timing(record, at)
        previous = record["predecessor"]
        if type(previous) is not dict:
            raise ValueError("Expected a tagged predecessor.")
        _enum(previous.get("kind"), ("ROOT", "UNKNOWN", "RECORD"))
        _keys(previous, "kind" + (" record" if previous["kind"] == "RECORD" else ""))
        if previous["kind"] == "RECORD":
            _refs([previous["record"]], "record_id")
        if kind == "DECLARE":
            _interval(record)
            _body(record["body"], record, at)
        else:
            record["effective_from"] = _time(record["effective_from"])
            if previous["kind"] == "ROOT":
                raise ValueError("Withdrawal cannot be a root.")
    value["records"] = _unique(value["records"], "record_id")
    _normalize_refs(value)
    catalog = {row["evidence_id"]: row for row in value["evidence"]}
    for node in [coverage, *value["records"], *value["evidence"]]:
        if node["observed_at"] > value["observed_at"]:
            raise ValueError("Inventory precedes a contained observation.")
    _check_refs(coverage["evidence_refs"], catalog, coverage["observed_at"])
    for record in value["records"]:
        _check_refs(record["evidence_refs"], catalog, record["observed_at"])
        if record["kind"] == "DECLARE":
            body = record["body"]
            for path, refs in _reference_arrays(body):
                if not path.startswith("/commitments/reports/"):
                    _check_refs(refs, catalog, record["observed_at"])
            for report in body["commitments"]["reports"]:
                for _, refs in _reference_arrays(report):
                    _check_refs(refs, catalog, report["observed_at"])
    return value


def _history(inventory):
    """Validate every component before resolving a whole-declaration replacement chain."""
    coverage = inventory["coverage"]
    records = {row["record_id"]: row for row in inventory["records"]}
    missing = set(coverage["missing_record_ids"])
    if missing & records.keys():
        raise ValueError("A declared missing record is supplied.")

    def referenced(ref):
        row = records.get(ref["record_id"])
        if row is None:
            if ref["record_id"] not in missing:
                raise ValueError("Unexplained dangling predecessor/root reference.")
        elif _digest(row) != ref["content_sha256"]:
            raise ValueError("Revision content fingerprint mismatch.")
        return row

    roots = {ref["record_id"] for ref in coverage["root_records"]}
    for ref in coverage["root_records"]:
        row = referenced(ref)
        if row is not None and row["predecessor"]["kind"] != "ROOT":
            raise ValueError("Declared root is not a root record.")
    children = {}
    backwards = []
    for index, row in enumerate(inventory["records"]):
        previous = row["predecessor"]
        if previous["kind"] == "ROOT" and row["record_id"] not in roots:
            raise ValueError("Supplied root is missing from coverage.")
        if previous["kind"] == "RECORD":
            parent = referenced(previous["record"])
            if parent is not None:
                children.setdefault(parent["record_id"], []).append(row)
                if any(row[key] < parent[key] for key in ("effective_from", "observed_at")) or (
                    row["source_available_at"] is not None and parent["source_available_at"] is not None and
                    row["source_available_at"] < parent["source_available_at"]
                ):
                    backwards.append(index)
    finished = set()
    for identifier in records:
        path, current = set(), identifier
        while current in records and current not in finished:
            if current in path:
                raise ValueError("Cyclic revision predecessor references.")
            path.add(current)
            previous = records[current]["predecessor"]
            if previous["kind"] != "RECORD":
                break
            current = previous["record"]["record_id"]
        finished.update(path)
    gaps = bool(missing) or coverage["starting_basis"] != "FROM_INCEPTION" or any(
        coverage[key] is not False for key in ("records_omitted", "history_truncated")) or any(
        row["predecessor"]["kind"] == "UNKNOWN" for row in records.values())
    if coverage["revision_completeness"] == "COMPLETE" and gaps:
        raise ValueError("Complete revision coverage contradicts declared gaps.")
    competing = len(roots) > 1 or any(len(rows) > 1 for rows in children.values())
    chain = []
    if len(roots) == 1 and not competing and not missing:
        row = records.get(next(iter(roots)))
        while row is not None:
            chain.append(row)
            row = next(iter(children.get(row["record_id"], [])), None)
        if len(chain) != len(records):
            chain = []
    incomplete = coverage["revision_completeness"] != "COMPLETE" or gaps or (bool(records) and not chain)
    return chain, incomplete, competing, backwards


def _context(value, q, at, account):
    if value is None:
        return None
    if q["effect_inventory"] is None:
        raise ValueError("Admission has no original evidence inventory.")
    _keys(value, "contract rule_version admission_id authority_id mandate_id mandate_revision purpose request_content_sha256 knowledge_boundary effective_from effective_until admitted_at available_at assurances")
    _enum(value["contract"], (ADMISSION_CONTRACT,))
    _enum(value["rule_version"], (ADMISSION_RULE,))
    _enum(value["purpose"], (PURPOSE,))
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(value[key])
    if type(value["mandate_revision"]) is not int or value["mandate_revision"] < 1:
        raise ValueError("Mandate revision must be a positive integer.")
    _hash(value["request_content_sha256"])
    if value["request_content_sha256"] != _digest(q):
        raise ValueError("Independent admission request fingerprint mismatch.")
    for key in ("knowledge_boundary", "admitted_at", "available_at"):
        value[key] = _time(value[key])
    inventory = q["effect_inventory"]
    if value["knowledge_boundary"] != at or not inventory["observed_at"] <= value["admitted_at"] <= value["available_at"] <= at:
        raise ValueError("Invalid admission boundary/timing.")
    if account is not None and _time(account["observation"]["timing"]["observed_at"]) > value["admitted_at"]:
        raise ValueError("Admission precedes its native account observation.")
    _interval(value)
    _keys(value["assurances"], " ".join(ASSURANCES))
    catalog = {row["evidence_id"]: row for row in inventory["evidence"]}
    for assurance in value["assurances"].values():
        _keys(assurance, "status evidence_refs")
        _enum(assurance["status"], ("ADMITTED", "UNRESOLVED"))
        assurance["evidence_refs"] = _refs(assurance["evidence_refs"])
        _check_refs(assurance["evidence_refs"], catalog, value["admitted_at"])
        if assurance["status"] == "ADMITTED" and (not assurance["evidence_refs"] or any(
            catalog[ref["evidence_id"]]["source_available_at"] is None for ref in assurance["evidence_refs"]
        )):
            raise ValueError("Admitted assurance requires causally available original support.")
    return value


def _account(q, at):
    pair = q["account_state"]
    if pair is None:
        return None
    _keys(pair, "snapshot snapshot_input")
    if type(pair["snapshot"]) is not dict or type(pair["snapshot_input"]) is not dict:
        raise ValueError("Native account pair requires serialized objects.")
    account = validate_causal_financial_account_state_snapshot(pair["snapshot"], pair["snapshot_input"])
    observation = account["observation"]
    actual = {key: observation["source"][key] for key in ("source_id", "source_contract", "source_contract_version")}
    actual.update({key: observation["account"][key] for key in ("account_id", "environment", "currency")})
    _same(q["scope"]["account"], actual, "Native account identity")
    if _time(account["requested_evaluation_timestamp"]) != at:
        raise ValueError("Native account evaluation boundary differs from K.")
    return account


def _coreferences(q, account, current):
    if account is None or current is None or current["kind"] != "DECLARE":
        return
    body = current["body"]
    if body["account_bundle_sha256"] != _digest(q["account_state"]):
        raise ValueError("Current declaration account-bundle fingerprint mismatch.")
    observation = account["observation"]
    _same(body["positions"]["state_at"], _time(observation["timing"]["effective_at"]), "Native position-state time")
    if body["positions"]["inventory_completeness"] == "COMPLETE" and observation["positions"]["completeness"] != "COMPLETE":
        raise ValueError("Complete local position claim contradicts native incompleteness.")
    native_mode, declared_mode = observation["account"]["position_mode"], body["mechanics"]["position_mode"]
    if native_mode != "UNKNOWN" and declared_mode != "UNKNOWN" and native_mode != declared_mode:
        raise ValueError("Native and declared position modes contradict.")


def _evaluate(request, trusted_context):
    _canonical(request)
    _canonical(trusted_context)
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope account_state effect_inventory")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    if q["assessment_economic_time"] != at:
        raise ValueError("Current position-effect basis requires T = K.")
    _scope(q["scope"])
    inventory = q["effect_inventory"] = _inventory(q["effect_inventory"], q["scope"], at)
    account = _account(q, at)
    chain, incomplete, competing, backwards = ([], False, False, []) if inventory is None else _history(inventory)
    current = next((row for row in reversed(chain) if row["effective_from"] <= at), None)
    _coreferences(q, account, current)
    context = _context(deepcopy(trusted_context), q, at, account)
    # Every supplied object, including inactive records and context, is now structurally validated.
    findings = []

    def unknown(code, subject):
        findings.append(dict(reason_code=code, subject=subject))

    def available(node, path):
        if node["source_available_at"] is None:
            unknown("SOURCE_AVAILABILITY_UNKNOWN", path + "/source_available_at")

    evidence = {} if inventory is None else {row["evidence_id"]: (index, row) for index, row in enumerate(inventory["evidence"])}

    def support(refs, path):
        if not refs:
            unknown("SUPPORTING_EVIDENCE_MISSING", path)
        for ref in refs:
            index, item = evidence[ref["evidence_id"]]
            available(item, "/request/effect_inventory/evidence/" + str(index))

    def cutoff(node, path):
        if node["source_information_cutoff"] != at:
            unknown("COVERAGE_NOT_CURRENT", path + "/source_information_cutoff")

    if account is None:
        unknown("MISSING_ACCOUNT_STATE", "/request/account_state")
    else:
        observation = account["observation"]
        root = "/request/account_state/snapshot/observation"
        available(observation["timing"], root + "/timing")
        if _time(observation["timing"]["effective_at"]) < at:
            unknown("ACCOUNT_STATE_NOT_CURRENT", root + "/timing/effective_at")
        if observation["positions"]["completeness"] != "COMPLETE":
            unknown("POSITION_INVENTORY_INCOMPLETE", root + "/positions/completeness")
        if observation["positions"]["items"]:
            unknown("ACCOUNT_NOT_FLAT", root + "/positions/items")
        if observation["account"]["position_mode"] == "UNKNOWN":
            unknown("ACCOUNT_MODE_UNRESOLVED", root + "/account/position_mode")
    admission_ok = context is not None
    if context is None:
        unknown("MISSING_HOST_ADMISSION", "/trusted_position_effect_context")
    else:
        if not _contains(context, at):
            unknown("ADMISSION_NOT_CURRENT", "/trusted_position_effect_context")
            admission_ok = False
        for name, assurance in context["assurances"].items():
            if assurance["status"] != "ADMITTED":
                unknown("ASSURANCE_UNRESOLVED", "/trusted_position_effect_context/assurances/" + name + "/status")
                admission_ok = False
    history_ok, resolved, basis = False, None, None
    if inventory is None:
        unknown("MISSING_EFFECT_INVENTORY", "/request/effect_inventory")
    else:
        root = "/request/effect_inventory"
        start = len(findings)
        coverage = inventory["coverage"]
        available(inventory, root)
        available(coverage, root + "/coverage")
        support(coverage["evidence_refs"], root + "/coverage/evidence_refs")
        for index, record in enumerate(inventory["records"]):
            path = root + "/records/" + str(index)
            available(record, path)
            support(record["evidence_refs"], path + "/evidence_refs")
        if coverage["declaration_completeness"] != "COMPLETE":
            unknown("COVERAGE_INCOMPLETE", root + "/coverage/declaration_completeness")
        if not _contains(coverage, at, "economic_from", "economic_until"):
            unknown("COVERAGE_NOT_CURRENT", root + "/coverage")
        cutoff(coverage, root + "/coverage")
        if incomplete:
            unknown("REVISION_HISTORY_INCOMPLETE", root + "/coverage")
        if competing:
            unknown("COMPETING_REVISION_CHAINS", root + "/records")
        for index in backwards:
            unknown("REVISION_ORDER_UNSUPPORTED", root + "/records/" + str(index))
        history_ok = len(findings) == start
        if current is None:
            if chain or (not inventory["records"] and not incomplete and not competing and
                         coverage["declaration_completeness"] == "COMPLETE"):
                unknown("NO_CURRENT_DECLARATION", root + "/records")
        else:
            index = inventory["records"].index(current)
            path = root + "/records/" + str(index)
            if history_ok and admission_ok:
                resolved = dict(record_id=current["record_id"], content_sha256=_digest(current))
            if current["kind"] == "WITHDRAW":
                unknown("CURRENT_DECLARATION_WITHDRAWN", path)
            elif not _contains(current, at):
                unknown("CURRENT_DECLARATION_EXPIRED", path + "/effective_until")
            else:
                body = current["body"]
                path += "/body"
                for relative, refs in _reference_arrays(body):
                    support(refs, path + relative)
                positions, mechanics, commitments = (body[key] for key in ("positions", "mechanics", "commitments"))
                for key, node in (("positions", positions), ("mechanics", mechanics), ("commitments", commitments)):
                    cutoff(node, path + "/" + key)
                    if "state_at" in node and node["state_at"] != at:
                        unknown("COVERAGE_NOT_CURRENT", path + "/" + key + "/state_at")
                if positions["inventory_completeness"] != "COMPLETE":
                    unknown("POSITION_INVENTORY_INCOMPLETE", path + "/positions/inventory_completeness")
                for key, node in (("positions", positions), ("mechanics", mechanics)):
                    if node["revision_completeness"] != "COMPLETE":
                        unknown("REVISION_HISTORY_INCOMPLETE", path + "/" + key + "/revision_completeness")
                if mechanics["position_mode"] == "UNKNOWN":
                    unknown("ACCOUNT_MODE_UNRESOLVED", path + "/mechanics/position_mode")
                for key, expected in (("model", MODEL), ("fill_aggregation", AGGREGATION)):
                    if mechanics[key] != expected:
                        unknown("MECHANICS_UNSUPPORTED_OR_UNKNOWN", path + "/mechanics/" + key)
                if mechanics["quantity_range"] is None:
                    unknown("QUANTITY_RANGE_UNESTABLISHED", path + "/mechanics/quantity_range")
                for name, claim in body["bindings"].items():
                    if claim["status"] != "COMPATIBLE":
                        unknown("BINDING_UNRESOLVED" if claim["status"] == "UNKNOWN" else "BINDING_INCOMPATIBLE",
                                path + "/bindings/" + name + "/status")
                cp = path + "/commitments"
                if not commitments["inventory_roster"] or not any(row["role"] == "PROVIDER" for row in commitments["inventory_roster"]):
                    unknown("COMMITMENT_COVERAGE_INCOMPLETE", cp + "/inventory_roster")
                for key, expected in (("source_universe_completeness", "COMPLETE"), ("actor_coverage", "ALL_ACCOUNT_ACTORS")):
                    if commitments[key] != expected:
                        unknown("COMMITMENT_COVERAGE_INCOMPLETE", cp + "/" + key)
                report_ids = {row["inventory_id"] for row in commitments["reports"]}
                for index, member in enumerate(commitments["inventory_roster"]):
                    if member["inventory_id"] not in report_ids:
                        unknown("COMMITMENT_REPORT_MISSING", cp + "/inventory_roster/" + str(index))
                for index, report in enumerate(commitments["reports"]):
                    rp = cp + "/reports/" + str(index)
                    available(report, rp)
                    cutoff(report, rp)
                    if report["state_at"] != at:
                        unknown("COVERAGE_NOT_CURRENT", rp + "/state_at")
                    for key in ("inventory_completeness", "revision_completeness"):
                        if report[key] != "COMPLETE":
                            unknown("COMMITMENT_COVERAGE_INCOMPLETE", rp + "/" + key)
                    for name, category in report["categories"].items():
                        if category["status"] != "EMPTY":
                            unknown("COMMITMENT_PRESENT" if category["status"] == "NONEMPTY" else "COMMITMENT_STATUS_UNKNOWN",
                                    rp + "/categories/" + name + "/status")
                if not findings:
                    basis = dict(model=MODEL, position_mode=mechanics["position_mode"], quantity_unit=q["scope"]["quantity_unit"],
                                 quantity_range=deepcopy(mechanics["quantity_range"]), resulting_direction=q["scope"]["entry_direction"],
                                 resulting_position_quantity=dict(kind="IDENTITY_OF_ENTRY_QUANTITY"), initial_position_count=0,
                                 terminal_position_count=1, terminal_position_count_delta=1, conditions=list(CONDITIONS))
    findings = sorted({_canonical(row): row for row in findings}.values(), key=_canonical)
    if not findings and basis is None:
        raise ValueError("Incomplete mapping proof without an unresolved finding.")
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
                  scope=deepcopy(q["scope"]), outcome="UNKNOWN" if findings else "ESTABLISHED",
                  reason_codes=sorted({row["reason_code"] for row in findings}) if findings else ["POSITION_EFFECT_BASIS_ESTABLISHED"],
                  resolved_record=resolved, effect_basis=basis, unresolved_findings=findings,
                  reconstruction_evidence=dict(request=q, trusted_position_effect_context_sha256=None if context is None else _digest(context)),
                  downstream_obligations=list(DOWNSTREAM_OBLIGATIONS), source_authentication=SOURCE_AUTHENTICATION,
                  authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = "current_entry_position_effect_basis_" + _digest(result)
    return result


def evaluate_current_entry_position_effect_basis(request: dict, *, trusted_position_effect_context=None) -> dict:
    """Reconstruct a conditional mapping under independently supplied host admission."""
    try:
        return deepcopy(_evaluate(request, trusted_position_effect_context))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed current entry position-effect basis request.") from exc


def validate_current_entry_position_effect_basis(assessment: dict, request: dict, *, trusted_position_effect_context=None) -> dict:
    """Replay every owned field and original dependency; a caller hash is never proof."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Assessment must be a serialized JSON object.")
        expected = evaluate_current_entry_position_effect_basis(request, trusted_position_effect_context=trusted_position_effect_context)
        _same(assessment, expected, "Position-effect assessment")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized position-effect assessment.") from exc
