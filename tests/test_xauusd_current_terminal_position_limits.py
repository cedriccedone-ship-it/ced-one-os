"""Synthetic source documents/host admissions; genuine public native-owner replay."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
import hashlib
import json
import sys

import pytest

from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regimes
from ced_one.business_divisions.trading import xauusd_current_entry_position_effect_basis as positions
from ced_one.business_divisions.trading import xauusd_current_terminal_position_limits as owner
from tests import test_trading_vertical_slice_v29 as rf
from tests import test_xauusd_current_entry_position_effect_basis as pf


T, EARLY, BEFORE, AFTER, END = pf.T, pf.EARLY, pf.BEFORE, pf.AFTER, pf.END
TIME_KEYS = {"assessment_economic_time", "knowledge_boundary", "observed_at", "source_available_at",
             "source_information_cutoff", "effective_from", "effective_until", "admitted_at", "available_at"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalized(value, key=None):
    if key in ("position_effect", "account_rule_regime"):
        return deepcopy(value)
    if type(value) is dict:
        return {k: normalized(v, k) for k, v in value.items()}
    if type(value) is list:
        result = [normalized(item) for item in value]
        if key in ("evidence", "evidence_refs"):
            return sorted(result, key=lambda row: row["evidence_id"])
        if key in ("native_mappings", "rule_bindings"):
            field = "native_reference" if key == "native_mappings" else "rule_reference"
            return sorted(result, key=lambda row: canonical(row[field]))
        if key == "applicable_approval_refs":
            return sorted(result, key=canonical)
        if key == "admissions":
            return sorted(result, key=lambda row: canonical(row["target"]))
        return result
    if value is not None and key in TIME_KEYS:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    return value


def eref(item):
    return dict(evidence_id=item["evidence_id"], envelope_sha256=digest(normalized(item)))


def nref(kind, pointer, node):
    return dict(kind=kind, pointer=pointer, content_sha256=digest(node))


def native(case):
    return case[0]["account_rule_regime"]["assessment_input"]


def package(case):
    return native(case)["manifest"]["packages"][0]


def rule(kind="quantity", maximum="0.2", effects=None, identifier=None):
    row = rf.rule("POSITION_LIMIT" if kind in ("quantity", "count") else kind)
    row["rule_id"] = identifier or kind
    row["effects"] = ["ENTRY"] if effects is None else effects
    if kind == "quantity":
        row["body"] = dict(type="POSITION_LIMIT", limit_kind="PER_POSITION_QUANTITY", quantity_unit=" lot ", maximum=maximum)
    elif kind == "count":
        row["body"]["maximum"] = maximum
    return row


def seal(case):
    """Reissue synthetic local pins, preserving every native representation."""
    q, _, context = case
    support = q["rule_support"]
    if support is not None:
        catalog = {item["evidence_id"]: item for item in support["evidence"]}

        def refresh(value):
            if type(value) is dict:
                if set(value) == {"evidence_id", "envelope_sha256"}:
                    if value["evidence_id"] in catalog:
                        value.update(eref(catalog[value["evidence_id"]]))
                else:
                    for item in value.values():
                        refresh(item)
            elif type(value) is list:
                for item in value:
                    refresh(item)
        refresh(support)
        if context is not None:
            refresh(context)
    if context is not None:
        context["request_content_sha256"] = digest(normalized(q))
    return case


def issue(case):
    """Build a fresh synthetic admission after native edits, through genuine constructors."""
    q, pc, _ = case
    p = q["position_effect"]
    if p is not None:
        pf.seal((p["request"], pc))
        p["assessment"] = positions.evaluate_current_entry_position_effect_basis(p["request"], trusted_position_effect_context=pc)
    pair = q["account_rule_regime"]
    originals, mappings, bindings = [], [], []
    refs = []
    approvals = []
    if pair is not None:
        data = rf.refresh(pair["assessment_input"])
        pair["assessment"] = regimes.CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT.analyze(data).to_dict()
        manifest = data["manifest"]
        assertion_source = dict(source_id="synthetic-review", source_contract="original-review", source_contract_version="1", source_snapshot_id="review")
        originals.append(dict(evidence_id="assertions", source=assertion_source, media_type="application/json",
                              content_base64=base64.b64encode(b'{"synthetic":true,"purpose":"independent fixture review"}').decode(),
                              content_sha256=hashlib.sha256(b'{"synthetic":true,"purpose":"independent fixture review"}').hexdigest(),
                              source_available_at=EARLY, observed_at=EARLY))
        for evidence in manifest["evidence"]:
            raw = b'SYNTHETIC provider terms: mandatory terminal upper bounds; reviewed populations, exceptions and current coverage.'
            originals.append(dict(evidence_id="original:" + evidence["evidence_id"], source=deepcopy(evidence["source"]),
                                  media_type="text/plain", content_base64=base64.b64encode(raw).decode(),
                                  content_sha256=hashlib.sha256(raw).hexdigest(), source_available_at=EARLY, observed_at=EARLY))
        by_id = {item["evidence_id"]: item for item in originals}
        refs = [eref(item) for item in originals]

        def add(kind, path, node):
            original = by_id["original:" + node["evidence_id"]] if kind in ("CLAUSE", "EVIDENCE") else by_id["assertions"]
            mappings.append(dict(native_reference=nref(kind, path, node), original_reference=eref(original), original_locator="synthetic original clause",
                                 relationship={"CLAUSE": "CLAUSE_SUPPORT", "EVIDENCE": "EXACT_DOCUMENT"}.get(kind, "ASSERTION_SUPPORT")))

        def clauses(path, items):
            for i, item in enumerate(items):
                add("CLAUSE", path + f"/{i}", item)

        add("MANIFEST", "/manifest", manifest)
        for i, evidence in enumerate(manifest["evidence"]):
            add("EVIDENCE", f"/manifest/evidence/{i}", evidence)
        for i, assignment in enumerate(manifest["assignments"]):
            ap = f"/manifest/assignments/{i}"
            add("ASSIGNMENT", ap, assignment)
            clauses(ap + "/evidence_refs", assignment["evidence_refs"])
            for j, binding in enumerate(assignment["package_bindings"]):
                clauses(ap + f"/package_bindings/{j}/evidence_refs", binding["evidence_refs"])
        for i, pkg in enumerate(manifest["packages"]):
            pp = f"/manifest/packages/{i}"
            add("PACKAGE", pp, pkg)
            clauses(pp + "/evidence_refs", pkg["evidence_refs"])
            clauses(pp + "/coverage/evidence_refs", pkg["coverage"]["evidence_refs"])
            for j, row in enumerate(pkg["rules"]):
                rp = pp + f"/rules/{j}"
                add("RULE", rp, row)
                clauses(rp + "/evidence_refs", row["evidence_refs"])
                body = row["body"]
                if body["type"] in ("STATIC_FLOOR", "DAILY_RESET_FLOOR"):
                    clauses(rp + "/body/measure/definition_refs", body["measure"]["definition_refs"])
                if body["type"] == "DAILY_RESET_FLOOR":
                    clauses(rp + "/body/reset_schedule/evidence_refs", body["reset_schedule"]["evidence_refs"])
                if body["type"] == "ACTION_WINDOW":
                    clauses(rp + "/body/evidence_refs", body["evidence_refs"])
                scope = row["instrument_scope"]
                population = "CONTAINS_ENTRY_INSTRUMENT" if scope["kind"] == "ALL_ACCOUNT_INSTRUMENTS" or q["scope"]["instrument"] in scope["instruments"] else "DISJOINT"
                bindings.append(dict(rule_reference=nref("RULE", rp, row),
                                     population=dict(relation=population, evidence_refs=deepcopy(refs)),
                                     quantity_denomination=dict(relation="IDENTICAL" if body.get("limit_kind") == "PER_POSITION_QUANTITY" else "NOT_APPLICABLE", evidence_refs=deepcopy(refs)),
                                     terminal_projection=dict(kind="EXPLICIT_TERMINAL_STATE" if body["type"] == "POSITION_LIMIT" else "UNKNOWN", evidence_refs=deepcopy(refs)),
                                     force=dict(status="MANDATORY_THROUGHOUT_P", exception_coverage="COMPLETE", exception_resolution="NONE_APPLICABLE",
                                                source_information_cutoff=T, evidence_refs=deepcopy(refs))))
        selected = pair["assessment"]["selected_regime"]
        for i, approval in enumerate(data["approvals"]):
            add("APPROVAL", f"/approvals/{i}", approval)
            if selected is not None and any(approval["approval_reference"] == a["approval_reference"] for a in selected["approval_references"]):
                approvals.append(nref("APPROVAL", f"/approvals/{i}", approval))
    q["rule_support"] = dict(observed_at=T, evidence=originals, native_mappings=mappings,
                             scope_binding=dict(status="COMPATIBLE", evidence_refs=deepcopy(refs)),
                             coverage=dict(terminal_limit_inventory="COMPLETE", exceptions_and_overrides="COMPLETE", source_information_cutoff=T, evidence_refs=deepcopy(refs)),
                             rule_bindings=bindings)
    targets = [dict(kind=kind) for kind in ("REGIME", "SCOPE", "COVERAGE")]
    targets += [dict(kind="RULE", rule_reference=deepcopy(binding["rule_reference"])) for binding in bindings]
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE, admission_id="synthetic-admission",
                   authority_namespace=dict(source_id="independent-test-host", source_contract="host-admission", source_contract_version="1"),
                   authority_id="synthetic-review-authority", mandate_id="synthetic-rule-review", mandate_revision=1, purpose=owner.PURPOSE,
                   request_content_sha256="0" * 64, knowledge_boundary=T, effective_from=EARLY, effective_until=END,
                   admitted_at=T, available_at=T, applicable_approval_refs=approvals,
                   admissions=[dict(target=target, status="ADMITTED", evidence_refs=deepcopy(refs)) for target in targets])
    case = (q, pc, context)
    return seal(case)


def sample(direction="LONG", mode="NETTING", rules=None):
    pq, pc = pf.sample(direction, mode)
    scope = deepcopy(pq["scope"])
    data = rf.sample()
    account = {key: scope["account"][key] for key in data["account"]}
    data.update(account=account, requested_knowledge_boundary=T, economic_timestamp=T)
    manifest = data["manifest"]
    manifest["timing"] = dict(observed_at=T, source_available_at=T)
    manifest["coverage"]["source_information_cutoff"] = T
    manifest["assignments"][0]["account"] = deepcopy(account)
    manifest["packages"][0]["interpretation"]["interpreted_at"] = EARLY
    manifest["evidence"][0]["timing"] = dict(observed_at=EARLY, source_available_at=None)
    data["approvals"][0].update(decided_at=EARLY, observed_at=EARLY)
    selected_rules = [rule()] if rules is None else deepcopy(rules)
    for row in selected_rules:
        if row["body"].get("limit_kind") == "PER_POSITION_QUANTITY":
            row["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[deepcopy(scope["instrument"])])
    manifest["packages"][0]["rules"] = selected_rules
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T, knowledge_boundary=T, scope=scope,
             position_effect=dict(assessment={}, request=pq), account_rule_regime=dict(assessment={}, assessment_input=data), rule_support=None)
    return issue((q, pc, None))


def run(case):
    return owner.evaluate_current_terminal_position_limits(case[0], trusted_position_effect_context=case[1], trusted_position_limit_context=case[2])


def validate(result, case):
    return owner.validate_current_terminal_position_limits(result, case[0], trusted_position_effect_context=case[1], trusted_position_limit_context=case[2])


def binding(case, index=0):
    return case[0]["rule_support"]["rule_bindings"][index]


def receipt(case, kind, index=0):
    return [row for row in case[2]["admissions"] if row["target"]["kind"] == kind][index]


def range_edit(case, a, b):
    pq = case[0]["position_effect"]["request"]
    pf.body((pq, case[1]))["mechanics"]["quantity_range"] = dict(minimum=a, maximum=b)
    return issue(case)


@pytest.fixture
def case():
    return sample()


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("mode", ["NETTING", "HEDGING"])
def test_genuine_native_positive(direction, mode):
    case = sample(direction, mode)
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["terminal_satisfying_domain"] == dict(kind="CLOSED_INTERVAL", minimum="0.1", maximum="0.2")
    assert result["negative_proofs"][0]["excluded_domain"] == dict(kind="UPPER_TAIL", lower_exclusive="0.2", upper_inclusive="2")
    assert result["position_effect_support"]["interval"] == dict(minimum="0.1", maximum="2")
    assert result["conditions"] == list(owner.CONDITIONS)
    assert result["rule_dispositions"][0]["disposition"] == "TERMINAL_LIMIT"
    assert result["reconstruction_evidence"]["request"] == normalized(case[0])
    assert result["reconstruction_evidence"]["trusted_position_effect_context_sha256"] == pf.digest(pf.normalized(case[1]))
    assert result["reconstruction_evidence"]["trusted_position_limit_context_sha256"] == digest(normalized(case[2]))
    assert validate(result, case) == result
    assert case == before
    assert set(result) == set("contract rule_version assessment_economic_time knowledge_boundary scope outcome reason_codes position_effect_support rule_dispositions terminal_limit_predicate terminal_satisfying_domain negative_proofs unresolved_findings conditions reconstruction_evidence downstream_obligations source_authentication authority execution assessment_identity".split())


@pytest.mark.parametrize("maximum,outcome,upper,negative", [
    ("0.09", "NOT_SUITABLE", None, "QUANTITY_LIMIT_EXCLUDES_ALL_P"),
    ("0.1", "ESTABLISHED", "0.1", "QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL"),
    ("2", "ESTABLISHED", "2", None), ("3", "ESTABLISHED", "2", None),
])
def test_quantity_boundaries(maximum, outcome, upper, negative):
    case = sample(rules=[rule(maximum=maximum)])
    result = run(case)
    assert result["outcome"] == outcome
    assert result["terminal_satisfying_domain"] == (dict(kind="EMPTY") if upper is None else dict(kind="CLOSED_INTERVAL", minimum="0.1", maximum=upper))
    assert [p["reason_code"] for p in result["negative_proofs"]] == ([] if negative is None else [negative])


@pytest.mark.parametrize("maximum,outcome", [(0, "NOT_SUITABLE"), (1, "ESTABLISHED"), (2, "ESTABLISHED")])
@pytest.mark.parametrize("projection", ["EXPLICIT_TERMINAL_STATE", "CONTINUOUS_NECESSARY_TERMINAL"])
def test_count_boundary_and_terminal_projection(maximum, outcome, projection):
    case = sample(rules=[rule("count", maximum)])
    binding(case)["terminal_projection"]["kind"] = projection
    result = run(seal(case))
    assert result["outcome"] == outcome
    assert result["terminal_limit_predicate"]["constraints"][0]["terminal_count"] == 1
    assert "EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE" in result["downstream_obligations"]
    assert result["authority"]["position_effect_compliance"] is False


@pytest.mark.parametrize("effects,disposition,outcome", [
    (["ENTRY"], "TERMINAL_LIMIT", "ESTABLISHED"), (["HOLDING"], "TERMINAL_LIMIT", "ESTABLISHED"),
    (["ACCOUNT_ELIGIBILITY"], "TERMINAL_LIMIT", "ESTABLISHED"), (["EXIT"], "OTHER_OBLIGATION", "ESTABLISHED"),
    (["PHASE_TRANSITION"], "OTHER_OBLIGATION", "ESTABLISHED"), (["PAYOUT"], "OTHER_OBLIGATION", "ESTABLISHED"),
    (["UNKNOWN"], "UNRESOLVED", "UNKNOWN"), (["EXIT", "HOLDING"], "TERMINAL_LIMIT", "ESTABLISHED"),
])
def test_all_lifecycle_effects(effects, disposition, outcome):
    result = run(sample(rules=[rule("count", 1, effects)]))
    assert result["outcome"] == outcome
    assert result["rule_dispositions"][0]["disposition"] == disposition


@pytest.mark.parametrize("kind", ["ACCOUNT_STATE_REQUIREMENT", "INSTRUMENT_ACTION_PERMISSION", "AUTOMATION_PERMISSION", "STATIC_FLOOR", "DAILY_RESET_FLOOR", "ACTION_WINDOW"])
def test_all_supported_other_bodies_retained(kind):
    result = run(sample(rules=[rule(kind)]))
    assert result["outcome"] == "ESTABLISHED"
    assert result["rule_dispositions"][0]["disposition"] == "OTHER_OBLIGATION"
    assert result["terminal_limit_predicate"]["constraints"] == []


@pytest.mark.parametrize("effects,outcome", [(["ENTRY"], "UNKNOWN"), (["HOLDING"], "UNKNOWN"), (["UNKNOWN"], "UNKNOWN"), (["PAYOUT"], "ESTABLISHED")])
def test_unsupported_representation(effects, outcome):
    result = run(sample(rules=[rule("UNSUPPORTED", effects=effects)]))
    assert result["outcome"] == outcome


@pytest.mark.parametrize("population,count,disposition", [("account", 1, "TERMINAL_LIMIT"), ("included", 1, "TERMINAL_LIMIT"), ("disjoint", 0, "DISJOINT_POPULATION")])
def test_population_counts(population, count, disposition):
    case = sample(rules=[rule("count", 1)])
    if population != "account":
        instrument = deepcopy(case[0]["scope"]["instrument"])
        if population == "disjoint": instrument["instrument_id"] = "other"
        package(case)["rules"][0]["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[instrument])
        case = issue(case)
    result = run(case)
    row = result["rule_dispositions"][0]
    assert result["outcome"] == "ESTABLISHED"
    assert (row["terminal_count"], row["disposition"]) == (count, disposition)


def test_different_namespaces_do_not_prove_disjointness(case):
    package(case)["rules"][0]["instrument_scope"]["instruments"][0]["source_id"] = "different"
    result = run(issue(case))
    assert result["outcome"] == "UNKNOWN"
    assert "POPULATION_UNRESOLVED" in result["reason_codes"]


def test_disjoint_unsupported_unknown_effect():
    case = sample(rules=[rule("UNSUPPORTED", effects=["UNKNOWN"])])
    other = {**case[0]["scope"]["instrument"], "instrument_id": "other"}
    package(case)["rules"][0]["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[other])
    result = run(issue(case))
    assert result["outcome"] == "ESTABLISHED"
    assert result["rule_dispositions"][0]["disposition"] == "DISJOINT_POPULATION"


def test_multiple_conjunctive_limits():
    case = sample(rules=[rule(maximum="0.4", identifier="a"), rule(maximum="0.3", identifier="b"), rule("count", 1)])
    result = run(case)
    assert result["terminal_satisfying_domain"]["maximum"] == "0.3"
    assert len(result["terminal_limit_predicate"]["constraints"]) == 3
    assert len(result["negative_proofs"]) == 2


@pytest.mark.parametrize("coverage", ["COMPLETE", "LIMITED", "UNKNOWN"])
def test_empty_rule_universe_needs_complete_coverage(coverage):
    case = sample(rules=[])
    package(case)["coverage"]["completeness"] = coverage
    result = run(issue(case))
    assert result["outcome"] == ("ESTABLISHED" if coverage == "COMPLETE" else "UNKNOWN")
    assert result["rule_dispositions"] == []
    assert result["terminal_satisfying_domain"] == (dict(kind="CLOSED_INTERVAL", minimum="0.1", maximum="2") if coverage == "COMPLETE" else None)


@pytest.mark.parametrize("kind", ["count", "quantity"])
def test_self_contained_all_p_negative_retains_unrelated_unknowns(kind):
    case = sample(rules=[rule(kind, 0 if kind == "count" else "0.01"), rule("UNSUPPORTED")])
    package(case)["coverage"]["completeness"] = "UNKNOWN"
    case = issue(case)
    case[0]["rule_support"]["coverage"]["exceptions_and_overrides"] = "UNKNOWN"
    case[2]["admissions"] = [r for r in case[2]["admissions"] if r["target"]["kind"] != "COVERAGE"]
    result = run(seal(case))
    assert result["outcome"] == "NOT_SUITABLE"
    assert result["terminal_satisfying_domain"] == dict(kind="EMPTY")
    assert result["terminal_limit_predicate"] is None
    assert {"COVERAGE_INCOMPLETE", "RULE_UNSUPPORTED", "RECEIPT_MISSING"} <= set(result["reason_codes"])
    assert len(result["negative_proofs"]) == 1
    assert {t["kind"] for t in result["negative_proofs"][0]["admission_targets"]} == {"REGIME", "SCOPE", "RULE"}


def test_partial_tail_with_unknown_preserves_no_optimistic_interval():
    result = run(sample(rules=[rule(), rule("UNSUPPORTED")]))
    assert result["outcome"] == "UNKNOWN"
    assert result["terminal_satisfying_domain"] is None
    assert result["terminal_limit_predicate"] is None
    assert [row["reason_code"] for row in result["negative_proofs"]] == ["QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL"]


@pytest.mark.parametrize("field,value,reason", [
    ("status", "UNKNOWN", "RULE_FORCE_UNRESOLVED"), ("exception_coverage", "LIMITED", "EXCEPTIONS_UNRESOLVED"),
    ("exception_resolution", "UNKNOWN", "EXCEPTIONS_UNRESOLVED"), ("source_information_cutoff", None, "EXCEPTIONS_UNRESOLVED"),
    ("source_information_cutoff", BEFORE, "EXCEPTIONS_UNRESOLVED"),
])
def test_unresolved_overrides_prevent_numeric_negative(field, value, reason):
    case = sample(rules=[rule("count", 0)])
    binding(case)["force"][field] = value
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []
    assert reason in result["reason_codes"]


def test_resolved_exception_with_unchanged_bound_is_supported(case):
    binding(case)["force"]["exception_resolution"] = "RESOLVED_WITH_BOUND_UNCHANGED"
    assert run(seal(case))["outcome"] == "ESTABLISHED"


@pytest.mark.parametrize("mode", ["competing", "future", "expired", "manifest_limited", "approval_rejected", "approval_missing"])
def test_native_regime_lifecycle(mode):
    case = sample(rules=[rule("count", 0)])
    data = native(case)
    if mode in ("competing", "future"):
        rf.add_package(data, 1 if mode == "competing" else 20)
    elif mode == "expired":
        package(case)["effective_period"]["effective_until"] = EARLY
        package(case)["effective_period"]["effective_from"] = "2025-12-01T00:00:00Z"
    elif mode == "manifest_limited":
        data["manifest"]["coverage"]["completeness"] = "LIMITED"
    elif mode == "approval_rejected":
        data["approvals"][0]["decision"] = "REJECTED"
    else:
        data["approvals"] = []
    result = run(issue(case))
    assert result["outcome"] == ("NOT_SUITABLE" if mode == "future" else "UNKNOWN")
    if mode != "future":
        assert result["negative_proofs"] == []
        assert "REGIME_NOT_UNIQUE" in result["reason_codes"]


@pytest.mark.parametrize("kind", ["REGIME", "SCOPE", "COVERAGE", "RULE"])
@pytest.mark.parametrize("status", ["missing", "UNRESOLVED", "incomplete_support"])
def test_receipt_target_and_support_closure(case, kind, status):
    target = receipt(case, kind)
    if status == "missing": case[2]["admissions"].remove(target)
    elif status == "UNRESOLVED": target["status"] = status
    else: target["evidence_refs"] = [r for r in target["evidence_refs"] if r["evidence_id"] == "assertions"]
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert {"missing": "RECEIPT_MISSING", "UNRESOLVED": "RECEIPT_UNRESOLVED", "incomplete_support": "ORIGINAL_SUPPORT_MISSING"}[status] in result["reason_codes"]


def test_global_receipt_cannot_replace_rule_receipt(case):
    case[2]["admissions"] = [r for r in case[2]["admissions"] if r["target"]["kind"] != "RULE"]
    assert run(case)["negative_proofs"] == []
    assert run(case)["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("which", ["position", "regime", "support", "context"])
def test_missing_parents_suppress_descendant_noise(case, which):
    q, pc, context = case
    if which == "position": q["position_effect"], pc = None, None
    elif which == "regime":
        q["account_rule_regime"] = None
        q["rule_support"] = None
        context = None
    elif which == "support": q["rule_support"], context = None, None
    else: context = None
    seal((q, pc, context))
    result = run((q, pc, context))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []
    if context is None: assert "RECEIPT_MISSING" not in result["reason_codes"]
    if which == "support": assert "RULE_BINDING_MISSING" not in result["reason_codes"]


@pytest.mark.parametrize("mutation", ["pin", "purpose", "knowledge", "authority_extra", "approval", "mandate_bool", "post_k", "orphan"])
def test_invalid_host_context(case, mutation):
    context = case[2]
    if mutation == "pin": context["request_content_sha256"] = "0" * 64
    elif mutation == "purpose": context["purpose"] = "TRADE_APPROVAL"
    elif mutation == "knowledge": context["knowledge_boundary"] = BEFORE
    elif mutation == "authority_extra": context["authority_namespace"]["authenticated"] = True
    elif mutation == "approval": context["applicable_approval_refs"] = []
    elif mutation == "mandate_bool": context["mandate_revision"] = True
    elif mutation == "post_k": context["available_at"] = AFTER
    else: case[0]["rule_support"] = None
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("field,value", [("effective_until", T), ("effective_from", AFTER)])
def test_noncurrent_host_context(case, field, value):
    case[2][field] = value
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert "ADMISSION_NOT_CURRENT" in result["reason_codes"]


@pytest.mark.parametrize("relation,reason", [("UNKNOWN", "QUANTITY_SEMANTICS_UNRESOLVED"), ("INCOMPATIBLE", "QUANTITY_SEMANTICS_INCOMPATIBLE")])
def test_honest_incompatible_quantity(case, relation, reason):
    binding(case)["quantity_denomination"]["relation"] = relation
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []
    assert reason in result["reason_codes"]


@pytest.mark.parametrize("status", ["UNKNOWN", "INCOMPATIBLE"])
def test_scope_semantic_uncertainty(case, status):
    case[0]["rule_support"]["scope_binding"]["status"] = status
    assert run(seal(case))["outcome"] == "UNKNOWN"


def test_unknown_projection_and_population(case):
    binding(case)["terminal_projection"]["kind"] = "UNKNOWN"
    binding(case)["population"]["relation"] = "UNKNOWN"
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert {"POPULATION_UNRESOLVED", "TERMINAL_PROJECTION_UNRESOLVED"} <= set(result["reason_codes"])


@pytest.mark.parametrize("target", ["MANIFEST", "ASSIGNMENT", "PACKAGE", "APPROVAL", "EVIDENCE", "RULE", "CLAUSE"])
def test_missing_required_native_mapping(case, target):
    case[0]["rule_support"]["native_mappings"] = [m for m in case[0]["rule_support"]["native_mappings"] if m["native_reference"]["kind"] != target]
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("hash_mode", ["null", "matching", "mismatch"])
def test_native_document_hashes(case, hash_mode):
    raw_digest = next(item["content_sha256"] for item in case[0]["rule_support"]["evidence"] if item["evidence_id"] == "original:terms")
    native(case)["manifest"]["evidence"][0]["document_sha256"] = None if hash_mode == "null" else raw_digest if hash_mode == "matching" else "0" * 64
    case = issue(case)
    if hash_mode == "mismatch":
        with pytest.raises(ValueError): run(case)
    else:
        result = run(case)
        assert result["outcome"] == "ESTABLISHED"
        assert result["reconstruction_evidence"]["request"]["account_rule_regime"]["assessment_input"]["manifest"]["evidence"][0]["document_sha256"] == native(case)["manifest"]["evidence"][0]["document_sha256"]


@pytest.mark.parametrize("pointer", ["/manifest/packages/00", "/manifest/packages/-1", "/manifest/packages/-", "#/manifest", "/manifest/packages/0/interpretation", "/manifest/packages/0/rules/0/body", "/manifest/packages/0/coverage", "/manifest/packages/0/~2", "/manifest/*", "/manifest/packages/0/../rules"])
def test_native_pointer_whitelist(case, pointer):
    case[0]["rule_support"]["native_mappings"][0]["native_reference"]["pointer"] = pointer
    with pytest.raises(ValueError): run((case[0], case[1], None))


@pytest.mark.parametrize("mutation", ["wrong_kind", "wrong_hash", "wrong_relationship", "wrong_original", "bad_raw_hash", "bad_envelope", "source", "publication", "late_mapping"])
def test_contradictory_supplied_mapping_rejects(case, mutation):
    support = case[0]["rule_support"]
    document = next(m for m in support["native_mappings"] if m["native_reference"]["kind"] == "EVIDENCE")
    original = next(e for e in support["evidence"] if e["evidence_id"] == "original:terms")
    if mutation == "wrong_kind": document["native_reference"]["kind"] = "RULE"
    elif mutation == "wrong_hash": document["native_reference"]["content_sha256"] = "0" * 64
    elif mutation == "wrong_relationship": document["relationship"] = "ASSERTION_SUPPORT"
    elif mutation == "wrong_original":
        clause = next(m for m in support["native_mappings"] if m["native_reference"]["kind"] == "CLAUSE")
        clause["original_reference"] = eref(next(e for e in support["evidence"] if e["evidence_id"] == "assertions"))
    elif mutation == "bad_raw_hash": original["content_sha256"] = "0" * 64
    elif mutation == "bad_envelope": document["original_reference"]["envelope_sha256"] = "0" * 64
    elif mutation == "source": original["source"]["source_id"] = "other"; seal(case)
    elif mutation == "publication":
        native(case)["manifest"]["evidence"][0]["timing"]["source_available_at"] = "2025-12-31T23:59:59Z"
        case = issue(case)
    else: original["observed_at"] = T; seal(case)
    with pytest.raises(ValueError): run((case[0], case[1], None))


@pytest.mark.parametrize("encoding", ["", "eA", "eA===", "eB==", "eA==\n", "?", None])
def test_original_base64_canonical(case, encoding):
    case[0]["rule_support"]["evidence"][0]["content_base64"] = encoding
    with pytest.raises(ValueError): run((case[0], case[1], None))


def test_required_unknown_source_availability_is_semantic_unknown(case):
    case[0]["rule_support"]["evidence"][0]["source_available_at"] = None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "SOURCE_AVAILABILITY_UNKNOWN" in result["reason_codes"]


def test_unused_unknown_source_does_not_block_but_post_k_rejects(case):
    item = deepcopy(case[0]["rule_support"]["evidence"][0])
    item.update(evidence_id="unreferenced", source_available_at=None)
    case[0]["rule_support"]["evidence"].append(item)
    assert run(seal(case))["outcome"] == "ESTABLISHED"
    item["observed_at"] = AFTER
    with pytest.raises(ValueError): run((case[0], case[1], None))


@pytest.mark.parametrize("duplicate", ["evidence", "native_mappings", "rule_bindings", "evidence_refs", "admissions", "approvals"])
def test_duplicate_references_reject(case, duplicate):
    if duplicate == "admissions": values = case[2]["admissions"]
    elif duplicate == "approvals": values = case[2]["applicable_approval_refs"]
    elif duplicate == "evidence_refs": values = binding(case)["force"]["evidence_refs"]
    else: values = case[0]["rule_support"][duplicate]
    values.append(deepcopy(values[0]))
    with pytest.raises(ValueError): run(seal(case))


@pytest.mark.parametrize("mutation", ["position", "regime", "rule", "native_account", "native_time", "scope", "orphan_position", "wrong_unit", "disjoint_member", "disjoint_accountwide", "contains_absent"])
def test_owner_tampering_and_literal_contradictions(case, mutation):
    if mutation == "position": case[0]["position_effect"]["assessment"]["effect_basis"]["terminal_position_count"] = 0
    elif mutation == "regime": case[0]["account_rule_regime"]["assessment"]["account"]["account_id"] = "other"
    elif mutation == "rule": package(case)["rules"][0]["body"]["maximum"] = "0.9"
    elif mutation == "native_account":
        native(case)["account"]["account_id"] = "other"
        native(case)["manifest"]["assignments"][0]["account"]["account_id"] = "other"
        case = issue(case)
    elif mutation == "native_time": native(case)["economic_timestamp"] = BEFORE; case = issue(case)
    elif mutation == "scope": case[0]["scope"]["venue_id"] = "other"
    elif mutation == "orphan_position": case[0]["position_effect"] = None
    elif mutation == "wrong_unit": package(case)["rules"][0]["body"]["quantity_unit"] = "lot"; case = issue(case)
    elif mutation == "disjoint_member": binding(case)["population"]["relation"] = "DISJOINT"
    elif mutation == "disjoint_accountwide":
        case = sample(rules=[rule("count", 1)])
        binding(case)["population"]["relation"] = "DISJOINT"
    else:
        package(case)["rules"][0]["instrument_scope"]["instruments"][0]["instrument_id"] = "other"
        case = issue(case)
        binding(case)["population"]["relation"] = "CONTAINS_ENTRY_INSTRUMENT"
    with pytest.raises(ValueError): run((case[0], case[1], None))


def test_unknown_owner_plus_malformed_unrelated_original(case):
    case[0]["position_effect"] = None
    case = (case[0], None, None)
    case[0]["rule_support"]["evidence"][0]["content_sha256"] = "invalid"
    with pytest.raises(ValueError): run(case)


def test_correctly_reconstructed_unknown_owner_propagates(case):
    pq = case[0]["position_effect"]["request"]
    pf.body((pq, case[1]))["commitments"]["reports"][0]["categories"]["POSITION_RESERVATIONS"]["status"] = "NONEMPTY"
    result = run(issue(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["position_effect_support"] is None
    assert result["negative_proofs"] == []
    assert "OWNER_NOT_ESTABLISHED" in result["reason_codes"]


def test_native_positive_without_native_admission_rejects(case):
    with pytest.raises(ValueError): run((case[0], None, case[2]))


def test_rule_binding_missing(case):
    case[0]["rule_support"]["rule_bindings"] = []
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "RULE_BINDING_MISSING" in result["reason_codes"]


def leaves(value, path=()):
    if type(value) is dict and value:
        for key, item in value.items(): yield from leaves(item, path + (key,))
    elif type(value) is list and value:
        for index, item in enumerate(value): yield from leaves(item, path + (index,))
    else: yield path


def get(value, path):
    for part in path: value = value[part]
    return value


def test_every_output_leaf_replayed_even_after_rehash(case):
    expected = run(case)
    for path in leaves(expected):
        changed = deepcopy(expected)
        value = get(changed, path)
        get(changed, path[:-1])[path[-1]] = not value if type(value) is bool else value + 1 if type(value) is int else "altered" if type(value) is str else {"altered": True}
        if path != ("assessment_identity",):
            changed["assessment_identity"] = owner.IDENTITY_PREFIX + digest({key: item for key, item in changed.items() if key != "assessment_identity"})
        with pytest.raises(ValueError): validate(changed, case)


def test_old_pin_does_not_admit_changed_original_bytes(case):
    previous = deepcopy(case[2])
    item = case[0]["rule_support"]["evidence"][0]
    raw = b'changed synthetic review'
    item.update(content_base64=base64.b64encode(raw).decode(), content_sha256=hashlib.sha256(raw).hexdigest())
    seal(case)
    with pytest.raises(ValueError): run((case[0], case[1], previous))


def test_local_ordering_and_timestamp_equivalence(case):
    expected = run(case)
    for key in ("evidence", "native_mappings", "rule_bindings"):
        case[0]["rule_support"][key].reverse()
    case[2]["admissions"].reverse()
    case[2]["applicable_approval_refs"].reverse()

    def rewrite(value, key=None):
        if key in ("position_effect", "account_rule_regime"): return
        if type(value) is dict:
            for field, child in value.items():
                if field in TIME_KEYS and child is not None:
                    value[field] = child.replace(".000000Z", "+00:00")
                else: rewrite(child, field)
        elif type(value) is list:
            if key == "evidence_refs": value.reverse()
            for child in value: rewrite(child)
    rewrite(case[0])
    rewrite(case[2])
    assert run(seal(case)) == expected


def test_native_arrays_and_spellings_preserved():
    case = sample(rules=[rule(maximum="0.2000", identifier="z"), rule("count", 1, identifier="a")])
    before = deepcopy(case[0]["account_rule_regime"])
    first = run(case)
    assert first["reconstruction_evidence"]["request"]["account_rule_regime"] == before
    assert first["terminal_satisfying_domain"]["maximum"] == "0.2"
    package(case)["rules"].reverse()
    second = run(issue(case))
    assert second["terminal_satisfying_domain"] == first["terminal_satisfying_domain"]
    assert second["assessment_identity"] != first["assessment_identity"]


def test_extreme_precision_singleton_and_no_ambient_context(case):
    digits = "1" * 5000
    tiny = "0." + "0" * 5000 + "1"
    case = range_edit(case, tiny, tiny)
    before_limit = sys.get_int_max_str_digits()
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["terminal_satisfying_domain"] == dict(kind="CLOSED_INTERVAL", minimum=tiny, maximum=tiny)
    case = range_edit(case, digits, digits)
    assert run(case)["outcome"] == "NOT_SUITABLE"
    assert sys.get_int_max_str_digits() == before_limit


def test_extreme_native_ceiling_comparison(case):
    package(case)["rules"][0]["body"]["maximum"] = "0.1" + "0" * 5000 + "1"
    case = issue(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["terminal_satisfying_domain"]["maximum"] == package(case)["rules"][0]["body"]["maximum"]


def test_detached_outputs_and_inputs(case):
    before = deepcopy(case)
    first = run(case)
    second = validate(first, case)
    assert case == before
    first["terminal_satisfying_domain"]["maximum"] = "999"
    assert second == run(case)
    case[0]["rule_support"]["evidence"][0]["media_type"] = "changed"
    case[2]["authority_id"] = "changed"
    assert second["reconstruction_evidence"]["request"]["rule_support"]["evidence"][0]["media_type"] != "changed"


def test_no_selection_or_authority_and_host_authentication_is_external(case):
    # A synthetic dictionary exercises the contract; it does not authenticate an issuer.
    result = run(case)
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict.fromkeys(("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval", "trade_decision", "financial_risk", "execution"), False)
    assert result["execution"] is False
    assert result["downstream_obligations"] == owner.DOWNSTREAM_OBLIGATIONS
    assert "selected_quantity" not in result
    assert run((case[0], case[1], None))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("time", ["2026-02-30T00:00:00Z", "2026-01-02T12:00:60Z", "2026-01-02T12:00:00+24:00", "2026-01-02T12:00:00+00:60", "2026-01-02T12:00:00.0000000Z", "2026-01-02T12:00:00", "0001-01-01T00:00:00+23:00"])
def test_invalid_timestamps(case, time):
    case[0]["knowledge_boundary"] = time
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("path", [(), ("scope",), ("rule_support",), ("rule_support", "coverage"), ("rule_support", "scope_binding"), ("rule_support", "evidence", 0), ("rule_support", "rule_bindings", 0), ("rule_support", "rule_bindings", 0, "force")])
def test_extra_request_fields_reject(case, path):
    get(case[0], path)["unexpected"] = True
    with pytest.raises(ValueError): run((case[0], case[1], None))


def test_non_json_cycle_and_bool_integer_rejected(case):
    case[0]["scope"]["currency"] = float("nan")
    with pytest.raises(ValueError): run(case)
    cycle = {}; cycle["self"] = cycle
    with pytest.raises(ValueError): owner.evaluate_current_terminal_position_limits(cycle)
    with pytest.raises(ValueError): validate({"execution": 0}, sample())


def test_connected_future_approval_is_preserved(case):
    future = deepcopy(native(case)["approvals"][0])
    future["approval_reference"]["source_snapshot_id"] = "known-future-approval"
    future["effective_period"]["effective_from"] = AFTER
    native(case)["approvals"].append(future)
    case = issue(case)
    assert len(case[2]["applicable_approval_refs"]) == 2
    assert run(case)["outcome"] == "ESTABLISHED"
    case[2]["applicable_approval_refs"].pop()
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("owner_name", ["position_effect", "account_rule_regime"])
def test_rehashed_native_output_tampering_rejects(case, owner_name):
    assessment = case[0][owner_name]["assessment"]
    if owner_name == "position_effect":
        assessment["effect_basis"]["terminal_position_count"] = 0
        assessment["assessment_identity"] = "current_entry_position_effect_basis_" + digest({key: item for key, item in assessment.items() if key != "assessment_identity"})
    else:
        assessment["selected_regime"]["package"]["rules"][0]["body"]["maximum"] = "999"
        # Native identity is deliberately public and reproducible, never admission.
        encoded = json.dumps({key: item for key, item in assessment.items() if key != "assessment_id"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assessment["assessment_id"] = "account_rule_regime_assessment_" + hashlib.sha256(encoded.encode()).hexdigest()[:24]
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("reason,edit", [
    ("COVERAGE_NOT_CURRENT", ("source_information_cutoff", None)),
    ("COVERAGE_NOT_CURRENT", ("source_information_cutoff", BEFORE)),
    ("COVERAGE_INCOMPLETE", ("terminal_limit_inventory", "LIMITED")),
    ("COVERAGE_INCOMPLETE", ("exceptions_and_overrides", "UNKNOWN")),
])
def test_supplemental_coverage_gates(case, reason, edit):
    case[0]["rule_support"]["coverage"][edit[0]] = edit[1]
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert reason in result["reason_codes"]
    assert result["negative_proofs"][0]["reason_code"] == "QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL"


@pytest.mark.parametrize("field", ["population", "quantity_denomination", "terminal_projection", "force"])
def test_empty_required_rule_support_cannot_be_admitted(case, field):
    binding(case)[field]["evidence_refs"] = []
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []
    assert "ORIGINAL_SUPPORT_MISSING" in result["reason_codes"]


def test_unused_numeric_unknowns_do_not_block_other_obligation():
    case = sample(rules=[rule("ACCOUNT_STATE_REQUIREMENT")])
    binding(case)["quantity_denomination"] = dict(relation="NOT_APPLICABLE", evidence_refs=[])
    binding(case)["terminal_projection"] = dict(kind="UNKNOWN", evidence_refs=[])
    binding(case)["force"] = dict(status="UNKNOWN", exception_coverage="UNKNOWN", exception_resolution="UNKNOWN", source_information_cutoff=None, evidence_refs=[])
    assert run(seal(case))["outcome"] == "ESTABLISHED"


def test_nonposition_positive_projection_rejects():
    case = sample(rules=[rule("UNSUPPORTED")])
    binding(case)["terminal_projection"]["kind"] = "EXPLICIT_TERMINAL_STATE"
    with pytest.raises(ValueError): run((case[0], case[1], None))


@pytest.mark.parametrize("mutation", ["dangling_original", "orphan_rule", "wrong_target_kind", "empty_admitted", "extra_receipt_field", "extra_target_field", "wrong_approval_kind"])
def test_admission_reference_attacks(case, mutation):
    target = receipt(case, "RULE")
    if mutation == "dangling_original": target["evidence_refs"][0]["evidence_id"] = "absent"
    elif mutation == "orphan_rule": target["target"]["rule_reference"]["pointer"] = "/manifest/packages/0/rules/999"
    elif mutation == "wrong_target_kind": target["target"]["kind"] = "PROVIDER_APPROVAL"
    elif mutation == "empty_admitted": target["evidence_refs"] = []
    elif mutation == "extra_receipt_field": target["approved"] = True
    elif mutation == "extra_target_field": target["target"]["ignore"] = False
    else: case[2]["applicable_approval_refs"][0]["kind"] = "RULE"
    with pytest.raises(ValueError): run(case)


@pytest.mark.parametrize("mutation", ["packet_observation", "original_observation", "publication_after_observation", "cutoff_after_observation", "admitted_after_k", "available_before_admission", "empty_interval", "outer_t_not_k"])
def test_impossible_chronology_rejects(case, mutation):
    support = case[0]["rule_support"]
    if mutation == "packet_observation": support["observed_at"] = AFTER
    elif mutation == "original_observation": support["evidence"][0]["observed_at"] = AFTER
    elif mutation == "publication_after_observation": support["evidence"][0]["source_available_at"] = AFTER
    elif mutation == "cutoff_after_observation": binding(case)["force"]["source_information_cutoff"] = AFTER
    elif mutation == "admitted_after_k": case[2]["admitted_at"] = AFTER
    elif mutation == "available_before_admission": case[2]["available_at"] = BEFORE
    elif mutation == "empty_interval": case[2]["effective_until"] = case[2]["effective_from"]
    else: case[0]["assessment_economic_time"] = BEFORE
    with pytest.raises(ValueError): run(seal(case))


def test_enormous_local_integer_hashing_without_global_limits(case):
    previous = sys.get_int_max_str_digits()
    case[2]["mandate_revision"] = 10 ** 5000
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert validate(result, case) == result
    assert sys.get_int_max_str_digits() == previous


def test_all_findings_address_existing_normalized_nodes():
    case = sample(rules=[rule("count", 0), rule("UNSUPPORTED"), rule(identifier="partial")])
    package(case)["coverage"]["completeness"] = "UNKNOWN"
    case = issue(case)
    receipt(case, "SCOPE")["status"] = "UNRESOLVED"
    binding(case, 2)["force"]["exception_resolution"] = "UNKNOWN"
    result = run(seal(case))
    root = dict(request=result["reconstruction_evidence"]["request"], trusted_position_effect_context=case[1], trusted_position_limit_context=normalized(case[2]))
    for finding in result["unresolved_findings"]:
        node = root
        for part in finding["subject"].split("/")[1:]:
            token = part.replace("~1", "/").replace("~0", "~")
            node = node[int(token)] if type(node) is list else node[token]
        assert finding["reason_code"] in owner.UNRESOLVED_REASONS


def test_real_risk_feasible_endpoint_does_not_select_or_override_terminal_ceiling():
    from tests import test_xauusd_current_risk_budget_quantity_feasibility as budgets

    financial_case = budgets.sample()
    policy = financial_case[0]["risk_policy"]["request"]

    def edit(provider_rule):
        budgets.pfixtures.instrument_scope(provider_rule)
        provider_rule["body"] = dict(type="POSITION_LIMIT", limit_kind="PER_POSITION_QUANTITY", quantity_unit=" lot ", maximum="0.2")

    budgets.pfixtures.set_rule(policy, "POSITION_LIMIT", edit)
    ns = financial_case[0]["risk_basis"]["assessment"]["reconstruction_evidence"]["selected_specification"]["specification"]["position_namespace"]
    instrument = {key: ns[key] for key in ("source_id", "source_contract", "source_contract_version", "environment", "instrument_id")}
    regime = policy["account_rule_regime"]
    regime["assessment_input"]["manifest"]["packages"][0]["rules"][0]["instrument_scope"]["instruments"] = [instrument]
    regime["assessment"] = rf.run(rf.refresh(regime["assessment_input"]))
    budgets.pfixtures.operand(policy, "INSTRUMENT_BINDING", dict(candidate=budgets.pfixtures.artifact(policy["candidate"]["formulation"]), provider_instrument=instrument))
    budgets.issue(financial_case)
    financial = budgets.run(financial_case)
    assert financial["outcome"] == "ESTABLISHED"
    assert financial["feasible_domain"]["domain"]["last_index"] == "9"
    # Independent propositions: this owner accepts P and rules, never that F.
    case = range_edit(sample(), "0.1", "1")
    terminal = run(case)
    assert terminal["terminal_satisfying_domain"] == dict(kind="CLOSED_INTERVAL", minimum="0.1", maximum="0.2")
    case[0]["risk_feasible_set"] = financial["feasible_domain"]
    with pytest.raises(ValueError): run(case)


def test_numeric_zero_cannot_impersonate_false_authority(case):
    result = run(case)
    result["execution"] = 0
    result["authority"]["trade_decision"] = 0
    result["assessment_identity"] = owner.IDENTITY_PREFIX + digest({key: value for key, value in result.items() if key != "assessment_identity"})
    with pytest.raises(ValueError): validate(result, case)
