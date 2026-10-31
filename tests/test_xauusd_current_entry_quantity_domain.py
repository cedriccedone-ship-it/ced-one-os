"""Synthetic source/admission fixtures test semantics, never real provider rules."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
from fractions import Fraction
import hashlib
import json

import pytest

from ced_one.business_divisions.trading import xauusd_current_entry_quantity_domain as owner


T = "2026-01-02T12:00:00.000000Z"
EARLY = "2026-01-01T00:00:00.000000Z"
BEFORE = "2026-01-02T11:59:59.999999Z"
AFTER = "2026-01-02T12:00:00.000001Z"
END = "2026-01-03T00:00:00.000000Z"
TIME_KEYS = {"assessment_economic_time", "knowledge_boundary", "source_available_at", "observed_at",
             "effective_from", "effective_until", "economic_from", "economic_until",
             "source_information_cutoff", "admitted_at", "available_at"}


def normalized(value, key=None):
    """Independent fixture encoding of the normative canonical representation."""
    if isinstance(value, dict):
        return {k: normalized(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return sorted((normalized(item) for item in value), key=canonical)
    if value is not None and key in TIME_KEYS:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    if key in ("origin", "increment", "minimum", "value") and type(value) is str:
        negative = value.startswith("-")
        whole, _, part = value.lstrip("-").partition(".")
        result = (whole.lstrip("0") or "0") + (("." + part.rstrip("0")) if part.rstrip("0") else "")
        return ("-" if negative and result != "0" else "") + result
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def ref(value, key):
    return {key: value[key], "content_sha256": digest(normalized(value))}


def grid(origin="0", increment="0.1", minimum="0.1", maximum="0.3"):
    return dict(model=owner.GRID_MODEL, origin=origin, increment=increment, minimum=minimum,
                maximum=dict(kind="UNBOUNDED") if maximum is None else dict(kind="FINITE", value=maximum))


def declaration(identifier="A", predecessor=None, start=EARLY, end=END, domain=None):
    return dict(record_id=identifier, kind="DECLARE",
                predecessor=dict(kind="ROOT") if predecessor is None else dict(kind="RECORD", record=ref(predecessor, "record_id")),
                effective_from=start, effective_until=end, source_available_at=EARLY, observed_at=EARLY,
                evidence_refs=[], domain=grid() if domain is None else domain)


def withdrawal(parent, identifier="W", start=T):
    return dict(record_id=identifier, kind="WITHDRAW", predecessor=dict(kind="RECORD", record=ref(parent, "record_id")),
                effective_from=start, source_available_at=EARLY, observed_at=EARLY, evidence_refs=[])


def seal(q, context):
    """Reissue synthetic content references after an intentional fixture revision."""
    inventory = q["quantity_inventory"]
    evidence = {item["evidence_id"]: item for item in inventory["evidence"]}
    def refresh(refs):
        return [ref(evidence[item["evidence_id"]], "evidence_id") if item["evidence_id"] in evidence else item for item in refs]
    for row in [inventory["coverage"], *inventory["records"]]:
        row["evidence_refs"] = refresh(row["evidence_refs"])
    inventory["unsupported_lifecycle_evidence"] = refresh(inventory["unsupported_lifecycle_evidence"])
    by_id = {row["record_id"]: row for row in inventory["records"]}
    done = set()
    pending = list(by_id)
    while pending:
        progressed = False
        for identifier in list(pending):
            row = by_id[identifier]
            previous = row["predecessor"]
            parent_id = previous.get("record", {}).get("record_id")
            if parent_id in by_id and parent_id not in done:
                continue
            if parent_id in by_id:
                previous["record"] = ref(by_id[parent_id], "record_id")
            done.add(identifier)
            pending.remove(identifier)
            progressed = True
        if not progressed:
            raise AssertionError("Fixture sealing does not support cycles")
    inventory["coverage"]["root_records"] = [ref(by_id[item["record_id"]], "record_id") if item["record_id"] in by_id else item
                                             for item in inventory["coverage"]["root_records"]]
    if context is not None:
        for assurance in context["assurances"].values():
            assurance["evidence_refs"] = refresh(assurance["evidence_refs"])
        context["inventory_content_sha256"] = digest(normalized(inventory))
    return q, context


def sample():
    source = dict(source_id="synthetic-provider", source_contract="test-inventory", source_contract_version="1", source_snapshot_id="snapshot-1")
    scope = dict(provider_id="synthetic-provider", venue_id="venue", environment="DEMO", account_id="account",
                 instrument_id="XAUUSD", quantity_unit="lot", entry_direction="LONG", entry_mechanism=owner.MECHANISM)
    evidence = dict(evidence_id="original", source=deepcopy(source), media_type="application/json",
                    content_base64=base64.b64encode(b'{"synthetic":true}').decode(), source_available_at=EARLY, observed_at=EARLY)
    support = [ref(evidence, "evidence_id")]
    record = declaration()
    record["evidence_refs"] = deepcopy(support)
    coverage = dict(declaration_id="coverage", source_available_at=T, observed_at=T, economic_from=EARLY, economic_until=END,
                    source_information_cutoff=T, quantity_rule_completeness="COMPLETE", revision_completeness="COMPLETE",
                    starting_basis="FROM_INCEPTION", root_records=[ref(record, "record_id")], missing_record_ids=[],
                    records_omitted=False, history_truncated=False, evidence_refs=deepcopy(support))
    inventory = dict(contract=owner.INVENTORY_CONTRACT, rule_version=owner.INVENTORY_RULE, model=owner.STREAM_MODEL,
                     source=deepcopy(source), scope=deepcopy(scope), source_available_at=T, observed_at=T,
                     evidence=[evidence], coverage=coverage, records=[record], unsupported_lifecycle_evidence=[])
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T, knowledge_boundary=T,
             scope=scope, quantity_inventory=inventory)
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE, admission_id="synthetic-admission",
                   authority_id="test-host", mandate_id="test-mandate", mandate_revision=1, purpose=owner.PURPOSE,
                   admission_basis="PROVIDER_DOCUMENTS_REVIEWED_EXTERNALLY", inventory_source=deepcopy(source),
                   inventory_content_sha256=digest(normalized(inventory)), scope=deepcopy(scope), knowledge_boundary=T,
                   admitted_at=T, available_at=T, effective_from=EARLY, effective_until=END,
                   assurances={key: dict(status="ADMITTED", evidence_refs=deepcopy(support)) for key in owner.ASSURANCES})
    return q, context


@pytest.fixture
def case():
    return sample()


def run(case):
    q, context = case
    return owner.evaluate_current_entry_quantity_domain(q, trusted_quantity_context=context)


def add(case, row):
    q, context = case
    row["evidence_refs"] = deepcopy(q["quantity_inventory"]["coverage"]["evidence_refs"])
    q["quantity_inventory"]["records"].append(row)
    return seal(q, context)


def test_established_complete_reconstruction_and_authority(case):
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["reason_codes"] == ["ENTRY_QUANTITY_DOMAIN_ESTABLISHED"]
    assert result["domain"] == dict(kind="REGULAR_GRID", origin="0", increment="0.1", first_index="1", last_index="3")
    assert result["domain_identity"] == "entry_quantity_domain_" + digest(dict(quantity_unit="lot", domain=result["domain"]))
    assert result["reconstruction_evidence"]["request"] == normalized(case[0])
    assert result["reconstruction_evidence"]["trusted_context_content_sha256"] == digest(normalized(case[1]))
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                                                "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
    assert result["downstream_obligations"] == ["BUDGET_AND_DAILY_LOSS_ELIGIBILITY", "CANDIDATE_VALIDITY", "INSTRUMENT_AND_UNIT_COMPATIBILITY",
        "MARGIN_AND_CAPITAL_FEASIBILITY", "MARKET_AND_ORDER_EXECUTION_FEASIBILITY", "MISSION_CONTROL_AUTHORIZATION",
        "POSITION_EFFECT_AND_OTHER_PROVIDER_COMPLIANCE", "RISK_CONSTRAINED_QUANTITY_SELECTION"]
    assert result["execution"] is False
    assert set(result) == set("contract rule_version assessment_economic_time knowledge_boundary scope outcome reason_codes resolved_record domain domain_identity reconstruction_evidence source_authentication downstream_obligations authority execution assessment_identity".split())
    assert not any(key in result for key in ("quantity", "selected_quantity", "budget", "authorization"))
    assert case == before
    assert owner.validate_current_entry_quantity_domain(result, case[0], trusted_quantity_context=case[1]) == result
    identity = result.pop("assessment_identity")
    assert identity == "current_entry_quantity_domain_" + digest(result)


def test_missing_inventory(case):
    case[0]["quantity_inventory"] = None
    result = run((case[0], None))
    assert result["outcome"] == "UNKNOWN"
    assert result["reason_codes"] == ["MISSING_INVENTORY"]
    assert result["domain"] is result["domain_identity"] is result["resolved_record"] is None
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("empty", [False, True])
def test_no_admission_even_with_empty_arithmetic(case, empty):
    if empty:
        case[0]["quantity_inventory"]["records"][0]["domain"] = grid("0.07", "0.1", "0", "0.06")
        seal(*case)
    result = run((case[0], None))
    assert result["outcome"] == "UNKNOWN" and result["domain"] is None
    assert result["reason_codes"] == ["MISSING_HOST_ADMISSION"]
    established = run(case)
    with pytest.raises(ValueError): owner.validate_current_entry_quantity_domain(established, case[0])


@pytest.mark.parametrize("origin,step,minimum,maximum,expected", [
    ("0.07", "0.1", "0", "0.06", {"kind": "EMPTY"}),
    ("-0.03", "0.10", "0", "0.07", dict(kind="REGULAR_GRID", origin="0.07", increment="0.1", first_index="0", last_index="0")),
    ("-1.2", "0.1", "-1", "0", {"kind": "EMPTY"}),
    ("0", "0.1", "0", "0", {"kind": "EMPTY"}),
    ("0", "0.1", "-1", "0.1", dict(kind="REGULAR_GRID", origin="0", increment="0.1", first_index="1", last_index="1")),
    ("-0.03", "0.1", "0.08", None, dict(kind="REGULAR_GRID", origin="0.07", increment="0.1", first_index="1", last_index=None)),
    ("0", "0.03", "0.1", "0.12", dict(kind="REGULAR_GRID", origin="0", increment="0.03", first_index="4", last_index="4")),
])
def test_exact_grid_cases(case, origin, step, minimum, maximum, expected):
    case[0]["quantity_inventory"]["records"][0]["domain"] = grid(origin, step, minimum, maximum)
    seal(*case)
    result = run(case)
    assert result["domain"] == expected
    assert result["outcome"] == ("NOT_SUITABLE" if expected["kind"] == "EMPTY" else "ESTABLISHED")


@pytest.mark.parametrize("origin", ["-0.23", "-0.1", "0", "0.07", "0.37"])
@pytest.mark.parametrize("step", ["0.1", "0.03"])
@pytest.mark.parametrize("bounds", [("-0.2", "0"), ("0", "0.07"), ("0.07", "0.4"), ("0.11", "0.4")])
def test_grid_against_independent_small_enumeration(case, origin, step, bounds):
    minimum, maximum = bounds
    case[0]["quantity_inventory"]["records"][0]["domain"] = grid(origin, step, minimum, maximum)
    seal(*case)
    descriptor = run(case)["domain"]
    o, d, m, M = map(Fraction, (origin, step, minimum, maximum))
    expected = {o+n*d for n in range(-100, 101) if o+n*d > 0 and m <= o+n*d <= M}
    actual = set() if descriptor["kind"] == "EMPTY" else {
        Fraction(descriptor["origin"]) + k*d for k in range(int(descriptor["first_index"]), int(descriptor["last_index"])+1)}
    assert actual == expected


def test_arbitrary_precision_without_enumeration_or_decimal_context(case):
    step = "0." + "0" * 5000 + "1"
    case[0]["quantity_inventory"]["records"][0]["domain"] = grid("0", step, "0", "1")
    seal(*case)
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["domain"]["increment"] == step
    assert result["domain"]["last_index"] == "1" + "0" * 5001
    assert result["domain"]["first_index"] == "1"


@pytest.mark.parametrize("start,expected", [(BEFORE, "B"), (T, "B"), (AFTER, "A")])
def test_replacement_boundaries_and_future_known(case, start, expected):
    parent = case[0]["quantity_inventory"]["records"][0]
    add(case, declaration("B", parent, start=start, domain=grid(maximum="0.5")))
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["resolved_record"]["record_id"] == expected


@pytest.mark.parametrize("kind", ["withdraw", "expired"])
def test_no_fallback(case, kind):
    parent = case[0]["quantity_inventory"]["records"][0]
    row = withdrawal(parent) if kind == "withdraw" else declaration("B", parent, start=EARLY, end=T)
    add(case, row)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["resolved_record"]["record_id"] == row["record_id"]
    assert result["reason_codes"] == ["CURRENT_DECLARATION_WITHDRAWN" if kind == "withdraw" else "CURRENT_DECLARATION_EXPIRED"]
    assert result["domain"] is None


def test_explicit_new_declaration_after_withdrawal(case):
    parent = case[0]["quantity_inventory"]["records"][0]
    w = withdrawal(parent, start=BEFORE)
    add(case, w)
    add(case, declaration("C", w, start=T))
    assert run(case)["resolved_record"]["record_id"] == "C"
    assert run(case)["outcome"] == "ESTABLISHED"


def test_all_future_records(case):
    case[0]["quantity_inventory"]["records"][0]["effective_from"] = AFTER
    seal(*case)
    result = run(case)
    assert result["reason_codes"] == ["NO_CURRENT_DECLARATION"]


@pytest.mark.parametrize("declared", [False, True])
def test_missing_predecessor_is_explicit(case, declared):
    inventory = case[0]["quantity_inventory"]
    a = inventory["records"][0]
    b = declaration("B", a, start=T)
    b["evidence_refs"] = deepcopy(a["evidence_refs"])
    inventory["records"] = [b]
    if declared:
        inventory["coverage"].update(revision_completeness="LIMITED", missing_record_ids=["A"])
    seal(*case)
    if not declared:
        with pytest.raises(ValueError): run(case)
    else:
        result = run(case)
        assert result["outcome"] == "UNKNOWN"
        assert result["reason_codes"] == ["DECLARED_RECORDS_MISSING", "REVISION_HISTORY_INCOMPLETE"]


@pytest.mark.parametrize("limitation", ["truncated", "omitted", "starting_basis", "unknown_predecessor", "unknown_flags"])
def test_honest_incomplete_history(case, limitation):
    inventory = case[0]["quantity_inventory"]
    c = inventory["coverage"]
    c["revision_completeness"] = "LIMITED"
    if limitation == "truncated": c["history_truncated"] = True
    elif limitation == "omitted": c["records_omitted"] = True
    elif limitation == "starting_basis": c["starting_basis"] = "INCOMPLETE_OR_UNKNOWN"
    elif limitation == "unknown_predecessor":
        inventory["records"][0]["predecessor"] = dict(kind="UNKNOWN")
        c["root_records"] = []
    else:
        c.update(revision_completeness="UNKNOWN", records_omitted=None, history_truncated=None)
    seal(*case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["domain"] is None
    assert "REVISION_HISTORY_INCOMPLETE" in result["reason_codes"]


@pytest.mark.parametrize("event", ["correction", "reinstate"])
def test_unsupported_lifecycle_preserved(case, event):
    inventory = case[0]["quantity_inventory"]
    evidence = deepcopy(inventory["evidence"][0])
    evidence.update(evidence_id=event, content_base64=base64.b64encode(event.encode()).decode())
    inventory["evidence"].append(evidence)
    inventory["unsupported_lifecycle_evidence"] = [ref(evidence, "evidence_id")]
    seal(*case)
    result = run(case)
    assert result["reason_codes"] == ["UNSUPPORTED_LIFECYCLE"]
    assert result["domain"] is None


@pytest.mark.parametrize("competing", ["roots", "branches", "decreasing_start"])
def test_conflicting_valid_source_records_are_unknown(case, competing):
    inventory = case[0]["quantity_inventory"]
    a = inventory["records"][0]
    if competing == "roots":
        b = declaration("B")
        b["evidence_refs"] = deepcopy(a["evidence_refs"])
        inventory["records"].append(b)
        inventory["coverage"]["root_records"].append(ref(b, "record_id"))
    elif competing == "branches":
        add(case, declaration("B", a, start=T))
        add(case, declaration("C", a, start=T))
    else:
        a["effective_from"] = T
        add(case, declaration("B", a, start=BEFORE))
    seal(*case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["reason_codes"] == ["UNSUPPORTED_LIFECYCLE" if competing == "decreasing_start" else "COMPETING_REVISION_CHAINS"]


@pytest.mark.parametrize("key", owner.ASSURANCES)
def test_independent_assurances_required(case, key):
    case[1]["assurances"][key] = dict(status="UNRESOLVED", evidence_refs=[])
    assert run(case)["reason_codes"] == [owner.ASSURANCE_REASONS[key]]


@pytest.mark.parametrize("target", ["inventory", "coverage", "record", "evidence"])
def test_unknown_source_availability(case, target):
    inventory = case[0]["quantity_inventory"]
    row = {"inventory": inventory, "coverage": inventory["coverage"], "record": inventory["records"][0], "evidence": inventory["evidence"][0]}[target]
    row["source_available_at"] = None
    seal(*case)
    assert run(case)["reason_codes"] == ["SOURCE_AVAILABILITY_UNKNOWN"]


@pytest.mark.parametrize("target", ["coverage", "record", "admission"])
def test_missing_supporting_material(case, target):
    inventory = case[0]["quantity_inventory"]
    if target == "admission":
        case[1]["assurances"]["source_authority"]["evidence_refs"] = []
        with pytest.raises(ValueError): run(case)
    else:
        row = inventory["coverage"] if target == "coverage" else inventory["records"][0]
        row["evidence_refs"] = []
        seal(*case)
        assert run(case)["reason_codes"] == ["SUPPORTING_EVIDENCE_MISSING"]


def test_missing_current_terms_are_not_empty(case):
    inventory = case[0]["quantity_inventory"]
    inventory["records"][0]["domain"] = None
    inventory["coverage"]["quantity_rule_completeness"] = "LIMITED"
    seal(*case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["domain"] is None
    assert result["reason_codes"] == ["CURRENT_DOMAIN_TERMS_MISSING", "QUANTITY_RULE_COVERAGE_INCOMPLETE"]


@pytest.mark.parametrize("field,value,reason", [
    ("source_information_cutoff", BEFORE, "COVERAGE_NOT_THROUGH_K"),
    ("source_information_cutoff", None, "COVERAGE_NOT_THROUGH_K"),
    ("economic_until", T, "COVERAGE_DOES_NOT_INCLUDE_T"),
    ("economic_from", AFTER, "COVERAGE_DOES_NOT_INCLUDE_T"),
])
def test_current_coverage_boundaries(case, field, value, reason):
    case[0]["quantity_inventory"]["coverage"][field] = value
    seal(*case)
    assert run(case)["reason_codes"] == [reason]


@pytest.mark.parametrize("field,value", [("effective_until", T), ("effective_from", AFTER)])
def test_admission_interval_is_not_trade_authority(case, field, value):
    case[1][field] = value
    assert run(case)["reason_codes"] == ["ADMISSION_OUTSIDE_EFFECTIVE_INTERVAL"]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_exact_scope_and_open_intervals(case, direction):
    q, c = case
    for scope in (q["scope"], q["quantity_inventory"]["scope"], c["scope"]): scope["entry_direction"] = direction
    q["quantity_inventory"]["coverage"]["economic_until"] = None
    q["quantity_inventory"]["records"][0]["effective_until"] = None
    c["effective_until"] = None
    c["admission_basis"] = "PROVIDER_ORIGIN_VERIFIED_EXTERNALLY"
    seal(*case)
    assert run(case)["outcome"] == "ESTABLISHED"
    assert run(case)["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"


def test_decimal_spelling_and_timestamp_identity(case):
    original = run(case)
    record = case[0]["quantity_inventory"]["records"][0]
    record["domain"].update(origin="-00.000", increment="00.1000", minimum="000.100")
    record["domain"]["maximum"]["value"] = "000.3000"
    case[0]["assessment_economic_time"] = "2026-01-02T13:00:00+01:00"
    record["observed_at"] = "2026-01-01T01:00:00+01:00"
    assert run(case) == original  # No new host pin is needed for equivalent normalized content.


def test_origin_shift_has_same_domain_but_different_evidence_identity(case):
    original = run(case)
    case[0]["quantity_inventory"]["records"][0]["domain"]["origin"] = "-0.2"
    seal(*case)
    changed = run(case)
    assert changed["domain_identity"] == original["domain_identity"]
    assert changed["assessment_identity"] != original["assessment_identity"]


def test_permutation_invariance(case):
    inventory = case[0]["quantity_inventory"]
    evidence = deepcopy(inventory["evidence"][0])
    evidence["evidence_id"] = "other"
    inventory["evidence"].append(evidence)
    for row in [inventory["coverage"], inventory["records"][0]]: row["evidence_refs"].append(ref(evidence, "evidence_id"))
    add(case, declaration("B", inventory["records"][0], start=T))
    baseline = run(case)
    def reverse(value):
        if type(value) is dict: return {key: reverse(item) for key, item in reversed(list(value.items()))}
        if type(value) is list: return [reverse(item) for item in reversed(value)]
        return value
    assert run((reverse(case[0]), reverse(case[1]))) == baseline


def test_raw_evidence_bytes_remain_bound(case):
    original = run(case)
    evidence = case[0]["quantity_inventory"]["evidence"][0]
    evidence["content_base64"] = base64.b64encode(b'{ "synthetic": true }').decode()
    with pytest.raises(ValueError): run(case)
    seal(*case)
    result = run(case)
    assert result["domain_identity"] == original["domain_identity"]
    assert result["assessment_identity"] != original["assessment_identity"]


def test_untrusted_approval_and_full_forged_identity_cannot_create_admission(case):
    result = run(case)
    case[0]["approved"] = True
    with pytest.raises(ValueError): run(case)
    del case[0]["approved"]
    result["domain"]["last_index"] = "99"
    result.pop("assessment_identity")
    result["assessment_identity"] = "current_entry_quantity_domain_" + digest(result)
    with pytest.raises(ValueError): owner.validate_current_entry_quantity_domain(result, case[0], trusted_quantity_context=case[1])


def paths(value, prefix=()):
    yield prefix
    if type(value) is dict:
        for key, item in value.items(): yield from paths(item, prefix + (key,))
    elif type(value) is list:
        for index, item in enumerate(value): yield from paths(item, prefix + (index,))


def at(value, path):
    for key in path: value = value[key]
    return value


REQUEST, CONTEXT = sample()
OBJECT_PATHS = [(which, path) for which, value in ((0, REQUEST), (1, CONTEXT)) for path in paths(value) if type(at(value, path)) is dict]


@pytest.mark.parametrize("which,path", OBJECT_PATHS)
def test_exact_schema_every_object(case, which, path):
    original = at(case[which], path)
    for key in original:
        modified = deepcopy(case)
        del at(modified[which], path)[key]
        with pytest.raises(ValueError): run(modified)
    modified = deepcopy(case)
    at(modified[which], path)["extra"] = True
    with pytest.raises(ValueError): run(modified)


@pytest.mark.parametrize("path", [p for p in paths(run((REQUEST, CONTEXT))) if not isinstance(at(run((REQUEST, CONTEXT)), p), (dict, list))])
def test_each_assessment_leaf_reconstructed(case, path):
    result = run(case)
    parent = at(result, path[:-1])
    old = parent[path[-1]]
    parent[path[-1]] = "altered" if old is None else None
    with pytest.raises(ValueError): owner.validate_current_entry_quantity_domain(result, case[0], trusted_quantity_context=case[1])


@pytest.mark.parametrize("field", ["origin", "increment", "minimum", "maximum"])
@pytest.mark.parametrize("bad", [0.1, True, False, 1, None, "NaN", "Infinity", "-Infinity", "1e-2", "+1", " 1", "1 ", ".1", "1.", "", [], {}])
def test_grid_numeric_representations_rejected(case, field, bad):
    domain = case[0]["quantity_inventory"]["records"][0]["domain"]
    if field == "maximum": domain["maximum"]["value"] = bad
    else: domain[field] = bad
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("bad", ["0", "-0.00", "-1"])
def test_nonpositive_increment(case, bad):
    case[0]["quantity_inventory"]["records"][0]["domain"]["increment"] = bad
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("field", ["observed_at", "source_available_at"])
@pytest.mark.parametrize("target", ["inventory", "coverage", "record", "evidence"])
def test_post_knowledge_evidence_rejected(case, field, target):
    inventory = case[0]["quantity_inventory"]
    row = {"inventory": inventory, "coverage": inventory["coverage"], "record": inventory["records"][0], "evidence": inventory["evidence"][0]}[target]
    row[field] = AFTER
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("field,value", [("admitted_at", AFTER), ("available_at", AFTER), ("admitted_at", BEFORE), ("available_at", BEFORE), ("knowledge_boundary", BEFORE)])
def test_admission_causal_rejection(case, field, value):
    case[1][field] = value
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("bad", ["2026-01-02T12:00:00", "2026-01-02", "2026-01-02T12:00:00.1234567Z", "2026-02-30T12:00:00Z", "2026-01-02T12:00:00+24:00", "2026-01-02T12:00:00+00:60", 1, True, None])
def test_invalid_timestamps(case, bad):
    case[0]["knowledge_boundary"] = bad
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("mutation", ["pin", "scope", "source", "purpose", "basis", "mandate", "hash_type", "assurance_extra"])
def test_context_rejections(case, mutation):
    c = case[1]
    if mutation == "pin": c["inventory_content_sha256"] = "0" * 64
    elif mutation == "scope": c["scope"]["account_id"] = "other"
    elif mutation == "source": c["inventory_source"]["source_snapshot_id"] = "other"
    elif mutation == "purpose": c["purpose"] = "TRADE_APPROVAL"
    elif mutation == "basis": c["admission_basis"] = "CALLER_APPROVED"
    elif mutation == "mandate": c["mandate_revision"] = True
    elif mutation == "hash_type": c["inventory_content_sha256"] = []
    else: c["assurances"]["execution"] = dict(status="ADMITTED", evidence_refs=[])
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("mutation", ["record_duplicate", "evidence_duplicate", "root_duplicate", "missing_present", "complete_gap", "limited_without_gap", "complete_unknown_flag", "unknown_predecessor_complete", "root_not_declared", "root_not_root", "dangling_evidence", "wrong_evidence_hash", "wrong_root_hash", "reversed_interval", "reversed_grid", "grid_model", "maximum_model", "source_scope", "post_cutoff", "publication_before_cutoff", "inventory_before_content", "withdraw_root", "unknown_missing_terms"])
def test_structural_material_rejected_before_unknown(case, mutation):
    q = case[0]
    i = q["quantity_inventory"]
    c, r, e = i["coverage"], i["records"][0], i["evidence"][0]
    if mutation == "record_duplicate":
        other = deepcopy(r); other["domain"]["minimum"] = "0"; i["records"].append(other)
    elif mutation == "evidence_duplicate": i["evidence"].append(deepcopy(e))
    elif mutation == "root_duplicate": c["root_records"].append(deepcopy(c["root_records"][0]))
    elif mutation == "missing_present": c["missing_record_ids"] = ["A"]
    elif mutation == "complete_gap": c["history_truncated"] = True
    elif mutation == "limited_without_gap": c["revision_completeness"] = "LIMITED"
    elif mutation == "complete_unknown_flag": c["records_omitted"] = None
    elif mutation == "unknown_predecessor_complete": r["predecessor"] = dict(kind="UNKNOWN"); c["root_records"] = []
    elif mutation == "root_not_declared": c["root_records"] = []
    elif mutation == "root_not_root": r["predecessor"] = dict(kind="UNKNOWN")
    elif mutation == "dangling_evidence": r["evidence_refs"][0]["evidence_id"] = "absent"
    elif mutation == "wrong_evidence_hash": r["evidence_refs"][0]["content_sha256"] = "0" * 64
    elif mutation == "wrong_root_hash": c["root_records"][0]["content_sha256"] = "0" * 64
    elif mutation == "reversed_interval": r["effective_until"] = EARLY
    elif mutation == "reversed_grid": r["domain"]["minimum"] = "1"
    elif mutation == "grid_model": r["domain"]["model"] = "CUSTOM"
    elif mutation == "maximum_model": r["domain"]["maximum"] = dict(kind="UNKNOWN")
    elif mutation == "source_scope": i["scope"]["account_id"] = "other"
    elif mutation == "post_cutoff": c["source_information_cutoff"] = AFTER
    elif mutation == "publication_before_cutoff": c["source_available_at"] = BEFORE
    elif mutation == "inventory_before_content": i["observed_at"] = BEFORE; i["source_available_at"] = BEFORE
    elif mutation == "withdraw_root": i["records"] = [dict(record_id="W", kind="WITHDRAW", predecessor=dict(kind="ROOT"), effective_from=T, source_available_at=EARLY, observed_at=EARLY, evidence_refs=[])]
    else: r["domain"] = None
    with pytest.raises(ValueError): run((q, None))


@pytest.mark.parametrize("encoded", ["", "!", "YQ", "YR==", "YQ==\n", True, None])
def test_invalid_source_encoding(case, encoded):
    case[0]["quantity_inventory"]["evidence"][0]["content_base64"] = encoded
    with pytest.raises(ValueError): run((case[0], None))


def test_tk_must_match_even_if_all_other_material_missing(case):
    case[0]["quantity_inventory"] = None
    case[0]["assessment_economic_time"] = BEFORE
    with pytest.raises(ValueError): run((case[0], None))


def test_unicode_preserved_and_surrogates_rejected(case):
    for scope in (case[0]["scope"], case[0]["quantity_inventory"]["scope"], case[1]["scope"]): scope["account_id"] = "账户"
    seal(*case)
    assert run(case)["scope"]["account_id"] == "账户"
    case[0]["scope"]["account_id"] = "\ud800"
    with pytest.raises(ValueError): run(case)


def test_detached_results_validator_and_nonmutation(case):
    before = deepcopy(case)
    result = run(case)
    validated = owner.validate_current_entry_quantity_domain(result, case[0], trusted_quantity_context=case[1])
    validated["reconstruction_evidence"]["request"]["scope"]["account_id"] = "mutated"
    result["authority"]["trade_decision"] = True
    assert case == before
    fresh = run(case)
    assert fresh["scope"]["account_id"] == "account" and not fresh["authority"]["trade_decision"]


def test_multiple_unknowns_are_sorted_and_retained(case):
    i = case[0]["quantity_inventory"]
    i["coverage"].update(revision_completeness="LIMITED", history_truncated=True, source_information_cutoff=BEFORE)
    i["records"][0]["domain"] = grid("0.07", "0.1", "0", "0.06")
    seal(*case)
    result = run((case[0], None))
    assert result["outcome"] == "UNKNOWN" and result["domain"] is None
    assert result["reason_codes"] == ["COVERAGE_NOT_THROUGH_K", "MISSING_HOST_ADMISSION", "REVISION_HISTORY_INCOMPLETE"]
    assert set(result["reason_codes"]) <= owner.REASON_CODES


@pytest.mark.parametrize("field", ["reason_codes", "downstream_obligations"])
def test_validator_rejects_python_container_coercions(case, field):
    result = run(case)
    result[field] = tuple(result[field])
    with pytest.raises(ValueError):
        owner.validate_current_entry_quantity_domain(result, case[0], trusted_quantity_context=case[1])


def test_explicitly_absent_original_evidence_stays_unknown(case):
    inventory = case[0]["quantity_inventory"]
    inventory["evidence"] = []
    inventory["coverage"]["evidence_refs"] = []
    inventory["records"][0]["evidence_refs"] = []
    seal(case[0], None)
    result = run((case[0], None))
    assert result["outcome"] == "UNKNOWN"
    assert result["reason_codes"] == ["MISSING_HOST_ADMISSION", "SUPPORTING_EVIDENCE_MISSING"]


def test_empty_complete_history_does_not_prove_an_empty_quantity_domain(case):
    inventory = case[0]["quantity_inventory"]
    inventory["records"] = []
    inventory["coverage"]["root_records"] = []
    seal(*case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["reason_codes"] == ["NO_CURRENT_DECLARATION"]
    assert result["domain"] is None


def test_chain_order_overrides_revision_names_with_equal_starts(case):
    inventory = case[0]["quantity_inventory"]
    parent = inventory["records"][0]
    parent["record_id"] = "z-last-lexically"
    inventory["coverage"]["root_records"] = [ref(parent, "record_id")]
    add(case, declaration("a-first-lexically", parent, start=EARLY))
    inventory["records"].reverse()
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["resolved_record"]["record_id"] == "a-first-lexically"


def test_unknown_coverage_retains_a_known_missing_record(case):
    inventory = case[0]["quantity_inventory"]
    inventory["coverage"].update(revision_completeness="UNKNOWN", source_information_cutoff=None,
                                 missing_record_ids=["known-omission"], records_omitted=True,
                                 history_truncated=None)
    seal(*case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["reason_codes"] == ["COVERAGE_NOT_THROUGH_K", "DECLARED_RECORDS_MISSING", "REVISION_HISTORY_INCOMPLETE"]


@pytest.mark.parametrize("path", [("coverage", "root_records"), ("records", 0, "evidence_refs")])
def test_duplicate_references_are_rejected_even_without_admission(case, path):
    references = at(case[0]["quantity_inventory"], path)
    references.append(deepcopy(references[0]))
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("which", ["withdrawal", "unbounded", "unknown_predecessor"])
def test_tagged_union_schemas(case, which):
    inventory = case[0]["quantity_inventory"]
    if which == "withdrawal":
        row = withdrawal(inventory["records"][0])
        add(case, row)
        target = inventory["records"][-1]
    elif which == "unbounded":
        target = inventory["records"][0]["domain"]["maximum"]
        target.clear()
        target["kind"] = "UNBOUNDED"
    else:
        target = inventory["records"][0]["predecessor"]
        target.clear()
        target["kind"] = "UNKNOWN"
        inventory["coverage"].update(root_records=[], revision_completeness="LIMITED")
    seal(*case)
    assert run(case)["outcome"] in ("ESTABLISHED", "UNKNOWN")
    target["extra"] = None
    with pytest.raises(ValueError): run((case[0], None))


def test_changed_owner_valid_source_and_scope_changes_identity(case):
    original = run(case)
    for scope in (case[0]["scope"], case[0]["quantity_inventory"]["scope"], case[1]["scope"]):
        scope["account_id"] = "another-account"
    case[0]["quantity_inventory"]["source"]["source_snapshot_id"] = "snapshot-2"
    case[1]["inventory_source"]["source_snapshot_id"] = "snapshot-2"
    seal(*case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["assessment_identity"] != original["assessment_identity"]
    assert result["domain_identity"] == original["domain_identity"]


def test_post_knowledge_validation_not_hidden_by_daily_like_caller_block(case):
    # No downstream policy field can grant trust or short-circuit malformed source evidence.
    inventory = case[0]["quantity_inventory"]
    inventory["coverage"].update(revision_completeness="LIMITED", history_truncated=True)
    inventory["records"][0]["observed_at"] = AFTER
    with pytest.raises(ValueError): run((case[0], None))
