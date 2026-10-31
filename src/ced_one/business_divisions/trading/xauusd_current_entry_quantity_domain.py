"""Independently admitted, source-scoped entry volume facts; no sizing authority."""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re
from typing import Any


CONTRACT = "trading.xauusd_current_entry_quantity_domain.v1"
RULE_VERSION = "xauusd_current_entry_quantity_domain_v1"
INVENTORY_CONTRACT = "trading.xauusd_current_entry_quantity_domain.inventory.v1"
INVENTORY_RULE = "xauusd_current_entry_quantity_domain_inventory_v1"
ADMISSION_CONTRACT = "trading.xauusd_current_entry_quantity_domain.admission.v1"
ADMISSION_RULE = "xauusd_current_entry_quantity_domain_admission_v1"
STREAM_MODEL = "WHOLE_ENTRY_DOMAIN_REPLACEMENT_STREAM_V1"
GRID_MODEL = "REGULAR_GRID_CLOSED_BOUNDS_V1"
MECHANISM = "IMMEDIATE_MARKET_ENTRY_SCENARIO_V1"
PURPOSE = "ENTRY_QUANTITY_FACT_ADMISSION_ONLY"
SOURCE_AUTHENTICATION = "NOT_VERIFIED_BY_THIS_CAPABILITY"
AUTHORITY = dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                           "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
DOWNSTREAM_OBLIGATIONS = sorted((
    "BUDGET_AND_DAILY_LOSS_ELIGIBILITY", "CANDIDATE_VALIDITY", "INSTRUMENT_AND_UNIT_COMPATIBILITY",
    "MARGIN_AND_CAPITAL_FEASIBILITY", "MARKET_AND_ORDER_EXECUTION_FEASIBILITY",
    "MISSION_CONTROL_AUTHORIZATION", "POSITION_EFFECT_AND_OTHER_PROVIDER_COMPLIANCE",
    "RISK_CONSTRAINED_QUANTITY_SELECTION",
))
ASSURANCES = ("source_authority", "quantity_rule_semantics", "revision_coverage", "evidence_availability")
ASSURANCE_REASONS = dict(zip(ASSURANCES, (
    "SOURCE_AUTHORITY_UNRESOLVED", "QUANTITY_SEMANTICS_UNRESOLVED",
    "REVISION_COVERAGE_UNRESOLVED", "EVIDENCE_AVAILABILITY_UNRESOLVED",
)))
REASON_CODES = frozenset((
    "ADMISSION_OUTSIDE_EFFECTIVE_INTERVAL", "COMPETING_REVISION_CHAINS", "COVERAGE_DOES_NOT_INCLUDE_T",
    "COVERAGE_NOT_THROUGH_K", "CURRENT_DECLARATION_EXPIRED", "CURRENT_DECLARATION_WITHDRAWN",
    "CURRENT_DOMAIN_TERMS_MISSING", "DECLARED_RECORDS_MISSING", "EVIDENCE_AVAILABILITY_UNRESOLVED",
    "MISSING_HOST_ADMISSION", "MISSING_INVENTORY", "NO_CURRENT_DECLARATION", "PREDECESSOR_UNKNOWN",
    "QUANTITY_RULE_COVERAGE_INCOMPLETE", "QUANTITY_SEMANTICS_UNRESOLVED", "REVISION_COVERAGE_UNRESOLVED",
    "REVISION_HISTORY_INCOMPLETE", "SOURCE_AUTHORITY_UNRESOLVED", "SOURCE_AVAILABILITY_UNKNOWN",
    "SUPPORTING_EVIDENCE_MISSING", "UNSUPPORTED_LIFECYCLE", "ENTRY_QUANTITY_DOMAIN_ESTABLISHED",
    "NO_POSITIVE_ENTRY_QUANTITY",
))
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


def _keys(value: Any, fields: str) -> None:
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("Object requires exactly its declared fields.")


def _text(value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("Identifier must contain a non-whitespace character.")
    value.encode("utf-8")  # Surrogate code points are never canonical source identifiers.
    return value


def _enum(value: Any, choices) -> str:
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported closed value.")
    return value


def _list(value: Any) -> list:
    if type(value) is not list:
        raise ValueError("Expected a list.")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _serialized(value: Any) -> None:
    """Serialized assessments admit JSON containers only, never Python coercions."""
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Serialized object keys must be strings.")
            key.encode("utf-8")
            _serialized(item)
    elif type(value) is list:
        for item in value:
            _serialized(item)
    elif type(value) is str:
        value.encode("utf-8")
    elif value is not None and type(value) not in (bool, int):
        raise ValueError("Assessment requires exact JSON types without binary floating point.")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _time(value: Any) -> str:
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ValueError("Timestamp requires seconds, timezone and at most microsecond precision.")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Invalid timezone offset.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid calendar timestamp.") from exc


def _optional_time(value: Any) -> str | None:
    return None if value is None else _time(value)


def _timing(value: dict, boundary: str) -> None:
    value["observed_at"] = _time(value["observed_at"])
    value["source_available_at"] = _optional_time(value["source_available_at"])
    if value["observed_at"] > boundary or (
        value["source_available_at"] is not None and value["source_available_at"] > value["observed_at"]
    ):
        raise ValueError("Evidence was not causally admissible by K.")


def _interval(value: dict, first="effective_from", last="effective_until") -> None:
    value[first], value[last] = _time(value[first]), _optional_time(value[last])
    if value[last] is not None and value[first] >= value[last]:
        raise ValueError("Effective interval must be nonempty.")


def _contains(value: dict, at: str, first="effective_from", last="effective_until") -> bool:
    return value[first] <= at and (value[last] is None or at < value[last])


def _source(value: Any) -> dict:
    _keys(value, "source_id source_contract source_contract_version source_snapshot_id")
    return {key: _text(item) for key, item in value.items()}


def _scope(value: Any) -> dict:
    _keys(value, "provider_id venue_id environment account_id instrument_id quantity_unit entry_direction entry_mechanism")
    result = {key: _text(item) for key, item in value.items()}
    _enum(result["environment"], ("DEMO", "LIVE"))
    _enum(result["entry_direction"], ("LONG", "SHORT"))
    _enum(result["entry_mechanism"], (MECHANISM,))
    return result


def _ref(value: Any, key: str) -> dict:
    _keys(value, key + " content_sha256")
    _text(value[key])
    if type(value["content_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["content_sha256"]) is None:
        raise ValueError("Content reference requires a lowercase SHA-256 digest.")
    return deepcopy(value)


def _unique(values: list, key) -> list:
    identifiers = [key(value) for value in values]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate identity or reference.")
    return sorted(values, key=_canonical)


def _refs(value: Any, key="evidence_id") -> list:
    return _unique([_ref(item, key) for item in _list(value)], lambda item: item[key])


def _decimal(value: Any) -> str:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Grid terms require finite plain decimal strings.")
    negative = value.startswith("-")
    whole, _, part = value.lstrip("-").partition(".")
    whole, part = whole.lstrip("0") or "0", part.rstrip("0")
    result = whole + ("." + part if part else "")
    return ("-" if negative and result != "0" else "") + result


def _integer(digits: str) -> int:
    # Chunk conversions avoid Python's configurable decimal-string digit limit.
    result = 0
    for index in range(0, len(digits), 9):
        chunk = digits[index:index + 9]
        result = result * 10 ** len(chunk) + int(chunk)
    return result


def _integer_text(value: int) -> str:
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    value = abs(value)
    chunks = []
    while value:
        value, chunk = divmod(value, 10 ** 9)
        chunks.append(chunk)
    return sign + str(chunks[-1]) + "".join(str(chunk).zfill(9) for chunk in reversed(chunks[:-1]))


def _fraction(value: str) -> Fraction:
    whole, _, part = value.lstrip("-").partition(".")
    return Fraction((-1 if value.startswith("-") else 1) * _integer(whole + part), 10 ** len(part))


def _plain(value: Fraction) -> str:
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("Grid descriptor is not a finite decimal.")
    scale = max(twos, fives)
    digits = _integer_text(abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)).zfill(scale + 1)
    return _decimal(("-" if value < 0 else "") + (
        digits[:-scale] + "." + digits[-scale:] if scale else digits))


def _grid(value: Any) -> dict | None:
    if value is None:
        return None
    _keys(value, "model origin increment minimum maximum")
    _enum(value["model"], (GRID_MODEL,))
    result = deepcopy(value)
    for field in ("origin", "increment", "minimum"):
        result[field] = _decimal(value[field])
    if _fraction(result["increment"]) <= 0:
        raise ValueError("Increment must be strictly positive.")
    maximum = value["maximum"]
    if type(maximum) is not dict:
        raise ValueError("Maximum requires a finite or explicit unbounded descriptor.")
    if maximum.get("kind") == "UNBOUNDED":
        _keys(maximum, "kind")
    else:
        _keys(maximum, "kind value")
        _enum(maximum["kind"], ("FINITE",))
        result["maximum"]["value"] = _decimal(maximum["value"])
        if _fraction(result["minimum"]) > _fraction(result["maximum"]["value"]):
            raise ValueError("Reversed finite quantity interval.")
    return result


def _descriptor(grid: dict) -> dict:
    origin, step, minimum = (_fraction(grid[key]) for key in ("origin", "increment", "minimum"))
    residue = origin - (origin // step) * step
    lower = (minimum - residue) / step
    first = max(-((-lower.numerator) // lower.denominator), (-residue / step) // 1 + 1)
    last = None
    if grid["maximum"]["kind"] == "FINITE":
        last = ((_fraction(grid["maximum"]["value"]) - residue) / step) // 1
        if last < first:
            return {"kind": "EMPTY"}
    return dict(kind="REGULAR_GRID", origin=_plain(residue), increment=grid["increment"],
                first_index=_integer_text(first), last_index=None if last is None else _integer_text(last))


def _evidence(value: Any, boundary: str) -> dict:
    _keys(value, "evidence_id source media_type content_base64 source_available_at observed_at")
    result = deepcopy(value)
    _text(result["evidence_id"])
    _text(result["media_type"])
    result["source"] = _source(result["source"])
    encoded = result["content_base64"]
    if type(encoded) is not str:
        raise ValueError("Original evidence requires canonical base64 bytes.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid original evidence encoding.") from exc
    if not raw or base64.b64encode(raw).decode("ascii") != encoded:
        raise ValueError("Original evidence must be nonempty canonical base64.")
    _timing(result, boundary)
    return result


def _predecessor(value: Any) -> dict:
    if type(value) is not dict:
        raise ValueError("Predecessor requires an explicit tagged value.")
    if value.get("kind") == "RECORD":
        _keys(value, "kind record")
        return dict(kind="RECORD", record=_ref(value["record"], "record_id"))
    _keys(value, "kind")
    _enum(value["kind"], ("ROOT", "UNKNOWN"))
    return deepcopy(value)


def _record(value: Any, boundary: str) -> dict:
    if type(value) is not dict:
        raise ValueError("Invalid stream record.")
    kind = _enum(value.get("kind"), ("DECLARE", "WITHDRAW"))
    fields = "record_id kind predecessor effective_from source_available_at observed_at evidence_refs"
    _keys(value, fields + (" effective_until domain" if kind == "DECLARE" else ""))
    result = deepcopy(value)
    _text(result["record_id"])
    result["predecessor"] = _predecessor(result["predecessor"])
    result["evidence_refs"] = _refs(result["evidence_refs"])
    _timing(result, boundary)
    result["effective_from"] = _time(result["effective_from"])
    if kind == "DECLARE":
        _interval(result)
        result["domain"] = _grid(result["domain"])
    elif result["predecessor"]["kind"] == "ROOT":
        raise ValueError("Withdrawal cannot be a stream root.")
    return result


def _coverage(value: Any, boundary: str) -> dict:
    _keys(value, "declaration_id source_available_at observed_at economic_from economic_until source_information_cutoff quantity_rule_completeness revision_completeness starting_basis root_records missing_record_ids records_omitted history_truncated evidence_refs")
    result = deepcopy(value)
    _text(result["declaration_id"])
    _timing(result, boundary)
    _interval(result, "economic_from", "economic_until")
    result["source_information_cutoff"] = _optional_time(result["source_information_cutoff"])
    cutoff = result["source_information_cutoff"]
    if cutoff is not None and (cutoff > boundary or (
        result["source_available_at"] is not None and cutoff > result["source_available_at"]
    )):
        raise ValueError("Coverage cutoff is future or precedes publication incorrectly.")
    for key in ("quantity_rule_completeness", "revision_completeness"):
        _enum(result[key], ("COMPLETE", "LIMITED", "UNKNOWN"))
    _enum(result["starting_basis"], ("FROM_INCEPTION", "INCOMPLETE_OR_UNKNOWN"))
    result["root_records"] = _refs(result["root_records"], "record_id")
    missing = [_text(item) for item in _list(result["missing_record_ids"])]
    result["missing_record_ids"] = _unique(missing, lambda item: item)
    result["evidence_refs"] = _refs(result["evidence_refs"])
    for key in ("records_omitted", "history_truncated"):
        if result[key] is not None and type(result[key]) is not bool:
            raise ValueError("Omission flags require booleans or explicit unknown.")
    return result


def _check_evidence_refs(references: list, evidence: dict) -> None:
    for ref in references:
        item = evidence.get(ref["evidence_id"])
        if item is None or _digest(item) != ref["content_sha256"]:
            raise ValueError("Missing or mismatched original evidence reference.")


def _check_records(inventory: dict) -> None:
    coverage = inventory["coverage"]
    records = {item["record_id"]: item for item in inventory["records"]}
    missing = set(coverage["missing_record_ids"])
    if missing & set(records):
        raise ValueError("A declared missing record was supplied.")

    def check(ref):
        item = records.get(ref["record_id"])
        if item is None:
            if ref["record_id"] not in missing:
                raise ValueError("Unexplained dangling stream reference.")
        elif _digest(item) != ref["content_sha256"]:
            raise ValueError("Stream reference content mismatch.")
        return item

    roots = {ref["record_id"] for ref in coverage["root_records"]}
    for ref in coverage["root_records"]:
        item = check(ref)
        if item is not None and item["predecessor"]["kind"] != "ROOT":
            raise ValueError("Declared root is not a root record.")
    for record in records.values():
        previous = record["predecessor"]
        if previous["kind"] == "ROOT" and record["record_id"] not in roots:
            raise ValueError("Supplied root is absent from the declared root set.")
        if previous["kind"] == "RECORD":
            check(previous["record"])
    # Check all supplied components, even when history or admission is incomplete.
    finished = set()
    for identifier in records:
        path = set()
        current = identifier
        while current in records and current not in finished:
            if current in path:
                raise ValueError("Cyclic stream predecessor references.")
            path.add(current)
            previous = records[current]["predecessor"]
            if previous["kind"] != "RECORD":
                break
            current = previous["record"]["record_id"]
        finished.update(path)

    incomplete = (bool(missing) or coverage["records_omitted"] is True or
                  coverage["history_truncated"] is True or coverage["starting_basis"] != "FROM_INCEPTION" or
                  any(row["predecessor"]["kind"] == "UNKNOWN" for row in records.values()))
    if coverage["revision_completeness"] == "COMPLETE" and (
        incomplete or coverage["records_omitted"] is not False or coverage["history_truncated"] is not False
    ):
        raise ValueError("Complete revision coverage contradicts declared gaps.")
    if coverage["revision_completeness"] == "LIMITED" and not incomplete:
        raise ValueError("Limited revision coverage requires a concrete limitation.")
    if coverage["quantity_rule_completeness"] == "COMPLETE" and any(
        row["kind"] == "DECLARE" and row["domain"] is None for row in records.values()
    ):
        raise ValueError("Complete quantity coverage contradicts missing domain terms.")


def _inventory(value: Any, scope: dict, boundary: str) -> dict | None:
    if value is None:
        return None
    _keys(value, "contract rule_version model source scope source_available_at observed_at evidence coverage records unsupported_lifecycle_evidence")
    result = deepcopy(value)
    _enum(result["contract"], (INVENTORY_CONTRACT,))
    _enum(result["rule_version"], (INVENTORY_RULE,))
    _enum(result["model"], (STREAM_MODEL,))
    result["source"] = _source(result["source"])
    result["scope"] = _scope(result["scope"])
    if result["scope"] != scope:
        raise ValueError("Inventory scope mismatch.")
    _timing(result, boundary)
    result["evidence"] = _unique([_evidence(item, boundary) for item in _list(result["evidence"])],
                                 lambda item: item["evidence_id"])
    result["records"] = _unique([_record(item, boundary) for item in _list(result["records"])],
                                lambda item: item["record_id"])
    result["coverage"] = _coverage(result["coverage"], boundary)
    result["unsupported_lifecycle_evidence"] = _refs(result["unsupported_lifecycle_evidence"])
    material = [*result["evidence"], *result["records"], result["coverage"]]
    if any(item["observed_at"] > result["observed_at"] for item in material):
        raise ValueError("Inventory precedes a contained observation.")
    evidence = {item["evidence_id"]: item for item in result["evidence"]}
    for item in [*result["records"], result["coverage"]]:
        _check_evidence_refs(item["evidence_refs"], evidence)
    _check_evidence_refs(result["unsupported_lifecycle_evidence"], evidence)
    _check_records(result)
    return result


def _context(value: Any, inventory: dict | None, scope: dict, boundary: str) -> dict | None:
    if value is None:
        return None
    _keys(value, "contract rule_version admission_id authority_id mandate_id mandate_revision purpose admission_basis inventory_source inventory_content_sha256 scope knowledge_boundary admitted_at available_at effective_from effective_until assurances")
    if inventory is None:
        raise ValueError("Admission has no inventory pin target.")
    result = deepcopy(value)
    _enum(result["contract"], (ADMISSION_CONTRACT,))
    _enum(result["rule_version"], (ADMISSION_RULE,))
    for key in ("admission_id", "authority_id", "mandate_id"):
        _text(result[key])
    if type(result["mandate_revision"]) is not int or result["mandate_revision"] < 1:
        raise ValueError("Mandate revision must be a positive integer.")
    _enum(result["purpose"], (PURPOSE,))
    _enum(result["admission_basis"], ("PROVIDER_ORIGIN_VERIFIED_EXTERNALLY", "PROVIDER_DOCUMENTS_REVIEWED_EXTERNALLY"))
    result["inventory_source"] = _source(result["inventory_source"])
    result["scope"] = _scope(result["scope"])
    result["knowledge_boundary"] = _time(result["knowledge_boundary"])
    if (result["scope"] != scope or result["inventory_source"] != inventory["source"] or
        result["knowledge_boundary"] != boundary or result["inventory_content_sha256"] != _digest(inventory)):
        raise ValueError("Independent admission source, scope, boundary or inventory pin mismatch.")
    for key in ("admitted_at", "available_at"):
        result[key] = _time(result[key])
    if not inventory["observed_at"] <= result["admitted_at"] <= result["available_at"] <= boundary:
        raise ValueError("Admission precedes its evidence or is unavailable by K.")
    _interval(result)
    _keys(result["assurances"], " ".join(ASSURANCES))
    evidence = {item["evidence_id"]: item for item in inventory["evidence"]}
    for assurance in result["assurances"].values():
        _keys(assurance, "status evidence_refs")
        _enum(assurance["status"], ("ADMITTED", "UNRESOLVED"))
        assurance["evidence_refs"] = _refs(assurance["evidence_refs"])
        if assurance["status"] == "ADMITTED" and not assurance["evidence_refs"]:
            raise ValueError("Admitted assurance requires supporting evidence references.")
        _check_evidence_refs(assurance["evidence_refs"], evidence)
    return result


def _findings(inventory: dict, context: dict | None, at: str) -> tuple[set[str], list[dict]]:
    reasons = set()
    coverage = inventory["coverage"]
    if context is None:
        reasons.add("MISSING_HOST_ADMISSION")
    else:
        if not _contains(context, at):
            reasons.add("ADMISSION_OUTSIDE_EFFECTIVE_INTERVAL")
        for key, assurance in context["assurances"].items():
            if assurance["status"] != "ADMITTED":
                reasons.add(ASSURANCE_REASONS[key])
    if coverage["quantity_rule_completeness"] != "COMPLETE":
        reasons.add("QUANTITY_RULE_COVERAGE_INCOMPLETE")
    if coverage["revision_completeness"] != "COMPLETE":
        reasons.add("REVISION_HISTORY_INCOMPLETE")
    if not _contains(coverage, at, "economic_from", "economic_until"):
        reasons.add("COVERAGE_DOES_NOT_INCLUDE_T")
    if coverage["source_information_cutoff"] != at:
        reasons.add("COVERAGE_NOT_THROUGH_K")
    if coverage["missing_record_ids"]:
        reasons.add("DECLARED_RECORDS_MISSING")
    if inventory["unsupported_lifecycle_evidence"]:
        reasons.add("UNSUPPORTED_LIFECYCLE")
    material = [inventory, coverage, *inventory["records"], *inventory["evidence"]]
    if any(item["source_available_at"] is None for item in material):
        reasons.add("SOURCE_AVAILABILITY_UNKNOWN")
    if not inventory["evidence"] or any(not item["evidence_refs"] for item in [coverage, *inventory["records"]]):
        reasons.add("SUPPORTING_EVIDENCE_MISSING")
    if any(row["kind"] == "DECLARE" and row["domain"] is None for row in inventory["records"]):
        reasons.add("CURRENT_DOMAIN_TERMS_MISSING")

    records = {row["record_id"]: row for row in inventory["records"]}
    children: dict[str, list[dict]] = {}
    roots = []
    unresolved = False
    for row in records.values():
        previous = row["predecessor"]
        if previous["kind"] == "ROOT":
            roots.append(row)
        elif previous["kind"] == "UNKNOWN":
            reasons.add("PREDECESSOR_UNKNOWN")
            unresolved = True
        else:
            parent = records.get(previous["record"]["record_id"])
            if parent is None:
                unresolved = True
            else:
                children.setdefault(parent["record_id"], []).append(row)
                if parent["effective_from"] > row["effective_from"]:
                    reasons.add("UNSUPPORTED_LIFECYCLE")
    competing = len(coverage["root_records"]) > 1 or any(len(rows) > 1 for rows in children.values())
    if competing:
        reasons.add("COMPETING_REVISION_CHAINS")
    chain = []
    if len(roots) == 1 and not competing and not unresolved:
        current = roots[0]
        while current is not None:
            chain.append(current)
            next_rows = children.get(current["record_id"], [])
            current = next_rows[0] if next_rows else None
        if len(chain) != len(records):
            reasons.add("REVISION_HISTORY_INCOMPLETE")
            chain = []
    if not records or (chain and not any(row["effective_from"] <= at for row in chain)):
        reasons.add("NO_CURRENT_DECLARATION")
    return reasons, chain


def _evaluate(request: Any, trusted_quantity_context: Any) -> dict:
    _keys(request, "contract rule_version assessment_economic_time knowledge_boundary scope quantity_inventory")
    q = deepcopy(request)
    _enum(q["contract"], (CONTRACT,))
    _enum(q["rule_version"], (RULE_VERSION,))
    for key in ("assessment_economic_time", "knowledge_boundary"):
        q[key] = _time(q[key])
    at = q["knowledge_boundary"]
    if q["assessment_economic_time"] != at:
        raise ValueError("Current assessment requires T = K.")
    q["scope"] = _scope(q["scope"])
    inventory = q["quantity_inventory"] = _inventory(q["quantity_inventory"], q["scope"], at)
    context = _context(trusted_quantity_context, inventory, q["scope"], at)
    resolved = domain = domain_identity = None
    outcome = "UNKNOWN"
    if inventory is None:
        reasons = {"MISSING_INVENTORY"}
    else:
        reasons, chain = _findings(inventory, context, at)
        # Evidence uncertainty always precedes interpreting even an empty grid.
        if not reasons:
            current = next((row for row in reversed(chain) if row["effective_from"] <= at), None)
            if current is None:
                reasons.add("NO_CURRENT_DECLARATION")
            else:
                resolved = dict(record_id=current["record_id"], content_sha256=_digest(current))
                if current["kind"] == "WITHDRAW":
                    reasons.add("CURRENT_DECLARATION_WITHDRAWN")
                elif not _contains(current, at):
                    reasons.add("CURRENT_DECLARATION_EXPIRED")
                else:
                    domain = _descriptor(current["domain"])
                    domain_identity = "entry_quantity_domain_" + _digest(dict(quantity_unit=q["scope"]["quantity_unit"], domain=domain))
                    outcome = "NOT_SUITABLE" if domain["kind"] == "EMPTY" else "ESTABLISHED"
                    reasons.add("NO_POSITIVE_ENTRY_QUANTITY" if outcome == "NOT_SUITABLE" else "ENTRY_QUANTITY_DOMAIN_ESTABLISHED")
    result = dict(contract=CONTRACT, rule_version=RULE_VERSION, assessment_economic_time=at, knowledge_boundary=at,
                  scope=deepcopy(q["scope"]), outcome=outcome, reason_codes=sorted(reasons), resolved_record=resolved,
                  domain=domain, domain_identity=domain_identity,
                  reconstruction_evidence=dict(request=q, trusted_context_content_sha256=None if context is None else _digest(context)),
                  source_authentication=SOURCE_AUTHENTICATION, downstream_obligations=list(DOWNSTREAM_OBLIGATIONS),
                  authority=dict(AUTHORITY), execution=False)
    result["assessment_identity"] = "current_entry_quantity_domain_" + _digest(result)
    return result


def evaluate_current_entry_quantity_domain(request: dict, *, trusted_quantity_context=None) -> dict:
    """Reconstruct current entry volume evidence; a host pin is not authentication."""
    try:
        return deepcopy(_evaluate(request, trusted_quantity_context))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed current entry quantity-domain request.") from exc


def validate_current_entry_quantity_domain(assessment: dict, request: dict, *, trusted_quantity_context=None) -> dict:
    """Rebuild complete output using independently supplied admission, never its own ID."""
    try:
        if type(assessment) is not dict:
            raise ValueError("Serialized assessment must be an object.")
        _serialized(assessment)
        expected = evaluate_current_entry_quantity_domain(request, trusted_quantity_context=trusted_quantity_context)
        if _canonical(assessment) != _canonical(expected):
            raise ValueError("Quantity-domain assessment differs from independent reconstruction.")
        return deepcopy(expected)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed serialized current entry quantity-domain assessment.") from exc
