"""Shared synthetic originals and real public-owner replay; never provider authentication."""
import base64
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import sys
from unittest.mock import patch

import pytest

from ced_one.business_divisions.trading import xauusd_current_entry_quantity_constraint_composition as owner
from ced_one.business_divisions.trading import xauusd_current_terminal_position_limits as terminal
from tests import test_xauusd_current_risk_budget_quantity_feasibility as ff
from tests import test_xauusd_current_terminal_position_limits as tf
from tests import test_xauusd_current_entry_position_effect_basis as pf


T, EARLY, END = ff.T, ff.EARLY, pf.END
AFTER = ff.AFTER
CONTEXTS = ("trusted_planning_context", "trusted_quantity_context", "trusted_feasibility_context",
            "trusted_position_effect_context", "trusted_position_limit_context")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def financial(case):
    return (case[0]["risk_budget_feasibility"]["request"], *case[1:4])


def limits(case):
    return (case[0]["terminal_position_limits"]["request"], *case[4:6])


def rebuild_financial(case, *, issue=True):
    f = financial(case)
    if issue:
        ff.issue(f)
    case[0]["risk_budget_feasibility"]["assessment"] = ff.run(f)
    return case


def rebuild_terminal(case, *, issue=True):
    t = limits(case)
    if issue:
        # Existing fixture issuers use their module boundary, not wall-clock time.
        with patch.object(tf, "T", T):
            t = tf.issue(t)
        case = (case[0], *case[1:4], t[1], t[2])
    case[0]["terminal_position_limits"]["assessment"] = tf.run(t)
    return case


@lru_cache(maxsize=4)
def joined(direction="LONG", mode="NETTING"):
    # Establish shared originals before constructing either final owner branch.
    f = ff.sample(direction)
    p = f[0]["risk_policy"]["request"]
    p["account_state"]["snapshot_input"]["observation"]["account"]["position_mode"] = mode
    ff.refresh_joined_account(f)
    ns = f[0]["risk_basis"]["assessment"]["reconstruction_evidence"]["selected_specification"]["specification"]["position_namespace"]
    instrument = {key: ns[key] for key in ("source_id", "source_contract", "source_contract_version", "environment", "instrument_id")}

    def edit(rule):
        rule["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[deepcopy(instrument)])
        rule["body"] = dict(type="POSITION_LIMIT", limit_kind="PER_POSITION_QUANTITY", quantity_unit=" lot ", maximum="0.2")

    ff.pfixtures.set_rule(p, "POSITION_LIMIT", edit)
    ff.pfixtures.bind_instrument(p, instrument)
    provider = p["account_rule_regime"]["assessment"]["selected_regime"]["assignment"]["provider_id"]
    d = f[0]["quantity_domain"]["request"]
    d["scope"]["provider_id"] = provider
    d["quantity_inventory"]["scope"] = deepcopy(d["scope"])
    f[2]["scope"] = deepcopy(d["scope"])
    ff.dfixtures.seal(d, f[2])
    ff.issue(f)
    shared_account = deepcopy(p["account_state"])
    shared_regime = deepcopy(p["account_rule_regime"])
    with patch.object(pf, "T", T):
        pq, pc = pf.sample(direction, mode)
    observation = shared_account["snapshot"]["observation"]
    account = {key: observation["source"][key] for key in ("source_id", "source_contract", "source_contract_version")}
    account.update({key: observation["account"][key] for key in ("account_id", "environment", "currency")})
    scope = dict(account=account, provider_namespace={key: ns[key] for key in ("source_id", "source_contract", "source_contract_version")},
                 provider_id=provider, venue_id=d["scope"]["venue_id"], instrument=instrument,
                 entry_direction=direction, entry_mechanism=owner.MECHANISM, quantity_unit=" lot ")
    pq["scope"] = deepcopy(scope)
    pq["account_state"] = shared_account
    pq["effect_inventory"]["scope"] = deepcopy(scope)
    body = pf.body((pq, pc))
    body["account_bundle_sha256"] = digest(shared_account)
    original_contents = dict(
        account=shared_account["snapshot_input"],
        mechanics=dict(synthetic=True, scope=scope, mode=mode, model="ONE_NEW_SEPARATE_POSITION",
                       aggregation="ALL_ENTRY_FILLS_TO_ONE_POSITION", minimum="0.1", maximum="2"),
        closure=dict(synthetic=True, account=account, state_at=T, all_actors=True,
                     sources=["broker", "outbox", "reservations"], categories={key: "EMPTY" for key in pf.CATEGORIES}),
    )
    for item in pq["effect_inventory"]["evidence"]:
        item["content_base64"] = base64.b64encode(canonical(original_contents[item["evidence_id"]]).encode()).decode()
    pf.seal((pq, pc))
    tq = dict(contract=terminal.CONTRACT, rule_version=terminal.RULE_VERSION, assessment_economic_time=T,
              knowledge_boundary=T, scope=deepcopy(scope), position_effect=dict(request=pq, assessment={}),
              account_rule_regime=shared_regime, rule_support=None)
    with patch.object(tf, "T", T):
        t = tf.issue((tq, pc, None))
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T,
             knowledge_boundary=T, scope=deepcopy(scope), risk_budget_feasibility=dict(request=f[0], assessment=ff.run(f)),
             terminal_position_limits=dict(request=t[0], assessment=tf.run(t)))
    return (q, *f[1:], t[1], t[2])


@pytest.fixture
def case():
    return deepcopy(joined())


def run(case):
    return owner.evaluate_current_entry_quantity_constraint_composition(case[0], **dict(zip(CONTEXTS, case[1:])))


def validate(result, case):
    return owner.validate_current_entry_quantity_constraint_composition(result, case[0], **dict(zip(CONTEXTS, case[1:])))


def change_range(case, minimum, maximum):
    pq = limits(case)[0]["position_effect"]["request"]
    pf.body((pq, case[4]))["mechanics"]["quantity_range"] = dict(minimum=minimum, maximum=maximum)
    return rebuild_terminal(case)


def change_grid(case, origin="0", step="0.1", minimum="0.1", maximum=None):
    q = financial(case)[0]["quantity_domain"]["request"]
    q["quantity_inventory"]["records"][0]["domain"] = ff.dfixtures.grid(origin, step, minimum, maximum)
    ff.dfixtures.seal(q, case[2])
    return rebuild_financial(case)


def change_cap(case, maximum):
    # One original rule bundle, then public reconstruction/admission on both branches.
    p = financial(case)[0]["risk_policy"]["request"]
    original = p["account_rule_regime"]["assessment_input"]
    original["manifest"]["packages"][0]["rules"][0]["body"]["maximum"] = maximum
    p["account_rule_regime"]["assessment"] = ff.regimes.run(ff.regimes.refresh(original))
    instrument = case[0]["scope"]["instrument"]
    p["provider_operands"] = []
    ff.pfixtures.bind_instrument(p, instrument)
    limits(case)[0]["account_rule_regime"] = deepcopy(p["account_rule_regime"])
    rebuild_financial(case)
    return rebuild_terminal(case)


def terminal_unknown(case):
    limits(case)[0]["rule_support"]["coverage"]["terminal_limit_inventory"] = "LIMITED"
    tf.seal(limits(case))
    return rebuild_terminal(case, issue=False)


def codes(result):
    return {row["kind"] for row in result["negative_proofs"]}


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("mode", ["NETTING", "HEDGING"])
def test_shared_originals_positive(direction, mode):
    case = deepcopy(joined(direction, mode))
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["composed_domain"] == dict(quantity_unit=" lot ", domain=dict(
        kind="REGULAR_GRID", origin="0", increment="0.1", first_index="1", last_index="2"))
    assert result["common_supported_domain"]["domain"]["last_index"] == "10"
    assert financial(case)[0]["risk_policy"]["request"]["account_state"] == limits(case)[0]["position_effect"]["request"]["account_state"]
    assert financial(case)[0]["risk_policy"]["request"]["account_rule_regime"] == limits(case)[0]["account_rule_regime"]
    assert all(row["status"] == "PROVEN" for row in result["join_checks"])
    assert validate(result, case) == result
    assert case == before


@pytest.mark.parametrize("minimum,maximum,reason,last", [
    ("0.2", "0.2", None, "2"), ("0.11", "0.19", "EMPTY_COMMON_SUPPORT", None),
    ("1.01", "2", "EMPTY_COMMON_SUPPORT", None), ("1", "1", "NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY", None),
    ("0.11", "1", None, "2"),
])
def test_support_and_singleton(case, minimum, maximum, reason, last):
    result = run(change_range(case, minimum, maximum))
    if reason:
        assert result["outcome"] == "NOT_SUITABLE"
        assert reason in codes(result)
        assert result["composed_domain"]["domain"] == dict(kind="EMPTY")
    else:
        assert result["outcome"] == "ESTABLISHED"
        assert result["composed_domain"]["domain"]["last_index"] == last


def test_nonempty_terminal_interval_without_grid_member(case):
    case = change_cap(change_range(case, "0.11", "1"), "0.19")
    result = run(case)
    assert limits(case)[0]["position_effect"]["assessment"]["outcome"] == "ESTABLISHED"
    assert case[0]["terminal_position_limits"]["assessment"]["terminal_satisfying_domain"] == dict(
        kind="CLOSED_INTERVAL", minimum="0.11", maximum="0.19")
    assert codes(result) == {"EMPTY_TERMINAL_INTERSECTION"}
    assert result["common_supported_domain"]["domain"]["kind"] == "REGULAR_GRID"


@pytest.mark.parametrize("minimum,expected", [("0.3", "NOT_SUITABLE"), ("0.2", "UNKNOWN"), ("0.1", "UNKNOWN")])
def test_partial_negative_coverage_and_strict_boundary(case, minimum, expected):
    case = terminal_unknown(change_grid(case, minimum=minimum))
    assert case[0]["risk_budget_feasibility"]["assessment"]["outcome"] == "ESTABLISHED"
    assert case[0]["terminal_position_limits"]["assessment"]["outcome"] == "UNKNOWN"
    result = run(case)
    assert result["outcome"] == expected
    assert result["unresolved_findings"]
    assert result["native_negative_proof_references"]
    assert result["common_supported_domain"] is not None
    if expected == "NOT_SUITABLE":
        assert codes(result) == {"TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE"}
        assert result["composed_domain"]["domain"] == dict(kind="EMPTY")
    else:
        assert result["composed_domain"] is None


@pytest.mark.parametrize("financial_state", ["ESTABLISHED", "NOT_SUITABLE", "UNKNOWN", None])
@pytest.mark.parametrize("terminal_state", ["ESTABLISHED", "NOT_SUITABLE", "UNKNOWN", None])
def test_all_owner_outcomes(case, financial_state, terminal_state):
    if terminal_state == "NOT_SUITABLE":
        case = change_cap(case, "0.09")
    elif terminal_state == "UNKNOWN":
        case = terminal_unknown(case)
    if financial_state == "NOT_SUITABLE":
        q = financial(case)[0]["risk_policy"]["request"]
        q["account_state"]["snapshot_input"]["observation"]["account_measures"]["equity"] = "0"
        ff.refresh_joined_account(financial(case))
        pq = limits(case)[0]["position_effect"]["request"]
        pq["account_state"] = deepcopy(q["account_state"])
        pf.body((pq, case[4]))["account_bundle_sha256"] = digest(pq["account_state"])
        case = rebuild_terminal(case)
        if terminal_state == "UNKNOWN":
            case = terminal_unknown(case)
        rebuild_financial(case)
    elif financial_state == "UNKNOWN":
        # Honest unresolved denomination, retaining native literals and originals.
        financial(case)[0]["binding_evidence"]["claims"]["quantity_denomination"]["status"] = "UNKNOWN"
        rebuild_financial(case)
    mutable = list(case)
    if financial_state is None:
        mutable[0]["risk_budget_feasibility"] = None
        mutable[1:4] = [None] * 3
    if terminal_state is None:
        mutable[0]["terminal_position_limits"] = None
        mutable[4:6] = [None] * 2
    case = tuple(mutable)
    for name, expected in (("risk_budget_feasibility", financial_state), ("terminal_position_limits", terminal_state)):
        if expected is not None:
            assert case[0][name]["assessment"]["outcome"] == expected
    result = run(case)
    expected = "NOT_SUITABLE" if "NOT_SUITABLE" in (financial_state, terminal_state) else (
        "ESTABLISHED" if (financial_state, terminal_state) == ("ESTABLISHED", "ESTABLISHED") else "UNKNOWN")
    assert result["outcome"] == expected
    if financial_state != "ESTABLISHED" or terminal_state is None:
        assert result["common_supported_domain"] is result["composed_domain"] is None
    if financial_state is None or terminal_state is None:
        assert "OWNER_MISSING" in result["reason_codes"]
    if financial_state == "NOT_SUITABLE":
        assert case[0]["risk_budget_feasibility"]["assessment"]["feasible_domain"] is None


def test_all_p_negative_with_other_unknowns(case):
    case = terminal_unknown(change_cap(case, "0.09"))
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert codes(result) == {"NATIVE_PREREQUISITE_NOT_SUITABLE", "TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE"}
    assert result["unresolved_findings"]
    assert result["composed_domain"]["domain"] == dict(kind="EMPTY")


def test_empty_support_precedes_terminal_attribution(case):
    result = run(change_range(change_cap(case, "0.09"), "1.01", "2"))
    assert "EMPTY_COMMON_SUPPORT" in codes(result)
    assert "TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE" not in codes(result)


def test_both_support_limitations_and_finite_main_domains(case):
    result = run(change_range(case, "0.3", "0.6"))
    outside = result["support_limitations"]
    assert outside["outside_risk_support"]["domain"]["last_index"] is None
    assert [(row["first_index"], row["last_index"]) for row in outside["financially_feasible_outside_position_support"]] == [("1", "2"), ("7", "9")]
    assert result["common_supported_domain"]["domain"]["last_index"] == "6"


@pytest.mark.parametrize("origin,step,minimum,maximum,first,last", [
    ("-1000000000000.03", "0.1", "0", None, "0", "1"),
    ("0.07", "0.1", "0", None, "0", "1"),
    ("0", "0.03", "0", "0.9", "4", "6"),
])
def test_canonical_grid_arithmetic(case, origin, step, minimum, maximum, first, last):
    case = change_range(case, "0.01", "2") if origin != "0" else case
    result = run(change_grid(case, origin, step, minimum, maximum))
    assert result["outcome"] == "ESTABLISHED"
    assert (result["composed_domain"]["domain"]["first_index"], result["composed_domain"]["domain"]["last_index"]) == (first, last)


def test_extreme_precision_without_global_setting_changes(case):
    step = "0." + "0" * 5000 + "1"
    case = change_grid(case, step=step)
    previous = sys.get_int_max_str_digits()
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    grid = result["composed_domain"]["domain"]
    assert grid["increment"] == step
    assert grid["first_index"] == "1" + "0" * 5000
    assert grid["last_index"] == "2" + "0" * 5000
    assert sys.get_int_max_str_digits() == previous


def test_count_negative_is_independently_replayed(case):
    p = financial(case)[0]["risk_policy"]["request"]
    original = p["account_rule_regime"]["assessment_input"]
    original["manifest"]["packages"][0]["rules"][0]["body"] = dict(
        type="POSITION_LIMIT", limit_kind="CONCURRENT_POSITION_COUNT", maximum=0)
    original["manifest"]["packages"][0]["rules"][0]["instrument_scope"] = dict(kind="ALL_ACCOUNT_INSTRUMENTS")
    p["account_rule_regime"]["assessment"] = ff.regimes.run(ff.regimes.refresh(original))
    p["provider_operands"] = []
    ff.pfixtures.bind_instrument(p, case[0]["scope"]["instrument"])
    ff.pfixtures.operand(p, "POSITION_COUNT_CONTEXT", dict(account_snapshot=ff.pfixtures.artifact(p["account_state"]["snapshot"]),
        inventory_complete=True, commitments_complete=True, committed_additional_positions=0, count_effect="QUANTITY_DEPENDENT"))
    limits(case)[0]["account_rule_regime"] = deepcopy(p["account_rule_regime"])
    rebuild_financial(case)
    case = rebuild_terminal(case)
    assert case[0]["risk_budget_feasibility"]["assessment"]["outcome"] == "ESTABLISHED"
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["composed_domain"]["domain"] == dict(kind="EMPTY")
    assert limits(case)[0]["position_effect"]["assessment"]["effect_basis"]["terminal_position_count"] == 1
    assert case[0]["terminal_position_limits"]["assessment"]["negative_proofs"][0]["reason_code"] == "COUNT_LIMIT_EXCLUDES_ALL_P"


def test_multiple_tails_keep_all_sufficient_witnesses(case):
    p = financial(case)[0]["risk_policy"]["request"]
    original = p["account_rule_regime"]["assessment_input"]
    rules = original["manifest"]["packages"][0]["rules"]
    second = deepcopy(rules[0])
    second["rule_id"] = "second"
    second["body"]["maximum"] = "0.25"
    rules.append(second)
    p["account_rule_regime"]["assessment"] = ff.regimes.run(ff.regimes.refresh(original))
    # Bind both actual native rule references, with original supporting evidence.
    p["provider_operands"] = []
    ff.pfixtures.bind_instrument(p, case[0]["scope"]["instrument"])
    operand = deepcopy(p["provider_operands"][0])
    ref = dict(rule_id="second", full_content_sha256=ff.pfixtures.digest(second))
    operand["rule_reference"] = ref
    operand["supporting_evidence"][0]["evidence_id"] = "second-instrument"
    operand["supporting_evidence"][0]["content"]["rule_reference"] = deepcopy(ref)
    p["provider_operands"].append(operand)
    limits(case)[0]["account_rule_regime"] = deepcopy(p["account_rule_regime"])
    rebuild_financial(case)
    case = terminal_unknown(change_grid(rebuild_terminal(case), minimum="0.3"))
    result = run(case)
    proof = next(row for row in result["negative_proofs"] if row["kind"] == "TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE")
    assert len(proof["native_proofs"]) == 2
    assert proof["native_proofs"] == sorted(proof["native_proofs"], key=lambda row: (row["owner"], row["collection"], row["index"]))


@pytest.mark.parametrize("change", ["snapshot", "input_only", "regime", "namespace", "account_namespace"])
def test_independently_valid_originals_cannot_be_spliced(case, change):
    pq = limits(case)[0]["position_effect"]["request"]
    if change in ("snapshot", "input_only"):
        original = pq["account_state"]["snapshot_input"]
        if change == "snapshot":
            original["observation"]["account_measures"]["balance"] = "9999"
        else:
            # Equivalent native output, different original input presentation.
            original["requested_evaluation_timestamp"] = T.replace("Z", "+00:00")
        pf.issue_account((pq, case[4]))
    elif change == "regime":
        limits(case)[0]["account_rule_regime"]["assessment_input"]["manifest"]["source"]["source_snapshot_id"] = "another-original"
    elif change == "namespace":
        scope = limits(case)[0]["scope"]
        scope["instrument"]["source_id"] = "other-instrument-source"
        pq["scope"] = deepcopy(scope)
        pq["effect_inventory"]["scope"] = deepcopy(scope)
        case[0]["scope"] = deepcopy(scope)
    else:
        scope = limits(case)[0]["scope"]
        scope["account"]["source_id"] = "another-account-source"
        pq["scope"] = deepcopy(scope)
        pq["effect_inventory"]["scope"] = deepcopy(scope)
        case[0]["scope"] = deepcopy(scope)
        pq["account_state"]["snapshot_input"]["observation"]["source"]["source_id"] = "another-account-source"
        pf.issue_account((pq, case[4]))
        data = limits(case)[0]["account_rule_regime"]["assessment_input"]
        data["account"]["source_id"] = "another-account-source"
        data["manifest"]["assignments"][0]["account"]["source_id"] = "another-account-source"
    case = rebuild_terminal(case)
    tf.validate(case[0]["terminal_position_limits"]["assessment"], limits(case))
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("field,value", [
    ("provider_id", "another-provider"), ("venue_id", "another-venue"),
    ("quantity_unit", "lot"), ("entry_direction", "SHORT"),
])
def test_known_outer_literal_contradictions(case, field, value):
    case[0]["scope"][field] = value
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("context_index", range(1, 6))
def test_each_independent_context_is_required_for_native_positive(case, context_index):
    changed = list(case)
    changed[context_index] = None
    # A previously issued positive output cannot be reused without its context.
    with pytest.raises(ValueError): run(tuple(changed))


def test_missing_denomination_admission_is_unknown(case):
    for receipt in case[3]["admissions"]:
        if receipt["target"] == dict(kind="BINDING", claim="quantity_denomination"):
            receipt["assurances"]["fact_and_policy_semantics"]["status"] = "UNRESOLVED"
    rebuild_financial(case, issue=False)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["common_supported_domain"] is result["composed_domain"] is None
    assert result["support_limitations"] == dict(outside_risk_support=None, financially_feasible_outside_position_support=None)


@pytest.mark.parametrize("context_index", range(1, 6))
@pytest.mark.parametrize("field,value", [("effective_until", T), ("effective_from", AFTER)])
def test_noncurrent_native_admissions(case, context_index, field, value):
    case[context_index][field] = value
    if context_index < 4:
        if context_index == 1:
            ff.rfixtures.align_policy(financial(case)[0]["risk_basis"]["request"], case[1])
        rebuild_financial(case)
    elif context_index == 4:
        case = rebuild_terminal(case)
    else:
        case = rebuild_terminal(case, issue=False)
    result = run(case)
    # Native planning treats a noncurrent mandate as an admitted scoped negative.
    assert result["outcome"] == ("NOT_SUITABLE" if context_index == 1 else "UNKNOWN")
    assert result["composed_domain"] is None


@pytest.mark.parametrize("context_index", range(1, 6))
def test_post_k_admission_rejects(case, context_index):
    field = "available_at"
    case[context_index][field] = AFTER
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("where", ["financial", "position", "terminal"])
def test_post_k_observation_rejects(case, where):
    if where == "financial":
        financial(case)[0]["binding_evidence"]["observed_at"] = AFTER
    elif where == "position":
        limits(case)[0]["position_effect"]["request"]["effect_inventory"]["evidence"][0]["observed_at"] = AFTER
    else:
        limits(case)[0]["rule_support"]["evidence"][0]["observed_at"] = AFTER
    with pytest.raises(ValueError): run(case)


def test_known_future_quantity_revision_does_not_activate(case):
    d = financial(case)[0]["quantity_domain"]["request"]
    inventory = d["quantity_inventory"]
    parent = inventory["records"][0]
    row = deepcopy(parent)
    row.update(record_id="future", predecessor=dict(kind="RECORD", record=ff.dfixtures.ref(parent, "record_id")),
               effective_from=AFTER)
    row["domain"] = ff.dfixtures.grid(minimum="10", maximum="11")
    inventory["records"].append(row)
    ff.dfixtures.seal(d, case[2])
    rebuild_financial(case)
    assert run(case)["outcome"] == "ESTABLISHED"
    assert financial(case)[0]["quantity_domain"]["assessment"]["resolved_record"]["record_id"] != "future"


def test_pending_commitment_cannot_be_promoted(case):
    pq = limits(case)[0]["position_effect"]["request"]
    pf.body((pq, case[4]))["commitments"]["reports"][0]["categories"]["PENDING_SUBMISSIONS"]["status"] = "NONEMPTY"
    case = rebuild_terminal(case)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["common_supported_domain"] is None
    assert limits(case)[0]["position_effect"]["assessment"]["effect_basis"] is None


@pytest.mark.parametrize("owner_name,indexes", [("risk_budget_feasibility", (1, 2, 3)), ("terminal_position_limits", (4, 5))])
def test_orphaned_contexts_reject(case, owner_name, indexes):
    case[0][owner_name] = None
    for index in indexes:
        changed = list(case)
        for other in indexes:
            if other != index:
                changed[other] = None
        with pytest.raises(ValueError): run(tuple(changed))


@pytest.mark.parametrize("missing", ["risk_budget_feasibility", "terminal_position_limits"])
def test_missing_owner_does_not_hide_malformed_supplied_material(case, missing):
    changed = list(case)
    case[0][missing] = None
    if missing == "risk_budget_feasibility":
        changed[1:4] = [None] * 3
        limits(case)[0]["rule_support"]["extra"] = True
    else:
        changed[4:6] = [None] * 2
        financial(case)[0]["risk_basis"]["request"]["extra"] = True
    with pytest.raises(ValueError): run(tuple(changed))


@pytest.mark.parametrize("owner_name", ["risk_budget_feasibility", "terminal_position_limits"])
def test_owner_rehashed_tampering_rejects(case, owner_name):
    value = case[0][owner_name]["assessment"]
    prefix = value["assessment_identity"].rsplit("_", 1)[0] + "_"
    value["execution"] = True
    value["assessment_identity"] = prefix + digest({key: item for key, item in value.items() if key != "assessment_identity"})
    with pytest.raises(ValueError): run(case)


def leaves(value, path=()):
    if type(value) is dict and value:
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif type(value) is list and value:
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    else:
        yield path


def get(value, path):
    for part in path:
        value = value[part]
    return value


def test_every_owned_leaf_reconstructed_after_rehash(case):
    result = run(case)
    owned = {key: value for key, value in result.items() if key != "reconstruction_evidence"}
    targets = list(leaves(owned)) + [("reconstruction_evidence", key) for key in result["reconstruction_evidence"] if key != "request"]
    targets += [("reconstruction_evidence", "request", name, part) for name in
                ("risk_budget_feasibility", "terminal_position_limits") for part in ("assessment", "request")]
    for path in targets:
        changed = deepcopy(result)
        original = get(changed, path)
        get(changed, path[:-1])[path[-1]] = (not original if type(original) is bool else original + 1 if type(original) is int
                                           else "changed" if type(original) is str else {"changed": True})
        if path != ("assessment_identity",):
            changed["assessment_identity"] = owner.IDENTITY_PREFIX + digest({key: value for key, value in changed.items() if key != "assessment_identity"})
        with pytest.raises(ValueError): validate(changed, case)


@pytest.mark.parametrize("path", [(), ("scope",), ("scope", "account"), ("scope", "instrument"),
                                  ("scope", "provider_namespace"), ("risk_budget_feasibility",), ("terminal_position_limits",)])
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_local_request_exact_keys(case, path, mutation):
    value = get(case[0], path)
    if mutation == "missing":
        value.pop(next(iter(value)))
    else:
        value["extra"] = None
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("mutation", ["extra", "missing", "reorder", "duplicate", "reference", "zero_false", "noncanonical_time"])
def test_closed_output_arrays_and_types(case, mutation):
    result = run(case)
    if mutation == "extra": result["selected_quantity"] = "0.2"
    elif mutation == "missing": result.pop("support_limitations")
    elif mutation == "reorder": result["join_checks"].reverse()
    elif mutation == "duplicate": result["join_checks"].append(deepcopy(result["join_checks"][0]))
    elif mutation == "reference": result["native_negative_proof_references"][0]["index"] = 100
    elif mutation == "zero_false": result["authority"]["execution"] = 0
    else: result["knowledge_boundary"] = T.replace("Z", "+00:00")
    result["assessment_identity"] = owner.IDENTITY_PREFIX + digest({key: value for key, value in result.items() if key != "assessment_identity"})
    with pytest.raises(ValueError): validate(result, case)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), (), {1: "non-string-key"}, {"bad": {1}}, "\ud800"])
def test_non_json_material_rejects(case, value):
    case[0]["scope"]["provider_id"] = value
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("value", [True, 1, "2026-01-02", "2026-01-02T00:32:00+24:00", "2026-01-02T00:32:00.0000001Z"])
def test_local_timestamp_strictness(case, value):
    case[0]["knowledge_boundary"] = value
    with pytest.raises(ValueError): run(case)


def test_t_equals_k_and_cyclic_json(case):
    case[0]["assessment_economic_time"] = AFTER
    with pytest.raises(ValueError): run(case)
    case[0]["assessment_economic_time"] = T
    case[0]["scope"]["provider_id"] = case[0]
    with pytest.raises(ValueError): run(case)


def test_identity_original_preservation_references_and_authority(case):
    result = run(case)
    expected_keys = "contract rule_version assessment_economic_time knowledge_boundary scope outcome reason_codes owner_references join_checks common_supported_domain composed_domain support_limitations native_negative_proof_references negative_proofs unresolved_findings conditions reconstruction_evidence downstream_obligations source_authentication authority execution assessment_identity"
    assert set(result) == set(expected_keys.split())
    assert result["assessment_identity"] == owner.IDENTITY_PREFIX + digest({key: value for key, value in result.items() if key != "assessment_identity"})
    assert result["reconstruction_evidence"]["request"] == case[0]
    for label, name in (("FINANCIAL", "risk_budget_feasibility"), ("TERMINAL", "terminal_position_limits")):
        pair = case[0][name]
        assert result["owner_references"][label.lower()] == dict(assessment_identity=pair["assessment"]["assessment_identity"], owner_bundle_sha256=digest(pair))
    for ref in result["native_negative_proof_references"]:
        name = "risk_budget_feasibility" if ref["owner"] == "FINANCIAL" else "terminal_position_limits"
        assert ref["content_sha256"] == digest(case[0][name]["assessment"][ref["collection"]][ref["index"]])
    assert result["conditions"] == list(owner.CONDITIONS)
    assert result["downstream_obligations"] == sorted(set(ff.owner.DOWNSTREAM_OBLIGATIONS) | set(terminal.DOWNSTREAM_OBLIGATIONS))
    assert result["authority"] == owner.AUTHORITY and not any(result["authority"].values())
    assert result["execution"] is False
    assert not {"quantity", "selected_quantity", "order", "decision", "authorization"} & result.keys()
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert set(result["reason_codes"]) <= owner.REASON_CODES
    f_reconstruction = case[0]["risk_budget_feasibility"]["assessment"]["reconstruction_evidence"]
    t_reconstruction = case[0]["terminal_position_limits"]["assessment"]["reconstruction_evidence"]
    for key in result["reconstruction_evidence"]:
        if key != "request":
            native = f_reconstruction if key in f_reconstruction else t_reconstruction
            assert result["reconstruction_evidence"][key] == native[key]
    historical = financial(case)[0]["risk_policy"]["request"]["financial_measurement"]["measurement_input"]
    assert historical["applicability_input"]["economic_timestamp"] != T


def test_negative_and_unresolved_proof_fields_reconstruct(case):
    case = terminal_unknown(change_grid(case, minimum="0.3"))
    result = run(case)
    assert result["outcome"] == "NOT_SUITABLE"
    targets = list(leaves(result["negative_proofs"], ("negative_proofs",)))
    targets += list(leaves(result["unresolved_findings"], ("unresolved_findings",)))
    for path in targets:
        changed = deepcopy(result)
        value = get(changed, path)
        get(changed, path[:-1])[path[-1]] = "changed" if type(value) is str else value + 1 if type(value) is int else {"changed": True}
        changed["assessment_identity"] = owner.IDENTITY_PREFIX + digest({key: value for key, value in changed.items() if key != "assessment_identity"})
        with pytest.raises(ValueError): validate(changed, case)


@pytest.mark.parametrize("origin,step", [("0", "0.1"), ("0.07", "0.1"), ("-0.02", "0.07")])
@pytest.mark.parametrize("minimum,maximum", [("0.01", "0.2"), ("0.11", "0.19"), ("0.3", "0.6")])
def test_against_independent_small_grid_enumeration(case, origin, step, minimum, maximum):
    case = change_range(change_grid(case, origin=origin, step=step, minimum="0"), minimum, maximum)
    result = run(case)
    values = {Fraction(origin) + n * Fraction(step) for n in range(-100, 101)}
    supported = {q for q in values if 0 < q <= 1 and Fraction(minimum) <= q <= Fraction(maximum)}
    feasible = {q for q in supported if 10*q + max(Fraction(2), 1+2*q) <= Fraction("11.8") and q <= Fraction("0.2")}
    def members(field):
        grid = field["domain"]
        if grid["kind"] == "EMPTY":
            return set()
        return {Fraction(grid["origin"]) + n*Fraction(grid["increment"])
                for n in range(int(grid["first_index"]), int(grid["last_index"]) + 1)}
    assert members(result["common_supported_domain"]) == supported
    assert members(result["composed_domain"]) == feasible


def test_local_equivalence_and_detached_mutation_isolation(case):
    before = deepcopy(case)
    result = run(case)
    replay = validate(result, case)
    assert case == before
    case[0]["assessment_economic_time"] = T.replace("Z", "+00:00")
    case[0]["knowledge_boundary"] = "2026-01-02T01:32:00+01:00"
    assert run(case) == result
    replay["scope"]["account"]["account_id"] = "changed"
    result["reconstruction_evidence"]["request"]["risk_budget_feasibility"]["request"].clear()
    assert case[0]["risk_budget_feasibility"]["request"] == before[0]["risk_budget_feasibility"]["request"]
    assert run(case)["scope"]["account"]["account_id"] != "changed"


def test_canonical_encoding_native_numbers_and_huge_signed_integers():
    value = {"é": [True, False, None, -0.0, 1.0, 1, -123, "text"]}
    assert owner._canonical(value) == canonical(value)
    giant = 10 ** 5000
    assert owner._canonical([-giant, giant]) == "[-1" + "0" * 5000 + ",1" + "0" * 5000 + "]"
