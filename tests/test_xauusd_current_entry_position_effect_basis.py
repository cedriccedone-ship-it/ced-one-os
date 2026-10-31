"""Synthetic external evidence/admission, with genuine native account reconstruction."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
import sys

import pytest

from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as accounts
from ced_one.business_divisions.trading import xauusd_current_entry_position_effect_basis as owner
from tests.test_trading_vertical_slice_v24 import sample as native_input


T = "2026-01-02T12:00:00.000000Z"
EARLY = "2026-01-01T00:00:00.000000Z"
BEFORE = "2026-01-02T11:59:59.999999Z"
AFTER = "2026-01-02T12:00:00.000001Z"
END = "2026-01-03T00:00:00.000000Z"
TIME_KEYS = {"assessment_economic_time", "knowledge_boundary", "source_available_at", "observed_at", "effective_from",
             "effective_until", "economic_from", "economic_until", "source_information_cutoff", "state_at", "admitted_at", "available_at"}
CATEGORIES = (
    "PENDING_SUBMISSIONS", "ACCEPTED_UNFILLED_ORDERS", "PARTIALLY_FILLED_ORDERS",
    "CANCELLATIONS_AWAITING_CONFIRMATION", "POSITION_RESERVATIONS", "POSITION_ALLOCATIONS",
    "OTHER_PROVIDER_OR_ACCOUNT_PENDING_EFFECTS",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def normalized(value, key=None):
    """Independent fixture implementation of local canonical presentation; native pairs are opaque."""
    if key == "account_state":
        return deepcopy(value)
    if type(value) is dict:
        return {k: normalized(v, k) for k, v in value.items()}
    if type(value) is list:
        items = [normalized(v) for v in value]
        if key in ("evidence", "evidence_refs", "binding_evidence_refs"):
            return sorted(items, key=lambda v: v["evidence_id"])
        if key in ("records", "root_records"):
            return sorted(items, key=lambda v: v["record_id"])
        if key in ("reports", "inventory_roster"):
            return sorted(items, key=lambda v: v["inventory_id"])
        if key == "missing_record_ids":
            return sorted(items)
        return items
    if value is not None and key in TIME_KEYS:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    if key in ("minimum", "maximum") and type(value) is str:
        result = value.rstrip("0").rstrip(".") if "." in value else value
        return "0" if result in ("0", "-0") else result
    return value


def ref(row, key="evidence_id"):
    return {key: row[key], "content_sha256": digest(normalized(row))}


def seal(case):
    """Reissue synthetic fixture receipts; never bypass any native owner validator."""
    q, context = case
    inventory = q["effect_inventory"]
    if inventory is None:
        return case
    catalog = {item["evidence_id"]: item for item in inventory["evidence"]}

    def refresh(value):
        if type(value) is dict:
            for key, item in value.items():
                if key in ("evidence_refs", "binding_evidence_refs"):
                    value[key] = [ref(catalog[r["evidence_id"]]) if r["evidence_id"] in catalog else r for r in item]
                else:
                    refresh(item)
        elif type(value) is list:
            for item in value:
                refresh(item)
    refresh(inventory)
    if context is not None:
        refresh(context)
    records = {row["record_id"]: row for row in inventory["records"]}
    pending, done = set(records), set()
    while pending:
        progressed = False
        for identifier in sorted(pending):
            previous = records[identifier]["predecessor"]
            parent = previous.get("record", {}).get("record_id")
            if parent in records and parent not in done:
                continue
            if parent in records:
                previous["record"] = ref(records[parent], "record_id")
            done.add(identifier)
            pending.remove(identifier)
            progressed = True
        if not progressed:
            raise AssertionError("Fixture sealing does not support cycles")
    coverage = inventory["coverage"]
    coverage["root_records"] = [ref(records[r["record_id"]], "record_id") if r["record_id"] in records else r
                                for r in coverage["root_records"]]
    if context is not None:
        context["request_content_sha256"] = digest(normalized(q))
    return case


def sample(direction="LONG", mode="NETTING"):
    original = native_input()
    original["requested_evaluation_timestamp"] = T
    observation = original["observation"]
    observation["account"]["position_mode"] = mode
    observation["timing"] = dict(effective_at=T, observed_at=T, source_available_at=T)
    observation["positions"] = dict(completeness="COMPLETE", items=[])
    pair = dict(snapshot=accounts.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(original).to_dict(), snapshot_input=original)
    namespace = dict(source_id="test-provider", source_contract="venue-facts", source_contract_version="1")
    account = {key: observation["source"][key] for key in ("source_id", "source_contract", "source_contract_version")}
    account.update({key: observation["account"][key] for key in ("account_id", "environment", "currency")})
    scope = dict(account=account, provider_namespace=namespace, provider_id="provider", venue_id="venue",
                 instrument={**namespace, "environment": "DEMO", "instrument_id": "provider:XAUUSD"},
                 entry_direction=direction, entry_mechanism=owner.MECHANISM, quantity_unit=" lot ")
    source = {**namespace, "source_snapshot_id": "original-1"}
    originals = (
        ("account", original),
        ("mechanics", dict(synthetic=True, scope=scope, mode=mode, model="ONE_NEW_SEPARATE_POSITION",
                           aggregation="ALL_ENTRY_FILLS_TO_ONE_POSITION", minimum="0.1", maximum="2")),
        ("closure", dict(synthetic=True, account=account, state_at=T, all_actors=True,
                         sources=["broker", "outbox", "reservations"], categories={key: "EMPTY" for key in CATEGORIES})),
    )
    evidence = [dict(evidence_id=identifier, source=deepcopy(source), media_type="application/json",
                     content_base64=base64.b64encode(canonical(content).encode()).decode(), source_available_at=T, observed_at=T)
                for identifier, content in originals]
    support = [ref(row) for row in evidence]
    roster, reports = [], []
    for identifier, role in (("broker", "PROVIDER"), ("outbox", "SUBMISSION_CHANNEL"), ("reservations", "RESERVATION_OR_ALLOCATION")):
        ns = {**namespace, "source_id": identifier}
        roster.append(dict(inventory_id=identifier, source_namespace=ns, source_account_id="source-account",
                           role=role, binding_evidence_refs=deepcopy(support)))
        reports.append(dict(inventory_id=identifier, source={**ns, "source_snapshot_id": "report-1"}, state_at=T,
                            source_information_cutoff=T, inventory_completeness="COMPLETE", revision_completeness="COMPLETE",
                            source_available_at=T, observed_at=T,
                            categories={key: dict(status="EMPTY", evidence_refs=deepcopy(support)) for key in CATEGORIES},
                            evidence_refs=deepcopy(support)))
    body = dict(account_bundle_sha256=digest(pair),
                positions=dict(state_at=T, source_information_cutoff=T, inventory_completeness="COMPLETE",
                               revision_completeness="COMPLETE", population_scope="ALL_ACCOUNT_POSITIONS", evidence_refs=deepcopy(support)),
                bindings={key: dict(status="COMPATIBLE", evidence_refs=deepcopy(support)) for key in owner.BINDINGS},
                mechanics=dict(position_mode=mode, model="ONE_NEW_SEPARATE_POSITION", fill_aggregation="ALL_ENTRY_FILLS_TO_ONE_POSITION",
                               quantity_range=dict(minimum="0.1", maximum="2"), source_information_cutoff=T,
                               revision_completeness="COMPLETE", evidence_refs=deepcopy(support)),
                commitments=dict(state_at=T, source_information_cutoff=T, population_scope="ALL_ACCOUNT_POSITION_AFFECTING_COMMITMENTS",
                                 source_universe_completeness="COMPLETE", actor_coverage="ALL_ACCOUNT_ACTORS", inventory_roster=roster,
                                 reports=reports, evidence_refs=deepcopy(support)))
    record = dict(record_id="A", kind="DECLARE", predecessor=dict(kind="ROOT"), effective_from=EARLY, effective_until=END,
                  source_available_at=T, observed_at=T, evidence_refs=deepcopy(support), body=body)
    coverage = dict(economic_from=EARLY, economic_until=END, source_information_cutoff=T, declaration_completeness="COMPLETE",
                    revision_completeness="COMPLETE", starting_basis="FROM_INCEPTION", root_records=[ref(record, "record_id")],
                    missing_record_ids=[], records_omitted=False, history_truncated=False, source_available_at=T, observed_at=T,
                    evidence_refs=deepcopy(support))
    inventory = dict(contract=owner.INVENTORY_CONTRACT, rule_version=owner.INVENTORY_RULE, source=deepcopy(source), scope=deepcopy(scope),
                     source_available_at=T, observed_at=T, evidence=evidence, coverage=coverage, records=[record])
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T, knowledge_boundary=T,
             scope=scope, account_state=pair, effect_inventory=inventory)
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE, admission_id="synthetic-admission",
                   authority_id="test-host", mandate_id="independent-test-mandate", mandate_revision=1, purpose=owner.PURPOSE,
                   request_content_sha256=digest(normalized(q)), knowledge_boundary=T, effective_from=EARLY, effective_until=END,
                   admitted_at=T, available_at=T,
                   assurances={key: dict(status="ADMITTED", evidence_refs=deepcopy(support)) for key in owner.ASSURANCES})
    return q, context


def run(case):
    return owner.evaluate_current_entry_position_effect_basis(case[0], trusted_position_effect_context=case[1])


def validate(assessment, case):
    return owner.validate_current_entry_position_effect_basis(assessment, case[0], trusted_position_effect_context=case[1])


def body(case):
    return case[0]["effect_inventory"]["records"][0]["body"]


def native(case):
    return case[0]["account_state"]["snapshot_input"]["observation"]


def issue_account(case):
    pair = case[0]["account_state"]
    pair["snapshot"] = accounts.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(pair["snapshot_input"]).to_dict()
    body(case)["account_bundle_sha256"] = digest(pair)
    body(case)["positions"]["state_at"] = pair["snapshot"]["observation"]["timing"]["effective_at"]
    return seal(case)


def add(case, kind="DECLARE", identifier="B", start=T, parent=None, end=END):
    inventory = case[0]["effect_inventory"]
    parent = inventory["records"][-1] if parent is None else parent
    row = dict(record_id=identifier, kind=kind, predecessor=dict(kind="RECORD", record=ref(parent, "record_id")),
               effective_from=start, source_available_at=T, observed_at=T, evidence_refs=deepcopy(parent["evidence_refs"]))
    if kind == "DECLARE":
        row.update(effective_until=end, body=deepcopy(next(r["body"] for r in inventory["records"] if r["kind"] == "DECLARE")))
    inventory["records"].append(row)
    seal(case)
    return row


@pytest.fixture
def case():
    return sample()


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("mode", ["NETTING", "HEDGING"])
def test_genuine_full_flat_closure(direction, mode):
    case = sample(direction, mode)
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["reason_codes"] == ["POSITION_EFFECT_BASIS_ESTABLISHED"]
    expected = dict(model="ONE_NEW_SEPARATE_POSITION", position_mode=mode, quantity_unit=" lot ",
                    quantity_range=dict(minimum="0.1", maximum="2"), resulting_direction=direction,
                    resulting_position_quantity=dict(kind="IDENTITY_OF_ENTRY_QUANTITY"), initial_position_count=0,
                    terminal_position_count=1, terminal_position_count_delta=1,
                    conditions=["ACCEPTED_ENTRY_FULLY_FILLED", "ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS",
                                "NO_UNRELATED_INTERVENING_STATE_CHANGE", "ADMITTED_MECHANICS_REMAIN_APPLICABLE"])
    assert result["effect_basis"] == expected
    assert result["resolved_record"] == ref(case[0]["effect_inventory"]["records"][0], "record_id")
    assert validate(result, case) == result
    assert case == before
    assert result["reconstruction_evidence"]["request"] == normalized(case[0])
    assert result["reconstruction_evidence"]["trusted_position_effect_context_sha256"] == digest(normalized(case[1]))
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance",
                                                "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
    assert result["execution"] is False
    assert not {"quantity", "selected_quantity", "order", "decision", "approval"} & result.keys()
    assert result["assessment_identity"] == "current_entry_position_effect_basis_" + digest({k: v for k, v in result.items() if k != "assessment_identity"})


@pytest.mark.parametrize("minimum,maximum", [("0.1", "2"), ("0.10", "0.100"), ("1.000", "1.001")])
def test_inclusive_interval_and_singleton(case, minimum, maximum):
    body(case)["mechanics"]["quantity_range"] = dict(minimum=minimum, maximum=maximum)
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED"
    interval = result["effect_basis"]["quantity_range"]
    lo, hi = map(Fraction, (interval["minimum"], interval["maximum"]))
    assert lo == Fraction(minimum) and hi == Fraction(maximum)
    assert lo <= Fraction(minimum) <= hi and lo <= Fraction(maximum) <= hi
    assert not lo <= lo / 2 <= hi and not lo <= hi + 1 <= hi


def test_extreme_precision_and_signed_decimal_rejection(case):
    tiny = "0." + "0" * 5000 + "1"
    huge = "1" + "0" * 5000 + ".1200"
    body(case)["mechanics"]["quantity_range"] = dict(minimum=tiny, maximum=huge)
    seal(case)
    limit_before = sys.get_int_max_str_digits()
    with localcontext() as ctx:
        ctx.prec = 2
        result = run(case)
    assert result["effect_basis"]["quantity_range"] == dict(minimum=tiny, maximum=huge[:-2])
    assert sys.get_int_max_str_digits() == limit_before
    assert validate(result, case) == result


@pytest.mark.parametrize("bounds", [("-0", "1"), ("-0.00", "1"), ("-1", "2"), ("0", "1"), ("2", "1"),
                                    ("+1", "2"), ("01", "2"), ("1e-2", "2"), (" 1", "2"), (1, "2"), (True, "2"),
                                    ("NaN", "2"), ("1", None), ("1", float("inf"))])
def test_invalid_range(case, bounds):
    body(case)["mechanics"]["quantity_range"] = dict(zip(("minimum", "maximum"), bounds))
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("state", ["missing", "partial", "unavailable", "stale", "nonflat", "unknown_mode", "availability_unknown"])
def test_native_account_unknowns(case, state):
    expected = {
        "missing": "MISSING_ACCOUNT_STATE", "partial": "POSITION_INVENTORY_INCOMPLETE",
        "unavailable": "POSITION_INVENTORY_INCOMPLETE", "stale": "ACCOUNT_STATE_NOT_CURRENT",
        "nonflat": "ACCOUNT_NOT_FLAT", "unknown_mode": "ACCOUNT_MODE_UNRESOLVED",
        "availability_unknown": "SOURCE_AVAILABILITY_UNKNOWN",
    }[state]
    if state == "missing":
        case[0]["account_state"] = None
        seal(case)
    else:
        obs = native(case)
        if state in ("partial", "unavailable"):
            obs["positions"]["completeness"] = "PARTIAL" if state == "partial" else "UNAVAILABLE"
            body(case)["positions"]["inventory_completeness"] = "LIMITED" if state == "partial" else "UNKNOWN"
        elif state == "stale": obs["timing"]["effective_at"] = BEFORE
        elif state == "nonflat": obs["positions"]["items"] = [dict(position_id="open", instrument_id="other", direction="SHORT", quantity="1", quantity_unit="unit")]
        elif state == "unknown_mode": obs["account"]["position_mode"] = "UNKNOWN"
        else: obs["timing"]["source_available_at"] = None
        issue_account(case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["effect_basis"] is None
    assert expected in result["reason_codes"]
    assert "NOT_SUITABLE" not in result.values()


def test_partial_native_cannot_be_promoted_by_local_claim_or_admission(case):
    native(case)["positions"]["completeness"] = "PARTIAL"
    issue_account(case)
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("status,reason", [("NONEMPTY", "COMMITMENT_PRESENT"), ("UNKNOWN", "COMMITMENT_STATUS_UNKNOWN")])
def test_each_commitment_category_blocks_mapping(case, category, status, reason):
    body(case)["commitments"]["reports"][1]["categories"][category]["status"] = status
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and result["effect_basis"] is None
    assert reason in result["reason_codes"]
    assert any(f["reason_code"] == reason and category in f["subject"] for f in result["unresolved_findings"])
    assert result["resolved_record"] is not None


@pytest.mark.parametrize("field,value", [("source_universe_completeness", "LIMITED"), ("source_universe_completeness", "UNKNOWN"),
                                        ("actor_coverage", "UNKNOWN")])
def test_source_and_actor_coverage(case, field, value):
    body(case)["commitments"][field] = value
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and "COMMITMENT_COVERAGE_INCOMPLETE" in result["reason_codes"]


@pytest.mark.parametrize("change", ["missing", "empty", "no_provider", "partial", "revisions", "stale_state", "stale_cutoff", "availability"])
def test_commitment_report_closure(case, change):
    closure = body(case)["commitments"]
    expected = "COMMITMENT_COVERAGE_INCOMPLETE"
    if change == "missing":
        closure["reports"] = closure["reports"][:1]
        expected = "COMMITMENT_REPORT_MISSING"
    elif change == "empty": closure.update(inventory_roster=[], reports=[])
    elif change == "no_provider": closure["inventory_roster"][0]["role"] = "SUBMISSION_CHANNEL"
    elif change == "partial": closure["reports"][0]["inventory_completeness"] = "LIMITED"
    elif change == "revisions": closure["reports"][0]["revision_completeness"] = "UNKNOWN"
    elif change == "stale_state":
        closure["reports"][0]["state_at"] = BEFORE
        expected = "COVERAGE_NOT_CURRENT"
    elif change == "stale_cutoff":
        closure["reports"][0]["source_information_cutoff"] = BEFORE
        expected = "COVERAGE_NOT_CURRENT"
    else:
        closure["reports"][0]["source_available_at"] = None
        expected = "SOURCE_AVAILABILITY_UNKNOWN"
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and expected in result["reason_codes"]


def test_pending_local_submission_survives_empty_provider_orders(case):
    closure = body(case)["commitments"]
    next(r for r in closure["reports"] if r["inventory_id"] == "outbox")["categories"]["PENDING_SUBMISSIONS"]["status"] = "NONEMPTY"
    assert "COMMITMENT_PRESENT" in run(seal(case))["reason_codes"]
    next(r for r in closure["reports"] if r["inventory_id"] == "outbox")["categories"]["PENDING_SUBMISSIONS"]["status"] = "EMPTY"
    assert run(seal(case))["outcome"] == "ESTABLISHED"


@pytest.mark.parametrize("change", ["unlisted", "duplicate_report", "duplicate_roster", "namespace", "category_extra", "category_missing"])
def test_commitment_structural_contradictions(case, change):
    c = body(case)["commitments"]
    if change == "unlisted": c["reports"][0]["inventory_id"] = "not-listed"
    elif change == "duplicate_report": c["reports"].append(deepcopy(c["reports"][0]))
    elif change == "duplicate_roster": c["inventory_roster"].append(deepcopy(c["inventory_roster"][0]))
    elif change == "namespace": c["reports"][0]["source"]["source_id"] = "another-provider"
    elif change == "category_extra": c["reports"][0]["categories"]["OTHER"] = dict(status="EMPTY", evidence_refs=[])
    else: del c["reports"][0]["categories"][CATEGORIES[0]]
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("key", owner.BINDINGS)
@pytest.mark.parametrize("status,reason", [("UNKNOWN", "BINDING_UNRESOLVED"), ("INCOMPATIBLE", "BINDING_INCOMPATIBLE")])
def test_bindings_require_explicit_admitted_semantics(case, key, status, reason):
    body(case)["bindings"][key]["status"] = status
    result = run(seal(case))
    assert reason in result["reason_codes"] and result["effect_basis"] is None


@pytest.mark.parametrize("field", ["source_id", "source_contract", "source_contract_version", "account_id", "environment", "currency"])
def test_native_account_identity_no_aliasing(case, field):
    value = "LIVE" if field == "environment" else "EUR" if field == "currency" else "different"
    case[0]["scope"]["account"][field] = value
    if field == "environment": case[0]["scope"]["instrument"]["environment"] = value
    case[0]["effect_inventory"]["scope"] = deepcopy(case[0]["scope"])
    seal(case)
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("change", ["inventory_scope", "instrument_environment", "account_pin", "position_time", "mode", "native_boundary", "native_tampering"])
def test_direct_identity_and_native_contradictions(case, change):
    if change == "inventory_scope": case[0]["effect_inventory"]["scope"]["instrument"]["instrument_id"] = "alias"
    elif change == "instrument_environment": case[0]["scope"]["instrument"]["environment"] = "LIVE"
    elif change == "account_pin": body(case)["account_bundle_sha256"] = "0" * 64
    elif change == "position_time": body(case)["positions"]["state_at"] = BEFORE
    elif change == "mode": body(case)["mechanics"]["position_mode"] = "HEDGING"
    elif change == "native_boundary":
        pair = case[0]["account_state"]
        pair["snapshot_input"]["requested_evaluation_timestamp"] = AFTER
        issue_account(case)
    else:
        case[0]["account_state"]["snapshot"]["authority"]["execution"] = True
    seal(case)
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("field,value,reason", [("model", "OTHER", "MECHANICS_UNSUPPORTED_OR_UNKNOWN"),
                                              ("model", "UNKNOWN", "MECHANICS_UNSUPPORTED_OR_UNKNOWN"),
                                              ("fill_aggregation", "OTHER", "MECHANICS_UNSUPPORTED_OR_UNKNOWN"),
                                              ("position_mode", "UNKNOWN", "ACCOUNT_MODE_UNRESOLVED"),
                                              ("quantity_range", None, "QUANTITY_RANGE_UNESTABLISHED"),
                                              ("revision_completeness", "LIMITED", "REVISION_HISTORY_INCOMPLETE"),
                                              ("source_information_cutoff", None, "COVERAGE_NOT_CURRENT")])
def test_unsupported_or_unknown_mechanics(case, field, value, reason):
    body(case)["mechanics"][field] = value
    assert reason in run(seal(case))["reason_codes"]


@pytest.mark.parametrize("name", owner.ASSURANCES)
def test_each_independent_assurance_is_required(case, name):
    case[1]["assurances"][name]["status"] = "UNRESOLVED"
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["resolved_record"] is None
    assert result["reason_codes"] == ["ASSURANCE_UNRESOLVED"]


@pytest.mark.parametrize("field,value", [("effective_from", AFTER), ("effective_until", T)])
def test_inactive_admission(case, field, value):
    case[1][field] = value
    assert run(case)["reason_codes"] == ["ADMISSION_NOT_CURRENT"]


@pytest.mark.parametrize("change", ["purpose", "pin", "knowledge", "late", "early", "empty_refs", "missing_ref", "wrong_digest", "boolean_revision", "orphan"])
def test_invalid_admission_rejects(case, change):
    c = case[1]
    if change == "purpose": c["purpose"] = "EXECUTION_APPROVAL"
    elif change == "pin": c["request_content_sha256"] = "0" * 64
    elif change == "knowledge": c["knowledge_boundary"] = BEFORE
    elif change == "late": c["available_at"] = AFTER
    elif change == "early": c["admitted_at"] = BEFORE
    elif change == "empty_refs": c["assurances"]["source_authority"]["evidence_refs"] = []
    elif change == "missing_ref": c["assurances"]["source_authority"]["evidence_refs"][0]["evidence_id"] = "absent"
    elif change == "wrong_digest": c["assurances"]["source_authority"]["evidence_refs"][0]["content_sha256"] = "0" * 64
    elif change == "boolean_revision": c["mandate_revision"] = True
    else: case[0]["effect_inventory"] = None
    with pytest.raises(ValueError): run(case)


def test_absent_owners_and_no_descendant_diagnostics(case):
    q = deepcopy(case[0])
    q.update(account_state=None, effect_inventory=None)
    result = run((q, None))
    assert result["reason_codes"] == ["MISSING_ACCOUNT_STATE", "MISSING_EFFECT_INVENTORY", "MISSING_HOST_ADMISSION"]
    assert result["resolved_record"] is result["effect_basis"] is None
    assert run((case[0], None))["reason_codes"] == ["MISSING_HOST_ADMISSION"]


@pytest.mark.parametrize("start,expected", [(BEFORE, "B"), (T, "B"), (AFTER, "A")])
def test_exact_successor_and_known_future(case, start, expected):
    add(case, start=start)["body"]["mechanics"]["quantity_range"]["maximum"] = "0.5"
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED" and result["resolved_record"]["record_id"] == expected
    assert result["effect_basis"]["quantity_range"]["maximum"] == ("0.5" if expected == "B" else "2")


@pytest.mark.parametrize("kind,reason", [("WITHDRAW", "CURRENT_DECLARATION_WITHDRAWN"), ("DECLARE", "CURRENT_DECLARATION_EXPIRED")])
def test_withdrawal_and_expiry_do_not_revive_predecessor(case, kind, reason):
    add(case, kind=kind, start=BEFORE, end=T)
    result = run(case)
    assert result["outcome"] == "UNKNOWN" and result["reason_codes"] == [reason]
    assert result["resolved_record"]["record_id"] == "B"
    assert result["effect_basis"] is None


def test_new_declaration_after_withdrawal(case):
    add(case, kind="WITHDRAW", start=BEFORE)
    add(case, identifier="C", start=T)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED" and result["resolved_record"]["record_id"] == "C"


def test_historical_body_is_not_current_account_truth(case):
    add(case, start=T)
    old_pair = deepcopy(case[0]["account_state"])
    old_pair["snapshot_input"]["observation"]["timing"] = dict(effective_at=EARLY, observed_at=EARLY, source_available_at=EARLY)
    old_pair["snapshot"] = accounts.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(old_pair["snapshot_input"]).to_dict()
    old = body(case)
    old["account_bundle_sha256"] = digest(old_pair)
    old["positions"].update(state_at=EARLY, inventory_completeness="UNKNOWN", revision_completeness="UNKNOWN")
    old["mechanics"].update(model="UNKNOWN", quantity_range=None)
    old["commitments"]["reports"][0]["categories"][CATEGORIES[0]]["status"] = "UNKNOWN"
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED" and result["resolved_record"]["record_id"] == "B"


@pytest.mark.parametrize("kind", ["branch", "roots"])
def test_competing_declarations_have_no_winner(case, kind):
    inv = case[0]["effect_inventory"]
    if kind == "branch":
        parent = inv["records"][0]
        add(case, parent=parent)
        add(case, identifier="C", parent=parent)
    else:
        row = deepcopy(inv["records"][0])
        row["record_id"] = "B"
        inv["records"].append(row)
        inv["coverage"]["root_records"].append(ref(row, "record_id"))
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and "COMPETING_REVISION_CHAINS" in result["reason_codes"]
    assert result["resolved_record"] is result["effect_basis"] is None


@pytest.mark.parametrize("declared", [True, False])
def test_missing_predecessor_must_be_explicit(case, declared):
    inv = case[0]["effect_inventory"]
    row = add(case)
    row["predecessor"]["record"] = dict(record_id="lost", content_sha256="1" * 64)
    inv["coverage"]["revision_completeness"] = "LIMITED"
    if declared: inv["coverage"]["missing_record_ids"] = ["lost"]
    seal(case)
    if declared:
        result = run(case)
        assert "REVISION_HISTORY_INCOMPLETE" in result["reason_codes"] and result["resolved_record"] is None
    else:
        with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("change", ["hash", "root", "cycle", "duplicate", "withdraw_root", "complete_gap", "supplied_missing"])
def test_malformed_lineage_rejects_before_semantics(case, change):
    inv = case[0]["effect_inventory"]
    if change == "hash":
        add(case)["predecessor"]["record"]["content_sha256"] = "0" * 64
    elif change == "root": inv["coverage"]["root_records"] = []
    elif change == "cycle":
        row = inv["records"][0]
        row["predecessor"] = dict(kind="RECORD", record=dict(record_id="A", content_sha256="0" * 64))
    elif change == "duplicate": inv["records"].append(deepcopy(inv["records"][0]))
    elif change == "withdraw_root":
        row = inv["records"][0]
        row.update(kind="WITHDRAW")
        del row["body"], row["effective_until"]
    elif change == "complete_gap": inv["coverage"]["records_omitted"] = True
    else: inv["coverage"]["missing_record_ids"] = ["A"]
    with pytest.raises(ValueError): run((case[0], None))


def test_backward_effective_order_is_unknown(case):
    add(case)["effective_from"] = "2025-12-31T00:00:00Z"
    result = run(seal(case))
    assert "REVISION_ORDER_UNSUPPORTED" in result["reason_codes"] and result["resolved_record"] is None


@pytest.mark.parametrize("field,value", [("revision_completeness", "LIMITED"), ("revision_completeness", "UNKNOWN"),
                                        ("declaration_completeness", "LIMITED"), ("source_information_cutoff", BEFORE),
                                        ("source_information_cutoff", None), ("economic_from", AFTER), ("economic_until", T)])
def test_incomplete_current_coverage(case, field, value):
    case[0]["effect_inventory"]["coverage"][field] = value
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and result["resolved_record"] is None


@pytest.mark.parametrize("empty", [True, False])
def test_no_current_declaration(case, empty):
    inv = case[0]["effect_inventory"]
    if empty:
        inv["records"] = []
        inv["coverage"]["root_records"] = []
    else: inv["records"][0]["effective_from"] = AFTER
    assert run(seal(case))["reason_codes"] == ["NO_CURRENT_DECLARATION"]


def get(value, path):
    for key in path:
        value = value[key]
    return value


def set_at(value, path, item):
    get(value, path[:-1])[path[-1]] = item


INV = ("effect_inventory",)
REC = INV + ("records", 0)
BODY = REC + ("body",)
REPORT = BODY + ("commitments", "reports", 0)
POST_K_PATHS = [INV + ("observed_at",), INV + ("source_available_at",), INV + ("evidence", 0, "observed_at"),
               INV + ("coverage", "source_information_cutoff"), REC + ("observed_at",),
               BODY + ("positions", "state_at"), BODY + ("mechanics", "source_information_cutoff"),
               BODY + ("commitments", "state_at"), REPORT + ("observed_at",), REPORT + ("state_at",)]


@pytest.mark.parametrize("path", POST_K_PATHS)
def test_post_k_and_impossible_local_timing(case, path):
    set_at(case[0], path, AFTER)
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("value", ["2026-01-02T12:00:00", "2026-01-02T12:00:00.0000001Z", "2026-02-30T00:00:00Z",
                                  "2026-01-02T12:00:60Z", "2026-01-02T12:00:00+24:00", "2026-01-02T12:00:00+00:60", 1, True])
def test_invalid_local_time(case, value):
    case[0]["assessment_economic_time"] = value
    with pytest.raises(ValueError): run((case[0], None))


def test_t_must_equal_k(case):
    case[0]["assessment_economic_time"] = BEFORE
    with pytest.raises(ValueError): run((case[0], None))


def test_evidence_observation_cannot_follow_report(case):
    report = body(case)["commitments"]["reports"][0]
    report.update(state_at=EARLY, source_information_cutoff=EARLY, source_available_at=EARLY, observed_at=EARLY)
    seal(case)
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("value", ["", "?", "eA", "eA===", "eA==\n", "eB==", None])
def test_evidence_encoding(case, value):
    case[0]["effect_inventory"]["evidence"][0]["content_base64"] = value
    with pytest.raises(ValueError): run((case[0], None))


def test_original_bytes_and_old_receipts(case):
    first = run(case)
    old_context = deepcopy(case[1])
    case[0]["effect_inventory"]["evidence"][0]["content_base64"] = base64.b64encode(b'{"different":true}').decode()
    with pytest.raises(ValueError): run((case[0], None))
    seal(case)
    with pytest.raises(ValueError): run((case[0], old_context))
    second = run(case)
    assert second["outcome"] == "ESTABLISHED"
    assert first["assessment_identity"] != second["assessment_identity"]


@pytest.mark.parametrize("path", [INV + ("coverage", "evidence_refs"), REC + ("evidence_refs",),
                                 BODY + ("positions", "evidence_refs"), BODY + ("mechanics", "evidence_refs"),
                                 BODY + ("bindings", "quantity_denomination", "evidence_refs"),
                                 BODY + ("commitments", "evidence_refs"),
                                 BODY + ("commitments", "inventory_roster", 0, "binding_evidence_refs"),
                                 REPORT + ("evidence_refs",), REPORT + ("categories", CATEGORIES[0], "evidence_refs")])
def test_empty_support_is_unknown_not_a_negative(case, path):
    set_at(case[0], path, [])
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and "SUPPORTING_EVIDENCE_MISSING" in result["reason_codes"]


def test_unknown_source_availability_requires_unresolved_admission(case):
    case[0]["effect_inventory"]["evidence"][0]["source_available_at"] = None
    seal(case)
    with pytest.raises(ValueError): run(case)
    for assurance in case[1]["assurances"].values():
        assurance["status"] = "UNRESOLVED"
    result = run(case)
    assert "SOURCE_AVAILABILITY_UNKNOWN" in result["reason_codes"]
    assert "ASSURANCE_UNRESOLVED" in result["reason_codes"]


def test_unreferenced_evidence_does_not_become_mandatory_support(case):
    extra = deepcopy(case[0]["effect_inventory"]["evidence"][0])
    extra.update(evidence_id="unreferenced", source_available_at=None)
    case[0]["effect_inventory"]["evidence"].append(extra)
    assert run(seal(case))["outcome"] == "ESTABLISHED"


OBJECT_PATHS = [(), ("scope",), ("scope", "account"), ("scope", "provider_namespace"), ("scope", "instrument"),
                ("account_state",), INV, INV + ("source",), INV + ("scope",), INV + ("coverage",),
                INV + ("evidence", 0), INV + ("evidence", 0, "source"), INV + ("coverage", "root_records", 0), REC,
                REC + ("predecessor",), REC + ("evidence_refs", 0), BODY, BODY + ("positions",), BODY + ("bindings",),
                BODY + ("bindings", "instrument_namespace"), BODY + ("mechanics",), BODY + ("mechanics", "quantity_range"),
                BODY + ("commitments",), BODY + ("commitments", "inventory_roster", 0),
                BODY + ("commitments", "inventory_roster", 0, "source_namespace"), REPORT, REPORT + ("source",),
                REPORT + ("categories",), REPORT + ("categories", CATEGORIES[0])]


@pytest.mark.parametrize("path", OBJECT_PATHS)
def test_every_local_object_has_exact_required_keys(case, path):
    for key in get(case[0], path):
        changed = deepcopy(case)
        del get(changed[0], path)[key]
        with pytest.raises(ValueError): run((changed[0], None))
    changed = deepcopy(case)
    get(changed[0], path)["approved"] = True
    with pytest.raises(ValueError): run((changed[0], None))


@pytest.mark.parametrize("path", [(), ("assurances",), ("assurances", "source_authority"),
                                 ("assurances", "source_authority", "evidence_refs", 0)])
def test_context_exact_required_keys(case, path):
    for key in get(case[1], path):
        changed = deepcopy(case)
        del get(changed[1], path)[key]
        with pytest.raises(ValueError): run(changed)
    changed = deepcopy(case)
    get(changed[1], path)["approved"] = True
    with pytest.raises(ValueError): run(changed)


def leaves(value, path=()):
    if type(value) is dict and value:
        for key, item in value.items(): yield from leaves(item, path + (key,))
    elif type(value) is list and value:
        for index, item in enumerate(value): yield from leaves(item, path + (index,))
    else: yield path


def test_every_output_leaf_is_reconstructed_even_after_rehash(case):
    expected = run(case)
    for path in leaves(expected):
        changed = deepcopy(expected)
        value = get(changed, path)
        altered = not value if type(value) is bool else value + 1 if type(value) is int else "altered" if type(value) is str else {"altered": True}
        set_at(changed, path, altered)
        if path != ("assessment_identity",):
            changed["assessment_identity"] = "current_entry_position_effect_basis_" + digest({k: v for k, v in changed.items() if k != "assessment_identity"})
        with pytest.raises(ValueError): validate(changed, case)


def test_canonical_ordering_equivalent_local_spellings_and_native_preservation(case):
    first = run(case)
    before_pair = deepcopy(case[0]["account_state"])
    def change(value, key=None):
        if key == "account_state": return
        if type(value) is dict:
            for k, item in list(value.items()):
                if k in TIME_KEYS and item is not None:
                    value[k] = datetime.fromisoformat(item.replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")
                else: change(item, k)
        elif type(value) is list:
            value.reverse()
            for item in value: change(item)
    change(case[0])
    change(case[1])
    body(case)["mechanics"]["quantity_range"].update(minimum="0.1000", maximum="2.0000")
    # Pins use normalized local representations, so their original values remain valid.
    assert run(case) == first
    assert case[0]["account_state"] == before_pair


def test_native_presentations_remain_bound(case):
    first = run(case)
    native(case)["account_measures"]["balance"] = "1000.0000"
    issue_account(case)
    second = run(case)
    assert second["outcome"] == "ESTABLISHED"
    assert first["assessment_identity"] != second["assessment_identity"]
    assert second["reconstruction_evidence"]["request"]["account_state"]["snapshot_input"]["observation"]["account_measures"]["balance"] == "1000.0000"


def test_mutation_isolation_and_unknown_reconstruction(case):
    before = deepcopy(case)
    result = run(case)
    validated = validate(result, case)
    result["scope"]["account"]["account_id"] = "changed"
    validated["effect_basis"]["quantity_range"]["maximum"] = "999"
    assert case == before
    assert run(case)["effect_basis"]["quantity_range"]["maximum"] == "2"
    body(case)["commitments"]["actor_coverage"] = "UNKNOWN"
    unknown = run(seal(case))
    assert validate(unknown, case) == unknown


@pytest.mark.parametrize("value", [None, [], True, 1, "assessment"])
def test_detached_validator_requires_serialized_object(case, value):
    with pytest.raises(ValueError): validate(value, case)


@pytest.mark.parametrize("value", [set(), (1,), object(), float("nan"), float("inf"), {1: "key"}, "\ud800"])
def test_non_json_material_rejects(case, value):
    case[0]["extra"] = value
    with pytest.raises(ValueError): run(case)


def test_structural_failure_precedes_unknown(case):
    case[0]["account_state"] = None
    body(case)["commitments"]["actor_coverage"] = "UNKNOWN"
    body(case)["mechanics"]["quantity_range"]["maximum"] = "NaN"
    with pytest.raises(ValueError): run((case[0], None))


def test_reason_vocabulary_subjects_and_fixed_obligations(case):
    body(case)["mechanics"]["model"] = "OTHER"
    body(case)["commitments"]["reports"][0]["categories"][CATEGORIES[0]]["status"] = "NONEMPTY"
    result = run(seal(case))
    assert result["reason_codes"] == ["COMMITMENT_PRESENT", "MECHANICS_UNSUPPORTED_OR_UNKNOWN"]
    for finding in result["unresolved_findings"]:
        assert finding["reason_code"] in owner.REASON_CODES
        root = dict(request=result["reconstruction_evidence"]["request"], trusted_position_effect_context=case[1])
        for token in finding["subject"].split("/")[1:]:
            root = root[int(token)] if type(root) is list else root[token.replace("~1", "/").replace("~0", "~")]
    assert result["unresolved_findings"] == sorted(result["unresolved_findings"], key=canonical)
    assert result["downstream_obligations"] == sorted((
        "ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL", "CANDIDATE_VALIDITY", "CURRENT_STATE_AND_MECHANICS_REVALIDATION",
        "ENTRY_QUANTITY_DOMAIN_MEMBERSHIP", "MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY", "MARKET_ORDER_AND_FILL_FEASIBILITY",
        "MISSION_CONTROL_CURRENT_AUTHORIZATION", "POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE",
        "POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM", "QUANTITY_SELECTION_POLICY_AND_SELECTION", "RISK_BUDGET_QUANTITY_FEASIBILITY"))


def test_large_mandate_integer_has_canonical_json_without_global_limit_change(case):
    ordinary = canonical(normalized(case[1]))
    digits = "1" + "0" * 5000
    expected_context = ordinary.replace('"mandate_revision":1', '"mandate_revision":' + digits)
    case[1]["mandate_revision"] = 10 ** 5000
    before = sys.get_int_max_str_digits()
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["reconstruction_evidence"]["trusted_position_effect_context_sha256"] == hashlib.sha256(expected_context.encode()).hexdigest()
    assert sys.get_int_max_str_digits() == before
    assert validate(result, case) == result


def test_timezone_equivalence_across_offsets_without_reissuing_receipts(case):
    expected = run(case)
    def shift(value, key=None):
        if key == "account_state": return
        if type(value) is dict:
            for name, item in list(value.items()):
                if name in TIME_KEYS and item is not None:
                    value[name] = datetime.fromisoformat(item.replace("Z", "+00:00")).astimezone(
                        timezone(timedelta(hours=1))).isoformat()
                else: shift(item, name)
        elif type(value) is list:
            for item in value: shift(item)
    shift(case[0])
    shift(case[1])
    assert run(case) == expected


@pytest.mark.parametrize("change", ["unknown_predecessor", "omitted", "truncated", "unknown_omission", "not_inception"])
def test_explicitly_incomplete_histories_remain_unknown(case, change):
    inv = case[0]["effect_inventory"]
    cov = inv["coverage"]
    cov["revision_completeness"] = "LIMITED"
    if change == "unknown_predecessor":
        inv["records"][0]["predecessor"] = dict(kind="UNKNOWN")
        cov["root_records"] = []
    elif change == "omitted": cov["records_omitted"] = True
    elif change == "truncated": cov["history_truncated"] = True
    elif change == "unknown_omission": cov["records_omitted"] = None
    else: cov["starting_basis"] = "INCOMPLETE_OR_UNKNOWN"
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN" and "REVISION_HISTORY_INCOMPLETE" in result["reason_codes"]
    assert result["effect_basis"] is result["resolved_record"] is None


@pytest.mark.parametrize("path", [INV + ("source_available_at",), INV + ("coverage", "source_available_at"),
                                 REC + ("source_available_at",)])
def test_missing_proof_envelope_availability_is_unknown(case, path):
    set_at(case[0], path, None)
    result = run(seal(case))
    assert "SOURCE_AVAILABILITY_UNKNOWN" in result["reason_codes"]
    assert result["resolved_record"] is result["effect_basis"] is None


def test_inactive_material_is_still_structurally_validated(case):
    future = add(case, start=AFTER)
    future["body"]["mechanics"]["quantity_range"]["minimum"] = "-1"
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("path", [INV + ("coverage", "evidence_refs"), INV + ("coverage", "root_records"),
                                 REC + ("evidence_refs",)])
def test_duplicate_reference_ids_reject_even_identical(case, path):
    refs = get(case[0], path)
    refs.append(deepcopy(refs[0]))
    with pytest.raises(ValueError): run((case[0], None))


@pytest.mark.parametrize("side", ["request", "context"])
def test_missing_vs_null_is_explicit_for_required_structures(case, side):
    if side == "request":
        for path in OBJECT_PATHS:
            if path in ((), ("account_state",), INV, BODY + ("mechanics", "quantity_range")): continue
            changed = deepcopy(case)
            set_at(changed[0], path, None)
            with pytest.raises(ValueError): run((changed[0], None))
    else:
        case[1]["assurances"] = None
        with pytest.raises(ValueError): run(case)


def test_output_schema_rejects_missing_and_additional_fields(case):
    expected = run(case)
    assert set(expected) == set("contract rule_version assessment_economic_time knowledge_boundary scope outcome reason_codes resolved_record effect_basis unresolved_findings reconstruction_evidence downstream_obligations source_authentication authority execution assessment_identity".split())
    for key in expected:
        changed = deepcopy(expected)
        del changed[key]
        with pytest.raises(ValueError): validate(changed, case)
    expected["approved"] = True
    with pytest.raises(ValueError): validate(expected, case)
